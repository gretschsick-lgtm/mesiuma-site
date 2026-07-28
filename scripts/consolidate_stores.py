#!/usr/bin/env python3
"""
店舗マスタ統合ツール（stores.json 6402 → Supabase canonical stores の安全な拡張）。

■ Source of Truth
  - canonical store master = Supabase `stores`（id = sha256(店舗名)[:10]）。
  - public/stores.json は別 id 方式の表示用マスタ。本ツールで各エントリに
    後方互換フィールド `canonical_store_id`（= 対応する DB stores.id）を付与する。

■ 照合順序（stores.json エントリ E → canonical DB store）
  1. existing_exact       : E.canonical_store_id が既に DB に存在（再実行時の冪等）
                            もしくは sha256(E.name) が DB id に一致（完全同名）
  2. existing_unique_match: x_url ハンドル完全一致 / 正規化名が DB に一意一致
  3. new_high_confidence  : DB 未該当かつ高信頼（実在店舗・名称一意・pref あり）→ DB 追加対象
  4. ambiguous            : 正規化名が DB 複数一致 / 同名が複数 pref に跨る（id 衝突リスク）
  5. duplicate            : stores.json 内で同一店舗の重複（同名・同 pref）→ 代表1件以外
  6. closed_or_invalid    : 閉店・仮店舗・無効名の疑い
  7. test_data            : テスト用データ

■ DB 変更方針（すべて gate: snapshot / affected / rollback を確定してから）
  - INSERT: new_high_confidence のみ（id = sha256(name)・重複 id は挿入しない）。
  - UPDATE: existing 一致店の **NULL 項目のみ**を stores.json の確定値で補完
            （既存の正しい値は絶対に上書きしない）。
  - DELETE: 禁止。無効化は is_active=false のみ。

使用:
  python scripts/consolidate_stores.py                     # dry-run 分類（DB/JSON 変更なし）
  python scripts/consolidate_stores.py --plan-out P.json   # 実行計画(INSERT/UPDATE集合)を出力
  python scripts/consolidate_stores.py --write-json        # stores.json に canonical_store_id 付与
  python scripts/consolidate_stores.py --apply-db          # DB へ INSERT/UPDATE 適用（gate 通過時のみ）
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import ssl
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORES_JSON = ROOT / "public" / "stores.json"

_X_HANDLE_RE = re.compile(r"(?:x|twitter)\.com/([^/?#]+)", re.IGNORECASE)
_CLOSED_RE = re.compile(r"(閉店|\(仮\)|（仮）|仮店舗|営業終了|跡地)")
_TEST_RE = re.compile(r"テスト|test", re.IGNORECASE)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip()).lower().replace(" ", "").replace("　", "")


def sid_of(name: str) -> str:
    return hashlib.sha256((name or "").encode()).hexdigest()[:10]


def handle_of(url: str) -> str:
    if not url:
        return ""
    m = _X_HANDLE_RE.search(url)
    return m.group(1).lower() if m else ""


def _env():
    u = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    k = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not u or not k:
        sys.exit("❌ Supabase 環境変数が未設定")
    return u, k


def sb_get_all(path: str) -> list[dict]:
    u, k = _env()
    ctx = ssl._create_unverified_context()
    rows, off = [], 0
    while True:
        req = urllib.request.Request(
            f"{u}/rest/v1/{path}&limit=1000&offset={off}",
            headers={"apikey": k, "Authorization": f"Bearer {k}"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            b = json.loads(r.read())
        if not b:
            break
        rows += b; off += 1000
        if len(b) < 1000:
            break
    return rows


def is_real_name(name: str) -> bool:
    n = (name or "").strip()
    if len(n) < 3:
        return False
    if _TEST_RE.search(n):
        return False
    if re.fullmatch(r"[\d\W]+", n):
        return False
    return True


def classify(stores: list[dict], db: list[dict]) -> dict:
    """各 stores.json エントリを分類。handle→分類 dict と、DB 操作計画を返す。"""
    real_db = [r for r in db if not _TEST_RE.search(r.get("name") or "")]
    db_ids = {r["id"] for r in db}
    by_norm: dict[str, list[dict]] = collections.defaultdict(list)
    by_xh: dict[str, dict] = {}
    for r in real_db:
        by_norm[r.get("normalized_name") or norm(r["name"])].append(r)
        h = handle_of(r.get("x_url"))
        if h:
            by_xh.setdefault(h, r)

    db_by_id = {r["id"]: r for r in db}
    results = {}       # stores.json id → classification dict
    inserts = {}       # canonical_id → row(dict) for INSERT (dedup by id)
    updates = {}       # canonical_id → {field: value} NULL 補完

    # ── フェーズ1: 各エントリの基本判定（test/closed/existing/new候補）──────────────
    exact_name_prefs: dict[str, set] = collections.defaultdict(set)  # sha256(name) → prefs（衝突検出）
    for e in stores:
        exact_name_prefs[sid_of(e.get("name"))].add(e.get("pref"))

    new_candidates: list[dict] = []
    for e in stores:
        name = e.get("name") or ""
        cid = sid_of(name)
        cls = canonical = None
        if _TEST_RE.search(name):
            cls = "test_data"
        elif (not is_real_name(name)) or _CLOSED_RE.search(name):
            cls = "closed_or_invalid"
        elif cid in db_ids:
            cls = "existing_exact"; canonical = cid
        else:
            xh = handle_of(e.get("x_url"))
            cands = by_norm.get(norm(name), [])
            if xh and xh in by_xh:
                cls = "existing_unique_match"; canonical = by_xh[xh]["id"]
            elif len(cands) == 1:
                cls = "existing_unique_match"; canonical = cands[0]["id"]
            elif len(cands) > 1:
                cls = "ambiguous"
            elif not e.get("pref"):
                cls = "ambiguous"                       # pref 無し → 安全に確定不可
            elif len(exact_name_prefs[cid]) > 1:
                cls = "ambiguous"                       # 同一 raw 名が複数 pref → id 衝突
            else:
                new_candidates.append(e); cls = "__pending__"
        results[e["id"]] = {"canonical_store_id": canonical, "classification": cls}

    # ── フェーズ2: 新規候補を (正規化名, pref) で統合（表記ゆれ重複を排除）────────────
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for e in new_candidates:
        groups[(norm(e.get("name")), e.get("pref"))].append(e)
    for key, members in groups.items():
        # 代表 = event_count 最大（tie は id）。canonical id = 代表 raw 名の sha256
        rep = max(members, key=lambda x: (x.get("event_count") or 0, x["id"]))
        rep_cid = sid_of(rep.get("name"))
        # 代表 id が既存 DB や他 INSERT と衝突する場合は保留（安全側）
        if rep_cid in db_ids:
            for e in members:
                results[e["id"]] = {"canonical_store_id": rep_cid, "classification": "existing_exact"}
            continue
        for e in members:
            if e["id"] == rep["id"]:
                results[e["id"]] = {"canonical_store_id": rep_cid, "classification": "new_high_confidence"}
                if rep_cid not in inserts:
                    row = {"id": rep_cid, "name": rep.get("name"),
                           "normalized_name": norm(rep.get("name")), "is_active": True}
                    if rep.get("pref"):    row["pref"] = rep["pref"]
                    if rep.get("address"): row["address"] = rep["address"]
                    if rep.get("x_url"):   row["x_url"] = rep["x_url"]
                    if rep.get("hp_url"):  row["hp_url"] = rep["hp_url"]
                    inserts[rep_cid] = row
            else:
                results[e["id"]] = {"canonical_store_id": rep_cid, "classification": "duplicate"}

    # ── UPDATE 計画（existing 一致店の NULL 補完のみ・上書きしない）────────────────
    for e in stores:
        r = results[e["id"]]
        cls, canonical = r["classification"], r["canonical_store_id"]
        if cls in ("existing_exact", "existing_unique_match") and canonical in db_by_id:
            dbrow = db_by_id[canonical]
            patch = {}
            for fld in ("pref", "address", "hp_url"):
                if not dbrow.get(fld) and e.get(fld):
                    patch[fld] = e[fld]
            if not dbrow.get("x_url") and e.get("x_url"):
                patch["x_url"] = e["x_url"]
            if patch:
                cur = updates.setdefault(canonical, {})
                for kk, vv in patch.items():
                    cur.setdefault(kk, vv)

    return dict(results=results, inserts=inserts, updates=updates,
                counts=collections.Counter(v["classification"] for v in results.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-out")
    ap.add_argument("--write-json", action="store_true")
    ap.add_argument("--apply-db", action="store_true")
    args = ap.parse_args()

    stores = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    db = sb_get_all("stores?select=id,name,normalized_name,x_url,is_active,pref,address,hp_url")
    plan = classify(stores, db)
    c = plan["counts"]

    print("=== stores.json 分類（read-only）===")
    print(f"stores.json 総数: {len(stores)} / DB canonical: {len(db)}")
    for k in ("existing_exact", "existing_unique_match", "new_high_confidence",
              "ambiguous", "duplicate", "closed_or_invalid", "test_data"):
        print(f"  {k}: {c.get(k,0)}")
    ins = plan["inserts"]; upd = plan["updates"]
    print(f"■ DB INSERT 予定(new_high_confidence・id dedup後): {len(ins)}")
    print(f"■ DB UPDATE 予定(既存店 NULL 補完): {len(upd)}")
    fld_fill = collections.Counter()
    for p in upd.values():
        for kk in p:
            fld_fill[kk] += 1
    print(f"   補完フィールド内訳: {dict(fld_fill)}")
    ins_fill = collections.Counter()
    for r in ins.values():
        for kk in ("pref", "address", "x_url", "hp_url"):
            if r.get(kk):
                ins_fill[kk] += 1
    print(f"   INSERT 付随フィールド: {dict(ins_fill)} / pref無し INSERT: {sum(1 for r in ins.values() if not r.get('pref'))}")

    if args.plan_out:
        Path(args.plan_out).write_text(json.dumps(
            {"results": plan["results"], "inserts": plan["inserts"], "updates": plan["updates"],
             "counts": dict(c)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"計画出力: {args.plan_out}")

    if args.write_json:
        changed = 0
        for e in stores:
            cid = plan["results"][e["id"]]["canonical_store_id"]
            if cid and e.get("canonical_store_id") != cid:
                e["canonical_store_id"] = cid; changed += 1
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STORES_JSON.parent,
                                         delete=False, suffix=".tmp") as tf:
            json.dump(stores, tf, ensure_ascii=False, indent=2)
            tmp = tf.name
        os.replace(tmp, STORES_JSON)
        print(f"✅ stores.json 更新: canonical_store_id 付与/更新 {changed} 件")

    if args.apply_db:
        _apply_db(plan)


def _apply_db(plan):
    u, k = _env()
    ctx = ssl._create_unverified_context()
    H = {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}
    # 全行を同一キー集合に揃える（PostgREST バルク INSERT はキー構成一致が必須）
    _COLS = ["id", "name", "normalized_name", "is_active", "pref", "address", "x_url", "hp_url"]
    ins = [{c: r.get(c) for c in _COLS} for r in plan["inserts"].values()]
    # INSERT（バルク・500件ずつ・on_conflict は id）
    done = 0
    for i in range(0, len(ins), 500):
        chunk = ins[i:i+500]
        req = urllib.request.Request(
            f"{u}/rest/v1/stores?on_conflict=id",
            data=json.dumps(chunk).encode(),
            headers={**H, "Prefer": "resolution=ignore-duplicates,return=minimal"}, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=60):
            done += len(chunk)
    print(f"INSERT 完了: {done} 件")
    # UPDATE（NULL 補完・1 store ずつ PATCH）
    upd_done = 0
    for cid, patch in plan["updates"].items():
        req = urllib.request.Request(
            f"{u}/rest/v1/stores?id=eq.{cid}",
            data=json.dumps(patch).encode(),
            headers={**H, "Prefer": "return=minimal"}, method="PATCH")
        with urllib.request.urlopen(req, context=ctx, timeout=30):
            upd_done += 1
    print(f"UPDATE 完了: {upd_done} 件")


if __name__ == "__main__":
    main()
