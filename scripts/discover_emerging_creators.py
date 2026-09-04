#!/usr/bin/env python3
"""
NS-P3 — Autonomous Emerging Creator / Micro Performer Discovery
        (candidate-only / DB無変更 / 自動連絡なし / 新secret不要)

目的:
  すでに有名な大手ではなく、「まだ規模は小さいが現在パチンコ・パチスロ関連活動を継続している」
  クリエイター/配信者/演者候補を早期発見・評価・ランキングする。
  件数より正確性を最優先。フォロワー数ランキングにしない。

責務分離:
  NS-P1 = 来店実績 / performer candidate。NS-P2 = 本人identity + free/affiliation(一次bio)。
  NS-P3 = creator分類 / visibility / emerging score / 有名層分離 / 将来来店候補ランキング。
  NS-P1/P2 を再利用し、独自に free 判定を作らない・「所属不明=フリー」もしない。

探索源(新secret不要・実測で確認済):
  - events_public.json の店舗公式投稿 @mention + cast(=パチンコ関連の人物候補プール)
  - x.com og:title(表示名) / og:description(現在bio) … 未ログイン取得(NS-P2と同じ)
  - bio 内の YouTube/TikTok/Twitch/lit.link URL … platform identity linking(名前一致だけで統合しない)
  - NS-P1 visits / NS-P2 free status

制約(正直):
  follower/subscriber 数は og meta に無く、新 API/secret なしでは取得不可。
  よって visibility_tier は「来店活動 + bio signal」ベース(follower ベースではない)。
  厳密な規模 tier / YouTube-TikTok 数値が必要なら CREDENTIAL_REQUIRED(停止境界)。

安全:
  production DB WRITE なし / schema migration なし / 自動連絡コードなし / 私的連絡先は集めない。
"""
from __future__ import annotations
import os, re, sys, json, time, argparse
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
import discover_free_performers as P1
import verify_free_status as V

ROOT = Path(__file__).parent.parent
STATE_FILE = Path(__file__).parent / ".emerging_state.json"
REPORT_DEFAULT = ROOT / "public" / "emerging_creators_report.json"

# classification
EMERGING_CREATOR = "EMERGING_CREATOR"
MICRO_PERFORMER = "MICRO_PERFORMER"
STREAMER_ONLY = "STREAMER_ONLY"
CONTENT_CREATOR = "CONTENT_CREATOR"
ESTABLISHED_PERFORMER = "ESTABLISHED_PERFORMER"
AFFILIATED_CREATOR = "AFFILIATED_CREATOR"
NON_RELEVANT = "NON_RELEVANT"
IDENTITY_UNCONFIRMED = "IDENTITY_UNCONFIRMED"
CONFLICT_REVIEW = "CONFLICT_REVIEW"

# パチンコ/パチスロ関連(bio 判定)
PACHI_KW = re.compile(r'(パチスロ|パチンコ|スロット|スマスロ|スマパチ|実践|実戦|稼働|設定狙|'
                      r'ホール|遊技|ぱちすろ|ぱちんこ|養分|万枚|据え置き|朝イチ|全ツ)')
# 配信/動画活動(bio 判定)
STREAM_KW = re.compile(r'(配信|生配信|ライブ|youtube|ユーチュー|tiktok|ティックトック|twitch|'
                       r'動画|チャンネル|ch\b|生放送)', re.I)

# X og:title の wrapper 表記(識別に使わない付随記法。人物名の一部として残さない)
#   旧: "名前 (@handle) on X"       新(日本語): "Xユーザーの名前（@handle）さん"
_OGT_HANDLE_PAREN = re.compile(r'[（(]\s*@[^）)]*[）)]')
_OGT_JP_PREFIX = re.compile(r'^Xユーザーの')
_OGT_JP_SUFFIX = re.compile(r'さん\s*$')
_OGT_EN_SUFFIX = re.compile(r'\s*on X\s*$', re.I)
_OGT_SLASH_SUFFIX = re.compile(r'\s*/\s*$')

