#!/usr/bin/env python3
"""
NS-P2 — Autonomous Free Status Verification（candidate-only / DB無変更 / 自動連絡なし / 新secret不要）

目的:
  NS-P1 の PERFORMER_UNCONFIRMED を、公開一次情報から
  FREE_CONFIRMED / AFFILIATED / FREE_LIKELY / CONFLICT_REVIEW / (IDENTITY_UNCONFIRMED)
  へ安全に自動分類する。

一次情報の源（新 credential 不要・実測で確認済み）:
  1. 既存 events_public.json の店舗公式投稿 detail 中の @mention（演者handle・名前整合で裏付け）
  2. x.com プロフィールの og:title(表示名) / og:description(現在bio) ← 未ログインで初期HTMLに含まれる
  3. cast_members(DB) の x_url / agency_id
  4. agencies(DB) の現行所属

安全原則(NS-P1と共通・厳守):
  - 「所属が見つからない=フリー」禁止。DM開放/募集/連絡先だけでは FREE_CONFIRMED にしない。
  - FREE_CONFIRMED = 本人bio等に現在フリーの明示 + 実来店 + 鮮度OK（NS-P1 classify を再利用）。
  - 本人フリー明示 と 現在所属(bio/事務所)が衝突 → CONFLICT_REVIEW（自動FREE禁止）。
  - identity は表示名だけで確定しない。store投稿@mention + 名前整合 or cast_members で解決。
    曖昧なら IDENTITY_UNCONFIRMED として停止（誤同定しない）。
  - production DB WRITE / schema migration / 自動連絡 / paid API / secret追加 は一切しない。
"""
from __future__ import annotations
import os, re, sys, json, time, ssl, argparse, urllib.request
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
import discover_free_performers as P1  # 再利用: classify_free_status / normalize_name / handle_of / freshness / 定数

ROOT = Path(__file__).parent.parent
EVENTS_JSON = ROOT / "public" / "events_public.json"
STATE_FILE = Path(__file__).parent / ".verify_state.json"
REPORT_DEFAULT = ROOT / "public" / "free_verification_report.json"

IDENTITY_UNCONFIRMED = "IDENTITY_UNCONFIRMED"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_MENTION = re.compile(r'@([A-Za-z0-9_]{2,50})')
_OG_DESC = re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"')
_OG_TITLE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"')

# 媒体/事務所 所属を示すブランド名（bio に現在の所属を示す強い手がかり）
MEDIA_AFFIL = re.compile(
    r'(パチマガ|スロマガ|パチンコ必勝ガイド|必勝本|パチスロ必勝|DMMぱちタウン|ぱちタウン|'
    r'プロダクション|エンタテインメント|エンターテインメント|芸能|所属|専属|レギュラー|'
    r'公式ライター|オフィシャルライター|株式会社)'
)
# X mention として除外する非人物ハンドル
_SKIP = frozenset(["i", "intent", "share", "home", "search", "hashtag", "twitter", "x"])


# ── 純粋関数（テスト対象）─────────────────────────────────────────────────
def extract_mention_handles(text: str, store_handle: str) -> list[str]:
    """店舗投稿 text から、店舗自身を除く @mention handle を抽出（＝演者handle候補）。"""
    sh = (store_handle or "").lower()
    out, seen = [], set()
    for m in _MENTION.finditer(text or ""):
        h = m.group(1).lower()
        if h and h != sh and h not in _SKIP and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def name_consistent(cast_name: str, display_name: str) -> bool:
    """演者名と X 表示名(og:title)の整合。誤同定防止のため一方が他方を含む/十分重なる場合のみ真。"""
    a = P1.normalize_name(cast_name)
    # og:title は "名前 (@handle) on X" 形式が多い → 名前部を取り出す
    d_raw = re.split(r'[（(]|@| on X| / ', display_name or "")[0]
    b = P1.normalize_name(d_raw)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    # 2文字以上の共通接頭（日本語名の姓一致など）
    common = 0
    for x, y in zip(a, b):
        if x == y:
            common += 1
        else:
            break
    return common >= 2 and common >= min(len(a), len(b)) * 0.6


def parse_profile(html: str) -> dict:
    """x.com 初期HTMLから og:title(表示名) / og:description(bio) を抽出。"""
    if not html:
        return {}
    t = _OG_TITLE.search(html)
    d = _OG_DESC.search(html)
    return {"display_name": (t.group(1) if t else None),
            "bio": (d.group(1) if d else None)}


