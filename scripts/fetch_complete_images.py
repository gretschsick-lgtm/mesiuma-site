#!/usr/bin/env python3
"""
complete_info.json の画像なしエントリに対して、X（Twitter）から画像URLを補完するスクリプト。

使い方:
  python scripts/fetch_complete_images.py              # 全件の画像なしを処理
  python scripts/fetch_complete_images.py --limit 50   # 最大50件ずつ処理
  python scripts/fetch_complete_images.py --headless   # ヘッドレスモード
"""

import argparse
import json
import re
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
    raise SystemExit(1)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

COMPLETE_JSON = Path(__file__).parent.parent / "public/complete_info.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"


def log(msg: str) -> None:
    print(msg, flush=True)


def launch_browser(pw, headless: bool = True):
    ctx = pw.chromium.launch_persistent_context(
        str(PLAYWRIGHT_PROFILE),
        headless=headless,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
    )
    return ctx


def fetch_tweet_images(page, tweet_url: str) -> list[str]:
    """Xのツイートページから画像URLを抽出"""
    try:
        page.goto(tweet_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        images = []

        # og:image メタタグ
        og = page.evaluate("""() => {
            const m = document.querySelector('meta[property="og:image"]');
            return m ? m.getAttribute('content') : null;
        }""")
        if og and "pbs.twimg.com" in og:
            # 大サイズに変換
            og_large = re.sub(r'\?.*$', '', og) + "?format=jpg&name=large"
            images.append(og_large)

        # ツイート内の画像（Twitter Card）
        img_urls = page.evaluate("""() => {
            const imgs = [...document.querySelectorAll('img[src*="pbs.twimg.com/media"]')];
            return imgs.map(img => img.src).filter(s => s.includes('/media/'));
        }""")
        for url in img_urls:
            clean = re.sub(r'\?.*$', '', url) + "?format=jpg&name=large"
            if clean not in images:
                images.append(clean)

        return images[:4]  # 最大4枚

    except Exception as e:
        log(f"  ⚠️  画像取得エラー: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="コンプリート情報の画像補完")
    parser.add_argument("--limit", type=int, default=200, help="最大処理件数（デフォルト200）")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    parser.add_argument("--force", action="store_true", help="画像あり エントリも再取得")
    args = parser.parse_args()

    data = json.loads(COMPLETE_JSON.read_text(encoding="utf-8"))

    # 画像なしのエントリを抽出
    if args.force:
        targets = [e for e in data if e.get("x_url")]
    else:
        targets = [e for e in data if not e.get("image_url") and e.get("x_url")]

    log(f"画像補完対象: {len(targets)}件 / 全{len(data)}件")
    if not targets:
        log("補完対象なし")
        return

    # limit適用
    targets = targets[:args.limit]
    log(f"処理件数: {len(targets)}件")

    # IDでO(1)引き当て
    id_to_entry = {e["id"]: e for e in data}

    changed = 0

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # Xにログインされているか確認
        try:
            page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "login" in page.url.lower() or "flow" in page.url.lower():
                log("❌ Xにログインできていません。ブラウザを開いてログインしてください。")
                ctx.close()
                return
            log("✅ Xログイン確認OK")
        except PlaywrightTimeout:
            log("⚠️  ログイン確認タイムアウト — 続行")

        for i, entry in enumerate(targets, 1):
            eid = entry["id"]
            x_url = entry.get("x_url", "")
            store = entry.get("store", "")
            machine = entry.get("machine", "")

            log(f"  [{i}/{len(targets)}] {store} / {machine}")

            images = fetch_tweet_images(page, x_url)
            if images:
                id_to_entry[eid]["image_url"] = images[0]
                if len(images) > 1:
                    id_to_entry[eid]["images"] = images
                changed += 1
                log(f"    ✅ 画像取得: {images[0][:80]}")
            else:
                log(f"    ⚠️  画像なし")

            time.sleep(1.5)

        ctx.close()

    if changed:
        COMPLETE_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"\n✅ complete_info.json 更新: {changed}件に画像追加")
    else:
        log("\n変更なし")


if __name__ == "__main__":
    main()
