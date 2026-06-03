#!/usr/bin/env python3
"""
register_cast.py — 演者マスタ自動登録スクリプト

使い方:
  # JSONファイルから一括登録
  python scripts/register_cast.py --input cast_list.json

  # 内容確認のみ（DB書き込みなし）
  python scripts/register_cast.py --input cast_list.json --dry-run

  # unknown_performers 一覧を出力
  python scripts/register_cast.py --list-unknown

  # unknown_performers を承認して cast_members に昇格
  python scripts/register_cast.py --approve-unknown <id>

入力 JSON スキーマ（配列）:
  [
    {
      "name":         "演者名（必須）",
      "display_name": "表示名（任意）",
      "x_url":        "https://x.com/..." （任意）,
      "profile_url":  "https://..." （任意）,
      "source_url":   "https://..." （任意）,
      "agency_name":  "事務所名（任意）",
      "agency_hp_url":"https://..." （任意・agency_name と併用）,
      "gender":       "male"|"female"|"other"|"unknown"（省略時: unknown）,
      "birthday":     "YYYY-MM-DD"（任意）,
      "area":         "地域（任意）",
      "source":       "auto"|"manual"（省略時: auto）
    },
    ...
  ]

重複判定:
  1. normalized_name が既存 cast_members に一致 → スキップ（X URL 変更のみ更新）
  2. source_url も profile_url もなし → unknown_performers に記録
  3. 上記に該当しない → cast_members に新規登録

制約（遵守事項）:
  - 演者削除禁止: is_active=false で運用
  - 性別不明は gender='unknown'
  - 事務所不明は agency_id=NULL
  - フリー演者は agency_id=NULL, source='freelance'
  - machine_resolver と同様に 85% 類似度の概念は演者名には適用しない
    （演者名は曖昧マッチではなく exact normalized match のみ）
"""

from __future__ import annotations

import argparse
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
_SUPABASE_URL  = _ENV.get("NEXT_PUBLIC_SUPABASE_URL", "")
_SERVICE_KEY   = _ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not _SUPABASE_URL or not _SERVICE_KEY:
    print("[ERROR] NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が未設定です。")
    sys.exit(1)

_BASE = f"{_SUPABASE_URL}/rest/v1"

# SSL コンテキスト（ローカル環境の証明書問題を回避）
_CTX = ssl.create_default_context()
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

def _upsert(path: str, body: dict | list, on_conflict: str) -> Any:
    headers = {**_HEADERS, "Prefer": f"resolution=merge-duplicates,return=representation"}
    url  = f"{_BASE}/{path}?on_conflict={on_conflict}"
    data = json.dumps(body, ensure_ascii=False).encode()
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, context=_CTX) as r:
        return json.loads(r.read())

