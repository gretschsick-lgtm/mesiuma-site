#!/usr/bin/env python3
"""
NS-9C — Safe DMM ID Backfill + Autonomous Canonical X Expansion

目的:
  DMM ぱちタウンの店舗ディレクトリと canonical stores を「厳格な一意 exact match」で対応付け、
  stores.dmm_id を NULL→value で段階的に backfill。確定した dmm_id 店舗について
  DMM per-store ページの「店舗公式X欄」を高信頼 source として抽出し、
  stores.x_url を NULL→value で段階 WRITE → 既存 resolver が自然に verified 化。

安全原則(精度 > 件数):
  - AUTO_MATCH は「pref exact + 正規化店名 exact + DMM directory 内で一意 + dmm_id 重複なし」のみ。
    曖昧は AMBIGUOUS / UNMATCHED として保持。推測 mapping 禁止。
  - normalize は安全側。本館/別館/号店/号館/新館/スロット館/EAST/WEST/駅前/本店 等の
    branch 識別子は絶対に吸収しない。
  - WRITE は NULL→value のみ。既存 dmm_id / x_url は絶対に上書きしない。
  - dmm_id / x_url の production WRITE は段階 rollout(5→20→50→200→auto)。各 stage で安全 gate。
  - X は DMM が店舗情報として明示した公式X(icon枠)のみ。本文中の任意 X は拾わない。
  - X WRITE 前に resolver simulation(verified→candidate / conflict / orphan 等)を必須。
  - store_handles.json は触らない(resolver の責務)。schema migration しない。
"""
from __future__ import annotations
import os, re, sys, json, time, ssl, argparse, unicodedata, urllib.request, urllib.parse
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
import resolve_store_handles as R
import discover_store_x as DX   # simulate_resolver / handle_of 再利用

ROOT = Path(__file__).parent.parent
STATE_FILE = Path(__file__).parent / ".dmm_backfill_state.json"
REPORT_DEFAULT = ROOT / "public" / "dmm_backfill_report.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 都道府県 → DMM URL slug
PREF_SLUG = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki",
    "栃木県": "tochigi", "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba",
    "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata", "富山県": "toyama",
    "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo",
    "奈良県": "nara", "和歌山県": "wakayama", "鳥取県": "tottori", "島根県": "shimane",
    "岡山県": "okayama", "広島県": "hiroshima", "山口県": "yamaguchi", "徳島県": "tokushima",
    "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi", "福岡県": "fukuoka",
    "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita",
    "宮崎県": "miyazaki", "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}

# 吸収してはいけない branch 識別子（これらが名前に含まれる場合、正規化で消さない）
_BRANCH_TOKENS = ["本館", "別館", "新館", "スロット館", "本店", "駅前", "east", "west",
                  "号店", "号館", "1号", "2号", "3号", "北口", "南口", "東口", "西口"]


# ══════════════════════════════════════════════════════════════════════════
# 純粋関数（テスト対象）
# ══════════════════════════════════════════════════════════════════════════

