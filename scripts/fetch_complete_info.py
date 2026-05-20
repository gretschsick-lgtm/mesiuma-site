#!/usr/bin/env python3
"""
X (Twitter) から「コンプリート」「全台コンプ」情報を収集して
public/complete_info.json を生成する。

今日のコンプリート一覧: 店舗名・機種名・画像URL を抽出。

Usage:
    python scripts/fetch_complete_info.py
    python scripts/fetch_complete_info.py --headless
    python scripts/fetch_complete_info.py --date 2026-05-20  # 特定日付
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
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

try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
COMPLETE_JSON   = Path(__file__).parent.parent / "public/complete_info.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"

# ---------------------------------------------------------------------------
# 検索クエリ（コンプリート関連）
# ---------------------------------------------------------------------------
COMPLETE_QUERIES = [
    "コンプリート機能 スロット",
    "コンプリート達成 スロット",
    "コンプリート機能発動",
    "コンプリート機能作動",
    "全台コンプリート スロット",
    "全台コンプ パチスロ",
    "全台制覇 スロット",
    "全台完走 スロット",
    "スマスロ コンプリート 達成",
    "スマスロ コンプリート 機能",
    "コンプリート おめでとう スロット",
    "コンプ達成 パチスロ",
    "コンプリート 番台 スロット",
]

# ノイズ除外キーワード（これらを含む場合は除外）
NOISE_KEYWORDS = [
    "コンプリート率が基準値",
    "ガチャ全て",
    "ガチャコンプ",
    "ミッションコンプリート",
    "コンプリートする！パチスロ生配信",
    "コレクションコンプ",
    "youtube.com/live",
    "ブログへは",
    "next.line",
]

# 機種名パターン（優先度順）
MACHINE_PATTERNS = [
    # 『機種名』にて → 最高精度
    r"[『「]([^』」]{3,30})[』」](?:にて|で|の)\s*(?:コンプリート|コンプ)",
    # 「機種名」コンプリート
    r"[『「【]([^』」】]{3,30})[』」】]\s*(?:コンプリート|コンプ|達成)",
    # スマスロ○○ / Lパチスロ○○ / パチスロ○○
    r"(?:スマスロ|Lパチスロ|パチスロ|スマパチ)\s*[　]?([^\s　\n#「」【】、。！!]{3,25}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$))",
    # L○○（スマスロ機種名）
    r"\bL([^\s　\n#「」【】、。！!]{3,20}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|\d+番台))",
    # ○○番台 機種名
    r"\d+番台\s*(?:の\s*)?([^\s　\n#「」【】、。！!]{3,25}?)(?=\s*(?:にて|で|が|コンプ|\n))",
    # 北斗/バジリスク/ミリオンゴッド 等の有名機種
    r"(北斗[^\s　\n#「」【】、。！!]{1,15}(?:章|篇|転生)?[^\s　\n#]{0,5})",
    r"(バジリスク[^\s　\n#「」【】、。！!]{0,15})",
    r"(ミリオンゴッド[^\s　\n#「」【】、。！!]{0,15})",
    r"(ゴッドイーター[^\s　\n#「」【】、。！!]{0,15})",
    r"(東京喰種[^\s　\n#「」【】、。！!]{0,10})",
    r"(ヴァルヴレイヴ[^\s　\n#「」【】、。！!]{0,10})",
    r"(炎炎ノ消防隊[^\s　\n#「」【】、。！!]{0,10})",
    r"(攻殻機動隊[^\s　\n#「」【】、。！!]{0,10})",
    r"(カバネリ[^\s　\n#「」【】、。！!]{0,10})",
    r"(モンスターハンター[^\s　\n#「」【】、。！!]{0,15})",
    r"(ジャグラー[^\s　\n#「」【】、。！!]{0,10})",
    r"(ハナハナ[^\s　\n#「」【】、。！!]{0,10})",
    r"(まどか[^\s　\n#「」【】、。！!]{0,15})",
    r"(リゼロ|Re:ゼロ[^\s　\n#「」【】、。！!]{0,10})",
    r"(ファフナー[^\s　\n#「」【】、。！!]{0,10})",
    r"(コードギアス[^\s　\n#「」【】、。！!]{0,15})",
    r"(牙狼[^\s　\n#「」【】、。！!]{0,15})",
]

# 店舗名パターン（優先度順）
STORE_PATTERNS = [
    # ハッシュタグから店舗名（#〇〇店 / #〇〇ホール）
    r"#([^\s　\n#「」【】、。！!]{2,20}(?:店|ホール))",
    # 既存チェーン名
    r"(マルハン[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(キコーナ[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(ガイア[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(?:PIA|ピーアーク)[^\s　、。！!\n]{0,15}([^\s　、。！!\n]{0,10}(?:店|ホール))",
    r"(楽園[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(エスパス[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(ダイナム[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(ニラク[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(ワンダーランド[^\s　、。！!\n]{0,20}(?:店|ホール)?)",
    r"(キャッスル[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(アミューズ[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(ミリオン[^\s　、。！!\n]{0,15}(?:店|ホール))",
    r"(Dステーション[^\s　、。！!\n]{0,15}(?:店|ホール)?)",
    r"(キング[^\s　、。！!\n]{0,20}(?:店|ホール))",
    r"([^\s　、。！!\n]{2,10}(?:パチンコ|スロット)[^\s　、。！!\n]{0,10}(?:店|ホール))",
    # 「〇〇店です」パターン
    r"([^\s　\n「」【】]{2,15}店)(?:です|でございます|より|です♪|でした)",
    # 一般的な「〇〇店」パターン（最後の手段）
    r"([^\s　\n「」【】、。！!]{2,12}店)",
]


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def _get_chrome_cookies() -> list[dict]:
    if not HAS_BROWSER_COOKIE3:
        return []
    result = []
    try:
        jar = browser_cookie3.chrome(domain_name=".x.com")
        for c in jar:
            pw_cookie: dict = {
                "name": c.name,
                "value": c.value,
                "domain": c.domain if c.domain else ".x.com",
                "path": c.path or "/",
                "secure": bool(c.secure),
                "httpOnly": False,
                "sameSite": "None",
            }
            if c.expires:
                pw_cookie["expires"] = int(c.expires)
            result.append(pw_cookie)
        log(f"🍪 Chrome cookies: {len(result)}個")
    except Exception as e:
        log(f"⚠️  browser_cookie3 error: {e}")
    return result


def launch_browser(playwright, headless: bool):
    chromium = playwright.chromium
    PLAYWRIGHT_PROFILE.mkdir(parents=True, exist_ok=True)
    browser = chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        locale="ja-JP",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    cookies = _get_chrome_cookies()
    if cookies:
        ctx.add_cookies(cookies)
        log(f"✅ {len(cookies)}個のcookieを注入")
    else:
        log("⚠️  Chromeのcookieなし — Xログイン失敗の可能性あり")
    return ctx


def extract_machine_name(text: str) -> str:
    for pat in MACHINE_PATTERNS:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            # 短すぎるものや記号のみを除外
            if len(name) < 3 or re.match(r'^[!！?？\s#@]+$', name):
                continue
            # ノイズ（URL, 汎用テキスト）を除外
            if "http" in name or "youtube" in name.lower():
                continue
            # 「スロ」「パチスロ」だけは機種名として不適切
            if name in ("スロ", "パチスロ", "スマスロ", "スマパチ"):
                continue
            return name.strip()[:35]
    return ""


def extract_store_name(text: str) -> str:
    # ノイズ的な「店」を含む語句を除外
    STORE_NG = ["ご来店", "来店", "来店者", "のご来店", "閉店", "景品入荷",
                "空台", "本日", "入荷店", "感謝", "毎日", "通常"]

    for pat in STORE_PATTERNS:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            if len(name) < 3:
                continue
            if any(ng in name for ng in STORE_NG):
                continue
            if re.match(r'^\d+', name):  # 数字始まりは除外
                continue
            return name[:28]
    return ""


def extract_images(article) -> list[str]:
    imgs = []
    for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
        src = img.get_attribute("src") or ""
        # 高解像度版に変換
        if src and src not in imgs:
            src = re.sub(r'\?.*$', '?format=jpg&name=large', src)
            imgs.append(src)
    return imgs


def is_complete_tweet(text: str) -> bool:
    # 本物のコンプリート報告キーワード
    valid_keywords = [
        "コンプリート機能", "コンプリート達成", "コンプリートが出ました",
        "コンプリート作動", "コンプリート発動", "コンプ達成",
        "全台コンプリート", "全台コンプ", "全台制覇", "全台完走",
        "コンプリートおめでとう", "コンプおめ",
        "でコンプリート", "がコンプリート", "のコンプリート",
        "2機種がコンプリート", "コンプリート 達成",
    ]
    if not any(kw in text for kw in valid_keywords):
        return False

    # ノイズ除外
    if any(ng in text for ng in NOISE_KEYWORDS):
        return False

    return True


def parse_tweet(text: str, tweet_url: str, images: list[str], today_str: str) -> dict | None:
    if not is_complete_tweet(text):
        return None

    store = extract_store_name(text)
    machine = extract_machine_name(text)

    # 店舗か機種、少なくとも1つは必要
    if not store and not machine:
        return None

    # ツイートから日付を推定
    tweet_date = today_str
    m = re.search(r'(\d{1,2})[/／](\d{1,2})', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        tweet_date = f"{datetime.now().year}-{month:02d}-{day:02d}"

    entry_id = hashlib.md5(f"{tweet_url}".encode()).hexdigest()[:12]

    return {
        "id": entry_id,
        "date": tweet_date,
        "store": store,
        "machine": machine,
        "text": text[:200].replace("\n", " "),
        "images": images[:4],
        "image_url": images[0] if images else "",
        "x_url": tweet_url,
        "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def scrape_complete_query(page, query: str, today_str: str, max_tweets: int = 50) -> list[dict]:
    results = []
    seen_urls: set[str] = set()

    encoded = query.replace(" ", "%20").replace("#", "%23")
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        log(f"  ⏱  Timeout: {query}")
        return results

    try:
        page.wait_for_selector(
            'article[data-testid="tweet"], article[role="article"]',
            timeout=10000
        )
    except PlaywrightTimeout:
        pass

    # スクロールで追加読み込み
    for _ in range(8):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1200)

    articles = page.query_selector_all('article[data-testid="tweet"]')
    if not articles:
        articles = page.query_selector_all('article[role="article"]')

    for article in articles[:max_tweets]:
        try:
            text = ""
            for txt_sel in ['[data-testid="tweetText"]', '[lang]']:
                el = article.query_selector(txt_sel)
                if el:
                    t = el.inner_text()
                    if len(t) > 10:
                        text = t
                        break

            tweet_url = ""
            time_el = article.query_selector("time")
            if time_el:
                href = time_el.evaluate("el => el.closest('a') ? el.closest('a').href : ''")
                if href and "status" in href:
                    tweet_url = href
            if not tweet_url:
                for lnk in article.query_selector_all('a[href*="/status/"]'):
                    href = lnk.get_attribute("href") or ""
                    if "/status/" in href:
                        tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                        break

            if not tweet_url or tweet_url in seen_urls:
                continue
            seen_urls.add(tweet_url)

            images = extract_images(article)
            entry = parse_tweet(text, tweet_url, images, today_str)
            if entry:
                results.append(entry)
                store_label = entry["store"] or "店舗不明"
                machine_label = entry["machine"] or "機種不明"
                img_count = len(entry["images"])
                log(f"    ✅ {store_label} / {machine_label} (画像{img_count}枚)")

        except Exception:
            continue

    return results


def load_existing(target_date: str) -> list[dict]:
    if not COMPLETE_JSON.exists():
        return []
    with open(COMPLETE_JSON, encoding="utf-8") as f:
        all_data: list[dict] = json.load(f)
    # 対象日付のデータのみ返す
    return [e for e in all_data if e.get("date") == target_date]


def save_complete(new_entries: list[dict], target_date: str):
    # 既存の全データを読み込み
    all_data: list[dict] = []
    if COMPLETE_JSON.exists():
        with open(COMPLETE_JSON, encoding="utf-8") as f:
            all_data = json.load(f)

    # 対象日付のデータを置き換え、他の日付は保持（直近30日分）
    other_dates = [e for e in all_data if e.get("date") != target_date]
    combined = other_dates + new_entries

    # 日付でソート（新しい順）
    combined.sort(key=lambda x: x.get("date", ""), reverse=True)

    # 直近30日分のみ保持
    cutoff = datetime.now().strftime("%Y-%m-") + "01"  # 簡易的な30日制限
    combined = combined[:2000]  # 最大2000件

    with open(COMPLETE_JSON, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    log(f"💾 complete_info.json に {len(new_entries)} 件保存 (合計 {len(combined)} 件)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    parser.add_argument("--date", default=None, help="対象日付 YYYY-MM-DD（デフォルト: 今日）")
    args = parser.parse_args()

    today = args.date or date.today().strftime("%Y-%m-%d")
    log("=" * 60)
    log(f"🎰 コンプリート情報収集開始  日付={today}  クエリ数={len(COMPLETE_QUERIES)}")

    all_new: list[dict] = []

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
            log("🥷 Stealth mode ON")

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ログイン確認
        try:
            page.goto("https://x.com/home", timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "login" in page.url.lower():
                log("❌ Xにログインできていません。ChromeでXにログインしているか確認してください。")
                ctx.close()
                return
            log("✅ Xログイン確認OK")
        except PlaywrightTimeout:
            log("⚠️  ログイン確認タイムアウト — 続行します")

        for i, query in enumerate(COMPLETE_QUERIES, 1):
            log(f"  [{i}/{len(COMPLETE_QUERIES)}] 🔍 {query}")
            try:
                results = scrape_complete_query(page, query, today)
                log(f"       → {len(results)} 件")
                all_new.extend(results)
                time.sleep(2)
            except Exception as e:
                log(f"  ❌ Error: {e}")

        page.close()
        ctx.close()

    # 重複除去
    seen: set[str] = set()
    deduped = []
    for e in all_new:
        if e["id"] not in seen:
            seen.add(e["id"])
            deduped.append(e)

    log(f"\n📊 収集結果: {len(deduped)} 件（重複除去後）")

    # 店舗・機種別サマリー表示
    log("\n=== 今日のコンプリート一覧 ===")
    for e in deduped:
        store = e["store"] or "店舗不明"
        machine = e["machine"] or "機種不明"
        imgs = len(e["images"])
        log(f"  🎰 {store} | {machine} | 画像{imgs}枚 | {e['x_url']}")

    if deduped:
        save_complete(deduped, today)
    else:
        log("ℹ️  コンプリート情報が見つかりませんでした")

    log("=" * 60)
    log(f"🎉 完了: {len(deduped)} 件のコンプリート情報を収集")


if __name__ == "__main__":
    main()
