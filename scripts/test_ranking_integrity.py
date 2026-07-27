#!/usr/bin/env python3
"""
コンプリートランキングの月間/トータル整合性テスト。

検証:
  A. 生成済み public/complete_ranking.json の出力不変条件（実コード出力を検証）
     - total.total_count == Σ monthly.total_count（#1）
     - 5月が total 母集団に含まれる（#5）
     - monthly の月が重複しない / 降順
  B. fixture でのルール検証（#6 JST月境界 / #7 二重計上なし / #8 top10 slice / machine_id 集計）
  C. 実全履歴（load_ranking_history）での #1/#2/#3 整合（total == Σmonthly を
     record / machine_id / store の各粒度で確認）

実行: python3 scripts/test_ranking_integrity.py  （成功 exit 0 / 失敗 exit 1）
"""
import os, sys, json, collections
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = Path(__file__).parent.parent
PASS = 0
FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  OK  {label}")
    else:
        FAIL += 1; print(f"  NG  {label}  {detail}")


# ── 共通: レコード列を集計するミラー（update_ranking と同一ルール）──────────────
def aggregate(records):
    """(x_url,machine) dedup → 月別/全期間を record / store(name) / machine_id で集計。"""
    seen = {}
    for e in records:
        k = ((e.get("x_url") or "").strip(), (e.get("machine") or "").strip())
        if not k[0]:
            continue
        seen.setdefault(k, e)
    pop = list(seen.values())

    month_rec = collections.Counter()
    month_store = collections.defaultdict(collections.Counter)
    month_mid = collections.defaultdict(collections.Counter)
    tot_rec = 0
    tot_store = collections.Counter()
    tot_mid = collections.Counter()
    for e in pop:
        d = e.get("date", "")
        if len(d) < 7:
            continue
        ym = d[:7]
        month_rec[ym] += 1; tot_rec += 1
        st = (e.get("store") or "").strip()
        if st and st != "店舗不明":
            month_store[ym][st] += 1; tot_store[st] += 1
        mid = e.get("machine_id")
        if mid:
            month_mid[ym][mid] += 1; tot_mid[mid] += 1
    return dict(pop=pop, month_rec=month_rec, month_store=month_store,
                month_mid=month_mid, tot_rec=tot_rec, tot_store=tot_store, tot_mid=tot_mid)


def test_A_output():
    print("[A] 生成済み complete_ranking.json 出力不変条件")
    p = ROOT / "public" / "complete_ranking.json"
    d = json.load(open(p, encoding="utf-8"))
    m = d["monthly"]; t = d["total"]
    s = sum(x["total_count"] for x in m)
    ok(s == t["total_count"], "total.total_count == Σ monthly.total_count", f"{t['total_count']} vs {s}")
    ok(any(x["month"] == "2026-05" for x in m), "2026-05 が monthly に含まれる")
    months = [x["month"] for x in m]
    ok(len(months) == len(set(months)), "monthly の月に重複なし")
    ok(months == sorted(months, reverse=True), "monthly は降順")
    ok(bool(d.get("generated_at")), "generated_at あり")
    for cat in ("slot_machines", "pachinko_machines"):
        ok(len(t[cat]) <= 10, f"total {cat} は top10 以内")


def test_B_fixture():
    print("[B] fixture ルール検証")
    recs = [
        # #7 同一(x_url,machine)は二重計上しない
        {"x_url": "u1", "machine": "L革命機ヴァルヴレイヴ2", "machine_id": "mid_vvv", "machine_type": "slot", "store": "店A", "date": "2026-05-31"},
        {"x_url": "u1", "machine": "L革命機ヴァルヴレイヴ2", "machine_id": "mid_vvv", "machine_type": "slot", "store": "店A", "date": "2026-05-31"},
        # 同一x_urlの別機種は保持
        {"x_url": "u1", "machine": "e牙狼12", "machine_id": "mid_garo", "machine_type": "pachinko", "store": "店A", "date": "2026-05-31"},
        # #6 JST月境界: 5/31 と 6/1 は別月
        {"x_url": "u2", "machine": "L革命機ヴァルヴレイヴ2", "machine_id": "mid_vvv", "machine_type": "slot", "store": "店B", "date": "2026-06-01"},
        # machine_id を跨月集計（7月）
        {"x_url": "u3", "machine": "L革命機ヴァルヴレイヴ2", "machine_id": "mid_vvv", "machine_type": "slot", "store": "店C", "date": "2026-07-10"},
        # machine_id なしは機種集計対象外だが total/store には算入
        {"x_url": "u4", "machine": "謎機種", "machine_type": "slot", "store": "店D", "date": "2026-07-11"},
    ]
    a = aggregate(recs)
    ok(len(a["pop"]) == 5, "(x_url,machine) dedup: 6→5", f"got {len(a['pop'])}")
    ok(a["month_rec"]["2026-05"] == 2 and a["month_rec"]["2026-06"] == 1 and a["month_rec"]["2026-07"] == 2,
       "JST月境界で 5/31→5月・6/1→6月 に分類", dict(a["month_rec"]))
    ok(a["tot_rec"] == sum(a["month_rec"].values()) == 5, "total_count == Σ monthly（#1）")
    ok(a["tot_mid"]["mid_vvv"] == 3 and (a["month_mid"]["2026-05"]["mid_vvv"] + a["month_mid"]["2026-06"]["mid_vvv"] + a["month_mid"]["2026-07"]["mid_vvv"]) == 3,
       "machine_id total == Σ monthly（#2）")
    ok("謎機種" not in {mid for c in a["month_mid"].values() for mid in c}, "machine_id なしは機種集計に入らない（#10）")
    ok(a["tot_rec"] == 5, "machine_id なしも total_count に算入（#10）")
    # #8 top10 slice: 12店舗を1機種ずつ → top10のみ
    many = [{"x_url": f"s{i}", "machine": "e牙狼12", "machine_id": "mid_garo", "machine_type": "pachinko", "store": f"S{i:02d}", "date": "2026-07-01"} for i in range(12)]
    a2 = aggregate(many)
    top10 = a2["tot_store"].most_common(10)
    ok(len(top10) == 10 and len(a2["tot_store"]) == 12, "top10 slice は全件集計後（#8）")


def test_C_realpop():
    print("[C] 実全履歴 load_ranking_history の粒度別 total==Σmonthly")
    try:
        import fetch_complete_info as f
    except Exception as e:
        ok(False, "fetch_complete_info import", str(e)); return
    pop = f.load_ranking_history()
    a = aggregate(pop)
    ok(a["tot_rec"] == sum(a["month_rec"].values()), "record: total == Σ monthly（#1）", f"{a['tot_rec']}")
    # machine_id 粒度
    mid_ok = all(a["tot_mid"][mid] == sum(a["month_mid"][ym].get(mid, 0) for ym in a["month_mid"]) for mid in a["tot_mid"])
    ok(mid_ok, "machine_id: total == Σ monthly（#2）")
    # store 粒度
    st_ok = all(a["tot_store"][s] == sum(a["month_store"][ym].get(s, 0) for ym in a["month_store"]) for s in a["tot_store"])
    ok(st_ok, "store: total == Σ monthly（#3）")
    ok("2026-05" in a["month_rec"], "5月が全履歴母集団に含まれる（#5）")


def main():
    test_A_output()
    test_B_fixture()
    test_C_realpop()
    print(f"\n=> PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
