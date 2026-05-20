#!/usr/bin/env python3
"""
パチスロ来店・取材イベント情報を X と Google News から収集して
public/events_public.json に追記する。

GitHub Actions 対応:
    X_AUTH_TOKEN / X_CT0 環境変数があれば CI 環境として動作。

Usage:
    python scripts/fetch_events.py
    python scripts/fetch_events.py --headless
    python scripts/fetch_events.py --source x        # X のみ
    python scripts/fetch_events.py --source google   # Google News のみ
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
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
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

EVENTS_JSON = Path(__file__).parent.parent / "public/events_public.json"
STORES_JSON = Path(__file__).parent.parent / "public/stores.json"

# ---------------------------------------------------------------------------
# 収集対象: X メディアアカウント（タイムライン監視）
# ---------------------------------------------------------------------------
MEDIA_ACCOUNTS = {
    # 取材番組・イベント情報集約
    "PAA_pmportal":     "パチマガスロマガ",
    "KD_56_PS":         "KD情報",
    "suropachi_staff":  "スロパチステーション",
    "janbari_info":     "ジャンバリ",
    "3x3star_slot":     "3×3STAR",
    "gorsei_tv":        "極誓",
    "kaido_adv":        "回胴アドベンチャー",
    "suro_select":      "スロセレ",
    "ps_chosain":       "PS調査員",
    "gokuzei_take":     "極誓取材",
    "yume_dori":        "夢ドリ",
    "asadera_tv":       "あさくら",
    "Slotol777":        "スロット情報",
    "buzzslot_jp":      "バズ・スロ",
    "minrepo_tohoku":   "東北みんレポ",
    "p_info_kanto":     "関東パチスロ情報",
    "chiba_pachislo":   "千葉パチスロ情報",
    "pachi_schedule":   "パチスロスケジュール",
    "uratencho777":     "裏店長",
    "rkmrn55":          "ロクマル",
    # タレント・ライター
    "mochizukisaki":    "望月咲",
    "kira_hikaru88":    "煌ひかる",
    "yuuki_kouda":      "倖田柚希",
    "happy_atsudori":   "ハッピー",
    "KarkunRR":         "カルクン",
}

# ---------------------------------------------------------------------------
# X 検索クエリ
# ---------------------------------------------------------------------------
X_QUERIES = [
    # 汎用イベント
    "来店イベント パチスロ",
    "取材 パチスロ 今日",
    "来店 スマスロ",
    "スロット取材 来店",
    "パチスロ 撮影 来店",

    # チェーン別
    "マルハン 来店 パチスロ",
    "キコーナ 来店 パチスロ",
    "ガイア 来店 パチスロ",
    "楽園 来店 パチスロ",
    "エスパス 来店 パチスロ",
    "PIA 来店 パチスロ",
    "ニラク 来店 パチスロ",
    "ダイナム 来店 パチスロ",

    # 関東
    "蒲田 来店 OR 取材 パチスロ",
    "新宿 来店 OR 取材 パチスロ",
    "池袋 来店 OR 取材 パチスロ",
    "川崎 来店 OR 取材 パチスロ",
    "横浜 来店 OR 取材 パチスロ",
    "大宮 来店 OR 取材 パチスロ",
    "千葉 来店 OR 取材 パチスロ",
    "渋谷 来店 OR 取材 パチスロ",
    "立川 来店 OR 取材 パチスロ",
    "町田 来店 OR 取材 パチスロ",

    # 関西
    "大阪 来店 OR 取材 パチスロ",
    "難波 来店 OR 取材 パチスロ",
    "梅田 来店 OR 取材 パチスロ",
    "神戸 来店 OR 取材 パチスロ",
    "京都 来店 OR 取材 パチスロ",

    # 中部
    "名古屋 来店 OR 取材 パチスロ",
    "静岡 来店 OR 取材 パチスロ",
    "浜松 来店 OR 取材 パチスロ",

    # 北海道・東北
    "札幌 来店 OR 取材 パチスロ",
    "仙台 来店 OR 取材 パチスロ",
    "青森 来店 OR 取材 パチスロ",
    "福島 来店 OR 取材 パチスロ",

    # 中国・四国・九州
    "広島 来店 OR 取材 パチスロ",
    "福岡 来店 OR 取材 パチスロ",
    "熊本 来店 OR 取材 パチスロ",
    "鹿児島 来店 OR 取材 パチスロ",
    "那覇 来店 OR 取材 パチスロ",
]

# Google News 検索クエリ
GOOGLE_QUERIES = [
    "パチスロ 来店イベント",
    "パチンコ 取材 イベント",
    "スロット 来店 今日",
    "パチスロ 来店 関東",
    "パチスロ 来店 関西",
    "パチスロ 来店 九州",
    "スマスロ 来店 取材",
    "パチンコ スロット イベント 今週",
]

# ---------------------------------------------------------------------------
# 都道府県マッピング
# ---------------------------------------------------------------------------
CITY_PREF = {
    "蒲田": "東京都", "大森": "東京都", "新宿": "東京都", "渋谷": "東京都",
    "池袋": "東京都", "秋葉原": "東京都", "立川": "東京都", "八王子": "東京都",
    "町田": "東京都", "吉祥寺": "東京都", "上野": "東京都", "錦糸町": "東京都",
    "川崎": "神奈川県", "横浜": "神奈川県", "相模原": "神奈川県", "藤沢": "神奈川県",
    "厚木": "神奈川県", "小田原": "神奈川県", "茅ヶ崎": "神奈川県",
    "大宮": "埼玉県", "浦和": "埼玉県", "川口": "埼玉県", "所沢": "埼玉県",
    "越谷": "埼玉県", "熊谷": "埼玉県",
    "千葉": "千葉県", "船橋": "千葉県", "柏": "千葉県", "松戸": "千葉県",
    "水戸": "茨城県", "宇都宮": "栃木県", "前橋": "群馬県", "高崎": "群馬県",
    "名古屋": "愛知県", "栄": "愛知県", "岡崎": "愛知県", "豊橋": "愛知県",
    "静岡": "静岡県", "浜松": "静岡県",
    "新潟": "新潟県", "金沢": "石川県", "長野": "長野県", "松本": "長野県",
    "甲府": "山梨県", "岐阜": "岐阜県", "富山": "富山県",
    "大阪": "大阪府", "難波": "大阪府", "梅田": "大阪府", "堺": "大阪府",
    "京都": "京都府", "神戸": "兵庫県", "三宮": "兵庫県", "姫路": "兵庫県",
    "奈良": "奈良県", "和歌山": "和歌山県", "大津": "滋賀県", "津": "三重県",
    "広島": "広島県", "岡山": "岡山県", "倉敷": "岡山県",
    "松山": "愛媛県", "高松": "香川県", "高知": "高知県", "徳島": "徳島県",
    "福岡": "福岡県", "博多": "福岡県", "北九州": "福岡県",
    "熊本": "熊本県", "鹿児島": "鹿児島県", "長崎": "長崎県",
    "大分": "大分県", "宮崎": "宮崎県", "那覇": "沖縄県",
    "札幌": "北海道", "旭川": "北海道", "函館": "北海道",
    "仙台": "宮城県", "盛岡": "岩手県", "秋田": "秋田県",
    "山形": "山形県", "福島": "福島県", "青森": "青森県",
}

PREF_AREA = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東",
    "埼玉県": "関東", "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部",
    "山梨県": "中部", "長野県": "中部", "岐阜県": "中部", "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿", "大阪府": "近畿",
    "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国・四国", "島根県": "中国・四国", "岡山県": "中国・四国",
    "広島県": "中国・四国", "山口県": "中国・四国",
    "徳島県": "中国・四国", "香川県": "中国・四国", "愛媛県": "中国・四国", "高知県": "中国・四国",
    "福岡県": "九州・沖縄", "佐賀県": "九州・沖縄", "長崎県": "九州・沖縄",
    "熊本県": "九州・沖縄", "大分県": "九州・沖縄", "宮崎県": "九州・沖縄",
    "鹿児島県": "九州・沖縄", "沖縄県": "九州・沖縄",
}

STORE_CHAIN_RE = re.compile(
    r"(マルハン|キコーナ|ガイア|PIA|ピア|楽園|エスパス|ジャンボ|ニラク|ハッピー|"
    r"ダイナム|ビックアップル|アビバ|ゲンキー|夢屋|メガガイア|プレイランド|"
    r"ヒロキ|タイヨー|ヴィーナス|ミリオン|ホームラン|パラッツォ|エース|"
    r"ゴールデン|サンパレス|ワンダーランド|グランド|クイーン|ドリーム|"
    r"マックス|ベガス|ロイヤル|フレスポ|ニューキング|ユーコー|"
    r"コンコルド|アミューズ|キャッスル|Ｄステーション|Dステーション|"
    r"メッセ|ビックマーチ|スーパーホール|平和島|楽天地)"
    r"[^\s　,、。！!\n]{0,20}?(店|ホール|パーラー)"
)

EVENT_LABEL_RE = {
    "来店":   re.compile(r"来店"),
    "取材":   re.compile(r"取材"),
    "撮影":   re.compile(r"撮影|ロケ"),
    "イベント": re.compile(r"イベント|特定日|設定示唆"),
}

CAST_RE = re.compile(
    r"(?:出演|ゲスト|来店者|MC)[：:\s]*([^\n,、。！!\s]{2,15}(?:さん|先生|プロ)?)|"
    r"([^\s]{2,8}(?:さん|先生|選手|プロ|氏))"
)


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def _get_x_cookies() -> list[dict]:
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0", "")
    if auth_token and ct0:
        log("🔑 環境変数からXのcookieを注入（CI）")
        return [
            {"name": "auth_token", "value": auth_token, "domain": ".x.com",
             "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0", "value": ct0, "domain": ".x.com",
             "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ]
    if HAS_BROWSER_COOKIE3:
        try:
            jar = browser_cookie3.chrome(domain_name=".x.com")
            result = []
            for c in jar:
                pw: dict = {
                    "name": c.name, "value": c.value,
                    "domain": c.domain or ".x.com", "path": c.path or "/",
                    "secure": bool(c.secure), "httpOnly": False, "sameSite": "None",
                }
                if c.expires:
                    pw["expires"] = int(c.expires)
                result.append(pw)
            log(f"🍪 Chrome cookie {len(result)}個取得")
            return result
        except Exception as e:
            log(f"⚠️  browser_cookie3: {e}")
    return []


def launch_browser(playwright, headless: bool):
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        locale="ja-JP",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    return ctx


def apply_x_cookies(ctx, cookies: list[dict]):
    if cookies:
        ctx.add_cookies(cookies)
        log(f"✅ Cookie {len(cookies)}個注入")


# ---------------------------------------------------------------------------
# 共通パース
# ---------------------------------------------------------------------------
def _guess_date(text: str) -> str:
    # "5/20", "5月20日", "05/20"
    m = re.search(r'(\d{1,2})[/／](\d{1,2})', text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{mo:02d}/{dy:02d}"
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{mo:02d}/{dy:02d}"
    today = date.today()
    return f"{today.month:02d}/{today.day:02d}"


def _guess_pref_area(text: str) -> tuple[str, str]:
    for city, pref in CITY_PREF.items():
        if city in text:
            return pref, PREF_AREA.get(pref, "全国")
    for pref, area in PREF_AREA.items():
        short = pref.replace("県", "").replace("都", "").replace("府", "")
        if pref in text or short in text:
            return pref, area
    return "不明", "全国"


def _guess_store(text: str) -> str:
    m = STORE_CHAIN_RE.search(text)
    return m.group(0).strip() if m else ""


def _guess_event_label(text: str) -> str:
    for label, pat in EVENT_LABEL_RE.items():
        if pat.search(text):
            return label
    return "イベント"


def _guess_cast(text: str) -> str:
    m = CAST_RE.search(text)
    if m:
        return (m.group(1) or m.group(2) or "").strip()[:40]
    return ""


def _make_id(store: str, date_str: str, url: str) -> str:
    return hashlib.md5(f"{store}-{date_str}-{url}".encode()).hexdigest()[:12]


def _make_event(text: str, url: str, image_url: str, source: str) -> dict | None:
    store = _guess_store(text)
    if not store:
        return None
    date_str = _guess_date(text)
    pref, area = _guess_pref_area(text)
    return {
        "id":        _make_id(store, date_str, url),
        "date":      date_str,
        "store":     store,
        "pref":      pref,
        "area":      area,
        "event":     _guess_event_label(text),
        "detail":    text[:250].replace("\n", " "),
        "cast":      _guess_cast(text),
        "highlight": "",
        "image_url": image_url,
        "x_url":     url if "x.com" in url else "",
        "url":       url,
        "source":    source,
    }


# ---------------------------------------------------------------------------
# X: タイムライン & 検索
# ---------------------------------------------------------------------------
def _x_extract_images(article) -> list[str]:
    imgs = []
    for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
        src = img.get_attribute("src") or ""
        if src and src not in imgs:
            imgs.append(src)
    return imgs


def _x_get_tweet_url(article) -> str:
    time_el = article.query_selector("time")
    if time_el:
        href = time_el.evaluate("el => el.closest('a') ? el.closest('a').href : ''")
        if href and "status" in href:
            return href
    for lnk in article.query_selector_all('a[href*="/status/"]'):
        href = lnk.get_attribute("href") or ""
        if "/status/" in href:
            return f"https://x.com{href}" if href.startswith("/") else href
    return ""


def scrape_x_timeline(page, username: str, max_tweets: int = 30) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    try:
        page.goto(f"https://x.com/{username}", timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
        except PlaywrightTimeout:
            return results
        for _ in range(5):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)
    except Exception as e:
        log(f"  ⚠️  @{username}: {e}")
        return results

    for article in page.query_selector_all('article[data-testid="tweet"]')[:max_tweets]:
        try:
            text_el = article.query_selector('[data-testid="tweetText"]')
            if not text_el:
                continue
            text = text_el.inner_text()
            if len(text) < 15:
                continue
            url = _x_get_tweet_url(article)
            if not url or url in seen:
                continue
            seen.add(url)
            images = _x_extract_images(article)
            ev = _make_event(text, url, images[0] if images else "", "x")
            if ev:
                results.append(ev)
                log(f"    ✅ @{username}: {ev['store']} [{ev['pref']}] {ev['date']}")
        except Exception:
            continue
    return results


def scrape_x_search(page, query: str, max_tweets: int = 40) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    encoded = query.replace(" ", "%20").replace("#", "%23")
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
        except PlaywrightTimeout:
            return results
        for _ in range(6):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(800)
    except Exception as e:
        log(f"  ⚠️  query={query!r}: {e}")
        return results

    for article in page.query_selector_all('article[data-testid="tweet"]')[:max_tweets]:
        try:
            text_el = article.query_selector('[data-testid="tweetText"]')
            if not text_el:
                continue
            text = text_el.inner_text()
            if len(text) < 15:
                continue
            tweet_url = _x_get_tweet_url(article)
            if not tweet_url or tweet_url in seen:
                continue
            seen.add(tweet_url)
            images = _x_extract_images(article)
            ev = _make_event(text, tweet_url, images[0] if images else "", "x")
            if ev:
                results.append(ev)
                log(f"    ✅ {ev['store']} [{ev['pref']}] {ev['date']} {ev['event']}")
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Google News スクレイピング
# ---------------------------------------------------------------------------
def scrape_google_news(page, query: str) -> list[dict]:
    results: list[dict] = []
    encoded = query.replace(" ", "+")
    url = f"https://news.google.com/search?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        for _ in range(3):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)
    except Exception as e:
        log(f"  ⚠️  Google News {query!r}: {e}")
        return results

    articles = page.query_selector_all('article')
    if not articles:
        articles = page.query_selector_all('h3 a, h4 a')

    for article in articles[:30]:
        try:
            # タイトル取得
            title_el = article.query_selector('h3, h4, a[href]')
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            if len(title) < 10:
                continue
            # リンク取得
            link_el = article.query_selector('a[href]')
            href = link_el.get_attribute("href") if link_el else ""
            if not href:
                continue
            if href.startswith("./"):
                href = "https://news.google.com/" + href[2:]
            elif href.startswith("/"):
                href = "https://news.google.com" + href

            # イベント・パチスロ関連かチェック
            combined = title
            ev = _make_event(combined, href, "", "google")
            if ev:
                results.append(ev)
                log(f"    📰 Google: {ev['store']} [{ev['pref']}] {ev['date']}")
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# events_public.json の読み書き
# ---------------------------------------------------------------------------
def load_events() -> tuple[list[dict], dict | None]:
    if not EVENTS_JSON.exists():
        return [], None
    with open(EVENTS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("events", []), data
    return data, None


def save_events(events: list[dict], original: dict | None):
    if original is not None and isinstance(original, dict):
        original["events"] = events
        out = original
    else:
        out = {"events": events}
    with open(EVENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"💾 events_public.json 保存: {len(events)}件")


def merge_events(existing: list[dict], new_events: list[dict]) -> tuple[list[dict], int]:
    existing_ids = {ev["id"] for ev in existing}
    existing_urls = {ev.get("url", "") for ev in existing if ev.get("url")}
    added = 0
    prepend: list[dict] = []
    for ev in new_events:
        if ev["id"] in existing_ids:
            continue
        if ev.get("url") and ev["url"] in existing_urls:
            continue
        prepend.append(ev)
        existing_ids.add(ev["id"])
        if ev.get("url"):
            existing_urls.add(ev["url"])
        added += 1
    # 新しいものを先頭に、古いものは3000件まで
    combined = prepend + existing
    return combined[:3000], added


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--source", choices=["x", "google", "all"], default="all")
    args = parser.parse_args()

    log("=" * 60)
    log(f"🚀 fetch_events 開始  source={args.source}  headless={args.headless}")

    existing, original = load_events()
    log(f"📦 既存イベント: {len(existing)}件")

    all_new: list[dict] = []

    with sync_playwright() as pw:
        ctx = launch_browser(pw, args.headless)

        # Xのcookieを注入
        if args.source in ("x", "all"):
            cookies = _get_x_cookies()
            apply_x_cookies(ctx, cookies)

        page = ctx.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ── X ──
        if args.source in ("x", "all"):
            # ログイン確認
            try:
                page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                if "login" in page.url.lower():
                    log("❌ Xにログインできていません")
                else:
                    log("✅ Xログイン確認OK")

                    # 1) メディアアカウント タイムライン
                    log(f"\n📋 メディアアカウント タイムライン収集 ({len(MEDIA_ACCOUNTS)}件)")
                    for username, label in MEDIA_ACCOUNTS.items():
                        log(f"  @{username} ({label})")
                        try:
                            results = scrape_x_timeline(page, username)
                            log(f"       → {len(results)}件")
                            all_new.extend(results)
                            time.sleep(1.5)
                        except Exception as e:
                            log(f"  ❌ {e}")

                    # 2) キーワード検索
                    log(f"\n🔍 X 検索クエリ ({len(X_QUERIES)}件)")
                    for i, query in enumerate(X_QUERIES, 1):
                        log(f"  [{i}/{len(X_QUERIES)}] {query}")
                        try:
                            results = scrape_x_search(page, query)
                            log(f"       → {len(results)}件")
                            all_new.extend(results)
                            time.sleep(1.5)
                        except Exception as e:
                            log(f"  ❌ {e}")

            except Exception as e:
                log(f"⚠️  X スクレイピングエラー: {e}")

        # ── Google News ──
        if args.source in ("google", "all"):
            log(f"\n📰 Google News 収集 ({len(GOOGLE_QUERIES)}件)")
            for i, query in enumerate(GOOGLE_QUERIES, 1):
                log(f"  [{i}/{len(GOOGLE_QUERIES)}] {query}")
                try:
                    results = scrape_google_news(page, query)
                    log(f"       → {len(results)}件")
                    all_new.extend(results)
                    time.sleep(2)
                except Exception as e:
                    log(f"  ❌ {e}")

        page.close()
        ctx.close()

    # 重複除去
    seen_ids: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen_ids or seen_ids.add(e["id"]))]  # type: ignore
    log(f"\n📊 収集合計: {len(deduped)}件（重複除去後）")

    merged, added = merge_events(existing, deduped)
    log(f"➕ 新規追加: {added}件 / 合計: {len(merged)}件")

    if added > 0:
        save_events(merged, original)

    log("=" * 60)


if __name__ == "__main__":
    main()
