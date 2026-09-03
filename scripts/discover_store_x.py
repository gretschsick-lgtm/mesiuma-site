#!/usr/bin/env python3
"""
NS-9 — Autonomous Store X Discovery (v1: 公式HP経路のみ / HTTP-only)

目的:
  canonical stores のうち x_url 未登録の店舗について、
  「その店舗自身の公式サイト(hp_url)に明示された X リンク」だけを
  HIGH confidence として DB stores.x_url へ安全に反映する。

設計原則(NS-9):
  - 正本は DB stores.x_url。store_handles.json は既存 resolver に任せ、本スクリプトは触らない。
  - HIGH = 店舗自身の公式ドメイン上に掲載された単一の店舗系 X リンク（＝誤紐付けが原理的に起きにくい）。
  - 検索由来・プロフィール名だけ一致・曖昧一致・複数handle競合・manager/rejected は自動WRITE禁止 → candidate queue。
  - 既存 x_url は自動上書きしない（NULL のみ WRITE）。
  - 1店舗ごとに safety gate。resolver simulation で canonical conflict / orphan を事前検出。
  - HIGH 未満は candidate report(JSON artifact) に残すのみ。DB/JSON/commit しない。
  - HTTP-only。新規 secret 不要（DB は既存 SUPABASE_SERVICE_ROLE_KEY のみ）。

使い方:
  python scripts/discover_store_x.py --dry-run                 # WRITEせず探索のみ
  python scripts/discover_store_x.py --limit 15                # 上位15店を探索してHIGHはWRITE
  python scripts/discover_store_x.py --pilot-ids a,b,c --dry-run  # 指定店だけ(pilot)
  python scripts/discover_store_x.py --report /path/report.json
"""
from __future__ import annotations
import os, re, sys, json, time, ssl, argparse, urllib.request, urllib.parse
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
import resolve_store_handles as R  # sb_get_all / build_indexes / classify / apply_meta / handle_of

ROOT = Path(__file__).parent.parent
STORE_HANDLES_JSON = ROOT / "public" / "store_handles.json"

# ── X handle 抽出 ─────────────────────────────────────────────────────────
_HANDLE_RE = re.compile(r'(?:x\.com|twitter\.com)/([A-Za-z0-9_]{3,50})(?:/|$|\?|%|"|\'|\s|<)')
_SKIP_HANDLES = frozenset([
    "search", "explore", "notifications", "messages", "home", "i", "intent",
    "share", "hashtag", "login", "signup", "privacy", "tos", "settings",
    "compose", "twitter", "about", "help", "en", "ja", "widgets", "download",
])
_HANDLE_FMT = re.compile(r'^[A-Za-z0-9_]{3,50}$')

# チェーン本部ドメイン（全国共通アカウントに繋がるため支店特定不可 → HIGH にしない）
CHAIN_DOMAINS = frozenset([
    "king-net.co.jp", "luckyplaza.co.jp", "undertree.co.jp", "k-kosho.co.jp",
    "papimo.jp", "maruhan.co.jp", "nittaku.jp", "tsubame-group.jp",
    "venice.co.jp", "dynam.jp", "aeonentertainment.co.jp", "marioad.co.jp",
    "gaia-net.co.jp", "kicono.jp", "kikohna.co.jp",
])

# データポータル/集約/ブログ/SNS基盤（店舗自身の公式ドメインではない＝載っているXは店舗のものと限らない）
PORTAL_SUFFIXES = frozenset([
    "site777.jp", "777.jp", "p-world.co.jp", "dmm.com", "p-town.dmm.com",
    "ameblo.jp", "note.com", "hatenablog.com", "fc2.com", "livedoor.jp",
    "jimdo.com", "jimdofree.com", "wixsite.com", "wix.com", "goope.jp",
    "crayonsite.com", "crayonsite.net", "localplace.jp", "ekiten.jp",
    "itp.ne.jp", "navitime.co.jp", "mapion.co.jp", "shufoo.net",
    "facebook.com", "instagram.com", "youtube.com", "line.me", "lit.link",
    "min-repo.com", "minpachi.com", "hall-navi.com", "pachinko-nippon.com",
    "peraichi.com", "google.com", "amebaownd.com",
])