# ── platform scale evidence(follower/subscriber API は使わない・取得不可のため) ──────────
# bio 内の自己申告オーディエンス/再生数を、単一の固定文言ではなく
# 「数値+倍数単位(万/K/M)」+「近接する指標キーワード」の組み合わせで検出する(推測しない)。
# 単なる文中の数字(来店店舗数・設定・G数等)を誤って規模指標として扱わないよう、
# 倍数単位(万/K/M)を伴う数値のみを候補とし、必ず指標キーワードとの近接一致を要求する。
_METRIC_NUM = re.compile(r'(\d+(?:\.\d+)?)\s*(万|[Kk]|[Mm])(?![a-zA-Z万])')
_SUB_KW = re.compile(r'(登録者数?|チャンネル登録|フォロワー|followers?|subscribers?)', re.I)
_VIEW_KW = re.compile(r'(再生回数|再生|views?)', re.I)
_PERIOD_MONTHLY = re.compile(r'(月間|毎月|monthly)', re.I)
_PERIOD_LIFETIME = re.compile(r'(累計|総再生|total|lifetime)', re.I)
# 「◯万人」だけで登録者/フォロワーの明示語が無い場合、チャンネル/プラットフォーム名との
# 近接がある時のみ audience 推定として扱う(無関係な文中の「◯万人」を拾わないため)。
_PLATFORM_CTX = re.compile(
    r'(youtube|tiktok|twitch|チャンネル|ch\b|サブ垢|サブアカ|サブch|アカウント|twitter)', re.I)

SUBSCRIBER_ESTABLISHED_THRESHOLD = 100_000   # 登録者/フォロワー 10万人以上
VIEWS_ESTABLISHED_THRESHOLD = 5_000_000      # 再生数(月間/累計問わず) 500万回以上
# (2つの閾値は意図的に別軸: 再生数は登録者数より桁が大きく出やすいため同一基準にしない)

# 表示名内のブランド/チャンネル表記(例: "じゃんじゃん【スロパチステーション】")。
# 同一ブランドを共有する複数アカウントの束ね(brand co-occurrence signal)にのみ使う。
_BRAND_TOKEN = re.compile(r'【([^】]{1,30})】')
# 有名/確立層の手がかり(bio)
ESTABLISHED_KW = re.compile(r'(所属|専属|レギュラー|公式ライター|オフィシャルライター|'
                            r'アンバサダー|プロダクション)')

_YT = re.compile(r'(https?://(?:www\.)?youtube\.com/[^\s"\'<)]+|https?://youtu\.be/[^\s"\'<)]+)')
_TT = re.compile(r'(https?://(?:www\.)?tiktok\.com/@[^\s"\'<)]+)')
_TW = re.compile(r'(https?://(?:www\.)?twitch\.tv/[^\s"\'<)]+)')


# ══════════════════════════════════════════════════════════════════════════
# 純粋関数（テスト対象）
# ══════════════════════════════════════════════════════════════════════════

def detect_platforms(bio: str) -> dict:
    """bio 内の本人 platform URL を抽出（名前一致でなく本人記載の相互リンク＝強い identity）。"""
    b = bio or ""
    yt = _YT.search(b)
    tt = _TT.search(b)
    tw = _TW.search(b)
    return {"youtube": (yt.group(1) if yt else None),
            "tiktok": (tt.group(1) if tt else None),
            "twitch": (tw.group(1) if tw else None)}


def pachislot_relevance(bio: str, visit_count: int = 0) -> dict:
    """bio + 来店実績から関連度。プロフィールに一言あるだけで高評価にしない。"""
    b = bio or ""
    hits = len(set(PACHI_KW.findall(b)))
    score = 0.0
    score += min(hits, 4) * 15         # bio のパチ関連語(最大60)
    if visit_count > 0:
        score += min(visit_count, 5) * 8   # 実来店は強い関連(最大40)
    level = "HIGH" if score >= 45 else ("MEDIUM" if score >= 20 else "LOW")
    return {"score": round(score, 1), "level": level, "bio_hits": hits}


def parse_x_display_name(raw: str) -> str:
    """
    X og:title から wrapper 表記を除いた表示名のみを抽出する純粋関数。
    旧形式 "名前 (@handle) on X" / 日本語形式 "Xユーザーの名前（@handle）さん" の
    両方に対応。(@handle) 部分・"Xユーザーの" 接頭・"さん"/" on X" 接尾を除去するのみで、
    絵文字・記号・括弧など本人が選んだ表示名自体は一切変更しない(=推測を加えない)。
    """
    s = (raw or "").strip()
    s = _OGT_HANDLE_PAREN.sub('', s)
    s = _OGT_JP_PREFIX.sub('', s)
    s = _OGT_EN_SUFFIX.sub('', s)
    s = _OGT_JP_SUFFIX.sub('', s)
    s = _OGT_SLASH_SUFFIX.sub('', s)
    return s.strip()


def extract_brand_token(display_name_clean: str) -> Optional[str]:
    """
    og:title清浄後の表示名内【ブランド/チャンネル表記】を抽出する純粋関数。
    無ければ None(=推測しない)。同一ブランドを名乗る複数アカウントの束ね(brand co-occurrence
    established signal)にのみ使う。個人の思いつきタグではなく実際に複数人が共有しているかは
    呼び出し側(run() の同一バッチ内集計)で判定するため、ここでは抽出のみ行う。
    """
    if not display_name_clean:
        return None
    m = _BRAND_TOKEN.search(display_name_clean)
    return m.group(1) if m else None


