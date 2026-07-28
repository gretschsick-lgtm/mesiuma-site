#!/usr/bin/env python3
"""
店舗ハンドル → canonical store 照合・分類ツール（store_handles.json の正規化）。

■ Source of Truth（重要）
  - complete データの **canonical store_id 空間 = Supabase `stores` テーブル**
    （id = sha256(店舗名)[:10]）。JSON complete 内の store_id も全てこの空間。
  - `public/stores.json`（6402件）は **別 id 方式のフロント表示用マスタ**であり、
    complete/ランキングの canonical store_id ではない（id 空間が非重複）。
  - よって本ツールは canonical = DB `stores` を基準に照合する（DB へは SELECT のみ）。

■ 照合順序（confidence 高→低）
  1. x_url_evidence : handle の x_url が DB store の公式 x_url と一致 → verified(Tier A)
  2. exact_name     : handle の店舗名が DB store 名と完全一致（一意）
  3. normalized_unique : 正規化店舗名が DB store と一意一致
  4. ambiguous      : 正規化名が複数 DB store に一致 → 保留（store_id なし）
  5. unregistered   : DB canonical マスタに該当なし → 保留（store_id なし）

■ 分類（verification_status）
  - verified  : x_url_evidence（DB store 自身が当該 X を公式として保持）。KPI 算入。
  - candidate : store_id は解決できたが公式 X 証拠が未確定 / DB 店が別 X 保有 /
                曖昧 / 未登録。KPI 非算入（後日 Tier A/B の公開根拠で確認）。
  - rejected  : （現状オフラインでは付与しない。閉店・凍結等は公開根拠確認が必要）
  - manager 型は店舗公式 X の KPI から除外（従来用途のため保持、excluded_manager）。

■ store_handles.json への付与（後方互換・既存キーは保持、キー追加のみ）
  store_id / verification_status / evidence_type / evidence_url / verified_at /
  is_active / rejection_reason / canonical_handle / match_method

■ 禁止事項の遵守
  - 推測 handle の生成・件数合わせの登録・実在未確認 handle の追加は行わない。
  - DB へは書き込まない（本ツールは SELECT のみ）。store_handles.json のみ更新。
  - X 表示名だけで公式判定しない（verified は DB 公式 x_url 一致のみ）。

使用:
  python scripts/resolve_store_handles.py            # dry-run（集計のみ・書き込まない）
  python scripts/resolve_store_handles.py --write     # store_handles.json を更新
  python scripts/resolve_store_handles.py --report-out /tmp/store_resolve_report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import ssl
import sys
import tempfile
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_HANDLES_JSON = ROOT / "public" / "store_handles.json"
STORES_JSON = ROOT / "public" / "stores.json"

_X_HANDLE_RE = re.compile(r"(?:x|twitter)\.com/([^/?#]+)", re.IGNORECASE)


def normalize_store_name(name: str) -> str:
    """店舗名正規化（register_stores.py と同一: NFKC + lower + 空白除去）。店舗専用。"""
    s = unicodedata.normalize("NFKC", (name or "").strip())
    return s.lower().replace(" ", "").replace("　", "")


def handle_of(url: str) -> str:
    """X/Twitter URL からハンドル（小文字）を取り出す。"""
    if not url:
        return ""
    m = _X_HANDLE_RE.search(url)
    return m.group(1).lower() if m else ""


def _sb_env() -> tuple[str, str]:
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("❌ NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が未設定です。")
    return url, key


def sb_get_all(path: str) -> list[dict]:
    """PostgREST から全行 SELECT（読み取り専用・ページング）。"""
    url, key = _sb_env()
    ctx = ssl._create_unverified_context()
    rows: list[dict] = []
    off, page = 0, 1000
    while True:
        req = urllib.request.Request(
            f"{url}/rest/v1/{path}&limit={page}&offset={off}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        rows.extend(batch)
        off += page
        if len(batch) < page:
            break
    return rows


def load_db_stores() -> list[dict]:
    return sb_get_all("stores?select=id,name,normalized_name,x_url,is_active,pref")


def build_indexes(db_stores: list[dict]):
    """正規化名 → [store], x_handle → store のインデックス。テスト行は canonical から除外。"""
    by_norm: dict[str, list[dict]] = collections.defaultdict(list)
    by_xhandle: dict[str, dict] = {}
    for r in db_stores:
        if "テスト" in (r.get("name") or ""):
            continue  # テストデータは canonical 母集団から除外
        key = r.get("normalized_name") or normalize_store_name(r["name"])
        by_norm[key].append(r)
        h = handle_of(r.get("x_url"))
        if h and h not in by_xhandle:
            by_xhandle[h] = r
    return by_norm, by_xhandle


def classify(store_handles: dict, by_norm: dict, by_xhandle: dict, as_of: str) -> dict:
    """
    store 型 handle を分類し、付与すべきメタデータ dict（handle→fields）を返す。
    manager / type 無しは excluded として最小限のみ付与。
    """
    meta: dict[str, dict] = {}
    for handle, v in store_handles.items():
        if not isinstance(v, dict):
            continue
        htype = v.get("type")
        if htype != "store":
            # manager 等: KPI 除外。既存用途保持のため type はそのまま、状態のみ明示。
            meta[handle] = {"verification_status": "excluded_manager" if htype == "manager" else "excluded"}
            continue

        xh = handle_of(v.get("x_url")) or handle.lower()
        nm = normalize_store_name(v.get("store"))
        fields: dict = {}

        # 1) x_url_evidence（DB 公式 x_url 一致）= verified(Tier A)
        st = by_xhandle.get(xh)
        if st:
            fields.update(
                store_id=st["id"],
                verification_status="verified",
                evidence_type="canonical_x_url",
                evidence_url=st.get("x_url"),
                is_active=bool(st.get("is_active", True)),
                match_method="x_url_evidence",
                canonical_pref=st.get("pref"),
            )
            meta[handle] = fields
            continue

        # 2/3) 名前一致（exact / normalized-unique）
        cands = by_norm.get(nm, [])
        if len(cands) == 1:
            store = cands[0]
            exact = (v.get("store") or "").strip() == (store.get("name") or "").strip()
            db_xh = handle_of(store.get("x_url"))
            fields.update(
                store_id=store["id"],
                verification_status="candidate",
                evidence_type="public_x_profile",
                evidence_url=v.get("x_url"),
                is_active=bool(store.get("is_active", True)),
                match_method="exact_name" if exact else "normalized_unique",
                canonical_pref=store.get("pref"),
            )
            if db_xh and db_xh != xh:
                # DB 店は別 X を公式保持 → この handle は非公式/二次の可能性
                fields["rejection_reason"] = "store_has_other_official_x"
            else:
                fields["rejection_reason"] = "needs_official_source_confirmation"
            meta[handle] = fields
            continue

        # 4) 曖昧（複数 DB store）
        if len(cands) > 1:
            meta[handle] = dict(
                store_id=None, verification_status="candidate",
                evidence_type=None, evidence_url=v.get("x_url"),
                match_method="ambiguous", rejection_reason="ambiguous_multi_store",
            )
            continue

        # 5) 未登録（canonical マスタに無し）
        meta[handle] = dict(
            store_id=None, verification_status="candidate",
            evidence_type=None, evidence_url=v.get("x_url"),
            match_method="unregistered", rejection_reason="not_in_canonical_master",
        )

    # canonical_handle: verified の store_id ごとに count 最大の 1 件を true、他 false
    by_store: dict[str, list[str]] = collections.defaultdict(list)
    for handle, f in meta.items():
        if f.get("verification_status") == "verified" and f.get("store_id"):
            by_store[f["store_id"]].append(handle)
    for sid, handles in by_store.items():
        handles.sort(key=lambda h: -(store_handles[h].get("count", 0)))
        for i, h in enumerate(handles):
            meta[h]["canonical_handle"] = (i == 0)

    # verified に verified_at を付与（既存値は保持）
    for handle, f in meta.items():
        if f.get("verification_status") == "verified":
            existing = store_handles[handle].get("verified_at")
            f["verified_at"] = existing or as_of
    return meta


def apply_meta(store_handles: dict, meta: dict) -> dict:
    """既存エントリにメタを非破壊マージ（既存キーは保持・追加のみ）。"""
    out = {h: (dict(v) if isinstance(v, dict) else v) for h, v in store_handles.items()}
    for handle, f in meta.items():
        if handle in out and isinstance(out[handle], dict):
            for k, val in f.items():
                out[handle][k] = val
    return out


def summarize(store_handles: dict, meta: dict, db_stores: list[dict]) -> dict:
    store_cnt = sum(1 for v in store_handles.values() if isinstance(v, dict) and v.get("type") == "store")
    mgr_cnt = sum(1 for v in store_handles.values() if isinstance(v, dict) and v.get("type") == "manager")
    status = collections.Counter(f.get("verification_status") for f in meta.values())
    method = collections.Counter(f.get("match_method") for f in meta.values() if f.get("match_method"))
    reason = collections.Counter(f.get("rejection_reason") for f in meta.values() if f.get("rejection_reason"))
    verified_ids = {f["store_id"] for f in meta.values()
                    if f.get("verification_status") == "verified" and f.get("store_id")}
    resolved_ids = {f["store_id"] for f in meta.values() if f.get("store_id")}
    # 複数 handle 店舗（store_id 解決済のうち 2 件以上）
    per_store = collections.Counter(f["store_id"] for f in meta.values() if f.get("store_id"))
    multi = sum(1 for c in per_store.values() if c > 1)
    # 都道府県別 verified カバー
    pref_cov = collections.Counter(f.get("canonical_pref") for f in meta.values()
                                   if f.get("verification_status") == "verified" and f.get("canonical_pref"))
    real_db = [r for r in db_stores if "テスト" not in (r.get("name") or "")]
    return dict(
        store_handles_total=store_cnt, manager_total=mgr_cnt,
        status=dict(status), method=dict(method), reason=dict(reason),
        verified_unique_canonical_stores=len(verified_ids),
        resolved_unique_store_ids=len(resolved_ids),
        multi_handle_stores=multi,
        db_stores_total=len(db_stores), db_stores_real=len(real_db),
        db_test_rows=len(db_stores) - len(real_db),
        kpi_target=5000, kpi_ratio=round(len(verified_ids) / 5000 * 100, 2),
        kpi_gap=5000 - len(verified_ids),
        pref_coverage=dict(pref_cov.most_common()),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="店舗ハンドル → canonical store 照合・分類")
    ap.add_argument("--write", action="store_true", help="store_handles.json を実際に更新（既定は dry-run）")
    ap.add_argument("--as-of", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    help="verified_at に用いる日付（既定=UTC 本日）")
    ap.add_argument("--report-out", default=None, help="集計レポート JSON の出力先")
    ap.add_argument("--backfill-map-out", default=None,
                    help="handle→store_id 対応表(store_id 解決分)の出力先（DB backfill 用）")
    args = ap.parse_args()

    store_handles = json.loads(STORE_HANDLES_JSON.read_text(encoding="utf-8"))
    db_stores = load_db_stores()
    by_norm, by_xhandle = build_indexes(db_stores)
    meta = classify(store_handles, by_norm, by_xhandle, args.as_of)
    summary = summarize(store_handles, meta, db_stores)

    print("=== 店舗ハンドル canonical 照合結果 ===")
    print(f"store 型 handle: {summary['store_handles_total']} / manager 型: {summary['manager_total']}")
    print(f"DB canonical stores: {summary['db_stores_real']} 実店舗 (+テスト {summary['db_test_rows']})")
    print(f"分類: {summary['status']}")
    print(f"照合方法: {summary['method']}")
    print(f"保留理由: {summary['reason']}")
    print(f"■ verified unique canonical store_id: {summary['verified_unique_canonical_stores']}")
    print(f"■ store_id 解決済 unique: {summary['resolved_unique_store_ids']} / 複数handle店舗: {summary['multi_handle_stores']}")
    print(f"■ KPI: {summary['verified_unique_canonical_stores']}/5000 "
          f"= {summary['kpi_ratio']}% / 不足 {summary['kpi_gap']}")

    if args.report_out:
        Path(args.report_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"レポート出力: {args.report_out}")

    if args.backfill_map_out:
        bmap = {h: {"store_id": f["store_id"], "verification_status": f["verification_status"]}
                for h, f in meta.items() if f.get("store_id")}
        Path(args.backfill_map_out).write_text(json.dumps(bmap, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"backfill マップ出力: {args.backfill_map_out}（{len(bmap)}件）")

    if args.write:
        merged = apply_meta(store_handles, meta)
        # count 降順（既存 collector と同一ソート）で書き出し
        ordered = dict(sorted(merged.items(),
                              key=lambda x: -(x[1].get("count", 0) if isinstance(x[1], dict) else 0)))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STORE_HANDLES_JSON.parent,
                                         delete=False, suffix=".tmp") as tf:
            json.dump(ordered, tf, ensure_ascii=False, indent=2)
            tmp = tf.name
        os.replace(tmp, STORE_HANDLES_JSON)
        print(f"✅ store_handles.json 更新: {len(ordered)} エントリ（メタ付与）")
    else:
        print("（dry-run: --write 指定で store_handles.json を更新します）")


if __name__ == "__main__":
    main()
