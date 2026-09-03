#!/usr/bin/env python3
"""
NS-P1 — Autonomous Free Performer Discovery（candidate-only / DB無変更 / 自動連絡なし）

目的:
  ホール来店演者のうち、公開一次情報で「現在フリー」と高確度に確認できる人物を
  継続的に自律探索し、営業候補リストを生成・更新する。
  ※ 件数より正確性を最優先。根拠が弱い人物は FREE_CONFIRMED にせず UNCONFIRMED で残す。

責務分離(NS-9とは別体系):
  NS-9 = 店舗identity / 店舗公式X。NS-P1 = 演者identity / 来店実績 / free status / 所属 / 営業候補。
  NS-9 の verified store X は本pipelineの強い discovery/evidence source として再利用する。

既存資産の再利用:
  - public/events_public.json  … 来店イベント(store公式投稿由来) = 来店実績evidence
  - cast_members (DB)           … 演者identity(normalized_name / x_url / agency_id / source)
  - agencies (DB)              … 所属(affiliation)

安全原則(絶対):
  - 「所属が検索で見つからない = フリー」としない。
  - DM開放/募集中/事務所名なし 等の弱い情報だけで FREE_CONFIRMED にしない。
  - FREE_CONFIRMED は本人一次情報等の明示的根拠 + 実来店根拠の両方を必須とし evidence を保持。
  - 演者への自動連絡(DM/メール/フォロー/いいね/リプ/フォーム送信)を一切「実装しない」。
  - production DB への WRITE / schema migration はしない(candidate-only)。

このpilotは candidate-only:
  events + cast_members から分類し candidate report を出力。DB へ書かない。
  FREE_CONFIRMED は本人プロフィール等の一次evidenceを要するため、evidenceを与えない
  live pilot では発生しない(安全側)。FREE分類ロジックは実装・テスト済み。
"""
from __future__ import annotations
import os, re, sys, json, time, ssl, argparse, unicodedata, urllib.request, urllib.parse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parent.parent
EVENTS_JSON = ROOT / "public" / "events_public.json"
STATE_FILE = Path(__file__).parent / ".performer_state.json"
REPORT_DEFAULT = ROOT / "public" / "free_performer_candidates.json"

# ── free status 分類 ──────────────────────────────────────────────────────
FREE_CONFIRMED = "FREE_CONFIRMED"
FREE_LIKELY = "FREE_LIKELY"
PERFORMER_UNCONFIRMED = "PERFORMER_UNCONFIRMED"
AFFILIATED = "AFFILIATED"
NOT_PERFORMER = "NOT_PERFORMER"
CONFLICT_REVIEW = "CONFLICT_REVIEW"

# 本人一次情報で「現在フリー」を示す明示表現（弱い示唆は含めない）
FREE_EXPLICIT = re.compile(
    r'(フリー(?:ランス|で活動|になりました|転向|に転向|活動中)|'
    r'独立(?:しました|して活動)|退所(?:しました)?(?:.{0,10}(フリー|独立))|'
    r'現在.{0,4}フリー|所属なし|事務所を退所)'
)
# 弱い示唆（これだけでは FREE_CONFIRMED にしない）
FREE_WEAK = re.compile(r'(DM(?:開放|受付)|お仕事(?:募集|依頼)|来店(?:依頼|募集)|案件募集|ご依頼)')
# 現在所属を示す表現
AFFIL_EXPLICIT = re.compile(r'(所属|専属|レギュラー|オフィシャルライター|公式ライター)')

# 演者ではない(店舗/店長/会社/媒体/データ)アカウントの手がかり
NOT_PERFORMER_HINTS = re.compile(
    r'(店$|店\b|ホール|会館|グループ|公式|店長|スタッフ|データ|情報|チャンネル|'
    r'編集部|newsβ?|news|公式アカウント|パチンコ|パチスロ店)'
)