def parse_platform_metrics(bio: str) -> list[dict]:
    """
    bio 内の自己申告 platform scale evidence を構造化抽出する純粋関数。
    follower/subscriber API は使わない(取得不可・新 credential 不要の制約)。
    単一の固定文言("チャンネル登録者数◯万人突破"等)だけに依存せず、
    「倍数単位(万/K/M)を伴う数値」+「近接する指標キーワード」の組み合わせのみを信頼する
    (文脈の無い数字は一切 metric として解釈しない=来店店舗数・設定・G数等と混同しない)。

    戻り値: [{"metric_type": "subscribers"|"views", "value": int,
             "period": "monthly"|"lifetime"|None, "source": str, "evidence_text": str}, ...]
    metric_type ごとに別 signal として保持し、登録者数と再生数を同一閾値で扱わない
    (呼び出し側 determine_visibility_tier がそれぞれ別の閾値で判定する)。
    """
    if not bio:
        return []
    out = []
    for m in _METRIC_NUM.finditer(bio):
        num_str, unit = m.group(1), m.group(2)
        try:
            base = float(num_str)
        except ValueError:
            continue
        mult = {"万": 10_000, "k": 1_000, "m": 1_000_000}[unit.lower()]
        value = int(base * mult)
        start, end = m.span()
        before, after = bio[max(0, start - 15):start], bio[end:end + 10]
        window = before + after
        evidence_text = bio[max(0, start - 15):end + 10].strip()
        if _SUB_KW.search(window):
            out.append({"metric_type": "subscribers", "value": value, "period": None,
                       "source": "bio_self_report", "evidence_text": evidence_text})
            continue
        if _VIEW_KW.search(window):
            period = ("monthly" if _PERIOD_MONTHLY.search(window)
                     else ("lifetime" if _PERIOD_LIFETIME.search(window) else None))
            out.append({"metric_type": "views", "value": value, "period": period,
                       "source": "bio_self_report", "evidence_text": evidence_text})
            continue
        # "◯万人"(数値直後が「人」)かつチャンネル/プラットフォーム名が近接する場合のみ
        # audience 推定として扱う(無関係な「◯万人」の誤爆を避けるため明示語を要求)。
        if after.startswith('人') and _PLATFORM_CTX.search(before):
            out.append({"metric_type": "subscribers", "value": value, "period": None,
                       "source": "bio_self_report_estimate", "evidence_text": evidence_text})
    return out


def has_large_audience_claim(bio: str) -> bool:
    """
    後方互換の要約 bool(登録者/フォロワー規模が確立閾値以上の自己申告があるか)。
    判定本体は parse_platform_metrics に一本化(表現依存の個別正規表現は持たない)。
    """
    return any(m["metric_type"] == "subscribers" and m["value"] >= SUBSCRIBER_ESTABLISHED_THRESHOLD
              for m in parse_platform_metrics(bio))


def is_creator_account(display_name: str, bio: str, from_x_profile: bool = False) -> bool:
    """
    店舗/会社/媒体/データ等でない人物アカウントか。

    入力ソースにより判定方法を分離する(source-type mismatch を避けるため):
      - from_x_profile=False (既定): events/cast など未解決の生テキストの可能性がある入力。
        NS-P1 の is_not_performer()(文断片・長すぎる名前を除外するヒューリスティック)を維持。
      - from_x_profile=True: identity 解決済み X アカウントの og:title 由来の正式な表示名。
        og:title は本人が選んだ実在の表示名(絵文字・記号・括弧・長さも本人の意匠)であり、
        「イベント文からのパース失敗」を想定した長さ/句読点ヒューリスティックは適用しない。
        店舗/会社/媒体の誤混入防止は、明示キーワード判定のみで維持する(推測を広げない)。
    """
    raw = display_name or ""
    if from_x_profile:
        name = parse_x_display_name(raw)
    else:
        # 旧: name_consistent と同じ簡易抽出(og:title 由来の可能性がある生テキストにも耐える)
        name = re.split(r'[（(]|@| on X| / ', raw)[0].strip()
        if P1.is_not_performer(name, ""):
            return False
    if re.search(r'(公式|店$|ホール|株式会社|データ|情報|newsβ?|編集部|まとめ|bot)', name):
        return False
    return True


