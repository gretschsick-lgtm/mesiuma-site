#!/usr/bin/env python3
"""
complete_info.json の text="" エントリを対象に、ツイートURLを直接訪問してテキストを再取得する。

使い方:
  python scripts/recrawl_empty_text.py              # ヘッドフル
  python scripts/recrawl_empty_text.py --headless   # ヘッドレス
  python scripts/recrawl_empty_text.py --dry-run    # 変更なし / 結果だけ出力
  python scripts/recrawl_empty_text.py --limit 10   # 最大10件のみ処理
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

ROOT = Path(__file__).parent.parent
COMPLETE_JSON = ROOT / "public" / "complete_info.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"

sys.path.insert(0, str(Path(__file__).parent))
from fetch_complete_info import is_store_tweet, extract_machine, extract_slot_number


def log(msg: str) -> None:
    print(msg, flush=True)


def _extract_text_from_tweet_page(page) -> str:
    """単一ツイートページからテキストを多段フォールバックで抽出する。"""
    # ターゲットは最初の article (ページの主ツイート)
    try:
        article = page.query_selector('article[data-testid="tweet"]')
        if not article:
            return ""
    except Exception:
        return ""

    for sel in ['[data-testid="tweetText"]', '[lang]']:
        el = article.query_selector(sel)
        if not el:
            continue
        try:
            t = (el.inner_text() or "").strip()
            if len(t) > 10:
                return t
        except Exception:
            pass
        try:
            t = (el.text_content() or "").strip()
            if len(t) > 10:
                return t
        except Exception:
            pass

    try:
        t = article.evaluate(
            "el => {"
            "  const tw = el.querySelector('[data-testid=\"tweetText\"]');"
            "  if (tw) { const v = tw.innerText || tw.textContent || '';"
            "    if (v.trim().length > 10) return v.trim(); }"
            "  const lang = el.querySelector('[lang]');"
            "  if (lang) { const v = lang.innerText || lang.textContent || '';"
            "    if (v.trim().length > 10) return v.trim(); }"
            "  return '';"
            "}"
        )
        t = (t or "").strip()
        if len(t) > 10:
            return t
    except Exception:
        pass

    return ""


def fetch_tweet_text(page, tweet_url: str) -> str:
    """ツイートページを訪問してテキストを返す。失敗時は空文字。"""
    try:
        page.goto(tweet_url, timeout=20000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        return ""

    cur = page.url.lower()
    if "login" in cur or "/flow/" in cur:
        raise RuntimeError("LOGIN_REQUIRED")

    # 主ツイートが表示されるまで待機（最大8秒）
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
    except PlaywrightTimeout:
        return ""

    page.wait_for_timeout(1500)

    text = _extract_text_from_tweet_page(page)

    # hydration 待機後リトライ
    if not text:
        page.wait_for_timeout(2000)
        text = _extract_text_from_tweet_page(page)

    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="変更を保存しない")
    parser.add_argument("--limit", type=int, default=0, help="処理上限件数（0=全件）")
    args = parser.parse_args()

    data = json.loads(COMPLETE_JSON.read_text(encoding="utf-8"))
    targets = [e for e in data if not (e.get("text") or "").strip() and e.get("x_url")]
    log(f"text空エントリ: {len(targets)}件 / 全{len(data)}件")

    if not targets:
        log("再クロール対象なし")
        return

    if args.limit > 0:
        targets = targets[:args.limit]
        log(f"処理上限: {args.limit}件")

    id_to_entry = {e["id"]: e for e in data}
    recovered = 0
    failed = 0

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PLAYWRIGHT_PROFILE),
            headless=args.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ログイン確認
        try:
            page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "login" in page.url.lower() or "flow" in page.url.lower():
                log("❌ Xにログインできていません")
                ctx.close()
                sys.exit(1)
            log("✅ Xログイン確認OK")
        except PlaywrightTimeout:
            log("⚠️  ログイン確認タイムアウト — 続行")

        for i, entry in enumerate(targets, 1):
            eid = entry["id"]
            x_url = entry.get("x_url", "")
            store = entry.get("store", "")
            machine = entry.get("machine", "")
            date = entry.get("date", "")

            log(f"  [{i}/{len(targets)}] {date} {store} / {machine}  {x_url}")

            try:
                text = fetch_tweet_text(page, x_url)
            except RuntimeError as e:
                if "LOGIN_REQUIRED" in str(e):
                    log("❌ セッション切れ — 中断")
                    break
                text = ""
            except Exception as e:
                log(f"    ⚠️  取得エラー: {e}")
                text = ""

            if text and is_store_tweet(text):
                log(f"    ✅ テキスト回復: [{text[:60]}...]")
                if not args.dry_run:
                    id_to_entry[eid]["text"] = text[:250].replace("\n", " ")
                    # machine/slot_number も再抽出して補完
                    if not id_to_entry[eid].get("machine"):
                        m = extract_machine(text)
                        if m:
                            id_to_entry[eid]["machine"] = m
                    if not id_to_entry[eid].get("slot_number"):
                        s = extract_slot_number(text)
                        if s:
                            id_to_entry[eid]["slot_number"] = s
                recovered += 1
            elif text:
                log(f"    ⚠️  テキスト取得済みだが店舗ツイートと判定されず: [{text[:60]}]")
                failed += 1
            else:
                log("    ❌ テキスト取得失敗（削除済み/非公開の可能性）")
                failed += 1

            time.sleep(1.5)

        ctx.close()

    log(f"\n=== 再クロール結果 ===")
    log(f"回復成功: {recovered}件 / 対象{len(targets)}件")
    log(f"取得失敗: {failed}件")

    if recovered > 0 and not args.dry_run:
        COMPLETE_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log(f"✅ complete_info.json 更新: {recovered}件のテキストを補完")
    elif args.dry_run:
        log("（dry-run: ファイル変更なし）")


if __name__ == "__main__":
    main()
