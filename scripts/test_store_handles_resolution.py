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
    by_norm, by_xh, by_id = R.build_indexes(db)
    ok("テストホール" not in {r["name"] for k in by_norm for r in by_norm[k]}, "build_indexes: テスト行を canonical から除外")
    meta = R.classify(handles, by_norm, by_xh, by_id, "2026-07-28")

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


def test_D_preserve_store_id():
    print("[D] 既存 store_id 保持ガード（合成 fixture）")
    db = [
        {"id": "sid_keep", "name": "保持店A", "normalized_name": "保持店a",
         "x_url": None, "is_active": True, "pref": "東京都"},
        {"id": "sid_xhit", "name": "エックス店", "normalized_name": "えっくす店",
         "x_url": "https://x.com/xhit_official", "is_active": True, "pref": "大阪府"},
        {"id": "sid_uniq", "name": "一意店B", "normalized_name": "一意店b",
         "x_url": None, "is_active": True, "pref": "京都府"},
    ]
    by_norm, by_xh, by_id = R.build_indexes(db)

    # helper 単体
    ok(R._should_preserve_existing_store_id({"store_id": "sid_keep"}, by_id) is True,
       "helper: canonical 実在の既存 store_id は保持可")
    ok(R._should_preserve_existing_store_id({"store_id": "orphan_xxx"}, by_id) is False,
       "helper: orphan store_id は保持不可")
    ok(R._should_preserve_existing_store_id({"store_id": None}, by_id) is False,
       "helper: store_id 無しは保持不可")

    handles = {
        # A: 既存store_idあり・canonical実在・name再解決不能(DB名と不一致)・強い競合なし → 保持
        "keep_a":  {"store": "旧名称ずれ店", "x_url": "https://x.com/keep_a", "count": 10,
                    "type": "store", "store_id": "sid_keep", "verification_status": "candidate",
                    "match_method": "ns4_enorm"},
        # B: 既存store_idありだが x_url が別store(sid_xhit)を明確に指す → canonical_x_url優先(旧IDは保持しない)
        "b_handle": {"store": "別名称店", "x_url": "https://x.com/xhit_official", "count": 5,
                     "type": "store", "store_id": "sid_keep", "verification_status": "candidate"},
        # C: 既存store_idが canonical 不在(orphan) → 保持せず None
        "orphan_h": {"store": "存在しない店", "x_url": "https://x.com/orphan_h", "count": 3,
                     "type": "store", "store_id": "orphan_zzz", "verification_status": "candidate"},
        # D: 既存store_idありだが name が別store(sid_uniq)へ一意一致 → resolver の一意解決を優先
        "d_handle": {"store": "一意店B", "x_url": "https://x.com/d_handle", "count": 4,
                     "type": "store", "store_id": "sid_keep", "verification_status": "candidate"},
        # E: store_id 無し candidate・name 再解決不能 → 勝手に store_id を付けない
        "e_handle": {"store": "未登録店", "x_url": "https://x.com/e_handle", "count": 2,
                     "type": "store", "verification_status": "candidate"},
    }
    meta = R.classify(handles, by_norm, by_xh, by_id, "2026-08-17")

    a = meta["keep_a"]
    ok(a["store_id"] == "sid_keep" and a["verification_status"] == "candidate"
       and a["match_method"] == "preserved_existing_link",
       "A: 有効な既存 store_id を name 再解決不能でも保持", a)

    b = meta["b_handle"]
    ok(b["store_id"] == "sid_xhit" and b["verification_status"] == "verified"
       and b["evidence_type"] == "canonical_x_url",
       "B: canonical_x_url が別storeを指す場合は旧IDでなく x_url store を採用", b)

    c = meta["orphan_h"]
    ok(c["store_id"] is None and c["match_method"] == "unregistered",
       "C: orphan の既存 store_id は保持せず None", c)

    d = meta["d_handle"]
    ok(d["store_id"] == "sid_uniq" and d["match_method"] in ("exact_name", "normalized_unique"),
       "D: name 一意一致は旧IDより優先(relink)", d)

    e = meta["e_handle"]
    ok(e["store_id"] is None,
       "E: store_id 無し candidate に勝手に store_id を付与しない", e)

    # F/G/H: 既存の保持ガード・canonical_x_url・manager は本 fixture では test_A で網羅済み。
    # ここでは preservation が verified/x_url/manager 経路を壊さないことを最小確認。
    hf = {
        "off_ver": {"store": "保持店A", "x_url": "https://x.com/off_ver", "count": 9, "type": "store",
                    "store_id": "sid_keep", "verification_status": "verified",
                    "evidence_type": "official_store_site", "evidence_url": "https://example.com/store",
                    "canonical_handle": True},
        "mgr_h": {"store": "保持店A 店長", "x_url": "https://x.com/mgr_h", "count": 1, "type": "manager",
                  "store_id": "sid_keep", "verification_status": "candidate"},
    }
    m2 = R.classify(hf, by_norm, by_xh, by_id, "2026-08-17")
    ok(m2["off_ver"]["verification_status"] == "verified"
       and m2["off_ver"]["evidence_type"] == "official_store_site"
       and m2["off_ver"]["store_id"] == "sid_keep",
       "F: official_store_site verified は保持ガードで巻き戻らない", m2["off_ver"])
    ok(m2["mgr_h"]["verification_status"] == "excluded_manager",
       "H: manager は excluded_manager（preservation の影響を受けない）", m2["mgr_h"])


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
    # verified の evidence は Tier A（公式サイト/チェーン/canonical x_url）のいずれか
    _VALID_EV = {"canonical_x_url", "official_chain_site", "official_store_site"}
    bad_v = [h for h, v in verified.items()
             if not v.get("store_id") or v.get("evidence_type") not in _VALID_EV]
    ok(not bad_v, "verified は store_id あり & Tier A evidence", f"{len(bad_v)}件")
    # 公式サイト根拠の verified は evidence_url 必須
    bad_url = [h for h, v in verified.items()
               if v.get("evidence_type") in ("official_chain_site", "official_store_site")
               and not v.get("evidence_url")]
    ok(not bad_url, "公式サイト根拠 verified は evidence_url あり", f"{len(bad_url)}件")

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
    test_D_preserve_store_id()
    test_B_apply_meta()
    test_C_real()
    print(f"\n=> PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
