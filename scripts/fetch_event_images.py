#!/usr/bin/env python3
"""
events_public.json で X URL はあるが image_url が空のイベントに対して
X のツイートページから画像URLを取得して補完するスクリプト。

Usage:
    python scripts/fetch_event_images.py            # 全対象を補完
    python scripts/fetch_event_images.py --limit 50 # 最大50件
    python scripts/fetch_event_images.py --days 7   # 直近7日分のみ
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

try:
    import browser_cookie3
    HAS_COOKIE3 = True
except ImportError:
    HAS_COOKIE3 = False

EVENTS_JSON = Path(__file__).parent.parent / "public/events_public.json"


def log(msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def _get_x_cookies() -> list[dict]:
    """Chrome の X クッキーを取得。"""
    if os.environ.get("X_AUTH_TOKEN"):
        return [
            {"name": "auth_token", "value": os.environ["X_AUTH_TOKEN"], "domain": ".x.com", "path": "/"},
            {"name": "ct0",        "value": os.environ.get("X_CT0", ""), "domain": ".x.com", "path": "/"},
        ]
    if HAS_COOKIE3:
        try:
            raw = browser_cookie3.chrome(domain_name=".x.com")
            return [
                {"name": c.name, "value": c.value, "domain": c.domain or ".x.com", "path": c.path or "/"}
                for c in raw if c.name in ("auth_token", "ct0", "twid")
            ]
        except Exception:
            pass
    return []


def get_tweet_image(page, tweet_url: str) -> str:
    """指定ツイートページから最初のメディア画像URLを取得。"""
    # デフォルト画像・プレースホルダーURL（これらは除外）
    PLACEHOLDER_PATTERNS = [
        "rweb/ssr/default",
        "abs.twimg.com/rweb",
        "profile_images",
        "profile_banners",
        "emoji",
    ]

    try:
        page.goto(tweet_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # pbs.twimg.com/media 画像を探す（最優先）
        imgs = page.query_selector_all('img[src*="pbs.twimg.com/media"]')
        for img in imgs:
            src = img.get_attribute("src") or ""
            if not src:
                continue
            if any(p in src for p in PLACEHOLDER_PATTERNS):
                continue
            # 高解像度版を取得
            src = re.sub(r'\?.*$', '', src) + "?format=jpg&name=large"
            return src

        # JavaScript で画像を検索（遅延読み込み対策）
        js_imgs = page.evaluate("""
            () => Array.from(document.querySelectorAll('img'))
                .map(img => img.src)
                .filter(src => src.includes('pbs.twimg.com/media'))
        """)
        for src in js_imgs:
            if not any(p in src for p in PLACEHOLDER_PATTERNS):
                src = re.sub(r'\?.*$', '', src) + "?format=jpg&name=large"
                return src

        # card画像確認（OGP）- デフォルト画像は除外
        meta = page.query_selector('meta[property="og:image"]')
        if meta:
            content = meta.get_attribute("content") or ""
            if content and "pbs.twimg.com" in content and not any(p in content for p in PLACEHOLDER_PATTERNS):
                return content

    except Exception as e:
        log(f"  ⚠️  {tweet_url}: {e}")
    return ""


def main():
    parser = argparse.ArgumentParser(description="イベント画像の補完")
    parser.add_argument("--limit", type=int, default=200, help="最大処理件数")
    parser.add_argument("--days", type=int, default=30, help="直近N日分のみ対象")
    parser.add_argument("--headless", action="store_true", default=True, help="ヘッドレスモード")
    args = parser.parse_args()

    # データ読み込み
    data = json.loads(EVENTS_JSON.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", [])

    # 対象フィルタリング: X URLあり&画像なし
    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%m/%d")
    targets = [
        e for e in events
        if e.get("x_url") and not e.get("image_url") and e.get("date", "") >= cutoff
    ]
    targets = targets[:args.limit]

    log(f"対象: {len(targets)}件 (直近{args.days}日、最大{args.limit}件)")

    if not targets:
        log("補完対象なし")
        return

    updated = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        cookies = _get_x_cookies()
        if cookies:
            ctx.add_cookies(cookies)
            log(f"✅ Cookie {len(cookies)}個注入")
        else:
            log("⚠️  X Cookie なし（ログイン不要な画像のみ取得）")

        page = ctx.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        for i, ev in enumerate(targets):
            url = ev["x_url"]
            log(f"[{i+1}/{len(targets)}] {ev.get('store','')[:20]} {ev.get('date','')} {url[:60]}")
            img = get_tweet_image(page, url)
            if img:
                ev["image_url"] = img
                log(f"  → {img[:70]}")
                updated += 1
            else:
                log(f"  → 画像なし")
            time.sleep(2.0)

        page.close()
        ctx.close()
        browser.close()

    log(f"\n✅ 補完完了: {updated}/{len(targets)}件")

    # 保存
    if updated > 0:
        if isinstance(data, dict):
            data["events"] = events
            EVENTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            EVENTS_JSON.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"✅ {EVENTS_JSON} を更新")


if __name__ == "__main__":
    main()