# ─── 正規化 ───────────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """
    演者名の正規化。重複判定に使用。
    - NFKC 正規化（全角→半角、濁点結合など）
    - 空白除去
    - 小文字化
    注意: 機種名の normalize_for_comparison とは別関数。混在禁止。
    """
    s = unicodedata.normalize("NFKC", name.strip())
    return s.lower().replace(" ", "").replace("\u3000", "")

# ─── 既存データ読み込み ────────────────────────────────────────────────────────

def load_existing_cast() -> dict[str, dict]:
    """normalized_name → cast_member row"""
    rows = _get("cast_members", "select=id,name,normalized_name,x_url,is_active&limit=2000")
    result: dict[str, dict] = {}
    for row in rows:
        key = row.get("normalized_name") or normalize_name(row["name"])
        result[key] = row
    return result

def load_existing_agencies() -> dict[str, dict]:
    """name → agency row"""
    rows = _get("agencies", "select=id,name,slug,hp_url,x_url&limit=500")
    return {r["name"]: r for r in rows}

def load_existing_unknown_performers() -> dict[str, dict]:
    """normalized_name → unknown_performers row"""
    rows = _get("unknown_performers", "select=id,raw_name,normalized_name,count,status&limit=2000")
    result: dict[str, dict] = {}
    for row in rows:
        key = row.get("normalized_name") or normalize_name(row["raw_name"])
        result[key] = row
    return result

# ─── バリデーション ────────────────────────────────────────────────────────────

_VALID_GENDERS = {"male", "female", "other", "unknown"}
_VALID_SOURCES = {"auto", "manual", "freelance"}

def validate_entry(entry: dict, idx: int) -> list[str]:
    errors: list[str] = []
    if not entry.get("name", "").strip():
        errors.append(f"[{idx}] name が空です")
    gender = entry.get("gender", "unknown")
    if gender not in _VALID_GENDERS:
        errors.append(f"[{idx}] gender='{gender}' が不正です ({_VALID_GENDERS})")
    source = entry.get("source", "auto")
    if source not in _VALID_SOURCES:
        errors.append(f"[{idx}] source='{source}' が不正です ({_VALID_SOURCES})")
    return errors

# ─── 事務所登録 ────────────────────────────────────────────────────────────────

def ensure_agency(
    agency_name: str,
    agency_hp_url: str | None,
    existing: dict[str, dict],
    dry_run: bool,
) -> str | None:
    """事務所を登録し id を返す。事務所名なしなら None を返す。"""
    if not agency_name:
        return None
    if agency_name in existing:
        return existing[agency_name]["id"]
    row = {
        "name":     agency_name,
        "hp_url":   agency_hp_url,
        "is_active": True,
    }
    if dry_run:
        print(f"  [DRY] agencies INSERT: {agency_name}")
        existing[agency_name] = {"id": "__dry_run__", "name": agency_name}
        return "__dry_run__"
    result = _post("agencies", row)
    new_row = result[0] if result else {}
    existing[agency_name] = new_row
    print(f"  [NEW] agency: {agency_name} ({new_row.get('id','')})")
    return new_row.get("id")

# ─── 演者登録 ──────────────────────────────────────────────────────────────────

def register_cast_member(
    entry: dict,
    existing_cast: dict[str, dict],
    existing_agencies: dict[str, dict],
    existing_unknown: dict[str, dict],
    stats: dict,
    dry_run: bool,
) -> None:
    name          = entry["name"].strip()
    norm          = normalize_name(name)
    display_name  = entry.get("display_name", "").strip() or None
    x_url         = entry.get("x_url", "").strip() or None
    profile_url   = entry.get("profile_url", "").strip() or None
    source_url    = entry.get("source_url", "").strip() or None
    agency_name   = entry.get("agency_name", "").strip() or None
    agency_hp_url = entry.get("agency_hp_url", "").strip() or None
    gender        = entry.get("gender", "unknown")
    birthday      = entry.get("birthday") or None
    area          = entry.get("area", "").strip() or None
    source        = entry.get("source", "auto")
    now_iso       = datetime.now(timezone.utc).isoformat()

    # ── 重複チェック ─────────────────────────────────────────────────────────
    if norm in existing_cast:
        existing_row = existing_cast[norm]
        updates: dict = {}
        # X URL 変更のみ更新（同一人物を維持する仕組み）
        if x_url and existing_row.get("x_url") != x_url:
            updates["x_url"] = x_url
        if updates:
            if not dry_run:
                _patch("cast_members", f"id=eq.{existing_row['id']}", updates)
            print(f"  [UPD] {name} — x_url 更新")
            stats["updated"] += 1
        else:
            stats["skipped"] += 1
        return

    # ── source_url / profile_url チェック ────────────────────────────────────
    if not source_url and not profile_url:
        # unknown_performers に記録
        if norm in existing_unknown:
            row = existing_unknown[norm]
            if row.get("status") in ("rejected", "ignored"):
                stats["skipped"] += 1
                return
            if not dry_run:
                _patch(
                    "unknown_performers",
                    f"id=eq.{row['id']}",
                    {"count": row["count"] + 1},
                )
            stats["unknown_incremented"] += 1
        else:
            unknown_row = {
                "raw_name":       name,
                "normalized_name": norm,
                "source_url":     source_url,
                "detected_at":    now_iso,
                "count":          1,
                "status":         "pending",
            }
            if not dry_run:
                result = _post("unknown_performers", unknown_row)
                new_id = result[0].get("id", "") if result else ""
                existing_unknown[norm] = {**unknown_row, "id": new_id}
            print(f"  [UNK] {name} → unknown_performers (source_url/profile_url なし)")
            stats["unknown_new"] += 1
        return

    # ── 事務所解決 ────────────────────────────────────────────────────────────
    agency_id = ensure_agency(agency_name, agency_hp_url, existing_agencies, dry_run)

    # ── cast_members 新規登録 ─────────────────────────────────────────────────
    cast_row: dict = {
        "name":              name,
        "normalized_name":   norm,
        "display_name":      display_name,
        "x_url":             x_url,
        "profile_url":       profile_url,
        "agency_id":         agency_id if agency_id != "__dry_run__" else None,
        "gender":            gender,
        "birthday":          birthday,
        "area":              area,
        "is_active":         True,
        "source":            source,
        "first_detected_at": now_iso,
        "ng_flag":           False,
    }
    # None 値を除外（DB のデフォルト値に委ねる）
    cast_row = {k: v for k, v in cast_row.items() if v is not None}

    if dry_run:
        print(f"  [DRY] cast_members INSERT: {name} (agency={agency_name or 'なし'})")
        stats["inserted"] += 1
        return

    result = _post("cast_members", cast_row)
    if result:
        new_row = result[0]
        existing_cast[norm] = new_row
        print(f"  [NEW] {name} → cast_members id={new_row.get('id','')} agency={agency_name or 'なし'}")
        stats["inserted"] += 1
    else:
        print(f"  [ERR] {name} — INSERT 失敗")
        stats["errors"] += 1

# ─── unknown_performers 管理 ──────────────────────────────────────────────────

def list_unknown(status_filter: str | None = "pending") -> None:
    params = "select=id,raw_name,normalized_name,source_url,count,status,detected_at"
    if status_filter:
        params += f"&status=eq.{status_filter}"
    params += "&order=count.desc&limit=100"
    rows = _get("unknown_performers", params)
    print(f"unknown_performers ({status_filter or '全件'}): {len(rows)} 件")
    for r in rows:
        print(f"  [{r['status']:8s}] count={r['count']:3d}  {r['raw_name']}")
        if r.get("source_url"):
            print(f"            {r['source_url']}")

def approve_unknown(performer_id: str, cast_data: dict) -> None:
    """unknown_performers を承認し cast_members に昇格する。"""
    rows = _get("unknown_performers", f"id=eq.{performer_id}&select=*")
    if not rows:
        print(f"[ERROR] id={performer_id} が見つかりません")
        return
    row = rows[0]
    if row["status"] != "pending":
        print(f"[WARN] status={row['status']} のため承認済みまたは却下済みです")
        return

    existing_cast = load_existing_cast()
    existing_agencies = load_existing_agencies()
    norm = normalize_name(row["raw_name"])
    if norm in existing_cast:
        print(f"[SKIP] {row['raw_name']} は既に cast_members に存在します")
    else:
        cast_row = {
            "name":              row["raw_name"],
            "normalized_name":   norm,
            "profile_url":       cast_data.get("profile_url") or cast_data.get("source_url"),
            "x_url":             cast_data.get("x_url"),
            "gender":            cast_data.get("gender", "unknown"),
            "is_active":         True,
            "source":            "manual",
            "first_detected_at": row["detected_at"],
            "ng_flag":           False,
        }
        cast_row = {k: v for k, v in cast_row.items() if v is not None}
        result = _post("cast_members", cast_row)
        print(f"[OK] {row['raw_name']} → cast_members id={result[0].get('id','') if result else '?'}")

    _patch("unknown_performers", f"id=eq.{performer_id}", {"status": "approved"})
    print(f"[OK] unknown_performers id={performer_id} → approved")

# ─── メイン ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="演者マスタ自動登録スクリプト")
    parser.add_argument("--input",           metavar="FILE", help="登録する演者 JSON ファイル")
    parser.add_argument("--dry-run",         action="store_true", help="DB に書き込まず内容確認のみ")
    parser.add_argument("--list-unknown",    action="store_true", help="unknown_performers 一覧を表示")
    parser.add_argument("--list-all-unknown",action="store_true", help="全ステータスの unknown_performers を表示")
    parser.add_argument("--approve-unknown", metavar="ID",  help="unknown_performers を承認して cast_members に昇格")
    parser.add_argument("--approve-data",    metavar="JSON",help="--approve-unknown 時に追加するデータ (JSON 文字列)")
    args = parser.parse_args()

    if args.list_unknown:
        list_unknown("pending")
        return

    if args.list_all_unknown:
        list_unknown(None)
        return

    if args.approve_unknown:
        cast_data = json.loads(args.approve_data) if args.approve_data else {}
        approve_unknown(args.approve_unknown, cast_data)
        return

    if not args.input:
        parser.print_help()
        return

    # ── 入力 JSON 読み込み ───────────────────────────────────────────────────
    with open(args.input, encoding="utf-8") as f:
        entries: list[dict] = json.load(f)

    print(f"入力: {len(entries)} 件 ({'DRY RUN' if args.dry_run else '本番'})")

    # バリデーション
    all_errors: list[str] = []
    for i, e in enumerate(entries):
        all_errors.extend(validate_entry(e, i))
    if all_errors:
        for err in all_errors:
            print(f"[VALIDATION ERROR] {err}")
        sys.exit(1)

    # 既存データ読み込み
    print("既存データを読み込み中...")
    existing_cast     = load_existing_cast()
    existing_agencies = load_existing_agencies()
    existing_unknown  = load_existing_unknown_performers()
    print(f"  cast_members:       {len(existing_cast)} 件")
    print(f"  agencies:           {len(existing_agencies)} 件")
    print(f"  unknown_performers: {len(existing_unknown)} 件")
    print()

    stats = {
        "inserted":            0,
        "updated":             0,
        "skipped":             0,
        "unknown_new":         0,
        "unknown_incremented": 0,
        "errors":              0,
    }

    for entry in entries:
        register_cast_member(
            entry,
            existing_cast,
            existing_agencies,
            existing_unknown,
            stats,
            dry_run=args.dry_run,
        )

    print()
    print("=== 結果 ===")
    print(f"  新規登録:             {stats['inserted']} 件")
    print(f"  更新(X URL):         {stats['updated']} 件")
    print(f"  スキップ(重複):       {stats['skipped']} 件")
    print(f"  unknown 新規:         {stats['unknown_new']} 件")
    print(f"  unknown カウント増:   {stats['unknown_incremented']} 件")
    print(f"  エラー:               {stats['errors']} 件")

if __name__ == "__main__":
    main()
