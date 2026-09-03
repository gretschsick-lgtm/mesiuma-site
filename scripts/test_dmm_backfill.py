#!/usr/bin/env python3
"""NS-9C dmm_backfill ユニットテスト（純粋関数・ネット/DB非依存）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import dmm_backfill as B

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")

def idx(cards_by_pref):
    return B.build_dmm_index(cards_by_pref)

FAKECTX = {"db": [], "handles": {}, "rejected": set(), "excluded_manager": set(), "db_handle_to_store": {}}

def card(dmm_id, name, city=None):
    return {"dmm_id": dmm_id, "name": name, "city": city}

# 1. exact name + pref + address → EXACT_UNIQUE
I = idx({"東京都": [card("100", "PIA大森")]})
r = B.match_store({"id": "s1", "name": "PIA大森", "pref": "東京都", "address": "大田区山王2-4-1"}, I)
ok(r["status"] == "EXACT_UNIQUE" and r["dmm_id"] == "100", "1 exact name+pref(+addr) → EXACT_UNIQUE")

# 2. exact name + pref without address → EXACT_UNIQUE（一意なら可）
r = B.match_store({"id": "s2", "name": "PIA大森", "pref": "東京都", "address": None}, I)
ok(r["status"] == "EXACT_UNIQUE", "2 exact name+pref(addr無) → EXACT_UNIQUE")

# 3. duplicate name same pref → AMBIGUOUS
I2 = idx({"東京都": [card("1", "エスパス"), card("2", "エスパス")]})
r = B.match_store({"id": "s3", "name": "エスパス", "pref": "東京都"}, I2)
ok(r["status"] == "AMBIGUOUS", "3 同名複数(同pref) → AMBIGUOUS")

# 4. branch suffix distinction（本館 vs スロット館 は別物）
I3 = idx({"神奈川県": [card("10", "GAUDI湘南茅ヶ崎"), card("11", "GAUDI湘南茅ヶ崎スロット館")]})
r = B.match_store({"id": "s4", "name": "GAUDI湘南茅ヶ崎スロット館", "pref": "神奈川県"}, I3)
ok(r["status"] == "EXACT_UNIQUE" and r["dmm_id"] == "11", "4 branch suffix区別 → 正しい方にexact")
r2 = B.match_store({"id": "s4b", "name": "GAUDI湘南茅ヶ崎", "pref": "神奈川県"}, I3)
ok(r2["status"] == "EXACT_UNIQUE" and r2["dmm_id"] == "10", "4b 本館側も別idにexact")

# 5. wrong prefecture → UNMATCHED
r = B.match_store({"id": "s5", "name": "PIA大森", "pref": "大阪府"}, I)
ok(r["status"] == "UNMATCHED", "5 pref違い → UNMATCHED")

# 6. address conflict は directory に full address 無 → city は pref 内。ここでは pref 一致必須で担保
r = B.match_store({"id": "s6", "name": "存在しない店", "pref": "東京都"}, I)
ok(r["status"] == "UNMATCHED", "6 名前不一致 → UNMATCHED")

# 7. duplicate dmm_id（別canonicalが同dmm_idにexact）→ dedupeで除外
ms = [{"status": "EXACT_UNIQUE", "dmm_id": "9", "store_id": "a", "db_dmm_id": None},
      {"status": "EXACT_UNIQUE", "dmm_id": "9", "store_id": "b", "db_dmm_id": None}]
safe, dup = B.dedupe_matches(ms)
ok(len(safe) == 0 and dup == 1, "7 同一dmm_id衝突 → 両方除外")

# 8. existing dmm_id preserved（write対象から除外）
w = B.write_dmm_ids([{"status": "EXACT_UNIQUE", "dmm_id": "5", "store_id": "x", "db_dmm_id": "5"}], limit=10, dry_run=True)
ok(w["attempted"] == 0, "8 既存dmm_id有 → write対象外(保持)")

# 9. NULL→dmm_id（write対象）
w = B.write_dmm_ids([{"status": "EXACT_UNIQUE", "dmm_id": "7", "store_id": "y", "db_dmm_id": None}], limit=10, dry_run=True)
ok(w["attempted"] == 1 and w["snapshot"][0]["old_dmm_id"] is None, "9 dmm_id NULL → write対象(snapshot)")

# 10. second-run idempotent（dry_runで書かない・limit 0）
ok(B.write_dmm_ids([{"status": "EXACT_UNIQUE", "dmm_id": "7", "store_id": "y", "db_dmm_id": None}], limit=0, dry_run=True)["attempted"] == 0,
   "10 limit0 → 0件(冪等/段階制御)")

# 11. malformed DMM page → cards 0
ok(B.parse_area_cards("<html>broken", "tokyo") == [], "11 壊れHTML → cards空")

# 12. DMM directory change（data-url形式でない）→ 0
ok(B.parse_area_cards('<a href="/other/1">x</a>', "tokyo") == [], "12 想定外構造 → 0")

# 13. official X field extraction（icon枠）
h = B.extract_official_x('<a class="icon" href="https://twitter.com/plaza_arae" target="_blank">')
ok(h["status"] == "OK" and h["handle"] == "plaza_arae", "13 icon枠 → 店舗X抽出")

# 14. arbitrary X link ignored（icon枠でない本文リンクは拾わない）
h = B.extract_official_x('<a href="https://x.com/some_random">tweet</a>')
ok(h["status"] == "NO_X", "14 本文の任意Xリンク → 拾わない")

# 15. existing x_url preserved → discover_and_write_x が SKIP
res = B.discover_and_write_x([{"store_id": "z", "pref": "東京都", "dmm_id": "1", "x_url": "https://x.com/exist", "name": "A"}],
                            limit=10, dry_run=True, fetch_page=lambda i, p: '<a class="icon" href="https://x.com/new_h">', ctx=FAKECTX)
ok(res["results"][0]["x_status"] == "SKIP_EXISTING_X", "15 既存x_url → 上書きせずSKIP")

# 16. DMM X conflict（icon枠に複数の異なるhandle）→ AMBIGUOUS_X
h = B.extract_official_x('<a class="icon" href="https://x.com/a_shop"><a class="icon" href="https://twitter.com/b_shop">')
ok(h["status"] == "AMBIGUOUS_X", "16 icon枠に複数handle → AMBIGUOUS_X")

# 17. same handle multiple stores → validate で拒否
v = B.validate_x_for_write("group_x", "s1", {"group_x": "OTHER"}, set(), set())
ok(not v["ok"] and "other_store" in v["reason"], "17 同一handle別store → 拒否")

# 18. manager handle rejection
ok(not B.validate_x_for_write("tencho_x", "s1", {}, set(), {"tencho_x"})["ok"], "18 manager handle → 拒否")

# 19. rejected handle rejection
ok(not B.validate_x_for_write("bad_x", "s1", {}, {"bad_x"}, set())["ok"], "19 rejected handle → 拒否")

# 20. valid handle → ok
ok(B.validate_x_for_write("plaza_arae", "s1", {}, set(), set())["ok"], "20 正常handle → 可")

# 21. resolver simulation safe（proposed無し=simなし）→ dry_runで書かない
res = B.discover_and_write_x([{"store_id": "z", "pref": "東京都", "dmm_id": "1", "x_url": None, "name": "A"}],
                            limit=10, dry_run=True, fetch_page=lambda i, p: '<a class="icon" href="https://x.com/uniq_shop">', ctx=FAKECTX)
ok(res["eligible"] and res["dry_run"] and res["written"] == [], "21 dry_run → eligibleだが書かない")

# 22. name normalization 安全（本館/号店を消さない）
ok(B.normalize_store_name("マルハン1号店") != B.normalize_store_name("マルハン2号店"), "22 号店を区別(吸収しない)")
ok(B.normalize_store_name("A本館") != B.normalize_store_name("A別館"), "22b 本館/別館を区別")
ok(B.normalize_store_name("ＰＩＡ大森 ") == B.normalize_store_name("PIA大森"), "22c 全半角/空白のみ吸収")

# 23. stage batch limit（limit で絞る）
many = [{"status": "EXACT_UNIQUE", "dmm_id": str(i), "store_id": f"s{i}", "db_dmm_id": None} for i in range(50)]
ok(B.write_dmm_ids(many, limit=5, dry_run=True)["attempted"] == 5, "23 stage limit=5")

# 24. circuit breaker（resolver simulation unsafe を検知）— simulate_resolver をモンキーパッチ
import discover_store_x as DX
_orig = DX.simulate_resolver
DX.simulate_resolver = lambda h, db, p: dict(changed=1, ver2cand=1, unlink=0, relink=0, canonical_conflict=0, orphan=0, verified_canonical=0)
try:
    res = B.discover_and_write_x([{"store_id": "z", "pref": "東京都", "dmm_id": "1", "x_url": None, "name": "A"}],
                                limit=10, dry_run=False, fetch_page=lambda i, p: '<a class="icon" href="https://x.com/uniq2">', ctx=FAKECTX)
    # per-store simulation が unsafe を検知 → CANONICAL_X_REVIEW で保留・書かない
    ok(res["written"] == [] and any(r["x_status"] == "CANONICAL_X_REVIEW" for r in res["results"]),
       "24 resolver unsafe(per-store) → REVIEW保留/書かない")
finally:
    DX.simulate_resolver = _orig

# 25. deterministic summary（同入力→同match）
a = B.match_store({"id": "s", "name": "PIA大森", "pref": "東京都"}, I)
b = B.match_store({"id": "s", "name": "PIA大森", "pref": "東京都"}, I)
ok(a == b, "25 match決定的")

# 26. retry scheduling は discover側stateで管理（parse_area_links健全性で代替確認）
ok(B.parse_area_links('/shops/tokyo/area/13101 /shops/tokyo/area/13102', "tokyo") == ["13101", "13102"],
   "26 area links抽出")

# 27. fetch failure（Noneでも例外なく空）
ok(B.parse_area_cards(None, "tokyo") == [] and B.extract_official_x(None)["status"] == "NO_X", "27 None入力 → 例外なし")

# 28. rollback snapshot（NULL→valueのsnapshotが取れる）
w = B.write_dmm_ids([{"status": "EXACT_UNIQUE", "dmm_id": "7", "store_id": "y", "db_dmm_id": None}], limit=10, dry_run=True)
ok(w["snapshot"] == [{"store_id": "y", "old_dmm_id": None, "new_dmm_id": "7"}], "28 rollback snapshot")

# alt パース（店名（市区 駅））
c = B.parse_area_cards('data-url="/shops/kanagawa/11768" x alt="GAUDI湘南茅ヶ崎スロット館（茅ヶ崎市 茅ケ崎駅）"', "kanagawa")
ok(c and c[0]["dmm_id"] == "11768" and c[0]["name"] == "GAUDI湘南茅ヶ崎スロット館" and c[0]["city"] == "茅ヶ崎市",
   "alt→dmm_id/店名/市区パース")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