def detect_affiliation_from_bio(bio: str) -> Optional[str]:
    """bio から現在の媒体/事務所所属の手がかりを検出（無ければ None）。"""
    if not bio:
        return None
    m = MEDIA_AFFIL.search(bio)
    return m.group(1) if m else None


def resolve_identity(cast_name: str, mention_handles: list[str], cast_member: Optional[dict],
                     fetch_profile: Callable[[str], Optional[dict]]) -> dict:
    """
    演者の X handle を解決。戻り値 {status, handle, display_name, reason}
      - cast_members に x_url があれば最優先（既知identity）
      - 無ければ store投稿の @mention 候補を名前整合で検証
      - 一意に整合する候補が1つ → 解決。0/複数 → IDENTITY_UNCONFIRMED
    """
    if cast_member and cast_member.get("x_url"):
        h = P1.handle_of(cast_member["x_url"])
        if h:
            return {"status": "RESOLVED", "handle": h,
                    "display_name": cast_member.get("name"), "reason": "cast_members_x_url"}

    matched = []
    for h in mention_handles:
        prof = fetch_profile(h)
        if not prof:
            continue
        if name_consistent(cast_name, prof.get("display_name") or ""):
            matched.append((h, prof.get("display_name")))
    if len(matched) == 1:
        return {"status": "RESOLVED", "handle": matched[0][0],
                "display_name": matched[0][1], "reason": "mention_name_consistent"}
    if len(matched) > 1:
        return {"status": IDENTITY_UNCONFIRMED, "handle": None, "display_name": None,
                "reason": f"multiple_consistent_handles({len(matched)})"}
    return {"status": IDENTITY_UNCONFIRMED, "handle": None, "display_name": None,
            "reason": "no_name_consistent_handle"}


def verify_one(cand: dict, mention_handles: list[str], cast_member: Optional[dict],
               agency: Optional[dict], fetch_profile: Callable[[str], Optional[dict]],
               now: float) -> dict:
    """1演者の identity解決 → 一次情報取得 → free/affiliation 分類。"""
    cast_name = cand.get("display_name") or cand.get("normalized_name")
    visit_confirmed = cand.get("visit_count", 0) >= 1

    ident = resolve_identity(cast_name, mention_handles, cast_member, fetch_profile)
    if ident["status"] != "RESOLVED":
        return dict(performer_id=cand.get("performer_id"), display_name=cast_name,
                    x_handle=None, identity_status=ident["status"],
                    free_status=P1.PERFORMER_UNCONFIRMED, free_confidence="none",
                    free_evidence_type=None, free_evidence_url=None,
                    affiliation=None, affiliation_evidence_url=None,
                    reason=ident["reason"], observed_at=P1._iso(now))

    handle = ident["handle"]
    prof = fetch_profile(handle) or {}
    bio = prof.get("bio")
    profile_url = f"https://x.com/{handle}"

    # bio 由来の現在所属（媒体/事務所）→ agency 相当として渡す
    bio_affil = detect_affiliation_from_bio(bio or "")
    agency_eff = agency
    if not agency_eff and bio_affil:
        agency_eff = {"name": bio_affil, "is_active": True, "hp_url": profile_url}

    # 一次情報の鮮度: bio は「現在状態」を直接示すので observed_at=now（age=0）
    fs = P1.classify_free_status(cast_member or {"name": cast_name}, bio, profile_url,
                                 agency_eff, visit_confirmed, evidence_age_days=0)

    rec = dict(
        performer_id=cand.get("performer_id"), display_name=cast_name,
        x_handle=handle, x_url=profile_url, identity_status="RESOLVED",
        identity_reason=ident["reason"],
        free_status=fs["free_status"], free_confidence=fs["free_confidence"],
        free_evidence_type=fs["free_evidence_type"], free_evidence_url=fs["free_evidence_url"],
        free_evidence_summary=fs["free_evidence_summary"],
        bio_excerpt=(bio[:140] if bio else None),
        affiliation=(agency_eff.get("name") if agency_eff else None),
        affiliation_evidence_url=(agency_eff.get("hp_url") if agency_eff else None),
        reason=fs["reason"], observed_at=P1._iso(now),
        visit_count=cand.get("visit_count"), unique_store_count=cand.get("unique_store_count"),
        prefectures_visited=cand.get("prefectures_visited"),
    )
    return rec


