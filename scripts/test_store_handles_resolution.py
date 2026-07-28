#!/usr/bin/env python3
"""
店舗ハンドル照合・分類（resolve_store_handles.py）の不変条件テスト。

検証:
  A. classify() のルール（合成 fixture・DB 非依存）
     - x_url_evidence → verified / canonical_x_url
     - name 一意一致だが DB 店が別 X 保有 → candidate / store_has_other_official_x
     - 曖昧（複数 DB 店）→ candidate / store_id なし / ambiguous
     - 未登録 → candidate / store_id なし / unregistered
     - manager 型 → excluded_manager（KPI 除外・store_id なし）
     - verified の store_id ごと canonical_handle は正確に 1 件
  B. apply_meta() 後方互換（既存キー保持・エントリ数不変・追加のみ）
  C. 実 store_handles.json の出力不変条件
     - store 型 handle は全件分類済（未分類ゼロ）
     - verified は store_id あり & evidence_type=canonical_x_url
     - verified store_id ごと canonical_handle=true は 1 件
     - manager 型は verified に混入しない（KPI 除外）

実行: python3 scripts/test_store_handles_resolution.py  （成功 exit 0 / 失敗 exit 1）
"""
import os
import sys
import json
import collections
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_store_handles as R

ROOT = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  OK  {label}")
    else:
        FAIL += 1; print(f"  NG  {label}  {detail}")


def test_A_classify():
    print("[A] classify() ルール（合成 fixture）")
    # DB canonical stores（テスト行は build_indexes が除外）
    db = [
        {"id": "sid_arrow", "name": "ARROW浪速店", "normalized_name": "arrow浪速店",
         "x_url": "https://x.com/arrow_naniwa", "is_active": True, "pref": "大阪府"},
        {"id": "sid_diffx", "name": "キクヤ春日井店", "normalized_name": "キクヤ春日井店",
         "x_url": "https://x.com/kikuya_official", "is_active": True, "pref": "愛知県"},
        # 曖昧: 同一正規化名の別 2 店
        {"id": "sid_dup1", "name": "夢屋", "normalized_name": "夢屋",
         "x_url": "https://x.com/yumeya_a", "is_active": True, "pref": "東京都"},
        {"id": "sid_dup2", "name": "夢屋", "normalized_name": "夢屋",
         "x_url": "https://x.com/yumeya_b", "is_active": True, "pref": "北海道"},
        {"id": "sid_test", "name": "テストホール", "normalized_name": "テストホール",
         "x_url": "https://x.com/testhall", "is_active": True, "pref": "東京都"},
    ]
    handles = {
        "arrow_naniwa":   {"store": "ARROW浪速店",  "x_url": "https://x.com/arrow_naniwa", "count": 30, "type": "store"},
        # handle キーは別だが x_url は canonical と同一 → 両方 verified（実データの複数handle店を再現）
        "arrow_alt":      {"store": "ARROW浪速店",  "x_url": "https://x.com/arrow_naniwa", "count": 5, "type": "store"},
        "kikuya_branch":  {"store": "キクヤ春日井店", "x_url": "https://x.com/kikuya_branch", "count": 8, "type": "store"},
        "yumeya_x":       {"store": "夢屋",          "x_url": "https://x.com/yumeya_x", "count": 4, "type": "store"},
        "unknown_shop":   {"store": "どこかホール",   "x_url": "https://x.com/unknown_shop", "count": 3, "type": "store"},
        "some_manager":   {"store": "ARROW浪速店 店長", "x_url": "https://x.com/some_manager", "count": 2, "type": "manager"},
    }
    by_norm, by_xh = R.build_indexes(db)
    ok("テストホール" not in {r["name"] for k in by_norm for r in by_norm[k]}, "build_indexes: テスト行を canonical から除外")
    meta = R.classify(handles, by_norm, by_xh, "2026-07-28")

    m = meta["arrow_naniwa"]
    ok(m["verification_status"] == "verified" and m["evidence_type"] == "canonical_x_url"
       and m["store_id"] == "sid_arrow", "x_url一致 → verified/canonical_x_url", m)
    ok(m.get("canonical_handle") is True, "count最大の verified は canonical_handle=true")
    ok(meta["arrow_alt"]["verification_status"] == "verified"
       and meta["arrow_alt"].get("canonical_handle") is False,
       "同一店の2つ目 verified は canonical_handle=false")

    k = meta["kikuya_branch"]
    ok(k["verification_status"] == "candidate" and k["store_id"] == "sid_diffx"
       and k["rejection_reason"] == "store_has_other_official_x",
       "名前一致だがDB別X → candidate/store_has_other_official_x", k)

    y = meta["yumeya_x"]
    ok(y["verification_status"] == "candidate" and y["store_id"] is None
       and y["match_method"] == "ambiguous", "曖昧(複数DB店) → candidate/store_idなし", y)

    u = meta["unknown_shop"]
    ok(u["verification_status"] == "candidate" and u["store_id"] is None
       and u["match_method"] == "unregistered", "未登録 → candidate/store_idなし", u)

    g = meta["some_manager"]
    ok(g["verification_status"] == "excluded_manager" and "store_id" not in g,
       "manager型 → excluded_manager/store_idなし", g)

    verified_ids = {f["store_id"] for f in meta.values() if f.get("verification_status") == "verified"}
    canon = [h for h, f in meta.items() if f.get("canonical_handle")]
    ok(len(canon) == len(verified_ids) == 1, "verified store_idごと canonical_handle は1件", (canon, verified_ids))


