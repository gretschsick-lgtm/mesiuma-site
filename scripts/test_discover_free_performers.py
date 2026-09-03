#!/usr/bin/env python3
"""NS-P1 discover_free_performers ユニットテスト（純粋関数/DB非依存）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import discover_free_performers as P

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")

NOW = 1_000_000.0
DAY = 86400

def cf(profile=None, agency=None, visit=True, age=None, identity=None):
    return P.classify_free_status(identity or {"name": "演者A"}, profile, "https://x.com/a/status/1",
                                  agency, visit, age)

# 1. 本人が現在フリー明記 → FREE_CONFIRMED候補
r = cf(profile="現在フリーで活動中です。来店依頼はDMまで")
ok(r["free_status"] == P.FREE_CONFIRMED, "1 本人フリー明記+来店 → FREE_CONFIRMED")

# 2. 事務所表記なしだけ → FREE_CONFIRMED禁止
r = cf(profile="パチスロ大好き！毎日実践中")
ok(r["free_status"] != P.FREE_CONFIRMED, "2 事務所表記なしだけ → FREE_CONFIRMEDにしない")

# 3. DM受付だけ → FREE_CONFIRMED禁止
r = cf(profile="お仕事のご依頼はDM開放しています")
ok(r["free_status"] == P.PERFORMER_UNCONFIRMED and r["free_status"] != P.FREE_CONFIRMED,
   "3 DM受付/募集だけ → FREE_CONFIRMED禁止(UNCONFIRMED)")

# 4. 現行所属確認 → AFFILIATED
r = cf(profile="遊技系タレント", agency={"name": "○○プロダクション", "is_active": True, "hp_url": "https://a.jp"})
ok(r["free_status"] == P.AFFILIATED, "4 現行事務所レコード → AFFILIATED")

# 5. 古い所属＋現在フリー明記 → 会社レコードが無ければ FREE_CONFIRMED（鮮度FRESH）
r = cf(profile="昨年○○を退所しました。現在はフリーで活動しています", agency=None, age=30)
ok(r["free_status"] == P.FREE_CONFIRMED, "5 退所→現在フリー明記(会社レコード無) → FREE_CONFIRMED")

# 6. 所属情報矛盾（本人フリー明記 かつ 現行事務所レコード）→ CONFLICT
r = cf(profile="現在フリーで活動中", agency={"name": "現行プロ", "is_active": True})
ok(r["free_status"] == P.CONFLICT_REVIEW, "6 free明示と現在所属の矛盾 → CONFLICT_REVIEW")

# 7. 店舗公式による来店告知（build_visits が拾う）
evs = [{"event": "来店", "cast": "たろうさん", "store": "マルハン◯◯店", "pref": "東京都", "area": "関東",
        "date": "12/01", "x_url": "https://x.com/maruhan_x/status/111"}]
v = P.build_visits(evs)
ok("たろう" in v and v["たろう"][0]["evidence_type"] == "store_official_post", "7 店舗公式来店告知 → visit化")

# 8. 本人による来店告知も visit（cast≠store であれば拾う）
evs2 = [{"event": "来店", "cast": "花子", "store": "花子", "pref": "東京都", "date": "1/1", "x_url": "u"}]
ok(P.build_visits(evs2) == {}, "8 cast==store(=本人でなく店/自己) は演者visitにしない")

# 9. 同名別handle → 別人（identity は cast_members.x_url 由来。handle違い=別レコード）
a = P.classify_performer("やまだ", [{"store": "A店", "pref": "東京都", "area": "関東", "visit_date": "1/1",
     "display_name": "やまだ", "evidence_url": "u", "evidence_account": ""}],
     {"id": 1, "name": "やまだ", "x_url": "https://x.com/yamada_1"}, {}, NOW)
b = P.classify_performer("やまだ", [{"store": "A店", "pref": "東京都", "area": "関東", "visit_date": "1/1",
     "display_name": "やまだ", "evidence_url": "u", "evidence_account": ""}],
     {"id": 2, "name": "やまだ", "x_url": "https://x.com/yamada_2"}, {}, NOW)
ok(a["x_handle"] != b["x_handle"] and a["performer_id"] != b["performer_id"], "9 同名別handle → 別人")

# 10. 同handle重複 → dedupe（build_visits は cast_by_norm で1人に集約）
ok(P.normalize_name("たろうさん") == P.normalize_name("たろう"), "10 敬称差の正規化一致(重複排除の基礎)")

# 11. 同一visit重複 → dedupe
evs3 = [{"event": "来店", "cast": "A", "store": "S店", "pref": "P", "date": "1/1", "x_url": "u"},
        {"event": "来店", "cast": "A", "store": "S店", "pref": "P", "date": "1/1", "x_url": "u2"}]
ok(len(P.build_visits(evs3)["a"]) == 1, "11 同一performer+store+date → visite重複排除")

# 12. manager/store account → NOT_PERFORMER
ok(P.is_not_performer("マルハン◯◯店", "マルハン◯◯店") and P.is_not_performer("◯◯店 店長", "X店"),
   "12 店舗/店長 → NOT_PERFORMER")

# 13. company/media account → NOT_PERFORMER
ok(P.is_not_performer("パチンコ情報チャンネル", "X") and P.is_not_performer("◯◯グループ公式", "X"),
   "13 会社/媒体 → NOT_PERFORMER")

# 13b. cast パース失敗の文断片 → NOT_PERFORMER（誤識別防止）
ok(P.is_not_performer("新宮店には、りんかさん", "S店") and P.is_not_performer("はコンコルド御前崎店さん", "X")
   and P.is_not_performer("すごく長い文章がそのままキャストに入ってしまった例です", "X"),
   "13b 文断片/店含み/長すぎ名 → NOT_PERFORMER")
ok(not P.is_not_performer("りんか", "S店"), "13c 正常な演者名は演者のまま")

# 14. stale free evidence → FREE_CONFIRMEDにしない(FREE_LIKELY)
r = cf(profile="フリーで活動しています", age=400)
ok(r["free_status"] == P.FREE_LIKELY and r["reason"] == "free_evidence_stale", "14 古いfree根拠 → FREE_LIKELY(再確認)")

# 15. retry scheduling
ok(P.retry_days(P.FREE_CONFIRMED) == 30 and P.retry_days(P.AFFILIATED) == 90
   and P.retry_days(P.CONFLICT_REVIEW) >= 3650, "15 retry間隔(status別)")

# 16. batch selection（limit で絞る & 期限前スキップ）
big = [{"event": "来店", "cast": f"P{i}さん", "store": f"S{i}店", "pref": "東京都", "date": "1/1",
        "x_url": f"https://x.com/s{i}/status/1"} for i in range(10)]
r = P.run(limit=3, report_path=None, state={}, now=NOW, events=big, cast_members=[], agencies=[])
ok(r["stats"]["performer_candidates"] == 3, "16 batch limit=3で3件")

# 17. second run idempotency（同 now → 全員 not due → 0件）
st = {}
P.run(limit=100, report_path=None, state=st, now=NOW, events=big, cast_members=[], agencies=[])
r2 = P.run(limit=100, report_path=None, state=st, now=NOW, events=big, cast_members=[], agencies=[])
ok(r2["stats"]["performer_candidates"] == 0, "17 2回目(期限前) → 0件(冪等)")

# 18. malformed X URL → handle空
ok(P.handle_of("not a url") == "" and P.handle_of("https://x.com/good_1/status/9") == "good_1",
   "18 malformed URL → handle安全処理")

# 19. source failure（events空）→ 例外なく0件
ok(P.run(limit=10, report_path=None, state={}, now=NOW, events=[], cast_members=[], agencies=[])["stats"]["performer_candidates"] == 0,
   "19 events空 → 例外なく0件")

# 20. rate-limit / DB取得失敗相当（cast_members空でも動作）
r = P.run(limit=5, report_path=None, state={}, now=NOW, events=big, cast_members=[], agencies=[])
ok(r["mode"] == "CANDIDATE_ONLY" and r["db_writes"] == 0, "20 cast_members空でもCANDIDATE_ONLY/db_writes0")

# 21. candidate report deterministic（同入力→同candidates順）
r1 = P.run(limit=5, report_path=None, state={}, now=NOW, events=big, cast_members=[], agencies=[])
r2 = P.run(limit=5, report_path=None, state={}, now=NOW, events=big, cast_members=[], agencies=[])
ok([c["performer_id"] for c in r1["candidates"]] == [c["performer_id"] for c in r2["candidates"]],
   "21 candidate report 決定的")

# 22. store identity unresolved → 無理にcanonical紐付けしない（store名のみ保持）
r = P.run(limit=1, report_path=None, state={}, now=NOW,
          events=[{"event": "来店", "cast": "Zさん", "store": "謎店", "pref": "P", "date": "1/1", "x_url": "https://x.com/z/status/1"}],
          cast_members=[], agencies=[])
ok(r["candidates"][0]["visits"][0]["store"] == "謎店" and "store_id" not in r["candidates"][0]["visits"][0],
   "22 store未解決 → canonical強制紐付けしない")

# 23. affiliation conflict blocks FREE_CONFIRMED
r = cf(profile="現在フリー", agency={"name": "現行", "is_active": True})
ok(r["free_status"] != P.FREE_CONFIRMED, "23 所属矛盾 → FREE_CONFIRMEDをブロック")

# 24. outdated free evidence triggers recheck（FREE_LIKELY + stale理由）
r = cf(profile="独立してフリーになりました", age=200)
ok(r["free_status"] == P.FREE_LIKELY, "24 古いfree根拠 → 再確認(FREE_LIKELY)")

# 25. already-known performer update without duplication（state更新・重複作成なし）
st = {}
P.run(limit=100, report_path=None, state=st, now=NOW, events=big, cast_members=[], agencies=[])
n1 = len(st)
P.run(limit=100, report_path=None, state=st, now=NOW + 100 * DAY, events=big, cast_members=[], agencies=[])
ok(len(st) == n1, "25 既知performer再訪 → state重複作成なし(更新のみ)")

# outreach score: FREE_CONFIRMED以外は0 / FREE_CONFIRMEDは加点
ok(P.outreach_priority_score({"free_status": P.PERFORMER_UNCONFIRMED}) == 0.0, "score: 非FREEは0")
ok(P.outreach_priority_score({"free_status": P.FREE_CONFIRMED, "free_freshness": "FRESH",
    "recent_visit_count": 5, "unique_store_count": 4, "visit_count": 8, "inquiry_method": "form"}) > 100,
   "score: FREE_CONFIRMEDは加点")

# 自動連絡コードが存在しないこと（安全確認: DM/フォロー等の送信関数が無い）
import inspect
src = inspect.getsource(P)
ok(not any(w in src for w in ["send_dm", "follow(", "post_reply", "send_email", "requests.post"]),
   "自動連絡/送信コードが存在しない")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