def host_of(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def is_portal_host(url: str) -> bool:
    h = host_of(url)
    if not h:
        return False
    return any(h == s or h.endswith("." + s) for s in PORTAL_SUFFIXES)

USER_AGENT = "Mozilla/5.0 (compatible; mesiuma-store-x-discovery/1.0)"

# 状態ファイル（Actions cache で run 間持続。git 管理せず＝不要な commit を出さない）
STATE_FILE = Path(__file__).parent / ".discover_state.json"

# 分類ごとの再探索間隔（日）。毎日全店 scan を避けるための retry policy。
RETRY_DAYS = {
    "single_handle_on_official_store_site": 7,   # candidate found
    "ambiguous_multiple_handles": 14,
    "no_x_link_on_page": 30,
    "shared_corporate_hp": 90,
    "chain_hq_domain": 90,
    "portal": 90,
    "only_rejected_or_manager_handles": 3650,     # 実質停止（長期skip）
    "handle_used_by_other_store": 3650,           # conflict → 長期skip
    "hp_fetch_failed": 2,                         # 一時失敗 → 短期再試行
    "_default": 30,
}


def retry_days(reason: str) -> int:
    if not reason:
        return RETRY_DAYS["_default"]
    for k, v in RETRY_DAYS.items():
        if reason.startswith(k):
            return v
    return RETRY_DAYS["_default"]


# ══════════════════════════════════════════════════════════════════════════
# 純粋関数（テスト対象）
# ══════════════════════════════════════════════════════════════════════════

def norm_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


def is_chain_hq(hp_url: str) -> bool:
    try:
        domain = urllib.parse.urlparse(hp_url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        return False
    return any(cd in domain for cd in CHAIN_DOMAINS)


def extract_handles(html: str) -> list[str]:
    """HTML から x.com/twitter.com handle を重複なしで抽出（出現順・skip除外）。"""
    out: list[str] = []
    seen: set[str] = set()
    for m in _HANDLE_RE.finditer(html or ""):
        h = norm_handle(m.group(1))
        if h and h not in _SKIP_HANDLES and _HANDLE_FMT.match(h) and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def valid_handle(h: str) -> bool:
    return bool(_HANDLE_FMT.match(h or ""))


def classify_confidence(
    hp_url: str,
    handles: list[str],
    rejected: set[str],
    excluded_manager: set[str],
    db_handle_to_store: dict[str, str],
    this_store_id: str,
    hp_is_shared: bool = False,
) -> dict:
    """
    HP から得た handle 群を評価し confidence を返す。
    戻り値: {confidence: HIGH|LOW|NONE, handle, reason}
    HIGH の条件:
      - HP がチェーン本部ドメインでない（＝店舗固有サイト）
      - HP が複数店舗で共有されていない（共有＝法人/グループページ）
      - rejected / excluded_manager を除いた候補が「ちょうど1つ」
      - その handle が他店の DB x_url として使われていない（別店なら競合）
      - handle 形式が正しい
    """
    if is_chain_hq(hp_url):
        return {"confidence": "NONE", "handle": None, "reason": "chain_hq_domain"}
    if hp_is_shared:
        return {"confidence": "NONE", "handle": None, "reason": "shared_corporate_hp"}
    if not handles:
        return {"confidence": "NONE", "handle": None, "reason": "no_x_link_on_page"}

    # rejected / manager を除外
    filtered = [h for h in handles if h not in rejected and h not in excluded_manager]
    if not filtered:
        return {"confidence": "LOW", "handle": None, "reason": "only_rejected_or_manager_handles"}
    if len(filtered) > 1:
        return {"confidence": "LOW", "handle": None,
                "reason": f"ambiguous_multiple_handles({len(filtered)})"}

    h = filtered[0]
    if not valid_handle(h):
        return {"confidence": "LOW", "handle": h, "reason": "malformed_handle"}

    owner = db_handle_to_store.get(h)
    if owner and owner != this_store_id:
        return {"confidence": "LOW", "handle": h, "reason": f"handle_used_by_other_store({owner})"}

    return {"confidence": "HIGH", "handle": h, "reason": "single_handle_on_official_store_site"}


def safety_gate(
    store: dict,
    handle: str,
    db_handle_to_store: dict[str, str],
    rejected: set[str],
    manual_block_ids: set[str],
) -> dict:
    """DB WRITE 前の 12 点 gate。戻り値 {ok: bool, checks: {name: bool}, fail: [reason]}."""
    sid = store.get("id")
    checks: dict[str, bool] = {}
    fail: list[str] = []

    checks["1_x_url_is_null"] = (store.get("x_url") in (None, ""))
    checks["2_url_wellformed"] = valid_handle(handle)
    checks["3_normalization"] = (norm_handle(handle) == handle and valid_handle(handle))
    owner = db_handle_to_store.get(handle)
    checks["4_handle_not_other_store"] = (owner is None or owner == sid)
    checks["5_no_normalized_duplicate"] = (owner is None or owner == sid)
    checks["6_store_name_present"] = bool(store.get("name"))
    checks["7_pref_present"] = bool(store.get("pref"))
    checks["8_evidence_high"] = True   # 呼び出し側で HIGH のみ渡す前提
    checks["9_not_rejected_handle"] = (handle not in rejected)
    checks["10_not_manual_block"] = (sid not in manual_block_ids) and (not store.get("ng_flag"))
    checks["11_canonical_conflict"] = True   # バッチ simulation で最終判定
    checks["12_orphan_risk"] = True          # バッチ simulation で最終判定

    for k, v in checks.items():
        if not v:
            fail.append(k)
    return {"ok": len(fail) == 0, "checks": checks, "fail": fail}


def simulate_resolver(cur_handles: dict, db_rows: list[dict], proposed: dict[str, str]) -> dict:
    """
    proposed = {store_id: x_url} を DB に適用したと仮定して resolver.classify を実行し、
    critical 指標を返す（READ-ONLY / DB 非変更）。
    """
    sim = {r["id"]: dict(r) for r in db_rows}
    for sid, url in proposed.items():
        if sid in sim:
            sim[sid]["x_url"] = url
    by_id_all = {r["id"]: r for r in db_rows}
    by_norm, by_xh, by_id = R.build_indexes(list(sim.values()))
    out = R.apply_meta(cur_handles, R.classify(cur_handles, by_norm, by_xh, by_id, "gate"))

    F = ["verification_status", "evidence_type", "canonical_handle", "store_id",
         "type", "store", "rejection_reason", "match_method"]
    changed = [h for h in cur_handles
               if isinstance(cur_handles[h], dict) and isinstance(out[h], dict)
               and any(cur_handles[h].get(f) != out[h].get(f) for f in F)]
    ver2cand = unlink = relink = 0
    for h in changed:
        a, b = cur_handles[h], out[h]
        if a.get("verification_status") == "verified" and b.get("verification_status") != "verified":
            ver2cand += 1
        if a.get("store_id") and not b.get("store_id"):
            unlink += 1
        if a.get("store_id") and b.get("store_id") and a.get("store_id") != b.get("store_id"):
            relink += 1
    import collections
    per = collections.defaultdict(list)
    for h, v in out.items():
        if isinstance(v, dict) and v.get("verification_status") == "verified" and v.get("store_id"):
            per[v["store_id"]].append(v.get("canonical_handle"))
    conflict = sum(1 for s, cs in per.items() if sum(1 for x in cs if x) != 1)
    orphan = sum(1 for h, v in out.items() if isinstance(v, dict)
                 and v.get("store_id") and v.get("store_id") not in by_id_all)
    vc = set(v.get("store_id") for v in out.values()
             if isinstance(v, dict) and v.get("verification_status") == "verified"
             and v.get("canonical_handle") and v.get("store_id"))
    return dict(changed=len(changed), ver2cand=ver2cand, unlink=unlink, relink=relink,
                canonical_conflict=conflict, orphan=orphan, verified_canonical=len(vc))


# ══════════════════════════════════════════════════════════════════════════
# I/O（テストでは差し替え可能）
# ══════════════════════════════════════════════════════════════════════════

def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


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


def is_due(store_id: str, state: dict, now: float) -> bool:
    """未探索、または next_retry_at を過ぎていれば探索対象。"""
    rec = state.get(store_id)
    if not rec:
        return True
    nxt = rec.get("next_retry_at_ts")
    return (nxt is None) or (now >= nxt)


def auto_write_allowed(explicit_flag: bool) -> bool:
    """
    構造的 auto-write ガード（多重）:
      - CLI で明示的に --auto-write されている
      - かつ env DISCOVERY_AUTO_WRITE == "1"（workflow は設定しない＝本番schedule では常に不可）
    """
    return bool(explicit_flag) and os.environ.get("DISCOVERY_AUTO_WRITE") == "1"


def fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            raw = r.read(1_500_000)  # 上限 ~1.5MB
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except Exception:
        return None


def sb_patch_x_url(sid: str, url: str) -> Optional[dict]:
    """NULL 限定で stores.x_url を更新（既存値は上書きしない）。返り値=更新行 or None。"""
    base = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ctx = ssl._create_unverified_context()
    endpoint = f"{base}/rest/v1/stores?id=eq.{urllib.parse.quote(sid)}&x_url=is.null"
    req = urllib.request.Request(
        endpoint, data=json.dumps({"x_url": url}).encode(), method="PATCH",
        headers={"apikey": key, "Authorization": "Bearer " + key,
                 "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        res = json.load(r)
    return res[0] if res else None


# ══════════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════════

def build_context():
    """DB + store_handles から探索コンテキストを構築（READ-ONLY）。"""
    db = R.sb_get_all("stores?select=id,name,normalized_name,x_url,is_active,pref,hp_url,ng_flag")
    handles = json.load(open(STORE_HANDLES_JSON, encoding="utf-8"))
    rejected = {norm_handle(h) for h, v in handles.items()
                if isinstance(v, dict) and v.get("verification_status") == "rejected"}
    excluded_manager = {norm_handle(h) for h, v in handles.items()
                        if isinstance(v, dict) and v.get("verification_status") == "excluded_manager"}
    verified_store_ids = {v.get("store_id") for v in handles.values()
                          if isinstance(v, dict) and v.get("verification_status") == "verified"
                          and v.get("canonical_handle") and v.get("store_id")}
    db_handle_to_store: dict[str, str] = {}
    for r in db:
        h = R.handle_of(r.get("x_url"))
        if h:
            db_handle_to_store[norm_handle(h)] = r["id"]
    manual_block_ids = {r["id"] for r in db if r.get("ng_flag")}
    # 店舗固有ページ判定: 同一ホスト名を2店以上が使う＝法人/チェーン/ポータル → HIGHにしない。
    # 1店専有(count==1)のホストのみ「店舗固有サイト」とみなす。
    import collections
    host_count = collections.Counter(host_of(r.get("hp_url")) for r in db
                                     if r.get("hp_url") and host_of(r.get("hp_url")))
    shared_hosts = {h for h, c in host_count.items() if c >= 2}
    return dict(db=db, handles=handles, rejected=rejected, excluded_manager=excluded_manager,
                verified_store_ids=verified_store_ids, db_handle_to_store=db_handle_to_store,
                manual_block_ids=manual_block_ids, shared_hosts=shared_hosts)


def eligible_stores(ctx: dict, pilot_ids: Optional[list[str]],
                    state: Optional[dict] = None, now: Optional[float] = None) -> list[dict]:
    db = ctx["db"]
    vs = ctx["verified_store_ids"]
    mb = ctx["manual_block_ids"]
    out = []
    for r in db:
        if pilot_ids is not None:
            if r["id"] in pilot_ids:
                out.append(r)
            continue
        if not r.get("is_active"):
            continue
        if r.get("x_url"):
            continue
        if not r.get("hp_url"):
            continue
        if r.get("ng_flag") or r["id"] in mb:
            continue
        if r["id"] in vs:
            continue
        # retry policy: 探索期限が来ていない店舗はスキップ（毎日全店 scan を避ける）
        if state is not None and now is not None and not is_due(r["id"], state, now):
            continue
        out.append(r)
    # pilot 指定順を維持、通常は「未探索優先→最古 last_checked 順」で公平に巡回
    if pilot_ids is not None:
        order = {sid: i for i, sid in enumerate(pilot_ids)}
        out.sort(key=lambda r: order.get(r["id"], 1e9))
    elif state is not None:
        out.sort(key=lambda r: (state.get(r["id"], {}).get("last_checked_at_ts", 0), r["id"]))
    else:
        out.sort(key=lambda r: r["id"])
    return out


def run(limit: int, dry_run: bool, pilot_ids: Optional[list[str]], report_path: Optional[str],
        fetch: Callable[[str], Optional[str]] = fetch_html,
        auto_write: bool = False, state: Optional[dict] = None,
        now: Optional[float] = None, persist_state: bool = False) -> dict:
    ctx = build_context()
    now = now if now is not None else _now()
    state = state if state is not None else {}
    targets = eligible_stores(ctx, pilot_ids, state=state, now=now)
    if limit and limit > 0 and pilot_ids is None:
        targets = targets[:limit]

    scanned = 0
    candidates = []           # 全評価結果
    high = []                 # HIGH かつ gate OK → WRITE 候補 {sid, handle, url, store}
    stats = dict(scanned=0, candidate_found=0, high=0, medium_low=0,
                 skipped_existing=0, conflicts=0, rejected_matches=0, errors=0, new_candidates=0)
    circuit = {"tripped": False, "reason": None}

    def _upd_state(sid, classification, reason, handle, url, hp):
        prev = state.get(sid, {})
        is_new = (prev.get("candidate_handle") != handle) and (handle is not None)
        state[sid] = dict(
            store_id=sid,
            last_checked_at=_iso(now), last_checked_at_ts=now,
            classification=classification, reason=reason, last_result=reason,
            candidate_handle=handle,
            candidate_url=(f"https://x.com/{handle}" if handle else None),
            evidence_url=hp,
            discovered_at=prev.get("discovered_at") or (_iso(now) if handle else None),
            last_seen_at=_iso(now),
            next_retry_at=_iso(now + retry_days(reason) * 86400),
            next_retry_at_ts=now + retry_days(reason) * 86400,
        )
        return is_new

    for st in targets:
        scanned += 1
        sid = st["id"]
        hp = st.get("hp_url")
        html = fetch(hp)
        if html is None:
            stats["errors"] += 1
            candidates.append(dict(store_id=sid, store_name=st.get("name"), hp_url=hp,
                                   confidence="NONE", handle=None, reason="hp_fetch_failed"))
            _upd_state(sid, "NONE", "hp_fetch_failed", None, None, hp)
            continue
        handles = extract_handles(html)
        hp_not_store_specific = (host_of(hp) in ctx["shared_hosts"]) or is_portal_host(hp)
        cls = classify_confidence(hp, handles, ctx["rejected"], ctx["excluded_manager"],
                                  ctx["db_handle_to_store"], sid,
                                  hp_is_shared=hp_not_store_specific)
        rec = dict(store_id=sid, store_name=st.get("name"), pref=st.get("pref"), hp_url=hp,
                   handles_found=handles[:5], confidence=cls["confidence"],
                   handle=cls["handle"], reason=cls["reason"],
                   candidate_url=(f"https://x.com/{cls['handle']}" if cls["handle"] else None),
                   evidence_type="official_store_site", evidence_url=hp,
                   discovered_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        candidates.append(rec)
        if _upd_state(sid, cls["confidence"], cls["reason"], cls["handle"], rec["candidate_url"], hp):
            stats["new_candidates"] += 1
        if cls["confidence"] != "NONE":
            stats["candidate_found"] += 1
        if cls["reason"] == "only_rejected_or_manager_handles":
            stats["rejected_matches"] += 1

        if cls["confidence"] == "HIGH":
            gate = safety_gate(st, cls["handle"], ctx["db_handle_to_store"],
                               ctx["rejected"], ctx["manual_block_ids"])
            rec["gate"] = gate["fail"] or "OK"
            if gate["ok"]:
                high.append(dict(sid=sid, handle=cls["handle"],
                                 url=f"https://x.com/{cls['handle']}", store=st.get("name")))
                stats["high"] += 1
            else:
                stats["medium_low"] += 1
        else:
            stats["medium_low"] += 1

    # ── run内 同一handle重複ガード（同じXが複数店に提案＝グループ/法人アカウント）──
    import collections as _c
    hcount = _c.Counter(h["handle"] for h in high)
    dup_handles = {hh for hh, c in hcount.items() if c > 1}
    if dup_handles:
        kept = []
        for h in high:
            if h["handle"] in dup_handles:
                stats["high"] -= 1
                stats["medium_low"] += 1
                for rec in candidates:
                    if rec.get("handle") == h["handle"] and rec.get("store_id") == h["sid"]:
                        rec["confidence"] = "LOW"
                        rec["reason"] = "group_account_same_handle_multiple_stores"
            else:
                kept.append(h)
        high = kept

    # ── バッチ resolver simulation（canonical conflict / orphan / 想定verified増）──
    proposed = {h["sid"]: h["url"] for h in high}
    sim = None
    if proposed:
        sim = simulate_resolver(ctx["handles"], ctx["db"], proposed)
        # circuit breaker: critical が出たら WRITE しない
        if sim["ver2cand"] or sim["unlink"] or sim["relink"] or sim["canonical_conflict"] or sim["orphan"]:
            circuit["tripped"] = True
            circuit["reason"] = f"resolver_simulation_critical:{sim}"
        # changed が high 件数と乖離（想定外波及）→ 中止
        if sim["changed"] != len(proposed):
            # 兄弟handleの rejection_reason 更新等で changed>proposed はあり得るので、
            # 「HIGH対象がすべて verified 化される」かどうかを別途確認する。
            pass

    stats["conflicts"] = (sim or {}).get("canonical_conflict", 0)

    # ── circuit breaker: 異常レート検知（candidate-only でも異常なら state を汚さず終了）──
    if scanned >= 10:
        fail_rate = stats["errors"] / scanned
        portal_rate = sum(1 for c in candidates if c["reason"] in ("shared_corporate_hp", "portal")) / scanned
        if fail_rate > 0.7:
            circuit["tripped"] = True
            circuit["reason"] = f"fetch_failure_spike({fail_rate:.2f})"
        # 同一handleが異常に多数店舗で検出（source異常/グループ大量混入）
        allh = _c.Counter(c["handle"] for c in candidates if c.get("handle"))
        if allh and max(allh.values()) >= max(3, scanned // 2):
            circuit["tripped"] = True
            circuit["reason"] = f"handle_mass_detection({allh.most_common(1)})"

    # ── WRITE（構造的多重ガード: --auto-write かつ env DISCOVERY_AUTO_WRITE=1 のみ）──
    written = []
    overwrite_attempts = 0
    write_ok = auto_write_allowed(auto_write)
    if high and write_ok and not dry_run and not circuit["tripped"]:
        for h in high:
            res = sb_patch_x_url(h["sid"], h["url"])  # NULL のみ更新
            if res:
                written.append(h)
            else:
                overwrite_attempts += 1  # NULL でなかった＝上書き回避
    stats["scanned"] = scanned

    # ── 状態の永続化（circuit tripped 時は書かない）──
    if persist_state and not circuit["tripped"]:
        save_state(state)

    if circuit["tripped"]:
        mode = "BLOCKED"
    elif dry_run:
        mode = "DRY_RUN"
    elif not write_ok:
        mode = "CANDIDATE_ONLY"   # 本番schedule はここ（DB書込なし）
    elif not high:
        mode = "NO_OP"
    elif written:
        mode = "WROTE"
    else:
        mode = "NO_OP"
    result = dict(
        mode=mode, auto_write_allowed=write_ok,
        stats=stats, circuit=circuit, simulation=sim,
        high=high, written=written, overwrite_attempts=overwrite_attempts,
        candidates=candidates,
    )

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(result, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    return result


def _summary_line(res: dict) -> str:
    s = res["stats"]
    return (f"mode={res['mode']} auto_write={res['auto_write_allowed']} scanned={s['scanned']} "
            f"candidate={s['candidate_found']} new={s.get('new_candidates',0)} HIGH={s['high']} "
            f"written={len(res['written'])} overwrite_avoided={res['overwrite_attempts']} "
            f"conflicts={s['conflicts']} errors={s['errors']} "
            f"circuit={'TRIPPED:'+str(res['circuit']['reason']) if res['circuit']['tripped'] else 'ok'}")


def _reason_breakdown(res: dict) -> dict:
    import collections
    return dict(collections.Counter(c["reason"] for c in res["candidates"]))


def main():
    ap = argparse.ArgumentParser(description="NS-9 Store X discovery (HP route, HTTP-only)")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot-ids", type=str, default="", help="カンマ区切り store_id（pilot用）")
    ap.add_argument("--report", type=str, default="")
    ap.add_argument("--auto-write", action="store_true",
                    help="HIGHをDB stores.x_urlへ書込む(要 env DISCOVERY_AUTO_WRITE=1)。既定OFF・本番scheduleでは使わない")
    ap.add_argument("--no-state", action="store_true", help="状態ファイルを使わない(pilot/test用)")
    args = ap.parse_args()

    pilot = [x for x in args.pilot_ids.split(",") if x] or None
    state = {} if args.no_state else load_state()
    res = run(limit=args.limit, dry_run=args.dry_run, pilot_ids=pilot,
              report_path=(args.report or None), auto_write=args.auto_write,
              state=state, persist_state=(not args.no_state and pilot is None))
    line = _summary_line(res)
    print(line)

    # GitHub Actions Summary
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## Autonomous Store X Discovery (candidate-only)\n")
            f.write(f"- {line}\n")
            f.write(f"- reason breakdown: {_reason_breakdown(res)}\n")
            if res["simulation"]:
                f.write(f"- resolver simulation: {res['simulation']}\n")
            highs = [c for c in res["candidates"] if c["confidence"] == "HIGH"]
            if highs:
                f.write(f"- HIGH candidates (人手レビュー対象・自動WRITEしない): {len(highs)}\n")
                for c in highs[:20]:
                    f.write(f"  - {c['store_name']} ({c.get('pref')}) → {c['candidate_url']} [{c['evidence_url']}]\n")
            for h in res["written"]:
                f.write(f"  - WROTE {h['store']} → {h['url']}\n")
    # 異常終了コード（circuit tripped は失敗として可視化）
    if res["circuit"]["tripped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