def determine_visibility_tier(*, visit_count: int, unique_stores: int, stream_active: bool,
                              platform_metrics: Optional[list] = None,
                              brand_established: bool = False) -> str:
    """
    visibility(規模)のみを決定する pure function。affiliation は入力に一切含めない
    ── 所属していること自体は affiliation_status のみに反映し、規模の別軸(visibility_tier)
    には流用しない(「所属=有名」「所属不明=小規模」どちらの決めつけも禁止)。

    観測 evidence(来店規模・platform 自己申告規模・同一batch内 brand 伝播)がある場合のみ
    ESTABLISHED/MID 等を判定し、evidence が無ければ UNKNOWN(小規模と決めつけない)。
    登録者/フォロワー数と再生数は別 metric_type として扱い、同一閾値で混同しない
    (再生数は登録者数よりも桁が大きく出やすいため)。
    """
    metrics = platform_metrics or []
    sub_scale = any(m["metric_type"] == "subscribers" and m["value"] >= SUBSCRIBER_ESTABLISHED_THRESHOLD
                    for m in metrics)
    view_scale = any(m["metric_type"] == "views" and m["value"] >= VIEWS_ESTABLISHED_THRESHOLD
                     for m in metrics)
    if sub_scale or view_scale or brand_established or visit_count >= 20 or unique_stores >= 12:
        return "ESTABLISHED"
    if visit_count >= 6 or unique_stores >= 4:
        return "MID"
    if visit_count >= 1 or stream_active:
        return "EMERGING"
    # 来店/配信/大規模自己申告のいずれも観測できない = 規模が「小さい」のではなく「不明」。
    # 数値を取得できない対象を無理に MICRO(小規模確定)にしない(famous guard の抜け穴防止)。
    return "UNKNOWN"


def classify_creator(identity_ok: bool, display_name: str, bio: str,
                     free_status: str, affiliation: Optional[str],
                     visit_count: int, platforms: dict, from_x_profile: bool = False) -> dict:
    """
    creator を分類。戻り値 {classification, reason}
    from_x_profile: display_name が identity 解決済み X og:title 由来かどうか
    (is_creator_account の判定方法・famous guard の入力ソース分離に使う)。
    """
    if not identity_ok:
        # identity不明のため visibility も判定不能(推測しない)。「UNKNOWN」は正式な tier 値として明示する。
        return {"classification": IDENTITY_UNCONFIRMED, "reason": "identity_unresolved", "tier": "UNKNOWN"}
    if not is_creator_account(display_name, bio, from_x_profile=from_x_profile):
        return {"classification": NON_RELEVANT, "reason": "store_company_media_account", "tier": "UNKNOWN"}
    rel = pachislot_relevance(bio, visit_count)
    stream_active = bool(STREAM_KW.search(bio or "")) or any(platforms.values())
    if free_status == "CONFLICT_REVIEW":
        return {"classification": CONFLICT_REVIEW, "reason": "free_affiliation_conflict", "tier": "UNKNOWN"}
    # パチ関連が弱く来店も無く配信も無い → 非対象
    if rel["level"] == "LOW" and visit_count == 0 and not stream_active:
        return {"classification": NON_RELEVANT, "reason": "low_pachislot_relevance", "tier": "UNKNOWN"}
    # 有名/確立層の分離。affiliation は visibility 判定に一切使わない(別軸として分離)。
    # bio 本人記載の platform scale 自己申告(登録者/再生数)のみを famous guard の入力にする。
    platform_metrics = parse_platform_metrics(bio)
    vt = determine_visibility_tier(visit_count=visit_count, unique_stores=0,
                                   stream_active=stream_active, platform_metrics=platform_metrics)
    if affiliation:
        # AFFILIATED だから自動 ESTABLISHED にはしない(vt は affiliation と無関係に決定済み)。
        # creator_status=AFFILIATED_CREATOR / affiliation_status=AFFILIATED / visibility_tier=vt
        # のように、所属と規模は独立した多軸として出力する。
        return {"classification": AFFILIATED_CREATOR, "reason": "affiliation_known", "tier": vt,
               "relevance": rel, "platform_metrics": platform_metrics}
    if vt == "ESTABLISHED":
        if any(m["metric_type"] == "subscribers" and m["value"] >= SUBSCRIBER_ESTABLISHED_THRESHOLD
              for m in platform_metrics):
            reason = "self_reported_large_audience"
        elif any(m["metric_type"] == "views" and m["value"] >= VIEWS_ESTABLISHED_THRESHOLD
                for m in platform_metrics):
            reason = "self_reported_large_views"
        else:
            reason = "high_activity_scale"
        return {"classification": ESTABLISHED_PERFORMER, "reason": reason, "tier": vt,
               "relevance": rel, "platform_metrics": platform_metrics}
    # emerging 層の細分
    if visit_count >= 1:
        cls = MICRO_PERFORMER if visit_count <= 5 else EMERGING_CREATOR
        return {"classification": cls, "reason": "small_scale_with_visits", "tier": vt,
               "relevance": rel, "platform_metrics": platform_metrics}
    if stream_active:
        # 来店なし・配信あり → STREAMER_ONLY か CONTENT_CREATOR
        cls = STREAMER_ONLY if re.search(r'(配信|生配信|ライブ|twitch|生放送)', bio or "") else CONTENT_CREATOR
        return {"classification": cls, "reason": "active_no_visit", "tier": vt,
               "relevance": rel, "platform_metrics": platform_metrics}
    return {"classification": EMERGING_CREATOR, "reason": "pachi_relevant_active", "tier": vt,
           "relevance": rel, "platform_metrics": platform_metrics}


