#!/usr/bin/env python3
"""
complete_info.json の画像・動画なしエントリに対して、X（Twitter）から補完するスクリプト。

使い方:
  python scripts/fetch_complete_images.py              # 全件の画像なしを処理
  python scripts/fetch_complete_images.py --limit 50   # 最大50件ずつ処理
  python scripts/fetch_complete_images.py --headless   # ヘッドレスモード
  python scripts/fetch_complete_images.py --force      # 画像あり エントリも再取得
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


def fetch_tweet_media(page, tweet_url: str) -> dict:
    """Xのツイートページから画像・動画URLを抽出"""
    result = {"images": [], "video_url": None}
    captured_video_urls: list[str] = []

    def on_request(request):
        url = request.url
        if "video.twimg.com" in url and ("/ext_tw_video/" in url or "/tweet_video/" in url or "/amplify_video/" in url):
            captured_video_urls.append(url)

    page.on("request", on_request)

    try:
        page.goto(tweet_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)  # 動画プレーヤー読み込み待ち

        # ── 画像 ─────────────────────────────────────────────
        og = page.evaluate("""() => {
            const m = document.querySelector('meta[property="og:image"]');
            return m ? m.getAttribute('content') : null;
        }""")
        if og and "pbs.twimg.com" in og:
            og_large = re.sub(r'\?.*$', '', og) + "?format=jpg&name=large"
            result["images"].append(og_large)

        img_urls = page.evaluate("""() => {
            const imgs = [...document.querySelectorAll('img[src*="pbs.twimg.com/media"]')];
            return imgs.map(img => img.src).filter(s => s.includes('/media/'));
        }""")
        for url in img_urls:
            clean = re.sub(r'\?.*$', '', url) + "?format=jpg&name=large"
            if clean not in result["images"]:
                result["images"].append(clean)
        result["images"] = result["images"][:4]

        # ── 動画 ─────────────────────────────────────────────
        # 1. og:video メタタグ（MP4 の場合あり）
        og_video = page.evaluate("""() => {
            const m = document.querySelector('meta[property="og:video:url"], meta[property="og:video"]');
            return m ? m.getAttribute('content') : null;
        }""")
        if og_video and "video.twimg.com" in og_video:
            result["video_url"] = og_video

        # 2. DOM の <video src> （tweet_video など）
        if not result["video_url"]:
            video_src = page.evaluate("""() => {
                const v = document.querySelector('video[src]');
                return v ? v.getAttribute('src') : null;
            }""")
            if video_src and "video.twimg.com" in video_src:
                result["video_url"] = video_src

        # 3. ネットワークキャプチャから取得
        if not result["video_url"] and captured_video_urls:
            # MP4 を優先、なければ m3u8（HLS）
            mp4_urls = [u for u in captured_video_urls if ".mp4" in u and "m3u8" not in u]
            m3u8_urls = [u for u in captured_video_urls if ".m3u8" in u]

            if mp4_urls:
                # 最高画質（URLに含まれる解像度で選択）
                def video_quality(url: str) -> int:
                    m = re.search(r'/(\d+)x(\d+)/', url)
                    return int(m.group(1)) * int(m.group(2)) if m else 0
                result["video_url"] = max(mp4_urls, key=video_quality)
            elif m3u8_urls:
                # マスタープレイリスト優先（"master" が含まれるURL）
                master = [u for u in m3u8_urls if "master" in u.lower() or "master_1200" in u.lower()]
                result["video_url"] = master[0] if master else m3u8_urls[0]

    except Exception as e:
        log(f"  ⚠️  メディア取得エラー: {e}")
    finally:
        page.remove_listener("request", on_request)

    return result


def main():
    parser = argparse.ArgumentParser(description="コンプリート情報の画像・動画補完")
    parser.add_argument("--limit", type=int, default=200, help="最大処理件数（デフォルト200）")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    parser.add_argument("--force", action="store_true", help="画像ありエントリも再取得")
    args = parser.parse_args()

    data = json.loads(COMPLETE_JSON.read_text(encoding="utf-8"))

    # 画像も動画もないエントリを対象（force時は全件）
    if args.force:
        targets = [e for e in data if e.get("x_url")]
    else:
        targets = [e for e in data if not e.get("image_url") and not e.get("video_url") and e.get("x_url")]

    log(f"メディア補完対象: {len(targets)}件 / 全{len(data)}件")
    if not targets:
        log("補完対象なし")
        return

    targets = targets[:args.limit]
    log(f"処理件数: {len(targets)}件")

    id_to_entry = {e["id"]: e for e in data}
    changed = 0

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ログイン確認
        try:
            page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "login" in page.url.lower() or "flow" in page.url.lower():
                log("❌ Xにログインできていません。")
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

            media = fetch_tweet_media(page, x_url)
            updated = False

            if media["images"]:
                id_to_entry[eid]["image_url"] = media["images"][0]
                if len(media["images"]) > 1:
                    id_to_entry[eid]["images"] = media["images"]
                log(f"    🖼  画像: {media['images'][0][:80]}")
                updated = True

            if media["video_url"]:
                id_to_entry[eid]["video_url"] = media["video_url"]
                fmt = "mp4" if ".mp4" in media["video_url"] else "m3u8"
                log(f"    🎬 動画({fmt}): {media['video_url'][:80]}")
                updated = True

            if updated:
                changed += 1
            else:
                log("    ⚠️  メディアなし")

            time.sleep(1.5)

        ctx.close()

    if changed:
        COMPLETE_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"\n✅ complete_info.json 更新: {changed}件にメディア追加")
    else:
        log("\n変更なし")


if __name__ == "__main__":
    main()
