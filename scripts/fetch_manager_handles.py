"""
店長・副店長・主任アカウント自動発掘スクリプト

処理:
  1. 既知の店舗アカウントのタイムラインを巡回
  2. 投稿文から @mention や manager_x_url の候補を抽出
  3. キーワード検索: "店長 コンプリート 番台" "tencho コンプリート"
  4. 発掘した候補を store_handles.json に type=manager で追加

使用例:
    python scripts/fetch_manager_handles.py --headless
    python scripts/fetch_manager_handles.py --headless --max-stores 50
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

# 店長アカウントの可能性を示すキーワード（handle / bio に含む場合）
MANAGER_KEYWORDS = [
    "tencho", "tenchou", "店長", "副店長", "主任", "店長公式",
    "tentyou", "storemanager", "store_manager",
]

# 明らかに店長アカウントでないキーワード（false positive 除去）
NG_KEYWORDS = ["公式", "official", "企業", "corp", "pr", "news"]

# 店長系キーワード収集クエリ
MANAGER_SEARCH_QUERIES = [
    "店長 コンプリート機能発動 番台",
    "店長 コンプリート達成 番台",
    "tencho コンプリート 番台",
    "副店長 コンプリート 番台",
    "当店長 コンプリート 番台",
    "うちの店長 コンプリート 番台",
    "店長より コンプリート 番台",
]

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
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
    """ツイート本文から @mention を抽出"""
    return [m.lower() for m in re.findall(r"@([A-Za-z0-9_]+)", text)]


def looks_like_manager(handle: str, bio: str = "") -> bool:
    """handle または bio が店長アカウントらしいか判定"""
    combined = (handle + " " + bio).lower()
    if any(ng in combined for ng in NG_KEYWORDS):
        return False
    return any(kw in combined for kw in MANAGER_KEYWORDS)


def search_x(page, query: str, max_results: int = 20) -> list[dict]:
    """X で query を検索し、ヒットしたツイートのメタデータを返す"""
    results = []
    try:
        encoded = query.replace(" ", "%20").replace("#", "%23")
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for _ in range(3):
            articles = page.query_selector_all("article[data-testid='tweet']")
            if len(articles) >= min(5, max_results):
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
                    results.append({"handle": handle, "text": text, "url": href})
            except Exception:
                pass
    except Exception as e:
        print(f"  ⚠️ 検索エラー ({query[:30]}...): {e}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-stores", type=int, default=30,
                        help="既知店舗アカウントのうち巡回する件数 (default=30)")
    parser.add_argument("--dry-run", action="store_true", help="store_handles.json を更新しない")
    args = parser.parse_args()

    if not HAS_PLAYWRIGHT:
        print("❌ playwright not installed.")
        sys.exit(1)

    sh = load_store_handles()
    existing_handles = {h.lower() for h in sh.keys()}
    existing_managers = {h.lower() for h, info in sh.items()
                         if isinstance(info, dict) and info.get("type") == "manager"}

    print(f"📋 store_handles 読み込み: {len(sh)}件 (manager: {len(existing_managers)}件)")

    # 上位店舗アカウント（巡回対象）
    store_accounts = sorted(
        [(h, info) for h, info in sh.items()
         if isinstance(info, dict) and info.get("count", 0) >= 1
         and info.get("type", "store") == "store"],
        key=lambda x: -x[1].get("count", 0)
    )[:args.max_stores]

    discovered: dict[str, dict] = {}

    launch_opts = {"headless": args.headless}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_opts)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # X ログイン
        try:
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
            print(f"⚠️ ログイン処理: {e}")

        # Step 1: キーワード検索で店長アカウントを発掘
        print(f"\n🔍 Step 1: キーワード検索 ({len(MANAGER_SEARCH_QUERIES)}件)")
        for q in MANAGER_SEARCH_QUERIES:
            print(f"  検索: {q}")
            results = search_x(page, q, max_results=30)
            for r in results:
                h = r["handle"]
                if h and h not in existing_handles and h not in discovered:
                    if looks_like_manager(h, r.get("text", "")):
                        # ツイート本文から @mention（店舗アカウントか？）を確認
                        mentioned = extract_handles_from_text(r.get("text", ""))
                        store_name = ""
                        for m in mentioned:
                            if m in {s.lower() for s, _ in store_accounts}:
                                store_name = sh.get(m, {}).get("store", "") if m in sh else ""
                                break
                        discovered[h] = {
                            "type": "manager",
                            "store": store_name,
                            "count": 0,
                            "x_url": f"https://x.com/{h}",
                        }
                        print(f"    ✅ 発見: @{h} (store={store_name or '?'})")
            time.sleep(2)

        # Step 2: 上位店舗タイムラインの @mention から店長候補抽出
        print(f"\n🔍 Step 2: 上位{len(store_accounts)}店舗タイムライン巡回")
        for handle, info in store_accounts:
            print(f"  @{handle} ({info.get('store', '?')})...")
            results = search_x(page, f"from:{handle} (店長 OR tencho OR manager)", max_results=10)
            for r in results:
                # 本文中の @mention を抽出
                mentions = extract_handles_from_text(r.get("text", ""))
                for m in mentions:
                    if m not in existing_handles and m not in discovered:
                        if looks_like_manager(m):
                            discovered[m] = {
                                "type": "manager",
                                "store": info.get("store", ""),
                                "count": 0,
                                "x_url": f"https://x.com/{m}",
                            }
                            print(f"    ✅ 発見: @{m} (store={info.get('store','?')})")
            time.sleep(1)

        ctx.close()

    # 結果集計
    print(f"\n📊 発掘結果: {len(discovered)}件の新規店長候補")

    if not args.dry_run and discovered:
        for h, info in discovered.items():
            sh[h] = info
        save_store_handles(sh)
        print(f"✅ store_handles.json 更新: {len(sh)}件 (+{len(discovered)}件)")
    elif args.dry_run:
        print("dry-run モード: store_handles.json は更新しません")
        for h, info in discovered.items():
            print(f"  @{h}: {info}")
    else:
        print("新規店長候補なし")

    current_managers = sum(1 for _, i in sh.items() if isinstance(i, dict) and i.get("type") == "manager")
    print(f"\n📋 manager アカウント: {len(existing_managers)}件 → {current_managers}件")


if __name__ == "__main__":
    main()