def normalize_name(name: str) -> str:
    """演者名正規化（register_cast.normalize_name 相当: NFKC+末尾敬称除去+空白除去+小文字）。"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name)
    s = re.sub(r'(さん|様|ちゃん|くん|氏)$', '', s.strip())
    s = re.sub(r'[\s　]+', '', s)
    return s.lower()


def handle_of(url: str) -> str:
    if not url:
        return ""
    m = re.search(r'(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,50})', url)
    return (m.group(1).lower() if m else "")


def is_not_performer(cast_name: str, store_name: str) -> bool:
    """cast が店舗/店長/会社/媒体/文断片＝演者でない、を判定（誤識別防止・厳しめ）。"""
    if not cast_name:
        return True
    if store_name and normalize_name(cast_name) == normalize_name(store_name):
        return True
    # 「店」を含む名は店舗/文断片の可能性が高い（例: "新宮店には、りんかさん"）
    if "店" in cast_name:
        return True
    # 文断片(句読点・助詞的表現)や長すぎる名は cast パース失敗 → 演者名として扱わない
    if re.search(r'[、。！!？?「」（）\(\)]', cast_name):
        return True
    if len(cast_name) > 15:
        return True
    return bool(NOT_PERFORMER_HINTS.search(cast_name))


def freshness(evidence_age_days: Optional[float]) -> str:
    if evidence_age_days is None:
        return "UNKNOWN"
    if evidence_age_days <= 90:
        return "FRESH"
    if evidence_age_days <= 180:
        return "ACCEPTABLE"
    return "STALE_RECHECK_REQUIRED"


def classify_free_status(
    identity: dict,
    profile_text: Optional[str],
    profile_evidence_url: Optional[str],
    agency: Optional[dict],
    visit_confirmed: bool,
    evidence_age_days: Optional[float] = None,
) -> dict:
    """
    厳格な free 判定。戻り値:
      {free_status, free_confidence, free_evidence_type, free_evidence_url,
       free_evidence_summary, reason}
    ルール:
      - 本人一次情報(profile_text)に現在フリーの明示 + 実来店 → FREE_CONFIRMED
      - 現在所属の明示(agency 現行 or profile に所属明示) → AFFILIATED
      - 本人フリー明示 と 現在所属 が両立 → CONFLICT_REVIEW
      - 弱い示唆のみ(DM開放/募集) → FREE にしない(UNCONFIRMED)
      - 来店確認のみで判断材料なし → PERFORMER_UNCONFIRMED
    """
    text = profile_text or ""
    has_free_explicit = bool(FREE_EXPLICIT.search(text))
    has_affil_explicit = bool(AFFIL_EXPLICIT.search(text))
    current_agency = bool(agency and agency.get("is_active", True) and agency.get("name")
                          and not str(agency.get("name", "")).startswith("テスト"))

    # 矛盾: 本人フリー明示 かつ 現在所属(事務所レコード or profile所属明示)
    if has_free_explicit and (current_agency or has_affil_explicit):
        return dict(free_status=CONFLICT_REVIEW, free_confidence="conflict",
                    free_evidence_type="primary_profile", free_evidence_url=profile_evidence_url,
                    free_evidence_summary="free明示と現在所属が両立", reason="affiliation_conflict")

    # AFFILIATED: 現在所属の明示
    if current_agency or has_affil_explicit:
        return dict(free_status=AFFILIATED, free_confidence="high",
                    free_evidence_type=("agency_record" if current_agency else "primary_profile"),
                    free_evidence_url=(agency.get("hp_url") if current_agency and agency else profile_evidence_url),
                    free_evidence_summary=(agency.get("name") if current_agency and agency else "profileに所属明示"),
                    reason="affiliation_confirmed")

    # FREE_CONFIRMED: 本人一次情報でフリー明示 + 実来店 + 鮮度が古すぎない
    if has_free_explicit and visit_confirmed:
        fr = freshness(evidence_age_days)
        if fr == "STALE_RECHECK_REQUIRED":
            return dict(free_status=FREE_LIKELY, free_confidence="stale",
                        free_evidence_type="primary_profile", free_evidence_url=profile_evidence_url,
                        free_evidence_summary="フリー明示だが根拠が古い(要再確認)", reason="free_evidence_stale")
        return dict(free_status=FREE_CONFIRMED, free_confidence="high",
                    free_evidence_type="primary_profile", free_evidence_url=profile_evidence_url,
                    free_evidence_summary="本人一次情報で現在フリー明示 + 実来店確認", reason="free_primary_confirmed")

    # 本人フリー明示だが来店未確認 → FREE_LIKELY
    if has_free_explicit and not visit_confirmed:
        return dict(free_status=FREE_LIKELY, free_confidence="medium",
                    free_evidence_type="primary_profile", free_evidence_url=profile_evidence_url,
                    free_evidence_summary="フリー明示だが来店実績未確認", reason="free_no_visit")

    # 弱い示唆のみ → FREE にしない
    if FREE_WEAK.search(text):
        return dict(free_status=PERFORMER_UNCONFIRMED, free_confidence="low",
                    free_evidence_type=None, free_evidence_url=None,
                    free_evidence_summary="DM開放/募集等の弱い示唆のみ(FREE根拠に不足)",
                    reason="weak_signal_only")

    # 来店は確認できるが free/所属いずれも不明
    return dict(free_status=PERFORMER_UNCONFIRMED, free_confidence="low",
                free_evidence_type=None, free_evidence_url=None,
                free_evidence_summary="来店は確認、所属/フリーは未確認",
                reason="insufficient_evidence")


def visit_key(performer_key: str, store: str, date: str) -> str:
    return f"{performer_key}|{normalize_name(store or '')}|{date or ''}"


def outreach_priority_score(p: dict) -> float:
    """
    純粋関数。営業候補の優先度。フォロワー数のみ・推測(ギャラ/空き)には依存しない。
    FREE_CONFIRMED を最重視し、来店の実績・多様性・鮮度・連絡手段の有無で加点。
    """
    if p.get("free_status") != FREE_CONFIRMED:
        return 0.0
    score = 100.0
    fr = p.get("free_freshness")
    score += {"FRESH": 40, "ACCEPTABLE": 15, "STALE_RECHECK_REQUIRED": 0, "UNKNOWN": 0}.get(fr, 0)
    score += min(p.get("recent_visit_count", 0), 10) * 4      # 直近来店
    score += min(p.get("unique_store_count", 0), 10) * 3      # 来店店舗の多様性
    score += min(p.get("visit_count", 0), 30) * 1
    if p.get("inquiry_method"):
        score += 15
    return round(score, 2)


# ── retry policy ──────────────────────────────────────────────────────────
RETRY_DAYS = {
    FREE_CONFIRMED: 30, FREE_LIKELY: 14, PERFORMER_UNCONFIRMED: 30,
    AFFILIATED: 90, CONFLICT_REVIEW: 3650, NOT_PERFORMER: 3650,
    "source_failure": 2, "_default": 30,
}


def retry_days(status: str) -> int:
    return RETRY_DAYS.get(status, RETRY_DAYS["_default"])


# ══════════════════════════════════════════════════════════════════════════
# I/O
# ══════════════════════════════════════════════════════════════════════════

def _ctx():
    return ssl._create_unverified_context()


def sb_get_all(path: str) -> list:
    base = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        return []
    out = []
    step = 1000
    off = 0
    while True:
        req = urllib.request.Request(base + "/rest/v1/" + path,
                                     headers={"apikey": key, "Authorization": "Bearer " + key,
                                              "Range": f"{off}-{off+step-1}"})
        try:
            with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
                chunk = json.load(r)
        except Exception:
            break
        out += chunk
        if len(chunk) < step:
            break
        off += step
    return out


def load_events() -> list:
    try:
        d = json.load(open(EVENTS_JSON, encoding="utf-8"))
        return d.get("events", d) if isinstance(d, dict) else d
    except Exception:
        return []


def load_state(path=STATE_FILE) -> dict:
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict, path=STATE_FILE) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(state, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ══════════════════════════════════════════════════════════════════════════
# 中核ロジック（テスト可能: 依存を引数で受ける）
# ══════════════════════════════════════════════════════════════════════════

def build_visits(events: list) -> dict:
    """来店イベントから演者→visit群を構築（cast≠store のみ・重複排除）。"""
    visits: dict[str, list] = {}
    seen: set[str] = set()
    for e in events:
        if e.get("event") != "来店":
            continue
        cast = (e.get("cast") or "").strip()
        store = (e.get("store") or "").strip()
        if not cast or is_not_performer(cast, store):
            continue
        pkey = normalize_name(cast)
        if not pkey:
            continue
        vk = visit_key(pkey, store, e.get("date", ""))
        if vk in seen:
            continue
        seen.add(vk)
        visits.setdefault(pkey, []).append(dict(
            store=store, pref=e.get("pref"), area=e.get("area"),
            visit_date=e.get("date"), evidence_url=e.get("x_url") or e.get("url"),
            evidence_type="store_official_post", evidence_account=handle_of(e.get("x_url") or e.get("url")),
            display_name=cast,
        ))
    return visits


def classify_performer(pkey: str, vlist: list, cast_member: Optional[dict],
                       agencies_by_id: dict, now: float,
                       profile_text: Optional[str] = None) -> dict:
    """1演者分の分類 + 集計。profile_text は live pilot では None（＝FREE_CONFIRMED は出ない）。"""
    display_name = vlist[0]["display_name"] if vlist else (cast_member or {}).get("name", pkey)
    x_url = (cast_member or {}).get("x_url")
    x_handle = handle_of(x_url)
    agency = agencies_by_id.get((cast_member or {}).get("agency_id")) if cast_member else None
    profile_evidence_url = (cast_member or {}).get("profile_url") or x_url
    visit_confirmed = len(vlist) >= 1

    # 集計（活動地域は自己申告でなく実来店を優先）
    prefs = [v["pref"] for v in vlist if v.get("pref")]
    areas = [v["area"] for v in vlist if v.get("area")]
    stores = {normalize_name(v["store"]) for v in vlist if v.get("store")}
    import collections
    region_counts = dict(collections.Counter(areas))

    fs = classify_free_status(cast_member or {"name": display_name}, profile_text,
                              profile_evidence_url, agency, visit_confirmed)

    rec = dict(
        performer_id=(f"cm:{cast_member['id']}" if cast_member else f"nm:{pkey}"),
        display_name=display_name,
        x_handle=x_handle or None,
        x_url=x_url,
        normalized_name=pkey,
        free_status=fs["free_status"],
        free_confidence=fs["free_confidence"],
        free_evidence_type=fs["free_evidence_type"],
        free_evidence_url=fs["free_evidence_url"],
        free_evidence_summary=fs["free_evidence_summary"],
        affiliation=(agency.get("name") if agency else None),
        affiliation_evidence_url=(agency.get("hp_url") if agency else None),
        inquiry_method=None,  # 一次情報未取得(自動連絡もしないため未使用)
        activity_regions=region_counts,
        prefectures_visited=sorted(set(prefs)),
        visit_count=len(vlist),
        unique_store_count=len(stores),
        recent_visit_count=len(vlist),  # 期間フィルタは date整形が必要なため暫定=総数
        latest_visit_date=(vlist[-1]["visit_date"] if vlist else None),
        identity_source=("cast_members" if cast_member else "event_name_only"),
        reason=fs["reason"],
        last_checked_at=_iso(now),
    )
    rec["outreach_priority_score"] = outreach_priority_score(rec)
    return rec


def run(limit: int, report_path: Optional[str], state: Optional[dict] = None,
        now: Optional[float] = None, events: Optional[list] = None,
        cast_members: Optional[list] = None, agencies: Optional[list] = None,
        persist_state: bool = False) -> dict:
    now = now if now is not None else _now()
    state = state if state is not None else {}
    events = events if events is not None else load_events()
    cast_members = cast_members if cast_members is not None else sb_get_all(
        "cast_members?select=id,name,normalized_name,x_url,agency_id,is_active,source,profile_url,ng_flag")
    agencies = agencies if agencies is not None else sb_get_all(
        "agencies?select=id,name,hp_url,is_active")

    agencies_by_id = {a["id"]: a for a in agencies}
    cast_by_norm = {}
    for c in cast_members:
        k = c.get("normalized_name") or normalize_name(c.get("name", ""))
        if k and k not in cast_by_norm:
            cast_by_norm[k] = c

    visits = build_visits(events)

    # retry: 期限が来ていない演者はスキップ（毎日全員再確認しない）
    pkeys = [k for k in visits.keys()
             if (state.get(k, {}).get("next_retry_at_ts") is None) or (now >= state[k]["next_retry_at_ts"])]
    # 未確認優先→最古 last_checked 順
    pkeys.sort(key=lambda k: state.get(k, {}).get("last_checked_at_ts", 0))
    if limit and limit > 0:
        pkeys = pkeys[:limit]

    stats = dict(store_posts_scanned=len(events), performer_candidates=0, visit_confirmed=0,
                 FREE_CONFIRMED=0, FREE_LIKELY=0, PERFORMER_UNCONFIRMED=0, AFFILIATED=0,
                 NOT_PERFORMER=0, CONFLICT_REVIEW=0, new_performers=0, new_visits=0,
                 duplicate_skipped=0, errors=0)
    circuit = {"tripped": False, "reason": None}
    candidates = []

    for pkey in pkeys:
        vlist = visits[pkey]
        cm = cast_by_norm.get(pkey)
        rec = classify_performer(pkey, vlist, cm, agencies_by_id, now)
        rec["visits"] = vlist
        candidates.append(rec)
        stats["performer_candidates"] += 1
        if rec["visit_count"] >= 1:
            stats["visit_confirmed"] += 1
        stats[rec["free_status"]] = stats.get(rec["free_status"], 0) + 1
        prev = state.get(pkey)
        if not prev:
            stats["new_performers"] += 1
        state[pkey] = dict(
            performer_id=rec["performer_id"], normalized_name=pkey,
            free_status=rec["free_status"], visit_status="confirmed" if rec["visit_count"] else "none",
            last_result=rec["reason"], last_checked_at=_iso(now), last_checked_at_ts=now,
            next_retry_at=_iso(now + retry_days(rec["free_status"]) * 86400),
            next_retry_at_ts=now + retry_days(rec["free_status"]) * 86400,
            visit_count=rec["visit_count"], unique_store_count=rec["unique_store_count"],
        )

    # circuit breaker: 同一 x_handle が異常に多数の人物へ（identity 崩壊の兆候）
    import collections
    hc = collections.Counter(c["x_handle"] for c in candidates if c.get("x_handle"))
    if hc and max(hc.values()) >= max(3, len(candidates) // 2 or 3):
        circuit["tripped"] = True
        circuit["reason"] = f"handle_identity_collision({hc.most_common(1)})"

    # 営業候補ランキング（FREE_CONFIRMED のみ・スコア降順）
    outreach = sorted([c for c in candidates if c["free_status"] == FREE_CONFIRMED],
                      key=lambda c: c["outreach_priority_score"], reverse=True)

    if persist_state and not circuit["tripped"]:
        save_state(state)

    result = dict(
        mode="CANDIDATE_ONLY",  # NS-P1 は常に candidate-only（DB write / 自動連絡なし）
        db_writes=0, external_messages=0,
        stats=stats, circuit=circuit,
        outreach_ranking=[{k: c[k] for k in ("performer_id", "display_name", "x_handle",
                          "free_status", "outreach_priority_score", "prefectures_visited",
                          "unique_store_count", "visit_count")} for c in outreach[:50]],
        candidates=candidates,
    )
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        # レポートには不要な個人情報を出さない（visits の evidence_url は公開投稿URLのみ）
        json.dump(result, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result


def _summary_line(res: dict) -> str:
    s = res["stats"]
    return (f"mode={res['mode']} db_writes={res['db_writes']} ext_msgs={res['external_messages']} "
            f"candidates={s['performer_candidates']} visit_confirmed={s['visit_confirmed']} "
            f"FREE_CONFIRMED={s['FREE_CONFIRMED']} FREE_LIKELY={s['FREE_LIKELY']} "
            f"UNCONFIRMED={s['PERFORMER_UNCONFIRMED']} AFFILIATED={s['AFFILIATED']} "
            f"NOT_PERFORMER={s['NOT_PERFORMER']} CONFLICT={s['CONFLICT_REVIEW']} "
            f"new={s['new_performers']} circuit={'TRIPPED:'+str(res['circuit']['reason']) if res['circuit']['tripped'] else 'ok'}")


def main():
    ap = argparse.ArgumentParser(description="NS-P1 free performer discovery (candidate-only)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--report", type=str, default=str(REPORT_DEFAULT))
    ap.add_argument("--no-state", action="store_true")
    args = ap.parse_args()

    state = {} if args.no_state else load_state()
    res = run(limit=args.limit, report_path=(args.report or None),
              state=state, persist_state=(not args.no_state))
    line = _summary_line(res)
    print(line)

    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## Free Performer Discovery (candidate-only)\n")
            f.write(f"- {line}\n")
            if res["outreach_ranking"]:
                f.write(f"- outreach candidates (FREE_CONFIRMED): {len(res['outreach_ranking'])}\n")
                for c in res["outreach_ranking"][:20]:
                    f.write(f"  - {c['display_name']} (@{c['x_handle']}) score={c['outreach_priority_score']} "
                            f"stores={c['unique_store_count']} pref={c['prefectures_visited']}\n")
    if res["circuit"]["tripped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