def normalize_store_name(name: str) -> str:
    """
    安全側の店名正規化: NFKC + 小文字 + 空白除去 + 一部記号統一のみ。
    branch 識別子・号数・地名・館種別は保持する（危険な吸収をしない）。
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name)
    s = s.replace("　", "").replace(" ", "")
    s = re.sub(r'[‐‑‒–—―ー−\-]', 'ー', s) if False else s  # ダッシュ統一はしない(誤結合防止)
    s = s.replace("　", "")
    # 括弧内(市区/駅)は directory alt の付随情報なので比較前に呼び出し側で除く
    return s.lower()


def strip_paren(name: str) -> str:
    """DMM alt の "店名（市区 駅）" から店名部のみ取り出す。"""
    return re.split(r'[（(]', name or "", 1)[0].strip()


def parse_area_links(html: str, pref_slug: str) -> list[str]:
    """pref ページから area コード一覧を抽出。"""
    return sorted(set(re.findall(rf'/shops/{re.escape(pref_slug)}/area/(\d+)', html or "")))


def parse_area_cards(html: str, pref_slug: str) -> list[dict]:
    """area ページから店舗カード(dmm_id, name, city)を抽出。"""
    out, seen = [], set()
    # data-url と、その近傍の img alt="店名（市区 駅）"
    for m in re.finditer(
            rf'data-url="/shops/{re.escape(pref_slug)}/(\d+)".*?alt="([^"]+)"',
            html or "", re.S):
        dmm_id, alt = m.group(1), m.group(2)
        if dmm_id in seen:
            continue
        seen.add(dmm_id)
        name = strip_paren(alt)
        cm = re.search(r'（([^ 　）]+)', alt)
        city = cm.group(1) if cm else None
        out.append({"dmm_id": dmm_id, "name": name, "city": city})
    return out


def build_dmm_index(cards_by_pref: dict) -> dict:
    """{pref_ja: {norm_name: [card,...]}} を構築。"""
    idx: dict = {}
    for pref_ja, cards in cards_by_pref.items():
        d = idx.setdefault(pref_ja, {})
        for c in cards:
            d.setdefault(normalize_store_name(c["name"]), []).append(c)
    return idx


def _branch_consistent(canon_name: str, dmm_name: str) -> bool:
    """branch 識別子が両者で矛盾しないか（片方だけに本館/号店等がある exact 一致は既に排除済だが二重防御）。"""
    a, b = canon_name, dmm_name
    for t in _BRANCH_TOKENS:
        if (t in a) != (t in b):
            return False
    return True


def match_store(store: dict, dmm_index: dict) -> dict:
    """
    canonical store を DMM index に厳格一致。
    戻り値 {status, dmm_id, dmm_name, reason}
      EXACT_UNIQUE / AMBIGUOUS / UNMATCHED
    """
    pref = store.get("pref")
    name = store.get("name")
    if not pref or not name or pref not in dmm_index:
        return {"status": "UNMATCHED", "dmm_id": None, "dmm_name": None, "reason": "no_pref_index_or_name"}
    key = normalize_store_name(name)
    cands = dmm_index[pref].get(key, [])
    if not cands:
        return {"status": "UNMATCHED", "dmm_id": None, "dmm_name": None, "reason": "no_exact_name_in_pref"}
    # branch 二重防御 + 一意性
    cands = [c for c in cands if _branch_consistent(name, c["name"])]
    if len(cands) == 1:
        return {"status": "EXACT_UNIQUE", "dmm_id": cands[0]["dmm_id"],
                "dmm_name": cands[0]["name"], "reason": "exact_name_pref_unique"}
    if len(cands) > 1:
        return {"status": "AMBIGUOUS", "dmm_id": None, "dmm_name": None,
                "reason": f"multiple_dmm_entries({len(cands)})"}
    return {"status": "UNMATCHED", "dmm_id": None, "dmm_name": None, "reason": "branch_conflict"}


def dedupe_matches(matches: list[dict]) -> tuple[list[dict], int]:
    """同一 dmm_id が複数 canonical に割当たる衝突を除外。戻り値(安全なmatch, 衝突数)。"""
    from collections import Counter
    ex = [m for m in matches if m.get("status") == "EXACT_UNIQUE" and m.get("dmm_id")]
    cnt = Counter(m["dmm_id"] for m in ex)
    dup = {k for k, v in cnt.items() if v > 1}
    safe = [m for m in ex if m["dmm_id"] not in dup]
    return safe, len(dup)


def extract_official_x(store_page_html: str) -> dict:
    """
    DMM 店舗ページの公式SNS(icon枠)から店舗X handle を抽出。
    店長X等の本文リンクは拾わない。複数の異なる handle があれば ambiguous。
    戻り値 {handle, status, reason}
    """
    icons = re.findall(r'<a class="icon"[^>]*href="https?://(?:x\.com|twitter\.com)/([A-Za-z0-9_]{2,30})"',
                       store_page_html or "")
    handles = []
    for h in icons:
        hl = h.lower()
        if hl not in handles:
            handles.append(hl)
    if not handles:
        return {"handle": None, "status": "NO_X", "reason": "no_official_x_icon"}
    if len(handles) > 1:
        return {"handle": None, "status": "AMBIGUOUS_X", "reason": f"multiple_icon_x({handles})"}
    return {"handle": handles[0], "status": "OK", "reason": "official_icon_x"}


def validate_x_for_write(handle: str, store_id: str, db_handle_to_store: dict,
                         rejected: set, excluded_manager: set) -> dict:
    """X write 可否の検証。戻り値 {ok, reason}"""
    if not handle or not re.match(r'^[A-Za-z0-9_]{2,30}$', handle):
        return {"ok": False, "reason": "invalid_handle"}
    if handle in rejected:
        return {"ok": False, "reason": "rejected_handle"}
    if handle in excluded_manager:
        return {"ok": False, "reason": "manager_handle"}
    owner = db_handle_to_store.get(handle)
    if owner and owner != store_id:
        return {"ok": False, "reason": f"handle_used_by_other_store({owner})"}
    return {"ok": True, "reason": "ok"}


# ══════════════════════════════════════════════════════════════════════════
# I/O
# ══════════════════════════════════════════════════════════════════════════

def _ctx():
    return ssl._create_unverified_context()


def fetch(url: str, timeout: int = 15) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
        with urllib.request.urlopen(req, context=_ctx(), timeout=timeout) as r:
            return r.read(800_000).decode("utf-8", "replace")
    except Exception:
        return None


def sb_patch(table_filter: str, body: dict) -> list:
    base = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(base + "/rest/v1/" + table_filter, data=json.dumps(body).encode(),
                                 method="PATCH",
                                 headers={"apikey": key, "Authorization": "Bearer " + key,
                                          "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
        return json.load(r)


def load_state() -> dict:
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {"dmm_index": {}, "stores": {}}


def save_state(st: dict) -> None:
    try:
        json.dump(st, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def crawl_pref(pref_ja: str, sleep: float = 0.3, max_areas: int = 0) -> list[dict]:
    """1 都道府県の全 area を crawl して店舗カードを返す。"""
    slug = PREF_SLUG.get(pref_ja)
    if not slug:
        return []
    top = fetch(f"https://p-town.dmm.com/shops/{slug}")
    areas = parse_area_links(top or "", slug)
    if max_areas:
        areas = areas[:max_areas]
    cards, seen = [], set()
    for a in areas:
        html = fetch(f"https://p-town.dmm.com/shops/{slug}/area/{a}")
        for c in parse_area_cards(html or "", slug):
            if c["dmm_id"] not in seen:
                seen.add(c["dmm_id"])
                cards.append(c)
        time.sleep(sleep)
    return cards


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ══════════════════════════════════════════════════════════════════════════
# orchestration
# ══════════════════════════════════════════════════════════════════════════

def load_stores() -> list:
    return R.sb_get_all("stores?select=id,name,pref,address,dmm_id,x_url,is_active")


def discover(prefs: list[str], stores: Optional[list] = None,
             crawl: Callable[[str], list] = crawl_pref) -> dict:
    """Stage 0: 指定 pref を crawl し canonical と厳格 match（READ-ONLY・DB write なし）。"""
    stores = stores if stores is not None else load_stores()
    cards_by_pref = {}
    for p in prefs:
        cards_by_pref[p] = crawl(p)
    idx = build_dmm_index(cards_by_pref)

    targets = [s for s in stores if s.get("is_active") and s.get("pref") in prefs]
    matches = []
    for s in targets:
        m = match_store(s, idx)
        m.update(store_id=s["id"], store_name=s["name"], pref=s.get("pref"),
                 has_address=bool(s.get("address")), db_dmm_id=s.get("dmm_id"))
        matches.append(m)
    safe, dup = dedupe_matches(matches)
    from collections import Counter
    st = Counter(m["status"] for m in matches)
    stats = dict(canonical_in_prefs=len(targets),
                 dmm_stores_discovered=sum(len(v) for v in cards_by_pref.values()),
                 EXACT_UNIQUE=st.get("EXACT_UNIQUE", 0), AMBIGUOUS=st.get("AMBIGUOUS", 0),
                 UNMATCHED=st.get("UNMATCHED", 0), duplicate_dmm_id=dup,
                 safe_writable=sum(1 for m in safe if not m["db_dmm_id"]))
    return dict(matches=matches, safe=safe, index_pref_counts={p: len(c) for p, c in cards_by_pref.items()},
                stats=stats)


def write_dmm_ids(safe_matches: list, limit: int, dry_run: bool = True) -> dict:
    """Stage n: EXACT_UNIQUE かつ db dmm_id NULL のみ NULL→value WRITE（段階 limit）。"""
    todo = [m for m in safe_matches if m["status"] == "EXACT_UNIQUE" and not m["db_dmm_id"]][:limit]
    snapshot = [{"store_id": m["store_id"], "old_dmm_id": None, "new_dmm_id": m["dmm_id"]} for m in todo]
    written, overwrite_avoided, errors = [], 0, 0
    if not dry_run:
        for m in todo:
            try:
                res = sb_patch(f"stores?id=eq.{urllib.parse.quote(m['store_id'])}&dmm_id=is.null",
                               {"dmm_id": m["dmm_id"]})
                if res and str(res[0].get("dmm_id")) == str(m["dmm_id"]):
                    written.append(m)
                else:
                    overwrite_avoided += 1
            except Exception:
                errors += 1
    return dict(attempted=len(todo), written=written, snapshot=snapshot,
                overwrite_avoided=overwrite_avoided, errors=errors, dry_run=dry_run)


def build_x_context():
    """resolver simulation + X validation 用のコンテキスト。"""
    db = R.sb_get_all("stores?select=id,name,normalized_name,x_url,is_active,pref")
    handles = json.load(open(DX.STORE_HANDLES_JSON, encoding="utf-8"))
    rejected = {DX.norm_handle(h) for h, v in handles.items()
                if isinstance(v, dict) and v.get("verification_status") == "rejected"}
    excluded_manager = {DX.norm_handle(h) for h, v in handles.items()
                        if isinstance(v, dict) and v.get("verification_status") == "excluded_manager"}
    db_handle_to_store = {}
    for r in db:
        h = R.handle_of(r.get("x_url"))
        if h:
            db_handle_to_store[DX.norm_handle(h)] = r["id"]
    return dict(db=db, handles=handles, rejected=rejected,
                excluded_manager=excluded_manager, db_handle_to_store=db_handle_to_store)


def discover_and_write_x(mapped_stores: list, limit: int, dry_run: bool = True,
                         fetch_page: Callable[[str], Optional[str]] = None,
                         ctx: Optional[dict] = None) -> dict:
    """
    dmm_id 確定店舗の DMM 公式X を抽出 → 検証 → resolver simulation → x_url NULL→value 段階WRITE。
    mapped_stores: [{store_id, pref, dmm_id, x_url(db), name}]
    ctx を注入すると DB アクセスを避けられる（テスト用）。
    """
    fetch_page = fetch_page or (lambda dmm_id, pref: fetch(
        f"https://p-town.dmm.com/shops/{PREF_SLUG.get(pref,'')}/{dmm_id}"))
    ctx = ctx if ctx is not None else build_x_context()
    results, proposed = [], {}
    for s in mapped_stores:
        if s.get("x_url"):
            results.append({**s, "x_status": "SKIP_EXISTING_X"})
            continue
        html = fetch_page(s["dmm_id"], s["pref"])
        ex = extract_official_x(html or "")
        if ex["status"] != "OK":
            results.append({**s, "x_status": ex["status"], "reason": ex["reason"]})
            continue
        val = validate_x_for_write(ex["handle"], s["store_id"], ctx["db_handle_to_store"],
                                   ctx["rejected"], ctx["excluded_manager"])
        if not val["ok"]:
            results.append({**s, "x_status": "REJECTED", "handle": ex["handle"], "reason": val["reason"]})
            continue
        results.append({**s, "x_status": "WRITE_ELIGIBLE", "handle": ex["handle"],
                        "url": f"https://x.com/{ex['handle']}"})
        proposed[s["store_id"]] = f"https://x.com/{ex['handle']}"

    # 段階 limit
    eligible = [r for r in results if r["x_status"] == "WRITE_ELIGIBLE"][:limit]
    proposed = {r["store_id"]: r["url"] for r in eligible}

    sim = None
    circuit = None
    if proposed:
        sim = DX.simulate_resolver(ctx["handles"], ctx["db"], proposed)
        if sim["ver2cand"] or sim["unlink"] or sim["relink"] or sim["canonical_conflict"] or sim["orphan"]:
            circuit = f"resolver_simulation_unsafe:{sim}"

    written, overwrite_avoided, errors = [], 0, 0
    if proposed and not dry_run and not circuit:
        for r in eligible:
            try:
                res = sb_patch(f"stores?id=eq.{urllib.parse.quote(r['store_id'])}&x_url=is.null",
                               {"x_url": r["url"]})
                if res and res[0].get("x_url") == r["url"]:
                    written.append(r)
                else:
                    overwrite_avoided += 1
            except Exception:
                errors += 1
    return dict(results=results, eligible=eligible, proposed=proposed, simulation=sim,
                circuit=circuit, written=written, overwrite_avoided=overwrite_avoided,
                errors=errors, dry_run=dry_run)


# ══════════════════════════════════════════════════════════════════════════
# CLI（手動段階実行 / workflow 用）
# ══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="NS-9C DMM id backfill + canonical X expansion")
    ap.add_argument("--prefs", type=str, required=True, help="カンマ区切り都道府県(日本語)")
    ap.add_argument("--dmm-limit", type=int, default=0, help="この run で書く dmm_id 上限(0=書かない)")
    ap.add_argument("--x-limit", type=int, default=0, help="この run で書く x_url 上限(0=書かない)")
    ap.add_argument("--write", action="store_true", help="production WRITE を実行(既定は dry-run)")
    ap.add_argument("--max-areas", type=int, default=0, help="pref あたり area 上限(0=全部)")
    ap.add_argument("--report", type=str, default=str(REPORT_DEFAULT))
    args = ap.parse_args()

    prefs = [p for p in args.prefs.split(",") if p]
    stores = load_stores()
    disc = discover(prefs, stores=stores,
                    crawl=lambda p: crawl_pref(p, max_areas=args.max_areas))
    dry = not args.write

    # dmm_id 段階 WRITE（NULL→value / EXACT_UNIQUE のみ / dedupe 済 safe）
    dmm_res = write_dmm_ids(disc["safe"], limit=args.dmm_limit, dry_run=dry)

    # X 抽出+WRITE: dmm_id 確定済み(この run 書込 + 既存)店舗が対象
    store_by_id = {s["id"]: s for s in stores}
    mapped = []
    for m in dmm_res["written"]:
        s = store_by_id.get(m["store_id"], {})
        mapped.append({"store_id": m["store_id"], "pref": m["pref"], "dmm_id": m["dmm_id"],
                       "x_url": s.get("x_url"), "name": m["store_name"]})
    x_res = discover_and_write_x(mapped, limit=args.x_limit, dry_run=dry) if mapped else \
        {"results": [], "eligible": [], "written": [], "simulation": None, "circuit": None, "overwrite_avoided": 0, "errors": 0, "dry_run": dry}

    out = dict(mode=("WRITE" if args.write else "DRY_RUN"), prefs=prefs,
               stage0=disc["stats"], index_pref_counts=disc["index_pref_counts"],
               dmm_write=dict(attempted=dmm_res["attempted"], written=len(dmm_res["written"]),
                              overwrite_avoided=dmm_res["overwrite_avoided"], errors=dmm_res["errors"],
                              snapshot=dmm_res["snapshot"]),
               x_write=dict(eligible=len(x_res["eligible"]), written=len(x_res["written"]),
                            circuit=x_res["circuit"], simulation=x_res["simulation"],
                            overwrite_avoided=x_res["overwrite_avoided"], errors=x_res["errors"]))
    print(json.dumps({k: out[k] for k in ("mode", "prefs", "stage0", "dmm_write", "x_write")}, ensure_ascii=False))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        json.dump(out, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## DMM Backfill + Canonical X Expansion\n")
            f.write(f"- mode={out['mode']} prefs={prefs}\n")
            f.write(f"- stage0: {out['stage0']}\n")
            f.write(f"- dmm_write: attempted={out['dmm_write']['attempted']} written={out['dmm_write']['written']}\n")
            f.write(f"- x_write: eligible={out['x_write']['eligible']} written={out['x_write']['written']} circuit={out['x_write']['circuit']}\n")


if __name__ == "__main__":
    main()