def famous_penalty(visit_count: int, unique_stores: int, affiliated: bool) -> float:
    """大規模/所属は Emerging ランキングで減点（有名層が1位になる構造を禁止）。"""
    p = 0.0
    if affiliated:
        p += 40
    if visit_count >= 20:
        p += 40
    elif visit_count >= 10:
        p += 20
    if unique_stores >= 12:
        p += 20
    return p


def emerging_creator_score(rec: dict) -> float:
    """
    観測事実のみで算出。小〜中規模で現在活動が強い人物を上位に。
    有名層は famous_penalty で抑制。フォロワー数には依存しない(取得不可)。
    """
    cls = rec.get("classification")
    if cls in (NON_RELEVANT, IDENTITY_UNCONFIRMED, CONFLICT_REVIEW):
        return 0.0
    score = 0.0
    rel = rec.get("relevance") or {}
    score += rel.get("score", 0) * 0.8                      # パチ関連度
    score += min(rec.get("visit_count", 0), 8) * 6          # 実来店(上限)
    score += min(rec.get("unique_store_count", 0), 6) * 4   # 来店店舗多様性
    if rec.get("stream_active"):
        score += 20
    if rec.get("platforms_count", 0) > 0:
        score += 10 * min(rec["platforms_count"], 2)        # 複数platform活動
    fr = rec.get("activity_status")
    score += {"ACTIVE": 25, "RECENT": 10}.get(fr, 0)
    if rec.get("free_status") == "FREE_CONFIRMED":
        score += 20
    score -= famous_penalty(rec.get("visit_count", 0), rec.get("unique_store_count", 0),
                            bool(rec.get("affiliation")))
    return round(max(score, 0.0), 2)


RETRY_DAYS = {EMERGING_CREATOR: 7, MICRO_PERFORMER: 7, STREAMER_ONLY: 10, CONTENT_CREATOR: 14,
              ESTABLISHED_PERFORMER: 60, AFFILIATED_CREATOR: 45, NON_RELEVANT: 3650,
              IDENTITY_UNCONFIRMED: 21, CONFLICT_REVIEW: 3650, "_default": 30}


def retry_days(classification: str) -> int:
    return RETRY_DAYS.get(classification, RETRY_DAYS["_default"])


# ══════════════════════════════════════════════════════════════════════════
# orchestration
# ══════════════════════════════════════════════════════════════════════════

def build_candidate_pool(events: list) -> dict:
    """events から creator 候補プール(normalized_name → {display, mention_handles})。"""
    midx = V.build_mention_index(events)
    visits = P1.build_visits(events)
    pool = {}
    for pkey, vlist in visits.items():
        pool[pkey] = {"display": vlist[0]["display_name"], "mentions": midx.get(pkey, []),
                      "visit_count": len(vlist),
                      "unique_stores": len({P1.normalize_name(v["store"]) for v in vlist if v.get("store")}),
                      "prefs": sorted({v["pref"] for v in vlist if v.get("pref")})}
    # mention のみ(cast に出ないが店舗が言及)も候補化
    for pkey, hs in midx.items():
        if pkey not in pool:
            pool[pkey] = {"display": pkey, "mentions": hs, "visit_count": 0,
                          "unique_stores": 0, "prefs": []}
    return pool