# ── I/O ─────────────────────────────────────────────────────────────────
def fetch_profile_live(handle: str, timeout: int = 12) -> Optional[dict]:
    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(f"https://x.com/{handle}", headers={"User-Agent": UA, "Accept-Language": "ja"})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            html = r.read(400_000).decode("utf-8", "replace")
        return parse_profile(html)
    except Exception:
        return None


def build_mention_index(events: list) -> dict:
    """performer normalized_name → 店舗投稿由来の @mention handle 候補（重複なし）。"""
    idx: dict[str, list] = {}
    for e in events:
        if e.get("event") != "来店":
            continue
        cast = (e.get("cast") or "").strip()
        store = (e.get("store") or "").strip()
        if not cast or P1.is_not_performer(cast, store):
            continue
        pkey = P1.normalize_name(cast)
        sh = P1.handle_of(e.get("x_url") or e.get("url"))
        text = (e.get("detail") or "") + " " + (e.get("highlight") or "")
        for h in extract_mention_handles(text, sh):
            idx.setdefault(pkey, [])
            if h not in idx[pkey]:
                idx[pkey].append(h)
    return idx


def run(limit: int, report_path: Optional[str], state: Optional[dict] = None,
        now: Optional[float] = None, candidates: Optional[list] = None,
        events: Optional[list] = None, cast_members: Optional[list] = None,
        agencies: Optional[list] = None,
        fetch_profile: Callable[[str], Optional[dict]] = fetch_profile_live,
        persist_state: bool = False) -> dict:
    now = now if now is not None else time.time()
    state = state if state is not None else {}
    events = events if events is not None else P1.load_events()
    cast_members = cast_members if cast_members is not None else P1.sb_get_all(
        "cast_members?select=id,name,normalized_name,x_url,agency_id,is_active,source")
    agencies = agencies if agencies is not None else P1.sb_get_all("agencies?select=id,name,hp_url,is_active")
    if candidates is None:
        # NS-P1 を candidate 源として利用（DB非依存・events から生成）
        p1 = P1.run(limit=100000, report_path=None, state={}, now=now,
                    events=events, cast_members=cast_members, agencies=agencies)
        candidates = p1["candidates"]

    agencies_by_id = {a["id"]: a for a in agencies}
    cast_by_norm = {}
    for c in cast_members:
        k = c.get("normalized_name") or P1.normalize_name(c.get("name", ""))
        if k and k not in cast_by_norm:
            cast_by_norm[k] = c
    mention_idx = build_mention_index(events)

    # verification queue 優先度: handle既知(mention/cast) → 来店多 → 来店店舗多 → 期限到来
    def due(pkey):
        rec = state.get(pkey)
        return (not rec) or (rec.get("next_verify_at_ts") is None) or (now >= rec["next_verify_at_ts"])

    queue = []
    for c in candidates:
        pkey = c.get("normalized_name")
        if not due(pkey):
            continue
        has_handle = bool(mention_idx.get(pkey)) or bool(cast_by_norm.get(pkey, {}).get("x_url"))
        queue.append((0 if has_handle else 1, -(c.get("visit_count") or 0),
                      -(c.get("unique_store_count") or 0), c))
    queue.sort(key=lambda t: (t[0], t[1], t[2]))
    todo = [t[3] for t in queue[:limit]] if limit and limit > 0 else [t[3] for t in queue]

    stats = dict(candidates=len(todo), x_handle_resolved=0, primary_profiles=0,
                 FREE_CONFIRMED=0, FREE_LIKELY=0, AFFILIATED=0, PERFORMER_UNCONFIRMED=0,
                 CONFLICT_REVIEW=0, IDENTITY_UNCONFIRMED=0, source_unavailable=0, errors=0)
    circuit = {"tripped": False, "reason": None}
    results = []

    for c in todo:
        pkey = c.get("normalized_name")
        cm = cast_by_norm.get(pkey)
        agency = agencies_by_id.get((cm or {}).get("agency_id")) if cm else None
        rec = verify_one(c, mention_idx.get(pkey, []), cm, agency, fetch_profile, now)
        results.append(rec)
        if rec["identity_status"] == "RESOLVED":
            stats["x_handle_resolved"] += 1
            if rec.get("bio_excerpt") is not None:
                stats["primary_profiles"] += 1
        stats[rec["free_status"]] = stats.get(rec["free_status"], 0) + 1
        if rec["identity_status"] == IDENTITY_UNCONFIRMED:
            stats["IDENTITY_UNCONFIRMED"] += 1
        # state 更新（freshness / next_verify_at）
        rd = P1.retry_days(rec["free_status"])
        state[pkey] = dict(performer_id=rec["performer_id"], x_handle=rec.get("x_handle"),
                           identity_status=rec["identity_status"], free_status=rec["free_status"],
                           free_confidence=rec["free_confidence"],
                           affiliation_status=("AFFILIATED" if rec.get("affiliation") else "unknown"),
                           last_verified_at=P1._iso(now), last_verified_at_ts=now,
                           next_verify_at=P1._iso(now + rd * 86400), next_verify_at_ts=now + rd * 86400,
                           verification_reason=rec["reason"])

    # circuit breaker: 同一handleが多数人物へ（identity崩壊）/ profile取得失敗が大半
    import collections
    hc = collections.Counter(r["x_handle"] for r in results if r.get("x_handle"))
    if hc and max(hc.values()) >= max(3, len(results) // 2 or 3):
        circuit["tripped"] = True
        circuit["reason"] = f"handle_identity_collision({hc.most_common(1)})"
    resolved = [r for r in results if r["identity_status"] == "RESOLVED"]
    if resolved:
        noprof = sum(1 for r in resolved if r.get("bio_excerpt") is None)
        if len(resolved) >= 10 and noprof / len(resolved) > 0.8:
            circuit["tripped"] = True
            circuit["reason"] = f"profile_source_unavailable_spike({noprof}/{len(resolved)})"

    # 営業候補ランキング（FREE_CONFIRMED のみ・NS-P1 のスコアを再利用）
    outreach = []
    for r in results:
        if r["free_status"] == P1.FREE_CONFIRMED:
            r["free_freshness"] = "FRESH"  # bio=現在状態・observed_at=now
            r["recent_visit_count"] = r.get("visit_count") or 0
            r["outreach_priority_score"] = P1.outreach_priority_score(r)
            outreach.append(r)
    outreach.sort(key=lambda r: r["outreach_priority_score"], reverse=True)

    if persist_state and not circuit["tripped"]:
        P1.save_state(state, STATE_FILE)

    result = dict(mode="CANDIDATE_ONLY", db_writes=0, external_messages=0, secret_additions=0,
                  stats=stats, circuit=circuit,
                  outreach_ranking=[{k: r.get(k) for k in ("performer_id", "display_name", "x_handle",
                     "free_status", "outreach_priority_score", "free_evidence_url", "prefectures_visited")}
                     for r in outreach[:50]],
                  results=results)
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(result, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result


def _summary(res: dict) -> str:
    s = res["stats"]
    return (f"mode={res['mode']} db_writes={res['db_writes']} ext_msgs={res['external_messages']} "
            f"secret_add={res['secret_additions']} candidates={s['candidates']} "
            f"handle_resolved={s['x_handle_resolved']} profiles={s['primary_profiles']} "
            f"FREE_CONFIRMED={s['FREE_CONFIRMED']} FREE_LIKELY={s['FREE_LIKELY']} "
            f"AFFILIATED={s['AFFILIATED']} UNCONFIRMED={s['PERFORMER_UNCONFIRMED']} "
            f"CONFLICT={s['CONFLICT_REVIEW']} IDENTITY_UNCONFIRMED={s['IDENTITY_UNCONFIRMED']} "
            f"circuit={'TRIPPED:'+str(res['circuit']['reason']) if res['circuit']['tripped'] else 'ok'}")


def main():
    ap = argparse.ArgumentParser(description="NS-P2 free status verification (candidate-only)")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--report", type=str, default=str(REPORT_DEFAULT))
    ap.add_argument("--no-state", action="store_true")
    args = ap.parse_args()
    state = {} if args.no_state else P1.load_state(STATE_FILE)
    res = run(limit=args.limit, report_path=(args.report or None), state=state,
              persist_state=(not args.no_state))
    line = _summary(res)
    print(line)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## Free Status Verification (candidate-only)\n")
            f.write(f"- {line}\n")
            for r in res["outreach_ranking"][:20]:
                f.write(f"  - FREE {r['display_name']} (@{r['x_handle']}) score={r.get('outreach_priority_score')} {r['free_evidence_url']}\n")
    if res["circuit"]["tripped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
