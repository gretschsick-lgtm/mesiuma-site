#!/usr/bin/env python3
"""NS-P2 verify_free_status ユニットテスト（純粋関数 + 注入fetcher・ネット/DB非依存）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import verify_free_status as V
import discover_free_performers as P1

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")

NOW = 1_000_000.0

# fake profile DB: handle -> {display_name, bio}
PROFILES = {
    "free_taro":   {"display_name": "フリー太郎 (@free_taro) on X", "bio": "現在フリーで活動中！パチスロ実践"},
    "agency_hana": {"display_name": "所属花子 (@agency_hana) on X", "bio": "○○プロダクション所属タレント"},
    "media_levin": {"display_name": "レビン (@media_levin) on X", "bio": "パチスロライター/パチマガスロマガ"},
    "dm_jiro":     {"display_name": "次郎 (@dm_jiro) on X", "bio": "お仕事のご依頼はDM開放中です"},
    "conflict_k":  {"display_name": "衝突子 (@conflict_k) on X", "bio": "現在フリーで活動中／○○プロダクション所属"},
    "sam_a":       {"display_name": "山田 (@sam_a) on X", "bio": "パチスロ好き"},
    "sam_b":       {"display_name": "山田 (@sam_b) on X", "bio": "パチスロ好き"},
    "nobio":       {"display_name": "ノー (@nobio) on X", "bio": None},
}
def fake_fetch(h):
    return PROFILES.get(h)

def cand(name, vc=2, us=2, pid=None):
    return dict(performer_id=pid or f"nm:{P1.normalize_name(name)}", display_name=name,
                normalized_name=P1.normalize_name(name), visit_count=vc, unique_store_count=us,
                prefectures_visited=["東京都"])

def verify(name, mentions, cm=None, agency=None, vc=2):
    return V.verify_one(cand(name, vc=vc), mentions, cm, agency, fake_fetch, NOW)

# 1. current self-declared free（bioに現在フリー明示）+来店 → FREE_CONFIRMED
r = verify("フリー太郎", ["free_taro"])
ok(r["free_status"] == P1.FREE_CONFIRMED and r["x_handle"] == "free_taro", "1 現在フリー明示+来店 → FREE_CONFIRMED")

# 2. stale self-declared free — verify_one は bio=現在状態(age=0)なので該当せず。
#    純粋分類側で古い根拠が FREE_LIKELY になることを確認（NS-P1 classify）
r2 = P1.classify_free_status({"name":"x"}, "独立してフリーになりました", "u", None, True, evidence_age_days=400)
ok(r2["free_status"] == P1.FREE_LIKELY, "2 古い自己申告free → FREE_LIKELY")

# 3. no agency found only（bioに所属もfreeも無い）→ FREE_CONFIRMEDにしない
r = verify("山田", ["sam_a"])
ok(r["free_status"] != P1.FREE_CONFIRMED and r["free_status"] == P1.PERFORMER_UNCONFIRMED,
   "3 所属もfreeも無い → FREE_CONFIRMED禁止")

# 4. DM inquiry only → FREE_CONFIRMED禁止
r = verify("次郎", ["dm_jiro"])
ok(r["free_status"] != P1.FREE_CONFIRMED, "4 DM開放だけ → FREE_CONFIRMED禁止")

# 5. current agency membership（bio所属明示）→ AFFILIATED
r = verify("所属花子", ["agency_hana"])
ok(r["free_status"] == P1.AFFILIATED, "5 bio所属明示 → AFFILIATED")

# 5b. 媒体所属(パチマガスロマガ) → AFFILIATED（媒体見逃さない）
r = verify("レビン", ["media_levin"])
ok(r["free_status"] == P1.AFFILIATED and r["affiliation"], "5b 媒体所属bio → AFFILIATED")

# 6. former agency + current free（cast_memberに旧agency無し・bioで現在free）→ FREE_CONFIRMED
r = verify("フリー太郎", ["free_taro"], cm={"name":"フリー太郎","x_url":"https://x.com/free_taro","agency_id":None})
ok(r["free_status"] == P1.FREE_CONFIRMED, "6 旧所属無+現在free明示 → FREE_CONFIRMED")

# 7. former free + current agency（DB現行agency有）→ AFFILIATED優先
r = verify("所属花子", ["agency_hana"], cm={"name":"所属花子","x_url":"https://x.com/agency_hana","agency_id":"a1"},
           agency={"name":"現行プロ","is_active":True,"hp_url":"https://a.jp"})
ok(r["free_status"] == P1.AFFILIATED, "7 現行agency有 → AFFILIATED")

# 8. conflicting evidence（bioに free明示 と 所属明示 両立）→ CONFLICT_REVIEW
r = verify("衝突子", ["conflict_k"])
ok(r["free_status"] == P1.CONFLICT_REVIEW, "8 free明示と所属明示の衝突 → CONFLICT_REVIEW")

# 9. same-name different person（複数handleが両方名前整合）→ IDENTITY_UNCONFIRMED
r = verify("山田", ["sam_a", "sam_b"])
ok(r["identity_status"] == V.IDENTITY_UNCONFIRMED, "9 同名で複数整合handle → IDENTITY_UNCONFIRMED")

# 10. handle-based identity（cast_members x_url 優先）
ident = V.resolve_identity("誰か", [], {"name":"誰か","x_url":"https://x.com/known_h"}, fake_fetch)
ok(ident["status"] == "RESOLVED" and ident["handle"] == "known_h", "10 cast_members x_url → identity解決")

# 11. search snippet only → FREE認定しない（snippetは扱わない=bio無し扱い→UNCONFIRMED）
r = verify("ノー", ["nobio"])
ok(r["free_status"] != P1.FREE_CONFIRMED, "11 bio取得不可(snippet相当) → FREE認定しない")

# 12. official profile evidence（bio=一次情報）が evidence_url 保持
r = verify("フリー太郎", ["free_taro"])
ok(r["free_evidence_url"] == "https://x.com/free_taro" and r["bio_excerpt"], "12 一次情報evidence_url/bio保持")

# 13. evidence freshness（bio=現在状態→FRESH扱いで FREE_CONFIRMED 可能）
ok(V.verify_one(cand("フリー太郎"), ["free_taro"], None, None, fake_fetch, NOW)["free_status"] == P1.FREE_CONFIRMED,
   "13 bio現在状態 → FRESH扱いでFREE可")

# 14. missing evidence date → bio現在状態はobserved_atで扱う（例外なく分類）
ok(V.verify_one(cand("山田"), ["sam_a"], None, None, fake_fetch, NOW)["observed_at"], "14 observed_at付与")

# 15. verification retry（status別 next_verify 間隔）
ok(P1.retry_days(P1.FREE_CONFIRMED) == 30 and P1.retry_days(P1.AFFILIATED) == 90, "15 retry間隔")

# 16. already fresh skip（run: 同now→次回未到来でskip）
big_events = [{"event":"来店","cast":"フリー太郎","store":"S店","pref":"東京都","date":"1/1",
               "x_url":"https://x.com/store_x","detail":"本日は @free_taro さん来店！"}]
st = {}
r1 = V.run(limit=50, report_path=None, state=st, now=NOW, events=big_events, cast_members=[], agencies=[], fetch_profile=fake_fetch, persist_state=False)
r2 = V.run(limit=50, report_path=None, state=st, now=NOW, events=big_events, cast_members=[], agencies=[], fetch_profile=fake_fetch, persist_state=False)
ok(r1["stats"]["candidates"] >= 1 and r2["stats"]["candidates"] == 0, "16 2回目(期限前) → skip(0件)")

# 17. source unavailable（fetch常にNone）→ IDENTITY_UNCONFIRMED（誤同定しない）
r = V.verify_one(cand("誰か"), ["somehandle"], None, None, lambda h: None, NOW)
ok(r["identity_status"] == V.IDENTITY_UNCONFIRMED, "17 profile取得不可 → IDENTITY_UNCONFIRMED")

# 18. malformed profile（og無し）→ 例外なく空
ok(V.parse_profile("<html>no meta</html>") == {"display_name": None, "bio": None}, "18 og無しHTML → 空")

# 19. duplicate evidence（同名+同mentionでも1人・run重複なし）
ev = [{"event":"来店","cast":"フリー太郎","store":"A","pref":"東京都","date":"1/1","x_url":"https://x.com/sx","detail":"@free_taro"},
      {"event":"来店","cast":"フリー太郎","store":"B","pref":"東京都","date":"1/2","x_url":"https://x.com/sx","detail":"@free_taro"}]
rr = V.run(limit=50, report_path=None, state={}, now=NOW, events=ev, cast_members=[], agencies=[], fetch_profile=fake_fetch)
ids=[x["performer_id"] for x in rr["results"]]
ok(len(ids)==len(set(ids)), "19 同一performerの重複結果なし")

# 20. second-run idempotency（state保持で2回目NO_OP）
ok(r2["stats"]["FREE_CONFIRMED"] == 0 and r2["stats"]["candidates"] == 0, "20 2回目 idempotent(NO_OP)")

# 追加: name_consistent の誤同定防止
ok(V.name_consistent("浜崎真緒", "浜崎真緒® (@Hamasaki_mao) on X"), "name_consistent: 一致")
ok(not V.name_consistent("田中", "全然違う名前 (@x) on X"), "name_consistent: 別名は不一致")
ok(V.extract_mention_handles("本日 @perf_a 来店 @store_x", "store_x") == ["perf_a"], "mention抽出: 店舗除外")

# 安全: 自動連絡/送信コードが存在しない
import inspect
src = inspect.getsource(V)
ok(not any(w in src for w in ["send_dm","follow(","post_reply","send_email","requests.post"]),
   "自動連絡/送信コードが存在しない")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