def test_B_apply_meta():
    print("[B] apply_meta() 後方互換")
    handles = {"h1": {"store": "A店", "x_url": "https://x.com/h1", "count": 3, "type": "store"}}
    meta = {"h1": {"store_id": "x", "verification_status": "verified"}}
    out = R.apply_meta(handles, meta)
    ok(len(out) == len(handles), "エントリ数不変")
    ok(out["h1"]["store"] == "A店" and out["h1"]["x_url"] == "https://x.com/h1"
       and out["h1"]["count"] == 3 and out["h1"]["type"] == "store", "既存キー保持")
    ok(out["h1"]["store_id"] == "x" and out["h1"]["verification_status"] == "verified", "新キー追加")
    ok(handles["h1"] == {"store": "A店", "x_url": "https://x.com/h1", "count": 3, "type": "store"},
       "元 dict を破壊しない（非破壊マージ）")


def test_C_real():
    print("[C] 実 store_handles.json 出力不変条件")
    p = ROOT / "public" / "store_handles.json"
    d = json.load(open(p, encoding="utf-8"))
    store_entries = {h: v for h, v in d.items() if isinstance(v, dict) and v.get("type") == "store"}
    unclassified = [h for h, v in store_entries.items() if "verification_status" not in v]
    ok(not unclassified, "store型 handle は全件分類済（未分類ゼロ）", f"{len(unclassified)}件未分類")

    verified = {h: v for h, v in d.items() if v.get("verification_status") == "verified"}
    bad_v = [h for h, v in verified.items()
             if not v.get("store_id") or v.get("evidence_type") != "canonical_x_url"]
    ok(not bad_v, "verified は store_id あり & canonical_x_url", f"{len(bad_v)}件")

    # verified store_id ごと canonical_handle=true は 1 件
    per = collections.defaultdict(list)
    for h, v in verified.items():
        per[v["store_id"]].append(v.get("canonical_handle"))
    multi_true = {sid: cs for sid, cs in per.items() if sum(1 for c in cs if c) != 1}
    ok(not multi_true, "verified store_idごと canonical_handle=true は1件", f"{len(multi_true)}店 不正")

    # manager 型は verified に混入しない
    mgr_verified = [h for h, v in d.items() if v.get("type") == "manager" and v.get("verification_status") == "verified"]
    ok(not mgr_verified, "manager型は verified に混入しない（KPI除外）", f"{len(mgr_verified)}件")

    verified_ids = {v["store_id"] for v in verified.values()}
    print(f"    （参考）verified handle {len(verified)} / verified unique store_id {len(verified_ids)}）")


def main():
    test_A_classify()
    test_B_apply_meta()
    test_C_real()
    print(f"\n=> PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
