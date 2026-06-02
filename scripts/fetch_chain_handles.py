"""
全国チェーン店 X アカウント自動発掘スクリプト

処理:
  1. CHAIN_DEFS に定義した各チェーンについて X 検索
  2. チェーン名 + コンプリートキーワードで候補ツイートを収集
  3. 発見ハンドルを store_handles.json に type=store で追加
  4. 既存ハンドルはスキップ（重複追加なし）

使用例:
    python scripts/fetch_chain_handles.py --headless
    python scripts/fetch_chain_handles.py --headless --chain dynam
    python scripts/fetch_chain_handles.py --headless --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
STORE_HANDLES_JSON = ROOT / "public" / "store_handles.json"

# ── チェーン定義 ──────────────────────────────────────────────────────────────
# key: チェーン識別子  value: dict(name, queries, handle_pattern, ng_keywords)
CHAIN_DEFS: dict[str, dict] = {
    "dynam": {
        "name": "ダイナム",
        "queries": ["ダイナム コンプリート 番台", "dynam コンプリート 番台"],
        "handle_patterns": ["dynam"],
        "ng_keywords": ["公式", "pr", "news", "campaign"],
    },
    "maruhan": {
        "name": "マルハン",
        "queries": ["マルハン コンプリート 番台", "maruhan コンプリート 番台"],
        "handle_patterns": ["maruhan"],
        "ng_keywords": ["official"],
    },
    "gaia": {
        "name": "ガイア",
        "queries": ["ガイア コンプリート 番台", "パチンコガイア コンプリート"],
        "handle_patterns": ["gaia"],
        "ng_keywords": [],
    },
    "cosmos": {
        "name": "コスモス",
        "queries": ["コスモス コンプリート 番台", "パチンココスモス コンプリート 番台"],
        "handle_patterns": ["cosmos", "cosmo"],
        "ng_keywords": [],
    },
    "kyoraku": {
        "name": "共楽",
        "queries": ["共楽 コンプリート 番台"],
        "handle_patterns": ["kyoraku", "kyouraku"],
        "ng_keywords": [],
    },
    "amuse": {
        "name": "アミューズ",
        "queries": ["アミューズ コンプリート 番台"],
        "handle_patterns": ["amuse"],
        "ng_keywords": [],
    },
    "pia": {
        "name": "PIA（ピアノ）",
        "queries": ["PIA コンプリート 番台", "ピアノ コンプリート 番台 from:pia"],
        "handle_patterns": ["pia_", "pia"],
        "ng_keywords": ["pia_gro", "piapro"],
    },
    "bigmarch": {
        "name": "ビックマーチ",
        "queries": ["ビックマーチ コンプリート 番台", "bigmarch コンプリート 番台"],
        "handle_patterns": ["bm_", "bigmarch"],
        "ng_keywords": [],
    },
    "king": {
        "name": "キング観光",
        "queries": ["キング観光 コンプリート 番台"],
        "handle_patterns": ["king", "kingkanko"],
        "ng_keywords": ["kingrecords", "kingjim"],
    },
    "hysfull": {
        "name": "123（ひふみ）",
        "queries": ["ひふみ コンプリート 番台", "123 コンプリート 番台 ひふみ"],
        "handle_patterns": ["123"],
        "ng_keywords": [],
    },
    "yasuda": {
        "name": "やすだ",
        "queries": ["やすだ コンプリート 番台"],
        "handle_patterns": ["yasuda"],
        "ng_keywords": [],
    },
    "dstation": {
        "name": "D'STATION",
        "queries": ["Dステーション コンプリート 番台", "dstation コンプリート 番台"],
        "handle_patterns": ["dstation", "d_station"],
        "ng_keywords": [],
    },
    "abc": {
        "name": "ABC",
        "queries": ["ABC コンプリート 番台 パチスロ"],
        "handle_patterns": ["abc_"],
        "ng_keywords": ["abcmart", "abc_tv", "abcnews"],
    },
    "kicona": {
        "name": "キコーナ",
        "queries": ["キコーナ コンプリート 番台"],
        "handle_patterns": ["kicona"],
        "ng_keywords": [],
    },
    "mgm": {
        "name": "MGM",
        "queries": ["MGM コンプリート 番台 パチスロ"],
        "handle_patterns": ["mgm"],
        "ng_keywords": ["mgmresorts", "mgmcinema"],
    },
    "nikko": {
        "name": "ニッコー",
        "queries": ["ニッコー コンプリート 番台 パチスロ"],
        "handle_patterns": ["nikko", "niccou"],
        "ng_keywords": [],
    },
    "veam": {
        "name": "VEAM",
        "queries": ["VEAM コンプリート 番台", "ビーム コンプリート 番台"],
        "handle_patterns": ["veam"],
        "ng_keywords": [],
    },
    "plateau": {
        "name": "プラトー",
        "queries": ["プラトー コンプリート 番台 パチスロ"],
        "handle_patterns": ["plateau"],
        "ng_keywords": [],
    },
    "rakuichi": {
        "name": "楽市",
        "queries": ["楽市 コンプリート 番台"],
        "handle_patterns": ["rakuichi"],
        "ng_keywords": [],
    },
    "mj": {
        "name": "MJ",
        "queries": ["MJ コンプリート 番台 パチスロ"],
        "handle_patterns": ["mj"],
        "ng_keywords": ["mjst", "mjgolf"],
    },
}

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def load_store_handles() -> dict:
    if STORE_HANDLES_JSON.exists():
        return json.loads(STORE_HANDLES_JSON.read_text(encoding="utf-8"))
    return {}


def save_store_handles(sh: dict) -> None:
    STORE_HANDLES_JSON.write_text(
        json.dumps(sh, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_handles_from_text(text: str) -> list[str]:
    return [m.lower() for m in re.findall(r"@([A-Za-z0-9_]+)", text)]


def handle_matches_chain(handle: str, chain: dict) -> bool:
    handle_lower = handle.lower()
    if any(ng in handle_lower for ng in chain.get("ng_keywords", [])):
        return False
    return any(pat in handle_lower for pat in chain.get("handle_patterns", []))


def search_x(page, query: str, max_results: int = 30) -> list[dict]:
    results = []
    try:
        encoded = query.replace(" ", "%20").replace("#", "%23")
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for _ in range(4):
            articles = page.query_selector_all("article[data-testid='tweet']")
            if len(articles) >= min(10, max_results):
                break
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(2000)

        articles = page.query_selector_all("article[data-testid='tweet']")
        for art in articles[:max_results]:
            try:
                link_el = art.query_selector("a[href*='/status/']")
                href = link_el.get_attribute("href") if link_el else ""
                handle_m = re.search(r"x\.com/([^/]+)/status", "https://x.com" + href) if href else None
                handle = handle_m.group(1).lower() if handle_m else ""

                text_el = art.query_selector("[data-testid='tweetText']")
                text = text_el.inner_text() if text_el else ""

                if handle:
                    results.append({"handle": handle, "text": text})
            except Exception:
                pass
    except Exception as e:
        print(f"  ⚠️ 検索エラー ({query[:40]}): {e}")
    return results


def discover_chain(page, chain_key: str, chain: dict, existing: set) -> dict[str, dict]:
    discovered: dict[str, dict] = {}

    for query in chain["queries"]:
        print(f"  🔍 {query}")
        results = search_x(page, query, max_results=50)
        for r in results:
            h = r["handle"]
            if not h or h in existing or h in discovered:
                continue
            if handle_matches_chain(h, chain):
                discovered[h] = {
                    "store": f"{chain['name']}（自動発掘）",
                    "x_url": f"https://x.com/{h}",
                    "count": 0,
                    "type": "store",
                }
                print(f"    ✅ @{h}")

            # ツイート本文から @mention も拾う
            for mention in extract_handles_from_text(r["text"]):
                if mention in existing or mention in discovered:
                    continue
                if handle_matches_chain(mention, chain):
                    discovered[mention] = {
                        "store": f"{chain['name']}（自動発掘）",
                        "x_url": f"https://x.com/{mention}",
                        "count": 0,
                        "type": "store",
                    }
                    print(f"    ✅ @{mention} (mention)")

        time.sleep(2)

    return discovered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--chain", type=str, default="",
                        help="特定チェーンのみ実行 (例: dynam,maruhan)")
    parser.add_argument("--dry-run", action="store_true", help="store_handles.json を更新しない")
    args = parser.parse_args()

    if not HAS_PLAYWRIGHT:
        print("❌ playwright not installed.")
        sys.exit(1)

    sh = load_store_handles()
    existing = {h.lower() for h in sh.keys()}
    print(f"📋 store_handles 読み込み: {len(sh)}件")

    # 対象チェーンの絞り込み
    if args.chain:
        keys = [k.strip() for k in args.chain.split(",")]
        target_chains = {k: CHAIN_DEFS[k] for k in keys if k in CHAIN_DEFS}
    else:
        target_chains = CHAIN_DEFS

    print(f"🎯 対象チェーン: {len(target_chains)}件\n")

    all_discovered: dict[str, dict] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # X ログイン
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from fetch_complete_info import _load_session, _login_with_credentials
            _load_session(ctx)
            page.goto("https://x.com/home", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "login" in page.url or "flow" in page.url:
                x_user = os.environ.get("X_USERNAME", "")
                x_pass = os.environ.get("X_PASSWORD", "")
                if x_user and x_pass:
                    _login_with_credentials(page, x_user, x_pass)
                else:
                    print("❌ X_USERNAME/X_PASSWORD 未設定")
                    sys.exit(1)
        except Exception as e:
            print(f"⚠️ ログイン: {e}")

        for chain_key, chain in target_chains.items():
            print(f"\n🔎 チェーン: {chain['name']} ({chain_key})")
            discovered = discover_chain(page, chain_key, chain, existing | {k.lower() for k in all_discovered})
            all_discovered.update(discovered)
            print(f"  → 今回発見: {len(discovered)}件")

        ctx.close()

    # 結果集計
    print(f"\n📊 発掘結果: {len(all_discovered)}件")

    if not args.dry_run and all_discovered:
        for h, info in all_discovered.items():
            sh[h] = info
        save_store_handles(sh)
        print(f"✅ store_handles.json 更新: {len(sh)}件 (+{len(all_discovered)}件)")
    elif args.dry_run:
        print("dry-run: store_handles.json は更新しません")
        for h, info in all_discovered.items():
            print(f"  @{h}: {info['store']}")
    else:
        print("新規候補なし")


if __name__ == "__main__":
    main()