def evaluate_one(pkey: str, info: dict, cast_member: Optional[dict], agency: Optional[dict],
                 fetch_profile: Callable, now: float) -> dict:
    display = info["display"]
    # identity: NS-P2 resolve_identity 再利用
    ident = V.resolve_identity(display, info["mentions"], cast_member, fetch_profile)
    handle = ident.get("handle")
    bio, prof_display = None, None
    if handle:
        prof = fetch_profile(handle) or {}
        bio, prof_display = prof.get("bio"), prof.get("display_name")
    # free/affiliation: NS-P2 分類再利用(bio を一次情報として)
    bio_affil = V.detect_affiliation_from_bio(bio or "")
    agency_eff = agency or ({"name": bio_affil, "is_active": True} if bio_affil else None)
    fs = P1.classify_free_status(cast_member or {"name": display}, bio,
                                 (f"https://x.com/{handle}" if handle else None),
                                 agency_eff, info["visit_count"] >= 1, evidence_age_days=0)
    platforms = detect_platforms(bio or "")
    stream_active = bool(STREAM_KW.search(bio or "")) or any(platforms.values())
    cls = classify_creator(bool(handle), prof_display or display, bio or "",
                           fs["free_status"], (agency_eff or {}).get("name"),
                           info["visit_count"], platforms,
                           from_x_profile=(prof_display is not None))
    rec = dict(
        creator_id=(f"x:{handle}" if handle else f"nm:{pkey}"),
        display_name=display, x_handle=handle,
        x_url=(f"https://x.com/{handle}" if handle else None),
        classification=cls["classification"], reason=cls["reason"],
        # 多軸表現: creator_status(=classification のエイリアス) / affiliation_status / visibility_tier
        # を分離して出力する(所属していない=MICRO、規模不明=MICRO、という決めつけを避けるため)。
        creator_status=cls["classification"],
        affiliation_status=("AFFILIATED" if (agency_eff or {}).get("name") else None),
        visibility_tier=cls.get("tier"), relevance=cls.get("relevance"),
        pachislot_relevance=(cls.get("relevance") or {}).get("level"),
        free_status=fs["free_status"], affiliation=(agency_eff or {}).get("name"),
        visit_count=info["visit_count"], unique_store_count=info["unique_stores"],
        prefectures_visited=info["prefs"],
        youtube=platforms["youtube"], tiktok=platforms["tiktok"], twitch=platforms["twitch"],
        platforms_count=sum(1 for v in platforms.values() if v),
        stream_active=stream_active,
        activity_status=("ACTIVE" if (info["visit_count"] >= 1 or handle) else "UNKNOWN"),
        bio_excerpt=(bio[:140] if bio else None),
        identity_status=("RESOLVED" if handle else IDENTITY_UNCONFIRMED),
        observed_at=P1._iso(now),
        # brand co-occurrence established signal 用(run() 側の同一バッチ集計でのみ使用)
        brand_token=(extract_brand_token(parse_x_display_name(prof_display)) if prof_display else None),
        # 構造化 platform scale evidence(登録者/再生数を別 metric として保持。閾値判定は
        # determine_visibility_tier が行う。ここでは observed evidence をそのまま保持するのみ)
        platform_scale_evidence=cls.get("platform_metrics") or [],
    )
    rec["emerging_score"] = emerging_creator_score(rec)
    rec["why_ranked"] = _why(rec)
    return rec


def _why(r: dict) -> str:
    parts = []
    if r.get("visit_count"):
        parts.append(f"来店{r['visit_count']}件/{r['unique_store_count']}店")
    if r.get("pachislot_relevance"):
        parts.append(f"パチ関連{r['pachislot_relevance']}")
    if r.get("platforms_count"):
        parts.append(f"platform{r['platforms_count']}")
    if r.get("free_status") == "FREE_CONFIRMED":
        parts.append("FREE_CONFIRMED")
    if r.get("affiliation"):
        parts.append(f"所属:{r['affiliation']}")
    parts.append(f"tier={r.get('visibility_tier')}")
    return " / ".join(parts) or "観測情報少"


