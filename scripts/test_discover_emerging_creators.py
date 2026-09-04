#!/usr/bin/env python3
"""NS-P3 discover_emerging_creators ユニットテスト（純粋関数+注入fetcher・ネット/DB非依存）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import discover_emerging_creators as E
import discover_free_performers as P1

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")

NOW = 1_000_000.0
PROF = {
    "streamer_a": {"display_name": "配信たろう (@streamer_a) on X", "bio": "パチスロ実践配信してます！YouTube→ https://youtube.com/@taro 毎日ライブ"},
    "micro_b":    {"display_name": "みくろ (@micro_b) on X", "bio": "パチンコ大好き 実践投稿中"},
    "famous_c":   {"display_name": "大物 (@famous_c) on X", "bio": "パチスロライター/パチマガスロマガ所属"},
    "store_d":    {"display_name": "マルハン◯◯店 (@store_d) on X", "bio": "本日の出玉速報"},
    "game_e":     {"display_name": "ゲーマー (@game_e) on X", "bio": "FPS大好き！たまにゲームします"},
    "free_f":     {"display_name": "ふりー (@free_f) on X", "bio": "パチスロ実践 現在フリーで活動中 YouTube→https://youtube.com/@f TikTok→https://tiktok.com/@f"},
    "tt_g":       {"display_name": "ティック (@tt_g) on X", "bio": "パチスロ動画 TikTok→ https://tiktok.com/@ttg"},
}
def fake(h): return PROF.get(h)

def ev(cast, store, pref="東京都", date="1/1", handle="sx", detail=""):
    return {"event": "来店", "cast": cast, "store": store, "pref": pref, "area": "関東",
            "date": date, "x_url": f"https://x.com/{handle}/status/1", "detail": detail}

# --- detect_platforms ---
p = E.detect_platforms("YouTube https://youtube.com/@taro TikTok https://tiktok.com/@taro")
ok(p["youtube"] and p["tiktok"], "1 platform link抽出(YouTube/TikTok)")
ok(E.detect_platforms("no links")["youtube"] is None, "2 リンクなし → None")

# --- pachislot_relevance ---
ok(E.pachislot_relevance("パチスロ実践 スロット 稼働", 3)["level"] == "HIGH", "3 パチ語+来店 → HIGH")
ok(E.pachislot_relevance("スロット好き", 0)["level"] == "LOW", "4 一言のみ → LOW")
ok(E.pachislot_relevance("FPS配信", 0)["level"] == "LOW", "5 無関係 → LOW")

# --- is_creator_account ---
ok(E.is_creator_account("配信たろう", "パチスロ実践"), "6 人物 → creator")
ok(not E.is_creator_account("マルハン◯◯店", "出玉"), "7 店舗 → creatorでない")
ok(not E.is_creator_account("パチンコ情報公式", "news"), "8 媒体/公式 → creatorでない")

# --- determine_visibility_tier (follower非依存・affiliationは入力に含めない=別軸) ---
ok(E.determine_visibility_tier(visit_count=0, unique_stores=0, stream_active=True, platform_metrics=[])
   == "EMERGING", "9 配信のみ小規模 → EMERGING")
ok(E.determine_visibility_tier(visit_count=2, unique_stores=1, stream_active=False, platform_metrics=[])
   == "EMERGING", "10 来店少 → EMERGING")
ok(E.determine_visibility_tier(visit_count=8, unique_stores=5, stream_active=False, platform_metrics=[])
   == "MID", "11 中規模来店 → MID")
ok(E.determine_visibility_tier(visit_count=25, unique_stores=15, stream_active=False, platform_metrics=[])
   == "ESTABLISHED", "12 大量来店 → ESTABLISHED")
# 13: 所属のみ(来店少)では自動 ESTABLISHED にしない(affiliationはvisibility判定の入力に存在しない
#     ─ determine_visibility_tier のシグネチャに affiliated 引数自体が無いことで構造的に保証)
ok(E.determine_visibility_tier(visit_count=1, unique_stores=1, stream_active=False, platform_metrics=[])
   == "EMERGING", "13 所属だけではESTABLISHEDにしない(affiliationはvisibility入力に無い)")
import inspect as _inspect
ok("affiliated" not in _inspect.signature(E.determine_visibility_tier).parameters,
   "13b determine_visibility_tierはaffiliationを引数に取らない(構造的分離の保証)")

# --- classify_creator ---
c = E.classify_creator(True, "配信たろう", "パチスロ実践配信 毎日ライブ", "PERFORMER_UNCONFIRMED", None, 0, {"youtube": "u", "tiktok": None, "twitch": None})
ok(c["classification"] == E.STREAMER_ONLY, "14 配信のみ活動 → STREAMER_ONLY")
c = E.classify_creator(True, "みくろ", "パチンコ実践", "PERFORMER_UNCONFIRMED", None, 3, {"youtube": None, "tiktok": None, "twitch": None})
ok(c["classification"] == E.MICRO_PERFORMER, "15 小規模来店 → MICRO_PERFORMER")
c = E.classify_creator(True, "大物", "パチスロライター", "AFFILIATED", "パチマガ", 5, {})
ok(c["classification"] == E.AFFILIATED_CREATOR, "16 所属 → AFFILIATED_CREATOR")
# Sentinel A: 所属あり・小規模signalのみ → affiliation_status=AFFILIATED だが
# visibility_tier は自動 ESTABLISHED に昇格しない(所属と規模は別軸)
ok(c["tier"] != "ESTABLISHED", "16b 所属のみ(小規模)ではvisibility_tierを自動ESTABLISHED化しない")
c = E.classify_creator(True, "有名", "パチスロ", "PERFORMER_UNCONFIRMED", None, 25, {})
ok(c["classification"] == E.ESTABLISHED_PERFORMER, "17 大量来店 → ESTABLISHED")
c = E.classify_creator(True, "マルハン店", "出玉速報", "PERFORMER_UNCONFIRMED", None, 0, {})
ok(c["classification"] == E.NON_RELEVANT, "18 店舗 → NON_RELEVANT")
c = E.classify_creator(True, "ゲーマー", "FPS大好き", "PERFORMER_UNCONFIRMED", None, 0, {})
ok(c["classification"] == E.NON_RELEVANT, "19 パチ関連弱+来店/配信なし → NON_RELEVANT")
c = E.classify_creator(False, "誰か", "", "PERFORMER_UNCONFIRMED", None, 0, {})
ok(c["classification"] == E.IDENTITY_UNCONFIRMED, "20 identity不明 → IDENTITY_UNCONFIRMED")
c = E.classify_creator(True, "衝突", "パチスロ", "CONFLICT_REVIEW", None, 2, {})
ok(c["classification"] == E.CONFLICT_REVIEW, "21 NS-P2 CONFLICT継承 → CONFLICT_REVIEW")

# --- famous_penalty / emerging_score ---
ok(E.famous_penalty(25, 15, True) > E.famous_penalty(2, 1, False), "22 大規模/所属ほど famous_penalty大")
small = {"classification": E.MICRO_PERFORMER, "relevance": {"score": 60}, "visit_count": 3, "unique_store_count": 2, "stream_active": True, "platforms_count": 1, "activity_status": "ACTIVE", "free_status": "PERFORMER_UNCONFIRMED"}
big = {"classification": E.EMERGING_CREATOR, "relevance": {"score": 60}, "visit_count": 30, "unique_store_count": 15, "stream_active": False, "platforms_count": 0, "activity_status": "ACTIVE", "affiliation": "大手"}
ok(E.emerging_creator_score(small) > E.emerging_creator_score(big), "23 小規模活発 > 有名層(famous penalty)")
ok(E.emerging_creator_score({"classification": E.NON_RELEVANT}) == 0.0, "24 NON_RELEVANT → score0")
ok(E.emerging_creator_score(small) == E.emerging_creator_score(dict(small)), "25 score決定的")

# --- FREE reuse / free emerging ---
r = E.evaluate_one("ふりー", {"display": "ふりー", "mentions": ["free_f"], "visit_count": 2, "unique_stores": 2, "prefs": ["東京都"]}, None, None, fake, NOW)
ok(r["free_status"] == "FREE_CONFIRMED", "26 NS-P2 free再利用: bio現在フリー → FREE_CONFIRMED")
ok(r["classification"] in (E.MICRO_PERFORMER, E.EMERGING_CREATOR), "27 free emerging候補に分類")
ok(r["youtube"] and r["tiktok"], "28 bioからYouTube/TikTok identity link")

# --- AFFILIATED reuse ---
r = E.evaluate_one("大物", {"display": "大物", "mentions": ["famous_c"], "visit_count": 1, "unique_stores": 1, "prefs": []}, None, None, fake, NOW)
ok(r["classification"] == E.AFFILIATED_CREATOR and r["affiliation"], "29 媒体所属 → AFFILIATED_CREATOR")

# --- retry ---
ok(E.retry_days(E.EMERGING_CREATOR) == 7 and E.retry_days(E.NON_RELEVANT) >= 3650, "30 retry間隔")

# --- parse_x_display_name(og:title wrapper 除去・純粋関数) ---
ok(E.parse_x_display_name("配信たろう (@streamer_a) on X") == "配信たろう", "36 旧形式wrapper除去")
ok(E.parse_x_display_name("Xユーザーのじゃんじゃん【スロパチステーション】（@janjan_sps）さん")
   == "じゃんじゃん【スロパチステーション】", "37 新形式(日本語)wrapper除去・絵文字/括弧は残す")
ok(E.parse_x_display_name("Xユーザーのあしなっくす✡️でちゃう！（@dechanax）さん")
   == "あしなっくす✡️でちゃう！", "38 新形式・記号/！は残す(句読点ヒューリスティック対象外)")
ok(E.parse_x_display_name("") == "", "39 空文字 → 例外なし")

# --- has_large_audience_claim(bio 本人記載の自己申告規模。follower APIは使わない) ---
ok(E.has_large_audience_claim("皆様のおかげでチャンネル登録者数100万人突破！"), "40 100万人突破 → True")
ok(not E.has_large_audience_claim("たろっぷTV㊗️12万人✨たろパチch㊗️7万人✨"),
   "41 閾値(10万)未満のchannel言及数値だけではESTABLISHED相当にしない → False")
ok(not E.has_large_audience_claim("フォロワー少ないですが頑張ります"), "42 数値なし → False")
ok(not E.has_large_audience_claim(None), "43 None → 例外なし")

# --- parse_platform_metrics: 表現非依存の構造化 platform scale evidence parser ---
# Sentinel B: "YouTube登録者12万人" → subscribers metric として正しくparse
mB = E.parse_platform_metrics("YouTube登録者12万人です。よろしくお願いします")
ok(any(m["metric_type"] == "subscribers" and m["value"] == 120_000 for m in mB),
   "59b 登録者+数値+万人を正しくsubscribers metricとしてparse")
# Sentinel C: "YouTube 12万人 / サブch 7万人" → 2つのmetricを安全にparse(単なる文中数字として無視しない)
mC = E.parse_platform_metrics("YouTube 12万人 / サブch 7万人 やってます")
ok(len(mC) == 2 and {m["value"] for m in mC} == {120_000, 70_000},
   "59c 複数channelのplatform数値を両方とも安全にparse(文中数字として無視しない)")
# Sentinel D: "YouTubeショート月間1000万再生" → views metric(monthly)として取得。subscriberと混同しない
mD = E.parse_platform_metrics("YouTubeショート月間1000万再生していただいてます")
ok(any(m["metric_type"] == "views" and m["value"] == 10_000_000 and m["period"] == "monthly" for m in mD),
   "59d 月間再生数をviews(monthly) metricとして取得・subscribersと別signalで保持")
ok(not any(m["metric_type"] == "subscribers" for m in mD),
   "59e 再生数をsubscribers扱いにしない(metric種別を混同しない)")
# Sentinel E: "来店予定 12店舗" → 12万人やsubscriberに誤parseしない(店舗数を規模指標にしない)
mE = E.parse_platform_metrics("来店予定 12店舗 詳細はDMで")
ok(mE == [], "59f 店舗数(倍数単位なし)をplatform metricに誤parseしない")
# Sentinel F: "設定6 / 1000G" → audience metricに誤parseしない(パチスロ用語の数字と混同しない)
mF = E.parse_platform_metrics("本日の実践 設定6 / 1000G でした")
ok(mF == [], "59g 設定/G数(倍数単位なし)をaudience metricに誤parseしない")
# 単なる出玉枚数など無関係な"数値+万"表記も、指標キーワード近接が無ければ subscribers/views にしない
mG = E.parse_platform_metrics("本日は5万枚の出玉でした！設定6挙動")
ok(not any(m["metric_type"] in ("subscribers", "views") for m in mG),
   "59h 指標キーワード近接の無い「万枚」(出玉枚数)はsubscribers/viewsに分類しない")

# --- is_creator_account: from_x_profile による source 分離 ---
# 解決済み X プロフィール由来の正当な人物名は「長い/絵文字/！」だけで除外しない
ok(E.is_creator_account("Xユーザーのじゃんじゃん【スロパチステーション】（@janjan_sps）さん", "",
                        from_x_profile=True), "44 解決済み実名(長い/括弧)を誤ってNON_RELEVANTにしない")
ok(E.is_creator_account("Xユーザーのあしなっくす✡️でちゃう！（@dechanax）さん", "",
                        from_x_profile=True), "45 解決済み実名(！を含む)を誤ってNON_RELEVANTにしない")
ok(E.is_creator_account("Xユーザーの現役DK🦍たろっぷ🦍（@taro5050taro）さん", "",
                        from_x_profile=True), "46 解決済み実名(絵文字複数)を誤ってNON_RELEVANTにしない")
# 一方、店舗/会社/媒体は from_x_profile=True でも明示キーワードで引き続き除外
ok(not E.is_creator_account("Xユーザーのプレイランドハッピー厚別店（@happy_atsubetsu）さん", "",
                            from_x_profile=True), "47 新形式でも店舗(店$)は除外を維持")
ok(not E.is_creator_account("Xユーザーのパチンコ情報局公式（@infoacc）さん", "",
                            from_x_profile=True), "48 新形式でも公式/情報アカウントは除外を維持")
ok(not E.is_creator_account("Xユーザーの◯◯ホール株式会社（@corpacc）さん", "",
                            from_x_profile=True), "49 新形式でもホール/株式会社は除外を維持")
# from_x_profile=False(既定)は従来通りの文断片ヒューリスティックを維持(後方互換)
ok(not E.is_creator_account("配信たろう、来店！パチンコの", ""), "50 未解決な生テキスト文断片は従来通り除外")

# --- famous guard: 大規模発信者は表示名バグ修正後も EMERGING に昇格しない(最重要回帰) ---
JANJAN_BIO = ("スロパチステーションのじゃんじゃんです！パチンコ実践動画をあげてます！"
              "パチンコの楽しさを広げるために奮闘中！皆様のおかげでチャンネル登録者数100万人突破！")
c_janjan = E.classify_creator(True, "Xユーザーのじゃんじゃん【スロパチステーション】（@janjan_sps）さん",
                              JANJAN_BIO, "PERFORMER_UNCONFIRMED", None, 8, {}, from_x_profile=True)
ok(c_janjan["classification"] == E.ESTABLISHED_PERFORMER,
   "51 100万人突破の実在発信者はEMERGINGでなくESTABLISHED_PERFORMERへ(famous guard)")
# 同じ活動規模(同じ配信ブランド)でも大規模を自称していなければ MICRO のまま(過剰昇格しない)
ISOMARU_BIO = "【いそまるの成り上がり回胴録】という実践動画に出演させていただいております。パチスロ実践"
c_isomaru = E.classify_creator(True, "Xユーザーのいそまる【スロパチステーション】（@isomaru_sps1）さん",
                               ISOMARU_BIO, "PERFORMER_UNCONFIRMED", None, 3, {}, from_x_profile=True)
ok(c_isomaru["classification"] == E.MICRO_PERFORMER,
   "52 同ブランドでも大規模自己申告が無ければMICRO_PERFORMERのまま(過剰昇格しない)")
# 店舗は from_x_profile=True でも NON_RELEVANT を維持(修正の副作用で店舗が通らないことの確認)
c_store = E.classify_creator(True, "Xユーザーのプレイランドハッピー厚別店（@happy_atsubetsu）さん",
                             "プレイランドハッピー厚別店の公式アカウント", "PERFORMER_UNCONFIRMED", None, 33, {},
                             from_x_profile=True)
ok(c_store["classification"] == E.NON_RELEVANT,
   "53 og:title修正後も店舗公式は来店件数が多くてもNON_RELEVANTを維持")

# --- brand co-occurrence established signal(いそまる事例の一般化・handle名のhardcode禁止) ---
# 架空のブランド名("カブ式団")を2アカウントで共有。片方だけが bio で大規模を自己申告し、
# もう片方(sentinel_peer)は自己申告が無い。それでも同一 run() バッチ内での brand 伝播により、
# sentinel_peer が visibility_tier=ESTABLISHED へ昇格し、Top Emerging から除外されることを検証する。
# 実装側に "sentinel_peer" や特定ハンドルへの分岐は存在しない(一般化された brand token 集計のみ)。
BRAND_PROF = {
    "sentinel_lead": {"display_name": "Xユーザーのりーだー【カブ式団】（@sentinel_lead）さん",
                       "bio": "カブ式団のりーだーです。パチスロ実践動画配信中。チャンネル登録者数50万人突破！"},
    "sentinel_peer": {"display_name": "Xユーザーのぴあ【カブ式団】（@sentinel_peer）さん",
                       "bio": "カブ式団のぴあです。パチスロ実践投稿してます。よろしくお願いします。"},
}
def fake_brand(h): return BRAND_PROF.get(h)
brand_events = [ev("りーださん", "A店", handle="bstore1", detail="@sentinel_lead 来店"),
                ev("ぴあさん", "B店", handle="bstore2", detail="@sentinel_peer 来店")]
r_brand = E.run(limit=50, report_path=None, state={}, now=NOW, events=brand_events,
                cast_members=[], agencies=[], fetch_profile=fake_brand)
rb = {r["x_handle"]: r for r in r_brand["results"]}
ok(rb["sentinel_lead"]["visibility_tier"] == "ESTABLISHED",
   "54 brand内で自己申告した本人はESTABLISHED(直接evidence)")
ok(rb["sentinel_peer"]["visibility_tier"] == "ESTABLISHED",
   "55 自己申告の無い同ブランドpeerもESTABLISHEDへ伝播(一般化signal・handle hardcodeなし)")
ok(rb["sentinel_peer"]["classification"] in (E.MICRO_PERFORMER, E.EMERGING_CREATOR),
   "56 creator_status自体は変更しない(established/creator種別は別軸)")
top_emerging_handles = {x["x_handle"] for x in r_brand["top_emerging"]}
ok("sentinel_lead" not in top_emerging_handles and "sentinel_peer" not in top_emerging_handles,
   "57 visibility_tier=ESTABLISHEDはbrand伝播分も含めTop Emergingランキングから除外")
# ブランドが無関係(異なる【】表記)なら伝播しないことも確認(誤爆しない)
UNRELATED_PROF = {
    "sentinel_lead2": {"display_name": "Xユーザーのりーだー２【別ブランド】（@sentinel_lead2）さん",
                        "bio": "別ブランドの人です。チャンネル登録者数50万人突破！"},
    "sentinel_unrelated": {"display_name": "Xユーザーのむかんけい【無関係団】（@sentinel_unrelated）さん",
                           "bio": "無関係団のむかんけいです。パチスロ実践投稿してます。"},
}
def fake_unrelated(h): return UNRELATED_PROF.get(h)
unrelated_events = [ev("りーだー２さん", "A店", handle="ustore1", detail="@sentinel_lead2 来店"),
                    ev("むかんけいさん", "B店", handle="ustore2", detail="@sentinel_unrelated 来店")]
r_unrel = E.run(limit=50, report_path=None, state={}, now=NOW, events=unrelated_events,
                cast_members=[], agencies=[], fetch_profile=fake_unrelated)
ru = {r["x_handle"]: r for r in r_unrel["results"]}
ok(ru["sentinel_unrelated"]["visibility_tier"] != "ESTABLISHED",
   "58 異なるブランド表記には伝播しない(誤爆しない)")

# --- run: pilot(注入fetch) / dedupe / idempotency ---
events = [ev("配信たろうさん", "S店", handle="store1", detail="@streamer_a 来店"),
          ev("みくろさん", "T店", handle="store2", detail="@micro_b"),
          ev("大物さん", "U店", handle="store3", detail="@famous_c"),
          ev("マルハン◯◯店", "マルハン◯◯店", handle="store_d"),
          ev("ゲーマーさん", "V店", handle="store4", detail="@game_e")]
st = {}
r1 = E.run(limit=50, report_path=None, state=st, now=NOW, events=events, cast_members=[], agencies=[], fetch_profile=fake)
ok(r1["mode"] == "CANDIDATE_ONLY" and r1["db_writes"] == 0 and r1["external_messages"] == 0, "31 candidate-only/DB0/連絡0")
ids = [x["creator_id"] for x in r1["results"]]
ok(len(ids) == len(set(ids)), "32 creator重複なし(dedupe)")
r2 = E.run(limit=50, report_path=None, state=st, now=NOW, events=events, cast_members=[], agencies=[], fetch_profile=fake)
ok(r2["stats"]["scanned"] == 0, "33 2回目(期限前) → 0件(冪等)")
ok([x["creator_id"] for x in r1["top_emerging"]] == [x["creator_id"] for x in E.run(limit=50, report_path=None, state={}, now=NOW, events=events, cast_members=[], agencies=[], fetch_profile=fake)["top_emerging"]],
   "34 ranking決定的")

# --- malformed URL / no outreach ---
ok(P1.handle_of("bad") == "" and E.detect_platforms(None)["tiktok"] is None, "35 malformed/None → 例外なし")
import inspect
src = inspect.getsource(E)
ok(not any(w in src for w in ["send_dm", "follow(", "post_reply", "send_email", "requests.post"]),
   "自動連絡/送信コードが存在しない")
# private contact collection absent (email/phone を収集フィールドに持たない)
ok("phone" not in src and "私用" not in src, "私的連絡先収集フィールドが存在しない")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
