#!/usr/bin/env python3
"""
register_stores.py — 店舗マスタ自動登録スクリプト

使い方:
  # JSON ファイルから一括登録
  python scripts/register_stores.py --input store_list.json

  # 内容確認のみ（DB 書き込みなし）
  python scripts/register_stores.py --input store_list.json --dry-run

  # public/stores.json を一括インポート
  python scripts/register_stores.py --import-stores-json

  # unknown_stores 一覧を表示
  python scripts/register_stores.py --list-unknown

  # unknown_stores を承認して stores に昇格
  python scripts/register_stores.py --approve-unknown <id>

入力 JSON スキーマ（配列）:
  [
    {
      "id":           "既存ID（省略時は自動生成なし → name で重複判定）",
      "name":         "店舗名（必須）",
      "pref":         "都道府県（任意）",
      "area":         "地域（任意）",
      "address":      "住所（任意）",
      "hp_url":       "公式サイト URL（任意）",
      "x_url":        "X 公式 URL（任意）",
      "pworld_id":    "P-WORLD 店舗 ID（任意）",
      "dmm_id":       "DMM ID（任意）",
      "source_url":   "情報収集元 URL（任意）",
      "parent_store_id": "移転元店舗 ID（任意）",
      "machines": [
        {
          "machine_name": "機種名（machines_master で解決）",
          "rate":  "4円",
          "count": 50
        }
      ]
    }
  ]

重複判定:
  1. id が指定されている場合: id で完全一致
  2. id なし: normalized_name で判定
  3. 既存店舗に address 変更があった場合: address_history に旧住所を保存
  4. is_active が false の店舗でも同一店舗として扱う

機種登録:
  - machine_name を machines_master で fuzzy 解決（normalized 完全一致）
  - 解決できない場合: unknown_machines に記録（machine_resolver.py 互換）
  - 機種名文字列の store_machines 保存は行わない

制約（遵守事項）:
  - 閉店店舗削除禁止: is_active=false で運用
  - P-WORLD リアルタイム問い合わせ禁止
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# ─── 環境変数 ─────────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.local")
    env: dict[str, str] = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    env.update(os.environ)
    return env

_ENV = _load_env()
_SUPABASE_URL = _ENV.get("NEXT_PUBLIC_SUPABASE_URL", "")
_SERVICE_KEY  = _ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not _SUPABASE_URL or not _SERVICE_KEY:
    print("[ERROR] NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が未設定です。")
    sys.exit(1)

_BASE = f"{_SUPABASE_URL}/rest/v1"
_CTX  = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE

# ─── HTTP ヘルパー ─────────────────────────────────────────────────────────────

_HEADERS = {
    "apikey":        _SERVICE_KEY,
    "Authorization": f"Bearer {_SERVICE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}

def _get(path: str, params: str = "") -> Any:
    url = f"{_BASE}/{path}{'?' + params if params else ''}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, context=_CTX) as r:
        return json.loads(r.read())

def _post(path: str, body: dict | list) -> Any:
    data = json.dumps(body, ensure_ascii=False).encode()
    req  = urllib.request.Request(f"{_BASE}/{path}", data=data, headers=_HEADERS, method="POST")
    with urllib.request.urlopen(req, context=_CTX) as r:
        return json.loads(r.read())

def _patch(path: str, params: str, body: dict) -> Any:
    url  = f"{_BASE}/{path}?{params}"
    data = json.dumps(body, ensure_ascii=False).encode()
    req  = urllib.request.Request(url, data=data, headers=_HEADERS, method="PATCH")
    with urllib.request.urlopen(req, context=_CTX) as r:
        return json.loads(r.read())

# ─── 正規化 ───────────────────────────────────────────────────────────────────

def normalize_store_name(name: str) -> str:
    """
    店舗名の正規化。重複判定に使用。
    register_cast.py の normalize_name / machine_resolver.py とは別関数。混在禁止。
    - NFKC 正規化
    - 空白除去
    - 小文字化
    """
    s = unicodedata.normalize("NFKC", name.strip())
    return s.lower().replace(" ", "").replace("\u3000", "")

def generate_store_id(name: str) -> str:
    """stores.id と同形式（10桁16進）の決定論的 ID を生成する。"""
    return hashlib.sha256(name.encode()).hexdigest()[:10]

def normalize_machine_name(name: str) -> str:
    """
    機種名正規化（machine_resolver.py の normalize_for_comparison と同一ロジック）。
    store_machines の機種解決に使用。
    """
    import re
    _PREFIX = re.compile(r"^(スマスロ|L|Ｌ|パチスロ|スロット|SLOT)\s*", re.IGNORECASE)
    s = unicodedata.normalize("NFKC", name.strip())
    prev = None
    while prev != s:
        prev = s
        s = _PREFIX.sub("", s)
    return s.lower().replace(" ", "").replace("\u3000", "")

# ─── 既存データ読み込み ────────────────────────────────────────────────────────

def load_existing_stores() -> tuple[dict[str, dict], dict[str, dict]]:
    """(id_map, norm_map) を返す。id_map: id→row, norm_map: normalized_name→row"""
    rows = _get("stores", "select=id,name,normalized_name,address,address_history,is_active,pworld_id,dmm_id&limit=10000")
    id_map:   dict[str, dict] = {}
    norm_map: dict[str, dict] = {}
    for row in rows:
        id_map[row["id"]] = row
        key = row.get("normalized_name") or normalize_store_name(row["name"])
        norm_map[key] = row
    return id_map, norm_map

def load_machines_master() -> dict[str, str]:
    """normalized_name → machine_id のマップ"""
    rows = _get("machines_master", "select=id,official_name,normalized_name&limit=1000")
    result: dict[str, str] = {}
    for row in rows:
        norm = row.get("normalized_name") or normalize_machine_name(row["official_name"])
        result[norm] = row["id"]
    return result

def load_existing_unknown_machines() -> dict[str, dict]:
    """normalized_raw_name → unknown_machines row"""
    rows = _get("unknown_machines", "select=id,raw_name,normalized_raw_name,count,status&limit=2000")
    result: dict[str, dict] = {}
    for row in rows:
        key = row.get("normalized_raw_name") or normalize_machine_name(row["raw_name"])
        result[key] = row
    return result

def load_existing_unknown_stores() -> dict[str, dict]:
    """normalized_name → unknown_stores row"""
    rows = _get("unknown_stores", "select=id,raw_name,normalized_name,count,status&limit=2000")
    result: dict[str, dict] = {}
    for row in rows:
        key = row.get("normalized_name") or normalize_store_name(row["raw_name"])
        result[key] = row
    return result

# ─── 機種解決 ─────────────────────────────────────────────────────────────────

def resolve_machine(
    machine_name: str,
    machines_master: dict[str, str],
    unknown_machines: dict[str, dict],
    source_url: str | None,
    dry_run: bool,
) -> str | None:
    """機種名 → machine_id を返す。解決不可なら None を返し unknown_machines に記録。"""
    norm = normalize_machine_name(machine_name)
    if norm in machines_master:
        return machines_master[norm]

    # 解決できない → unknown_machines に記録
    now_iso = datetime.now(timezone.utc).isoformat()
    if norm in unknown_machines:
        row = unknown_machines[norm]
        if row.get("status") not in ("rejected", "ignored"):
            if not dry_run:
                _patch("unknown_machines", f"id=eq.{row['id']}", {"count": row["count"] + 1})
    else:
        row_data = {
            "raw_name":           machine_name,
            "normalized_raw_name": norm,
            "source_url":         source_url,
            "detected_at":        now_iso,
            "count":              1,
            "status":             "pending",
        }
        if not dry_run:
            result = _post("unknown_machines", row_data)
            if result:
                unknown_machines[norm] = {**row_data, "id": result[0].get("id", "")}
        unknown_machines[norm] = {"raw_name": machine_name, "count": 1, "status": "pending"}
    return None

# ─── store_machines 登録 ──────────────────────────────────────────────────────

def register_store_machines(
    store_id: str,
    machines_input: list[dict],
    machines_master: dict[str, str],
    unknown_machines: dict[str, dict],
    source_url: str | None,
    stats: dict,
    dry_run: bool,
) -> None:
    """store_machines テーブルに機種を登録する。"""
    now_iso = datetime.now(timezone.utc).isoformat()
    for m in machines_input:
        machine_name = m.get("machine_name", "").strip()
        if not machine_name:
            continue
        machine_id = resolve_machine(machine_name, machines_master, unknown_machines, source_url, dry_run)
        if not machine_id:
            stats["unknown_machine"] += 1
            continue

        rate  = m.get("rate", "").strip() or None
        count = m.get("count") or None

        row = {
            "store_id":    store_id,
            "machine_id":  machine_id,
            "rate":        rate,
            "count":       count,
            "is_active":   True,
            "detected_at": now_iso,
        }
        row = {k: v for k, v in row.items() if v is not None}

        if dry_run:
            stats["sm_inserted"] += 1
            continue

        try:
            _post("store_machines", row)
            stats["sm_inserted"] += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if "duplicate" in body.lower() or "unique" in body.lower():
                # ON CONFLICT: 台数・貸玉率を更新
                updates: dict = {}
                if rate  is not None: updates["rate"]  = rate
                if count is not None: updates["count"] = count
                updates["updated_at"] = now_iso
                _patch("store_machines", f"store_id=eq.{store_id}&machine_id=eq.{machine_id}", updates)
                stats["sm_updated"] += 1
            else:
                stats["sm_errors"] += 1

# ─── 店舗登録 ─────────────────────────────────────────────────────────────────

def register_store(
    entry: dict,
    id_map: dict[str, dict],
    norm_map: dict[str, dict],
    unknown_stores: dict[str, dict],
    machines_master: dict[str, str],
    unknown_machines: dict[str, dict],
    stats: dict,
    dry_run: bool,
) -> None:
    name      = entry.get("name", "").strip()
    if not name:
        stats["errors"] += 1
        return

    norm         = normalize_store_name(name)
    entry_id     = entry.get("id", "").strip() or None
    pref         = entry.get("pref", "").strip() or None
    area         = entry.get("area", "").strip() or None
    address      = entry.get("address", "").strip() or None
    hp_url       = entry.get("hp_url", "").strip() or None
    x_url        = entry.get("x_url", "").strip() or None
    pworld_id    = entry.get("pworld_id", "").strip() or None
    dmm_id       = entry.get("dmm_id", "").strip() or None
    source_url   = entry.get("source_url", "").strip() or None
    parent_id    = entry.get("parent_store_id", "").strip() or None
    machines_in  = entry.get("machines", [])
    now_iso      = datetime.now(timezone.utc).isoformat()

    # ── 既存店舗検索 ──────────────────────────────────────────────────────────
    existing: dict | None = None
    if entry_id and entry_id in id_map:
        existing = id_map[entry_id]
    elif norm in norm_map:
        existing = norm_map[norm]

    if existing:
        updates: dict = {}
        # normalized_name 未設定なら補完
        if not existing.get("normalized_name"):
            updates["normalized_name"] = norm

        # 住所変更 → address_history に旧住所を保存
        old_address = existing.get("address")
        if address and old_address and address != old_address:
            history = existing.get("address_history") or []
            history.append({"address": old_address, "changed_at": now_iso})
            updates["address"] = address
            updates["address_history"] = history
            print(f"  [ADDR] {name}: 住所変更を記録 {old_address[:30]}... → {address[:30]}...")

        # URL 類は上書き（空でない場合のみ）
        for fld, val in [("hp_url", hp_url), ("x_url", x_url),
                          ("pworld_id", pworld_id), ("dmm_id", dmm_id), ("source_url", source_url)]:
            if val and existing.get(fld) != val:
                updates[fld] = val

        if updates:
            if not dry_run:
                _patch("stores", f"id=eq.{existing['id']}", updates)
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

        if machines_in:
            register_store_machines(existing["id"], machines_in, machines_master, unknown_machines, source_url, stats, dry_run)
        return

    # ── 新規登録 ─────────────────────────────────────────────────────────────
    store_row: dict = {
        "name":            name,
        "normalized_name": norm,
        "pref":            pref,
        "area":            area,
        "address":         address,
        "hp_url":          hp_url,
        "x_url":           x_url,
        "pworld_id":       pworld_id,
        "dmm_id":          dmm_id,
        "source_url":      source_url,
        "parent_store_id": parent_id,
        "is_active":       True,
        "ng_flag":         False,
        "meshiuma_score":  0,
        "event_count_30d": 0,
        "complete_count_30d": 0,
        "cast_count_30d":  0,
        "address_history": [],
    }
    # ID: 入力値 > 店舗名から決定論的生成（10桁16進 = stores.json 互換形式）
    store_row["id"] = entry_id or generate_store_id(name)
    store_row = {k: v for k, v in store_row.items() if v is not None}

    if dry_run:
        print(f"  [DRY] stores INSERT: {name} ({pref})")
        stats["inserted"] += 1
        if machines_in:
            register_store_machines("__dry__", machines_in, machines_master, unknown_machines, source_url, stats, dry_run)
        return

    try:
        result  = _post("stores", store_row)
        new_row = result[0] if result else {}
        new_id  = new_row.get("id", "")
        id_map[new_id]  = new_row
        norm_map[norm]  = new_row
        print(f"  [NEW] {name} ({pref}) id={new_id}")
        stats["inserted"] += 1
        if machines_in and new_id:
            register_store_machines(new_id, machines_in, machines_master, unknown_machines, source_url, stats, dry_run)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERR] {name}: {e.code} {body[:100]}")
        stats["errors"] += 1

# ─── public/stores.json インポート ────────────────────────────────────────────

def import_from_stores_json(dry_run: bool, limit: int | None) -> None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "public", "stores.json")
    with open(path, encoding="utf-8") as f:
        stores_data = json.load(f)

    entries = []
    for s in stores_data:
        entry = {
            "id":      s.get("id"),
            "name":    s.get("name", ""),
            "pref":    s.get("pref"),
            "area":    s.get("area"),
            "address": s.get("address"),
            "hp_url":  s.get("hp_url"),
            "x_url":   s.get("x_url"),
        }
        entries.append(entry)

    if limit:
        entries = entries[:limit]

    print(f"public/stores.json から {len(entries)} 件をインポート ({'DRY RUN' if dry_run else '本番'})")
    _run_registration(entries, dry_run)

# ─── unknown_stores 管理 ──────────────────────────────────────────────────────

def list_unknown(status_filter: str | None = "pending") -> None:
    params = "select=id,raw_name,normalized_name,source_url,count,status,detected_at"
    if status_filter:
        params += f"&status=eq.{status_filter}"
    params += "&order=count.desc&limit=100"
    rows = _get("unknown_stores", params)
    print(f"unknown_stores ({status_filter or '全件'}): {len(rows)} 件")
    for r in rows:
        print(f"  [{r['status']:8s}] count={r['count']:3d}  {r['raw_name']}")

def approve_unknown(store_id_arg: str, store_data: dict) -> None:
    rows = _get("unknown_stores", f"id=eq.{store_id_arg}&select=*")
    if not rows:
        print(f"[ERROR] id={store_id_arg} が見つかりません")
        return
    row = rows[0]
    if row["status"] != "pending":
        print(f"[WARN] status={row['status']} のため処理済みです")
        return

    id_map, norm_map = load_existing_stores()
    machines_master  = load_machines_master()
    unknown_machines = load_existing_unknown_machines()
    unknown_stores   = load_existing_unknown_stores()

    entry = {
        "name":       row["raw_name"],
        "source_url": row.get("source_url"),
        **store_data,
    }
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0,
             "sm_inserted": 0, "sm_updated": 0, "sm_errors": 0,
             "unknown_machine": 0, "unknown_new": 0, "unknown_incremented": 0}
    register_store(entry, id_map, norm_map, unknown_stores, machines_master, unknown_machines, stats, dry_run=False)
    _patch("unknown_stores", f"id=eq.{store_id_arg}", {"status": "approved"})
    print(f"[OK] unknown_stores id={store_id_arg} → approved")

# ─── 登録実行ループ ────────────────────────────────────────────────────────────

def _run_registration(entries: list[dict], dry_run: bool) -> None:
    print("既存データを読み込み中...")
    id_map, norm_map = load_existing_stores()
    machines_master  = load_machines_master()
    unknown_machines = load_existing_unknown_machines()
    unknown_stores   = load_existing_unknown_stores()
    print(f"  stores:           {len(id_map)} 件")
    print(f"  machines_master:  {len(machines_master)} 件")
    print(f"  unknown_machines: {len(unknown_machines)} 件")
    print(f"  unknown_stores:   {len(unknown_stores)} 件")
    print()

    stats = {
        "inserted":           0,
        "updated":            0,
        "skipped":            0,
        "errors":             0,
        "sm_inserted":        0,
        "sm_updated":         0,
        "sm_errors":          0,
        "unknown_machine":    0,
        "unknown_new":        0,
        "unknown_incremented":0,
    }

    for entry in entries:
        register_store(entry, id_map, norm_map, unknown_stores, machines_master, unknown_machines, stats, dry_run)

    print()
    print("=== 結果 ===")
    print(f"  stores 新規登録:         {stats['inserted']} 件")
    print(f"  stores 更新:             {stats['updated']} 件")
    print(f"  stores スキップ(重複):   {stats['skipped']} 件")
    print(f"  stores エラー:           {stats['errors']} 件")
    print(f"  store_machines 登録:     {stats['sm_inserted']} 件")
    print(f"  store_machines 更新:     {stats['sm_updated']} 件")
    print(f"  unknown_machines 記録:   {stats['unknown_machine']} 件")
    print(f"  stores エラー合計:       {stats['errors']} 件")

# ─── メイン ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="店舗マスタ自動登録スクリプト")
    parser.add_argument("--input",             metavar="FILE", help="登録する店舗 JSON ファイル")
    parser.add_argument("--import-stores-json",action="store_true", help="public/stores.json を一括インポート")
    parser.add_argument("--limit",             type=int,       help="--import-stores-json の件数上限（テスト用）")
    parser.add_argument("--dry-run",           action="store_true", help="DB に書き込まず内容確認のみ")
    parser.add_argument("--list-unknown",      action="store_true", help="unknown_stores 一覧を表示")
    parser.add_argument("--list-all-unknown",  action="store_true", help="全ステータスの unknown_stores を表示")
    parser.add_argument("--approve-unknown",   metavar="ID",   help="unknown_stores を承認して stores に昇格")
    parser.add_argument("--approve-data",      metavar="JSON", help="--approve-unknown 時に追加するデータ (JSON 文字列)")
    args = parser.parse_args()

    if args.list_unknown:
        list_unknown("pending")
        return

    if args.list_all_unknown:
        list_unknown(None)
        return

    if args.approve_unknown:
        store_data = json.loads(args.approve_data) if args.approve_data else {}
        approve_unknown(args.approve_unknown, store_data)
        return

    if args.import_stores_json:
        import_from_stores_json(dry_run=args.dry_run, limit=args.limit)
        return

    if not args.input:
        parser.print_help()
        return

    with open(args.input, encoding="utf-8") as f:
        entries = json.load(f)

    print(f"入力: {len(entries)} 件 ({'DRY RUN' if args.dry_run else '本番'})")
    _run_registration(entries, args.dry_run)

if __name__ == "__main__":
    main()