def run(limit: int, report_path: Optional[str], state: Optional[dict] = None, now: Optional[float] = None,
        events: Optional[list] = None, cast_members: Optional[list] = None, agencies: Optional[list] = None,
        fetch_profile: Callable = None, persist_state: bool = False) -> dict:
    now = now if now is not None else time.time()
    state = state if state is not None else {}
    events = events if events is not None else P1.load_events()
    cast_members = cast_members if cast_members is not None else P1.sb_get_all(
        "cast_members?select=id,name,normalized_name,x_url,agency_id,is_active")
    agencies = agencies if agencies is not None else P1.sb_get_all("agencies?select=id,name,hp_url,is_active")
    fetch_profile = fetch_profile or V.fetch_profile_live

    cast_by_norm = {}
    for c in cast_members:
        k = c.get("normalized_name") or P1.normalize_name(c.get("name", ""))
        if k and k not in cast_by_norm:
            cast_by_norm[k] = c
    ag_by_id = {a["id"]: a for a in agencies}
    pool = build_candidate_pool(events)

    def due(k):
        r = state.get(k)
        return (not r) or (r.get("next_check_at_ts") is None) or (now >= r["next_check_at_ts"])
    keys = [k for k in pool if due(k)]
    # 未確認優先 → 来店多い順(活動シグナル)で公平巡回
    keys.sort(key=lambda k: (state.get(k, {}).get("last_checked_at_ts", 0), -pool[k]["visit_count"]))
    if limit and limit > 0:
        keys = keys[:limit]

    stats = {k: 0 for k in [EMERGING_CREATOR, MICRO_PERFORMER, STREAMER_ONLY, CONTENT_CREATOR,
             ESTABLISHED_PERFORMER, AFFILIATED_CREATOR, NON_RELEVANT, IDENTITY_UNCONFIRMED, CONFLICT_REVIEW]}
    stats.update(scanned=len(keys), new_candidates=0)
    circuit = {"tripped": False, "reason": None}
    results, seen_ids = [], set()

    for k in keys:
        cm = cast_by_norm.get(k)
        ag = ag_by_id.get((cm or {}).get("agency_id")) if cm else None
        rec = evaluate_one(k, pool[k], cm, ag, fetch_profile, now)
        if rec["creator_id"] in seen_ids:   # dedupe(同一handle)
            continue
        seen_ids.add(rec["creator_id"])
        results.append(rec)
        stats[rec["classification"]] = stats.get(rec["classification"], 0) + 1
        if k not in state:
            stats["new_candidates"] += 1
        state[k] = dict(creator_id=rec["creator_id"], x_handle=rec["x_handle"],
                        classification=rec["classification"], visibility_tier=rec["visibility_tier"],
                        emerging_score=rec["emerging_score"], free_status=rec["free_status"],
                        activity_status=rec["activity_status"], last_result=rec["reason"],
                        last_checked_at=P1._iso(now), last_checked_at_ts=now,
                        next_check_at=P1._iso(now + retry_days(rec["classification"]) * 86400),
                        next_check_at_ts=now + retry_days(rec["classification"]) * 86400)

    # circuit breaker: 同一handle大量 / established 大量誤判定
    import collections
    hc = collections.Counter(r["x_handle"] for r in results if r.get("x_handle"))
    if hc and max(hc.values()) >= max(3, len(results) // 2 or 3):
        circuit["tripped"] = True
        circuit["reason"] = f"handle_collision({hc.most_common(1)})"

    # brand co-occurrence established signal(名前のhardcodeではなく、同一batch内で観測された
    # 強いevidenceの伝播): 同じ【ブランド】表記(exact normalized token)を名乗るアカウント群の
    # うち、いずれか1件でも自己完結した established evidence(大量来店/大量店舗/bio自己申告
    # subscribers/views の閾値超え)を持つ場合、その【ブランド】を「今回の scan で確認できた
    # 大規模媒体」とみなし、同ブランドの他アカウントも visibility_tier=ESTABLISHED とする
    # (classification/creator_status は変更しない=affiliation/established/creator種別は別軸)。
    #
    # 過剰伝播防止:
    #   - exact normalized token(strip 済み)一致のみ。部分一致・大小文字ゆるめ一致はしない。
    #   - identity 解決済み(brand_token は og:title 由来のため resolved person のみが持つ)。
    #   - store/company/media(NON_RELEVANT) / identity不明 / conflict は
    #     伝播元(evidence source)にも伝播先にも一切含めない。
    _RESOLVED_CREATOR_CLS = (EMERGING_CREATOR, MICRO_PERFORMER, STREAMER_ONLY, CONTENT_CREATOR,
                             ESTABLISHED_PERFORMER, AFFILIATED_CREATOR)
    def _direct_established(r: dict) -> bool:
        metrics = r.get("platform_scale_evidence") or []
        metric_scale = any(
            (m["metric_type"] == "subscribers" and m["value"] >= SUBSCRIBER_ESTABLISHED_THRESHOLD) or
            (m["metric_type"] == "views" and m["value"] >= VIEWS_ESTABLISHED_THRESHOLD)
            for m in metrics)
        return (r.get("visit_count", 0) >= 20 or r.get("unique_store_count", 0) >= 12 or metric_scale)
    brand_groups = collections.defaultdict(list)
    for r in results:
        token = (r.get("brand_token") or "").strip()
        if token and r["classification"] in _RESOLVED_CREATOR_CLS:
            brand_groups[token].append(r)
    known_large_brands = {tok for tok, members in brand_groups.items()
                          if any(_direct_established(m) for m in members)}
    for r in results:
        token = (r.get("brand_token") or "").strip()
        if (token and token in known_large_brands and r["classification"] in _RESOLVED_CREATOR_CLS
                and r["visibility_tier"] != "ESTABLISHED"):
            r["visibility_tier"] = "ESTABLISHED"
            r["why_ranked"] = r["why_ranked"] + f" / known_large_media_brand({token})"

    def rank(pred):
        return sorted([r for r in results if pred(r)], key=lambda r: r["emerging_score"], reverse=True)
    # visibility_tier=ESTABLISHED は「あまり有名でない候補」ランキングから除外する
    # (creator_status が MICRO/EMERGING でも、brand 伝播等で ESTABLISHED と判明した場合は含めない)
    _not_established = lambda r: r["visibility_tier"] != "ESTABLISHED"
    top_emerging = rank(lambda r: r["classification"] in (EMERGING_CREATOR, MICRO_PERFORMER, STREAMER_ONLY, CONTENT_CREATOR)
                        and _not_established(r))
    top_free = rank(lambda r: r["free_status"] == "FREE_CONFIRMED" and
                    r["classification"] in (EMERGING_CREATOR, MICRO_PERFORMER, STREAMER_ONLY, CONTENT_CREATOR)
                    and _not_established(r))
    visit_ready = rank(lambda r: r["visit_count"] >= 1 and r["identity_status"] == "RESOLVED" and
                       r["pachislot_relevance"] in ("HIGH", "MEDIUM") and
                       r["classification"] not in (NON_RELEVANT, ESTABLISHED_PERFORMER) and
                       _not_established(r))

    if persist_state and not circuit["tripped"]:
        P1.save_state(state, STATE_FILE)

    tier_stats = collections.Counter(r["visibility_tier"] for r in results)

    def slim(rs):
        return [{k: r.get(k) for k in ("creator_id", "display_name", "x_handle", "youtube", "tiktok",
                "classification", "creator_status", "affiliation_status", "visibility_tier",
                "pachislot_relevance", "visit_count",
                "unique_store_count", "prefectures_visited", "free_status", "affiliation",
                "platform_scale_evidence", "brand_token",
                "emerging_score", "why_ranked")} for r in rs[:30]]
    result = dict(mode="CANDIDATE_ONLY", db_writes=0, external_messages=0, secret_additions=0,
                  stats=stats, tier_stats=dict(tier_stats), circuit=circuit,
                  top_emerging=slim(top_emerging), top_free_emerging=slim(top_free),
                  visit_ready=slim(visit_ready), results=results)
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(result, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result


def _summary(res: dict) -> str:
    s = res["stats"]
    return (f"mode={res['mode']} db_writes={res['db_writes']} ext_msgs={res['external_messages']} "
            f"secret_add={res['secret_additions']} scanned={s['scanned']} "
            f"EMERGING={s[EMERGING_CREATOR]} MICRO={s[MICRO_PERFORMER]} STREAMER={s[STREAMER_ONLY]} "
            f"CONTENT={s[CONTENT_CREATOR]} ESTABLISHED={s[ESTABLISHED_PERFORMER]} "
            f"AFFILIATED={s[AFFILIATED_CREATOR]} NON_RELEVANT={s[NON_RELEVANT]} "
            f"IDENTITY_UNCONFIRMED={s[IDENTITY_UNCONFIRMED]} CONFLICT={s[CONFLICT_REVIEW]} "
            f"circuit={'TRIPPED:'+str(res['circuit']['reason']) if res['circuit']['tripped'] else 'ok'}")


def main():
    ap = argparse.ArgumentParser(description="NS-P3 emerging creator discovery (candidate-only)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--report", type=str, default=str(REPORT_DEFAULT))
    ap.add_argument("--no-state", action="store_true")
    args = ap.parse_args()
    state = {} if args.no_state else P1.load_state(STATE_FILE)
    res = run(limit=args.limit, report_path=(args.report or None), state=state,
              persist_state=(not args.no_state))
    print(_summary(res))
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## Emerging Creator Discovery (candidate-only)\n")
            f.write(f"- {_summary(res)}\n")
            for label, key in [("Top Emerging", "top_emerging"), ("Top Free Emerging", "top_free_emerging"),
                               ("Visit-ready", "visit_ready")]:
                f.write(f"### {label}\n")
                for r in res[key][:10]:
                    f.write(f"  - {r['display_name']} (@{r['x_handle']}) score={r['emerging_score']} "
                            f"[{r['classification']}/{r['visibility_tier']}] {r['why_ranked']}\n")
    if res["circuit"]["tripped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
