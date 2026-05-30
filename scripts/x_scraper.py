#!/usr/bin/env python3
"""
X (Twitter) scraper — 全国パチスロ来店・取材イベント自動収集
4時間ごとの自動実行対応。初回のみ headed 起動でXログイン確認。

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    初回セットアップ（ログイン確認）:
        python scripts/x_scraper.py --setup

    通常実行（headless可）:
        python scripts/x_scraper.py

    定期実行（launchd / cron から呼ぶ場合）:
        python scripts/x_scraper.py --headless
"""

import json
import re
import time
import hashlib
import sys
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from playwright_stealth import stealth, Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHROME_PROFILE   = Path.home() / "Library/Application Support/Google/Chrome/Default"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"
COOKIES_FILE     = Path(__file__).parent / ".x_cookies.json"
EVENTS_JSON      = Path(__file__).parent.parent / "public/events_public.json"
STORES_JSON      = Path(__file__).parent.parent / "public/stores.json"
FLOOR_MAPS_DIR   = Path(__file__).parent.parent / "public/floor_maps"
LOG_FILE         = Path(__file__).parent / "x_scraper.log"

# 低貸し専門店 識別キーワード（店舗名・ツイート本文）
LOW_RENTAL_KEYWORDS = [
    "1パチ", "2パチ", "5スロ", "8スロ", "10スロ", "20スロ",
    "低貸し", "低貸専門", "低貸玉", "低単価", "低価格",
    "1円パチンコ", "5円スロット", "10円スロット",
]

# 777CON-PASS ホール検索ベースURL
CON_PASS_SEARCH_URL = "https://www.777con-pass.net/search.html"

# ---------------------------------------------------------------------------
# アカウントタイムライン監視対象
# ---------------------------------------------------------------------------
MEDIA_ACCOUNTS: dict[str, str] = {
    # 取材番組・メディア系
    "suropachi_staff": "スロパチステーション",
    "janbari_info":    "ジャンバリ",
    "PAA_pmportal":    "パチマガスロマガ",
    "KD_56_PS":        "KD情報",
    "Slotol777":       "スロット情報",
    "3x3star_slot":    "3×3STAR",
    "gorsei_tv":       "極誓",
    "kaido_adv":       "回胴アドベンチャー",
    "suro_select":     "スロセレ",
    "buzzslot_jp":     "バズ・スロ",
    "slotimes_jp":     "SLOTIMES",
    "yume_dori":       "夢ドリ",
    "asadera_tv":      "あさくら",
    "ps_chosain":      "PS調査員",
    "realdoc_pachi":   "REAL取材",
    "gokumichi_dome":  "限界突破DOME",
    "gokuzei_take":    "極誓取材",
    # 全国イベント集約系（重要）
    "minrepo_tohoku":  "東北みんレポ",
    "p_info_kanto":    "関東パチスロ情報",
    "chiba_pachislo":  "千葉パチスロ情報",
    "uratencho777":    "裏店長",
    "rkmrn55":         "ロクマル",
    "pachi_schedule":  "パチスロスケジュール",
    # 主要タレント・ライター系
    "mochizukisaki":   "望月咲",
    "kira_hikaru88":   "煌ひかる",
    "yuuki_kouda":     "倖田柚希",
    "matsuitaxi":      "マツイ",
    "motsu_pachi":     "モツ",
    "KarkunRR":        "カルクン",
    "happy_atsudori":  "ハッピー",
    "hanakawa65":      "花川",
}

# 全国 検索クエリ（チェーン店名 × イベント種別 + 都道府県エリア）
SEARCH_QUERIES = [
    # ── チェーン別（来店）──
    "マルハン 来店 パチスロ",
    "キコーナ 来店 パチスロ",
    "ガイア 来店 パチスロ",
    "PIA 来店 パチスロ",
    "楽園 来店 パチスロ",
    "エスパス 来店 パチスロ",
    "ジャンボ 来店 パチスロ",
    "ニラク 来店 パチスロ",
    "ハッピー 来店 パチスロ",
    "ネットカフェ 来店 OR スロット -ネカフェ",  # ネット系は除外
    "ビッグアップル 来店 パチスロ",
    "ガイナックス 来店 OR パチスロ",

    # ── チェーン別（取材）──
    "マルハン 取材 パチスロ",
    "キコーナ 取材 パチスロ",
    "ガイア 取材 パチスロ",
    "PIA 取材 パチスロ",
    "楽園 取材 パチスロ",
    "エスパス 取材 パチスロ",

    # ── 汎用（来店イベント）──
    "来店イベント パチスロ 今日",
    "来店イベント スロット 今週",
    "来店 スマスロ",
    "来店 北斗 OR バジリスク OR 鉄拳 パチスロ",
    "来店 エヴァ OR ゴッドイーター OR ジャグラー パチスロ",

    # ── 汎用（取材・撮影）──
    "取材 パチスロ イベント",
    "取材 スロット 来店",
    "撮影 パチスロ 来店",
    "メシウマ 取材 OR 来店",
    "PS調査員 取材",
    "サザンスター 取材",
    "ゴーゴージャグラー 取材",
    "スロット取材 来店",

    # ── 関東エリア ──
    "蒲田 来店 OR 取材 パチスロ",
    "大森 来店 OR 取材 パチスロ",
    "川崎 来店 OR 取材 パチスロ",
    "横浜 来店 OR 取材 パチスロ",
    "相模原 来店 OR 取材 パチスロ",
    "藤沢 来店 OR 取材 パチスロ",
    "厚木 来店 OR 取材 パチスロ",
    "新宿 来店 OR 取材 パチスロ",
    "渋谷 来店 OR 取材 パチスロ",
    "池袋 来店 OR 取材 パチスロ",
    "秋葉原 来店 OR 取材 パチスロ",
    "立川 来店 OR 取材 パチスロ",
    "八王子 来店 OR 取材 パチスロ",
    "町田 来店 OR 取材 パチスロ",
    "大宮 来店 OR 取材 パチスロ",
    "浦和 来店 OR 取材 パチスロ",
    "川口 来店 OR 取材 パチスロ",
    "所沢 来店 OR 取材 パチスロ",
    "千葉 来店 OR 取材 パチスロ",
    "船橋 来店 OR 取材 パチスロ",
    "柏 来店 OR 取材 パチスロ",
    "水戸 来店 OR 取材 パチスロ",
    "宇都宮 来店 OR 取材 パチスロ",
    "前橋 来店 OR 取材 パチスロ",

    # ── 中部エリア ──
    "名古屋 来店 OR 取材 パチスロ",
    "栄 来店 OR 取材 パチスロ",
    "静岡 来店 OR 取材 パチスロ",
    "浜松 来店 OR 取材 パチスロ",
    "新潟 来店 OR 取材 パチスロ",
    "金沢 来店 OR 取材 パチスロ",
    "長野 来店 OR 取材 パチスロ",
    "松本 来店 OR 取材 パチスロ",
    "甲府 来店 OR 取材 パチスロ",

    # ── 関西エリア ──
    "大阪 来店 OR 取材 パチスロ",
    "難波 来店 OR 取材 パチスロ",
    "梅田 来店 OR 取材 パチスロ",
    "京都 来店 OR 取材 パチスロ",
    "神戸 来店 OR 取材 パチスロ",
    "三宮 来店 OR 取材 パチスロ",
    "奈良 来店 OR 取材 パチスロ",
    "和歌山 来店 OR 取材 パチスロ",

    # ── 中国・四国エリア ──
    "広島 来店 OR 取材 パチスロ",
    "岡山 来店 OR 取材 パチスロ",
    "松山 来店 OR 取材 パチスロ",
    "高松 来店 OR 取材 パチスロ",
    "高知 来店 OR 取材 パチスロ",

    # ── 九州・沖縄エリア ──
    "福岡 来店 OR 取材 パチスロ",
    "博多 来店 OR 取材 パチスロ",
    "熊本 来店 OR 取材 パチスロ",
    "鹿児島 来店 OR 取材 パチスロ",
    "長崎 来店 OR 取材 パチスロ",
    "大分 来店 OR 取材 パチスロ",
    "宮崎 来店 OR 取材 パチスロ",
    "那覇 来店 OR 取材 パチスロ",

    # ── 北海道・東北エリア ──
    "札幌 来店 OR 取材 パチスロ",
    "仙台 来店 OR 取材 パチスロ",
    "盛岡 来店 OR 取材 パチスロ",
    "秋田 来店 OR 取材 パチスロ",
    "山形 来店 OR 取材 パチスロ",
    "福島 来店 OR 取材 パチスロ",
    "青森 来店 OR 取材 パチスロ",
]

# 都道府県マッピング（市区名 → 都道府県）
CITY_PREF = {
    "蒲田": "東京都", "大森": "東京都", "新宿": "東京都", "渋谷": "東京都",
    "池袋": "東京都", "秋葉原": "東京都", "立川": "東京都", "八王子": "東京都",
    "町田": "東京都",
    "川崎": "神奈川県", "横浜": "神奈川県", "相模原": "神奈川県", "藤沢": "神奈川県",
    "厚木": "神奈川県", "小田原": "神奈川県", "茅ヶ崎": "神奈川県", "海老名": "神奈川県",
    "平塚": "神奈川県", "みなとみらい": "神奈川県",
    "大宮": "埼玉県", "浦和": "埼玉県", "川口": "埼玉県", "所沢": "埼玉県",
    "千葉": "千葉県", "船橋": "千葉県", "柏": "千葉県",
    "水戸": "茨城県", "宇都宮": "栃木県", "前橋": "群馬県",
    "名古屋": "愛知県", "栄": "愛知県",
    "静岡": "静岡県", "浜松": "静岡県",
    "新潟": "新潟県", "金沢": "石川県", "長野": "長野県", "松本": "長野県",
    "甲府": "山梨県",
    "大阪": "大阪府", "難波": "大阪府", "梅田": "大阪府",
    "京都": "京都府", "神戸": "兵庫県", "三宮": "兵庫県",
    "奈良": "奈良県", "和歌山": "和歌山県",
    "広島": "広島県", "岡山": "岡山県",
    "松山": "愛媛県", "高松": "香川県", "高知": "高知県",
    "福岡": "福岡県", "博多": "福岡県",
    "熊本": "熊本県", "鹿児島": "鹿児島県", "長崎": "長崎県",
    "大分": "大分県", "宮崎": "宮崎県", "那覇": "沖縄県",
    "札幌": "北海道", "仙台": "宮城県", "盛岡": "岩手県",
    "秋田": "秋田県", "山形": "山形県", "福島": "福島県", "青森": "青森県",
}

PREF_AREA = {
    "北海道": "北海道", "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東", "埼玉県": "関東",
    "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
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

EVENT_KEYWORDS = {
    "raiten":  ["来店", "来店イベント", "来店取材"],
    "torisai": ["取材", "取材イベント", "メディア取材"],
    "satsuei": ["撮影", "ロケ", "動画撮影"],
}

STORE_CHAIN_RE = re.compile(
    r"(マルハン|キコーナ|ガイア|PIA|ピア|楽園|エスパス|ジャンボ|ニラク|ハッピー|"
    r"ビッグアップル|スーパーハリウッド|アビバ|ゲンキー|夢屋|ライジン|メガガイア|"
    r"プレイランド|ヒロキ|エムアール|タイヨー|"
    r"ヴィーナス|ミリオン|ホームラン|パラッツォ|ビスタ|エース|ニュートーキョー|"
    r"ゴールデン|サンパレス|ワイルド|ニューキング|ユーコー|レイジングブル|"
    r"グランド|パレット|スターダスト|クイーン|ドリーム|ファンキー|"
    r"マックス|ベガス|ロイヤル|フレスポ|ドンキ|イオン)"
    r"[^\s　,、。！!\n]{0,20}?(店|ホール)"
)

CAST_PATTERNS = [
    r"出演[：:\s]*([^\n　,、。！!\n]+)",
    r"ゲスト[：:\s]*([^\n　,、。！!\n]+)",
    r"来店者[：:\s]*([^\n　,、。！!\n]+)",
    r"([^\s]{2,8}(?:さん|先生|選手|プロ|氏))",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def make_id(store: str, date_str: str, x_url: str) -> str:
    key = f"{store}-{date_str}-{x_url}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def guess_date(text: str) -> str:
    m = re.search(r'(\d{1,2})[/／](\d{1,2})', text)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
    today = date.today()
    return f"{today.month:02d}/{today.day:02d}"


def guess_store_pref_area(text: str) -> tuple[str, str, str] | None:
    # Try to extract store name from tweet
    m = STORE_CHAIN_RE.search(text)
    store = m.group(0) if m else ""

    # Guess city/pref from text
    pref, area = "", "全国"
    for city, p in CITY_PREF.items():
        if city in text:
            pref = p
            area = PREF_AREA.get(p, "関東")
            # Refine store name with city if no city in store yet
            if store and city not in store:
                store = store  # keep as-is
            break

    if not store:
        # No recognizable chain store found — skip
        return None

    if not pref:
        # Guess from prefecture names in tweet
        for p in PREF_AREA:
            if p in text or p.replace("県","").replace("都","").replace("府","") in text:
                pref = p
                area = PREF_AREA[p]
                break

    if not pref:
        pref = "不明"

    return store, pref, area


def guess_event_type(text: str) -> str:
    for ev_type, keywords in EVENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return ev_type
    return "normal"


def guess_cast(text: str) -> str:
    for pat in CAST_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:40]
    return ""


def tweet_to_event(text: str, tweet_url: str) -> dict | None:
    info = guess_store_pref_area(text)
    if not info:
        return None
    store, pref, area = info
    date_str = guess_date(text)
    ev_type = guess_event_type(text)
    cast = guess_cast(text)
    detail = text[:200].replace("\n", " ")
    event_label = next(
        (kw for kws in EVENT_KEYWORDS.values() for kw in kws if kw in text),
        ""
    )
    return {
        "id": make_id(store, date_str, tweet_url),
        "date": date_str,
        "store": store,
        "pref": pref,
        "area": area,
        "event": event_label,
        "detail": detail,
        "cast": cast,
        "highlight": "",
        "x_url": tweet_url,
        "url": tweet_url,
        "source": "x",
    }


# ---------------------------------------------------------------------------
# Browser launch
# ---------------------------------------------------------------------------

def _get_chrome_cookies_for_playwright() -> list[dict]:
    """browser_cookie3 でChromeのX認証cookieを取得し、Playwright形式で返す"""
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
        log(f"🍪 Chrome cookies: {[c['name'] for c in result]}")
    except Exception as e:
        log(f"⚠️  browser_cookie3 error: {e}")
    return result


def launch_browser(playwright, headless: bool):
    """
    Chrome の auth_token を browser_cookie3 で直接取得してPlaywrightに注入。
    Chrome が起動中でもOK。
    """
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

    # Chrome の認証クッキーを注入
    cookies = _get_chrome_cookies_for_playwright()
    if cookies:
        ctx.add_cookies(cookies)
        log(f"✅ {len(cookies)} cookies injected from Chrome")
    else:
        log("⚠️  No cookies from Chrome — X login may fail")

    return ctx




# ---------------------------------------------------------------------------
# Scrape one query
# ---------------------------------------------------------------------------

def scrape_query(page, query: str, max_tweets: int = 40) -> list[dict]:
    results = []
    seen_urls: set[str] = set()

    encoded = query.replace(" ", "%20").replace("#", "%23").replace("|", "%7C")
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        log(f"  ⏱  Timeout: {query}")
        return results

    # Wait for first tweet to appear
    try:
        page.wait_for_selector(
            'article[data-testid="tweet"], article[role="article"]',
            timeout=10000
        )
    except PlaywrightTimeout:
        pass

    # Scroll to load more
    for _ in range(6):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1500)

    # Collect articles
    articles = []
    for sel in ['article[data-testid="tweet"]', 'article[role="article"]', 'div[data-testid="cellInnerDiv"] article']:
        articles = page.query_selector_all(sel)
        if articles:
            break

    if not articles:
        return results

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

            # Get URL
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

            ev = tweet_to_event(text, tweet_url)
            if ev:
                results.append(ev)
                log(f"    ✅ {ev['store']} [{ev['pref']}] {ev['date']} {ev['event']} {ev['cast']}")

        except Exception as e:
            continue

    return results


# ---------------------------------------------------------------------------
# events_public.json load / save / merge
# ---------------------------------------------------------------------------

def load_events() -> tuple[list[dict], object]:
    if EVENTS_JSON.exists():
        with open(EVENTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("events", []), data
        return data, None
    return [], None


def save_events(events: list[dict], original):
    if isinstance(original, dict):
        original["events"] = events
        out = original
    else:
        out = events
    with open(EVENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"💾 Saved {len(events)} total events → {EVENTS_JSON}")


def merge_events(existing: list[dict], new_events: list[dict]) -> tuple[list[dict], int]:
    existing_ids  = {ev["id"] for ev in existing}
    existing_urls = {ev.get("x_url", "") for ev in existing if ev.get("x_url")}

    added, prepend = 0, []
    for ev in new_events:
        if ev["id"] in existing_ids:
            continue
        if ev.get("x_url") and ev["x_url"] in existing_urls:
            continue
        prepend.append(ev)
        existing_ids.add(ev["id"])
        if ev.get("x_url"):
            existing_urls.add(ev["x_url"])
        added += 1

    return prepend + existing, added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード（定期実行用）")
    args = parser.parse_args()

    log("=" * 60)
    log(f"🚀 x_scraper start  headless={args.headless}  queries={len(SEARCH_QUERIES)}")

    existing, original = load_events()
    log(f"📦 Existing events: {len(existing)}")

    all_new: list[dict] = []

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)

        page = ctx.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
            log("🥷 Stealth mode ON")
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # Verify login
        try:
            page.goto("https://x.com/home", timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            if "login" in page.url.lower():
                log("❌ Xにログインできていません。Chromeでmesiuma77にログインしているか確認してください。")
                ctx.close()
                return
            log("✅ Logged into X")
        except PlaywrightTimeout:
            log("⚠️  Login check timed out, proceeding...")

        for i, query in enumerate(SEARCH_QUERIES, 1):
            log(f"  [{i}/{len(SEARCH_QUERIES)}] 🔍 {query}")
            try:
                results = scrape_query(page, query)
                log(f"       → {len(results)} hits")
                all_new.extend(results)
                time.sleep(2)
            except Exception as e:
                log(f"  ❌ Error: {e}")

        # フロアマップ取得（HP URLある全店を毎回再チェック・変更検知）
        fetch_floor_maps(page)

        # 低貸し・777CON-PASS メタデータ更新
        update_stores_metadata(page)

        page.close()
        ctx.close()

    # Deduplicate across queries
    seen: set[str] = set()
    deduped = [ev for ev in all_new if not (ev["id"] in seen or seen.add(ev["id"]))]  # type: ignore

    log(f"📊 New candidates: {len(deduped)}")
    merged, added = merge_events(existing, deduped)
    log(f"➕ Added: {added}")

    if added > 0:
        save_events(merged, original)
        _rebuild_stores(merged)
        # Auto-rebuild Next.js site
        import subprocess
        log("🔨 Building site...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(EVENTS_JSON.parent.parent),
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log("✅ Build complete")
        else:
            log(f"⚠️  Build failed: {result.stderr[-500:]}")
    else:
        log("✅ No new events to add.")

    log("=" * 60)


def _rebuild_stores(events: list[dict]):
    """events から stores.json を更新（既存フィールドを保持しつつ event_count を更新）"""
    PREF_NORM = {
        '北海道':'北海道',
        '青森':'青森県','岩手':'岩手県','宮城':'宮城県','秋田':'秋田県','山形':'山形県','福島':'福島県',
        '茨城':'茨城県','栃木':'栃木県','群馬':'群馬県','埼玉':'埼玉県','千葉':'千葉県',
        '東京':'東京都','神奈川':'神奈川県',
        '新潟':'新潟県','富山':'富山県','石川':'石川県','福井':'福井県','山梨':'山梨県',
        '長野':'長野県','岐阜':'岐阜県','静岡':'静岡県','愛知':'愛知県',
        '三重':'三重県','滋賀':'滋賀県','京都':'京都府','大阪':'大阪府','兵庫':'兵庫県',
        '奈良':'奈良県','和歌山':'和歌山県',
        '鳥取':'鳥取県','島根':'島根県','岡山':'岡山県','広島':'広島県','山口':'山口県',
        '徳島':'徳島県','香川':'香川県','愛媛':'愛媛県','高知':'高知県',
        '福岡':'福岡県','佐賀':'佐賀県','長崎':'長崎県','熊本':'熊本県',
        '大分':'大分県','宮崎':'宮崎県','鹿児島':'鹿児島県','沖縄':'沖縄県',
    }
    for p in list(PREF_NORM.values()):
        PREF_NORM[p] = p
    PREF_AREA = {
        '北海道':'北海道',
        '青森県':'東北','岩手県':'東北','宮城県':'東北','秋田県':'東北','山形県':'東北','福島県':'東北',
        '茨城県':'関東','栃木県':'関東','群馬県':'関東','埼玉県':'関東','千葉県':'関東','東京都':'関東','神奈川県':'関東',
        '新潟県':'中部','富山県':'中部','石川県':'中部','福井県':'中部','山梨県':'中部','長野県':'中部','岐阜県':'中部','静岡県':'中部','愛知県':'中部',
        '三重県':'近畿','滋賀県':'近畿','京都府':'近畿','大阪府':'近畿','兵庫県':'近畿','奈良県':'近畿','和歌山県':'近畿',
        '鳥取県':'中国・四国','島根県':'中国・四国','岡山県':'中国・四国','広島県':'中国・四国','山口県':'中国・四国',
        '徳島県':'中国・四国','香川県':'中国・四国','愛媛県':'中国・四国','高知県':'中国・四国',
        '福岡県':'九州・沖縄','佐賀県':'九州・沖縄','長崎県':'九州・沖縄','熊本県':'九州・沖縄',
        '大分県':'九州・沖縄','宮崎県':'九州・沖縄','鹿児島県':'九州・沖縄','沖縄県':'九州・沖縄',
    }

    # Build event_count map from events
    ev_count: dict[str, int] = {}
    ev_meta: dict[str, dict] = {}
    for ev in events:
        name = (ev.get("store") or "").strip()
        if not name:
            continue
        ev_count[name] = ev_count.get(name, 0) + 1
        if name not in ev_meta:
            raw_pref = (ev.get("pref") or "").strip()
            pref = PREF_NORM.get(raw_pref, raw_pref)
            area = PREF_AREA.get(pref, ev.get("area", ""))
            sid = hashlib.md5(name.encode()).hexdigest()[:10]
            ev_meta[name] = {"id": sid, "name": name, "pref": pref, "area": area}

    stores_path = EVENTS_JSON.parent / "stores.json"

    # Load existing stores (preserving hp_url, x_url, address, map_url, floor_map_url etc.)
    existing_stores: dict[str, dict] = {}
    if stores_path.exists():
        with open(stores_path, encoding="utf-8") as f:
            for s in json.load(f):
                existing_stores[s["name"]] = s

    # Update event_count for existing stores; add new stores
    for name, count in ev_count.items():
        if name in existing_stores:
            existing_stores[name]["event_count"] = count
        else:
            meta = ev_meta[name]
            existing_stores[name] = {
                "id": meta["id"], "name": name,
                "pref": meta["pref"], "area": meta["area"],
                "event_count": count,
                "hp_url": None, "x_url": None, "address": None, "map_url": None,
                "floor_map_url": None, "is_low_rental": False,
                "lottery_time": None, "con_pass_url": None,
            }

    result = sorted(existing_stores.values(), key=lambda x: (x.get("area",""), x.get("pref",""), x.get("name","")))
    with open(stores_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log(f"🏪 stores.json updated: {len(result)} stores")


def _is_low_rental(name: str) -> bool:
    return any(kw in name for kw in LOW_RENTAL_KEYWORDS)


# ---------------------------------------------------------------------------
# チェーン別 X URL マッピング（個別店舗アカウント）
# ---------------------------------------------------------------------------
CHAIN_X_URLS: dict[str, str] = {
    # ワンダーランド（九州・熊本・大分・長崎）— 個別店舗Xアカウント
    "ワンダーランド香椎本館":        "https://x.com/wl_kashii",
    "ワンダーランド香椎Ⅱ":          "https://x.com/wl_kashii2",
    "ワンダーランド西新":            "https://x.com/wl_nishijin",
    "ワンダーランド百年橋店":        "https://x.com/wl_hyakunenbashi",
    "ワンダーランド南ヶ丘店":        "https://x.com/wl__minamigaoka",
    "ワンダーランド須恵店":          "https://x.com/wl_sue",
    "ワンダーランド1188福岡東店":    "https://x.com/wl_fkhigashi",
    "ワンダーランド　うきはバイパス店": "https://x.com/wl_ukihab",
    "ワンダーランドうきはバイパス店": "https://x.com/wl_ukihab",
    "ワンダーランド柳川":            "https://x.com/wl_yanagawa",
    "ワンダーランド三潴店":          "https://x.com/wl_mizuma",
    "ワンダーランド高田店":          "https://x.com/wl_takada",
    "ワンダーランド大川店":          "https://x.com/wl_ookawa",
    "ワンダーランド770東合川店":     "https://x.com/wl_770aikawa",
    "ワンダーランド吉井店":          "https://x.com/wl_yoshii",
    "ワンダーランド小郡三沢店":      "https://x.com/wl_ogoori",
    "ワンダーランド八江店":          "https://x.com/wl_hachie",
    "ワンダーランドメタルポリス":    "https://x.com/wl_metalpolice",
    "ワンダーランド日出町店":        "https://x.com/wl_hinodemachi",
    "ワンダーランド伊万里店":        "https://x.com/wl_imari",
    "ワンダーランド江北店":          "https://x.com/wl_kouhoku",
    "ワンダーランド武雄店":          "https://x.com/wl_takeo",
    "ワンダーランド鹿島店":          "https://x.com/wl_kashima",
    "ワンダーランド中津米山店":      "https://x.com/wl_nakatsu",
    "ワンダーランド大分皆春店":      "https://x.com/wl_minaharu",
    "ワンダーランド1177大分南店":    "https://x.com/wl_o_minami",
    "ワンダーランド臼杵店":          "https://x.com/wl_usuki",
    "ワンダーランド光の森店":        "https://x.com/wl_hikarinomori",
    "ワンダーランド佐世保白岳店":    "https://x.com/wl_s_sasebo",
    "ワンダーランド諫早店":          "https://x.com/wl__isahaya",
    "ワンダーランド1188鹿児島新栄店": "https://x.com/wl_kshinei",
    "ワンダーランド1177谷山店":      "https://x.com/wl_taniyama",
    "ワンダーランド1188宮崎芳士店":  "https://x.com/wl_imo1188",
    "ワンダーランド小戸本館":        "https://x.com/wl_odo",
    "ワンダーランド小戸Ⅱ":          "https://x.com/wl_od2",
    "ワンダーランド1188大刀洗店":    "",   # Xなし
    # ミリオン（徳島・香川・高知・兵庫・千葉）
    "ミリオン川内店":          "https://x.com/mn_kawauchi",
    "ミリオン昭和店":          "https://x.com/mn_syowa",
    "ミリオン沖浜店":          "https://x.com/mn_okinohama",
    "ミリオン鳴門店":          "https://x.com/mn_naruto_ps",
    "ミリオン観音寺店":        "https://x.com/mn_kanonji",
    "ミリオン島田店":          "https://x.com/mn_shimada",
    "ミリオン池田店":          "https://x.com/mn_ikeda_ps",
    "ミリオン三加茂店":        "https://x.com/mn_mikamo_ps",
    "ミリオン美馬店":          "https://x.com/mn__mima",
    "ミリオン阿波店":          "https://x.com/mn_awa",
    "ミリオン市場店":          "https://x.com/mn_ichiba",
    "ミリオン鴨島店":          "https://x.com/mn_kamojima",
    "ミリオン石井店":          "https://x.com/mn_ishii",
    "ミリオン国府店":          "https://x.com/mn_kokufu",
    "ミリオン藍住店":          "https://x.com/mn_aizumi_ps",
    "ミリオン北島店":          "https://x.com/mn_kitajima",
    "ミリオン中吉野店":        "https://x.com/mn_nakayoshino",
    "ミリオン佐古店":          "https://x.com/mn_sako",
    "ミリオン駅前店":          "https://x.com/mn_ekimae",
    "ミリオン末広店":          "https://x.com/mn_suehiro",
    "ミリオン論田店":          "https://x.com/mn_ronden_ps",
    "ミリオン金磯店":          "https://x.com/mn_kanaiso",
    "ミリオン羽浦店":          "https://x.com/mn_hanoura",
    "ミリオン津峰店":          "https://x.com/mn_tsunomine",
    "ミリオン海南店":          "https://x.com/mn_kainan",
    "ミリオン宇多津店":        "https://x.com/mn_utazu",
    "ミリオン高松東店":        "https://x.com/mn_takamatsu",
    "ミリオン観音寺吉岡店":    "https://x.com/mn_k_yoshioka",
    "ミリオン土佐道路店":      "https://x.com/mn_tosadoro",
    "ミリオン一宮店":          "https://x.com/mn_ikku",
    "ミリオン野市店":          "https://x.com/mn_noichi",
    "ミリオン大津店":          "https://x.com/mn_otsu_ps",
    "ミリオン南国店":          "https://x.com/mn_nankoku",
    "ミリオン南国おおそね店":  "https://x.com/mn_osone_ps",
    "ミリオン明石店":          "https://x.com/mn_akashi",
    "ミリオン習志野店":        "https://x.com/mn_narashino",
}

# ワンダーランド個別店舗HP URL マッピング（チェーン本社URLではなく個別ページ）
WONDERLAND_HP_URLS: dict[str, str] = {
    "ワンダーランド香椎本館":        "https://www.wonderland.gr.jp/kashii/",
    "ワンダーランド香椎Ⅱ":          "https://www.wonderland.gr.jp/kashii2/",
    "ワンダーランド西新":            "https://www.wonderland.gr.jp/nishijin/",
    "ワンダーランド百年橋店":        "https://www.wonderland.gr.jp/hyakunenbashi/",
    "ワンダーランド南ヶ丘店":        "https://www.wonderland.gr.jp/minamigaoka/",
    "ワンダーランド須恵店":          "https://www.wonderland.gr.jp/sue/",
    "ワンダーランド1188福岡東店":    "https://www.wonderland.gr.jp/fk-higashi/",
    "ワンダーランド　うきはバイパス店": "https://www.wonderland.gr.jp/ukiha-b/",
    "ワンダーランドうきはバイパス店": "https://www.wonderland.gr.jp/ukiha-b/",
    "ワンダーランド柳川":            "https://www.wonderland.gr.jp/yanagawa/",
    "ワンダーランド三潴店":          "https://www.wonderland.gr.jp/mizuma/",
    "ワンダーランド高田店":          "https://www.wonderland.gr.jp/takada/",
    "ワンダーランド大川店":          "https://www.wonderland.gr.jp/ookawa/",
    "ワンダーランド770東合川店":     "https://www.wonderland.gr.jp/higashiaikawa/",
    "ワンダーランド吉井店":          "https://www.wonderland.gr.jp/yoshii/",
    "ワンダーランド小郡三沢店":      "https://www.wonderland.gr.jp/ogoori/",
    "ワンダーランド八江店":          "https://www.wonderland.gr.jp/hachie/",
    "ワンダーランドメタルポリス":    "https://www.wonderland.gr.jp/mp-hachie/",
    "ワンダーランド日出町店":        "https://www.wonderland.gr.jp/hinodemachi/",
    "ワンダーランド伊万里店":        "https://www.wonderland.gr.jp/imari/",
    "ワンダーランド江北店":          "https://www.wonderland.gr.jp/kouhoku/",
    "ワンダーランド武雄店":          "https://www.wonderland.gr.jp/takeo/",
    "ワンダーランド鹿島店":          "https://www.wonderland.gr.jp/kashima/",
    "ワンダーランド中津米山店":      "https://www.wonderland.gr.jp/nakatsu/",
    "ワンダーランド大分皆春店":      "https://www.wonderland.gr.jp/minaharu/",
    "ワンダーランド1177大分南店":    "https://www.wonderland.gr.jp/oitaminami/",
    "ワンダーランド臼杵店":          "https://www.wonderland.gr.jp/usuki/",
    "ワンダーランド光の森店":        "https://www.wonderland.gr.jp/hikarinomori/",
    "ワンダーランド佐世保白岳店":    "https://www.wonderland.gr.jp/s-sasebo/",
    "ワンダーランド諫早店":          "https://www.wonderland.gr.jp/isahaya/",
    "ワンダーランド1188鹿児島新栄店": "https://www.wonderland.gr.jp/k-shinei/",
    "ワンダーランド1177谷山店":      "https://www.wonderland.gr.jp/taniyama/",
    "ワンダーランド1188宮崎芳士店":  "https://www.wonderland.gr.jp/m-houji/",
    "ワンダーランド小戸本館":        "https://www.wonderland.gr.jp/odo/",
    "ワンダーランド小戸Ⅱ":          "https://www.wonderland.gr.jp/odo2/",
    "ワンダーランド1188大刀洗店":    "https://www.wonderland.gr.jp/tachiarai/",
}

# チェーンHPからの個別店舗ページ取得設定
# method: "js_search" → Playwright で検索フォームを操作
# method: "static_list" → 静的な店舗一覧ページから全店を収集
CHAIN_HP_CONFIGS: dict[str, dict] = {
    "maruhan.co.jp": {
        "method": "js_search",
        "search_url": "https://www.maruhan.co.jp/hall/",
        "name_prefix": ["■マルハン", "□マルハン", "マルハン"],
        # 検索inputのセレクタ候補（複数試す）
        "search_selectors": [
            "input[placeholder*='店舗名']",
            "input[placeholder*='フリーワード']",
            "input[placeholder*='キーワード']",
            "input[type='search']",
            ".keyword-input input",
            "#keyword",
            "input[name='keyword']",
        ],
        "result_link_selector": "a[href*='/hall/store'], a[href*='/hall/shop'], .store-name a, .hall-name a",
    },
    "dynam.jp": {
        "method": "js_search",
        "search_url": "https://www.dynam.jp/shop/search/",
        "name_prefix": ["ダイナム"],
        "search_selectors": [
            "input[placeholder*='店舗名']",
            "input[placeholder*='フリーワード']",
            "input[placeholder*='キーワード']",
            "input[type='search']",
            "input[name='keyword']",
            "#keyword",
        ],
        "result_link_selector": "a[href*='/shop/'], .shop-name a, .store-list a",
    },
    "wonderland.gr.jp": {
        "method": "static_list",
        "list_url": "https://www.wonderland.gr.jp/all_usrs/1.html",
        "base_url": "https://www.wonderland.gr.jp",
        "name_prefix": ["ワンダーランド"],
    },
}


# フロアマップ画像と判定するキーワード（URL・alt・周辺テキスト）
_FLOOR_MAP_IMG_RE = re.compile(
    r"(floor|フロア|flo_|map|layout|配置|台配置|マップ|floor_map|floormap)",
    re.IGNORECASE,
)
_FLOOR_MAP_NEARBY_RE = re.compile(r"(フロアマップ|フロア|台配置|マップ|平面図)")


def _to_absolute_url(src: str, page_url: str) -> str:
    """相対URLを絶対URLに変換する"""
    if src.startswith("http"):
        return src
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        parts = page_url.split("/")
        origin = parts[0] + "//" + parts[2]   # "https://domain.com"
        return origin + src
    return src


def _find_floor_map_in_page(page) -> str | None:
    """現在開いているページからフロアマップ画像URLを探す（店舗HP・X専用）"""
    try:
        # Pass 1: URLまたはaltにフロアマップキーワードがある画像
        for img in page.query_selector_all("img[src]"):
            src = img.get_attribute("src") or ""
            alt = img.get_attribute("alt") or ""
            if not (_FLOOR_MAP_IMG_RE.search(src) or _FLOOR_MAP_IMG_RE.search(alt)):
                continue
            # アイコン・ロゴ（極小サイズ）を除外
            try:
                w = img.evaluate("el => el.naturalWidth")
                h = img.evaluate("el => el.naturalHeight")
                if w and h and (w < 100 or h < 100):
                    continue
            except Exception:
                pass
            if src:
                return _to_absolute_url(src, page.url)

        # Pass 2: 「フロアマップ」テキストの近くにある画像
        for img in page.query_selector_all("img[src]"):
            src = img.get_attribute("src") or ""
            if not src or src.endswith(".svg"):
                continue
            try:
                nearby = img.evaluate(
                    "el => (el.closest('section,div,td,li') || el.parentElement || {}).innerText || ''"
                )
                if _FLOOR_MAP_NEARBY_RE.search(nearby or ""):
                    return _to_absolute_url(src, page.url)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fetch_floor_map_from_dmm(page, store_name: str) -> str | None:
    """
    ⚠️ 法的リスク回避のため無効化（2026-05）。
    DMM/p-town からのフロアマップ取得は一切行わない。常に None を返す。
    """
    return None


def _strip_name_prefix(name: str, prefixes: list[str]) -> str:
    """店舗名からチェーン名プレフィックスと特殊文字を除去して検索用テキストを返す"""
    # 先頭の特殊文字を除去
    clean = re.sub(r'^[■□▲▼●○◆◇★☆\s]+', '', name)
    for p in prefixes:
        if clean.startswith(p):
            clean = clean[len(p):]
            break
    return clean.strip()


def _x_search_floor_map(page, query: str) -> str | None:
    """X検索クエリを実行してフロアマップ画像URLを返す"""
    try:
        encoded = query.replace(" ", "%20").replace('"', "%22")
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=5000)
        except Exception:
            pass
        for _ in range(2):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)
        for article in page.query_selector_all('article[data-testid="tweet"]')[:20]:
            try:
                for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
                    src = img.get_attribute("src") or ""
                    if src:
                        return src
            except Exception:
                continue
    except Exception:
        pass
    return None


def _x_profile_floor_map(page, x_url: str) -> str | None:
    """店舗の公式Xプロフィールからフロアマップ画像URLを返す"""
    try:
        page.goto(x_url, timeout=12000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        for article in page.query_selector_all('article[data-testid="tweet"]')[:30]:
            try:
                text = ""
                el = article.query_selector('[data-testid="tweetText"]')
                if el:
                    text = el.inner_text() or ""
                if not _FLOOR_MAP_NEARBY_RE.search(text):
                    continue
                for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
                    src = img.get_attribute("src") or ""
                    if src:
                        return src
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fetch_floor_map_via_chain_hp_js(page, store: dict, cfg: dict) -> str | None:
    """
    Playwrightでチェーン検索ページを操作して個別店舗ページへ遷移し
    フロアマップ画像を取得する（マルハン・ダイナム等JS-renderedサイト用）
    """
    name = store.get("name", "")
    clean = _strip_name_prefix(name, cfg.get("name_prefix", []))
    if not clean:
        return None

    try:
        page.goto(cfg["search_url"], timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # 検索inputを探して店舗名を入力
        found_input = False
        for sel in cfg.get("search_selectors", []):
            el = page.query_selector(sel)
            if el:
                try:
                    el.fill(clean)
                    page.wait_for_timeout(300)
                    el.press("Enter")
                    found_input = True
                    break
                except Exception:
                    continue

        if not found_input:
            return None

        page.wait_for_timeout(3000)

        # 検索結果から店舗リンクを探す
        for result_sel in cfg.get("result_link_selector", "").split(", "):
            for a in page.query_selector_all(result_sel.strip())[:5]:
                try:
                    href = a.get_attribute("href") or ""
                    text = (a.inner_text() or "").strip()
                    if not href:
                        continue
                    # 店舗名の一部が含まれるリンクを優先
                    if clean[:3] in text or clean[:3] in href:
                        target = _to_absolute_url(href, cfg["search_url"])
                        page.goto(target, timeout=12000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        return _find_floor_map_in_page(page)
                except Exception:
                    continue

    except Exception:
        pass

    return None


# ワンダーランド店舗リスト（slug → 店舗名）キャッシュ
_wonderland_slug_map: dict[str, str] = {}


def _fetch_floor_map_via_wonderland(page, store: dict) -> str | None:
    """
    ワンダーランドの全店舗リストから該当店舗ページを特定してフロアマップを取得する
    """
    global _wonderland_slug_map
    name = store.get("name", "")

    # 一度だけスラッグリストを取得してキャッシュ
    if not _wonderland_slug_map:
        try:
            page.goto("https://www.wonderland.gr.jp/all_usrs/1.html",
                      timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            for a in page.query_selector_all("a[href]"):
                href = a.get_attribute("href") or ""
                # /kashii/ のような1段のスラッグのみ
                if re.match(r'^/[a-z0-9_-]+/$', href):
                    _wonderland_slug_map[href] = ""  # 店舗名は後で取得
            log(f"   ワンダーランド スラッグ数: {len(_wonderland_slug_map)}")
        except Exception:
            pass

    if not _wonderland_slug_map:
        return None

    # 各ページを訪問して店舗名を照合
    for slug, cached_name in list(_wonderland_slug_map.items()):
        # キャッシュ済みの場合はスキップ（対象店舗と一致しなければ）
        if cached_name and cached_name != name:
            continue

        store_url = f"https://www.wonderland.gr.jp{slug}"
        try:
            page.goto(store_url, timeout=12000, wait_until="domcontentloaded")
            page.wait_for_timeout(800)

            # ページ内の店舗名を取得
            page_name = ""
            for sel in ["h1", ".shop-name", ".store-name", "title"]:
                el = page.query_selector(sel)
                if el:
                    t = el.inner_text() or ""
                    if "ワンダーランド" in t:
                        page_name = t.strip()
                        break
            if not page_name:
                # bodyテキストから店舗名を探す
                body = page.evaluate("() => document.body.innerText")
                m = re.search(r'ワンダーランド[^\n\r　]{1,20}', body or "")
                if m:
                    page_name = m.group(0).strip()

            _wonderland_slug_map[slug] = page_name

            # 店舗名が一致したらフロアマップを探す
            if page_name and (
                name in page_name or page_name in name or
                _strip_name_prefix(name, ["ワンダーランド"]) in page_name
            ):
                img_url = _find_floor_map_in_page(page)
                if img_url:
                    return img_url
                # フロアマップキーワードなし → 大きな画像（200×200以上）を候補に
                for img in page.query_selector_all("img[src]"):
                    src = img.get_attribute("src") or ""
                    if not src or src.endswith(".svg") or "icon" in src.lower():
                        continue
                    try:
                        w = img.evaluate("el => el.naturalWidth")
                        h = img.evaluate("el => el.naturalHeight")
                        if w and h and w >= 300 and h >= 200:
                            return _to_absolute_url(src, store_url)
                    except Exception:
                        continue
                break  # 名前が一致するページを処理したら終了
        except Exception:
            continue

    return None


def _fetch_floor_map_for_store(page, store: dict) -> str | None:
    """
    1店舗のフロアマップURLを取得する。
    優先順位:
      1. DMM p-town（最多カバレッジ、UIには表示せずローカル保存のみ）
      2. チェーンHP個別店舗ページ（マルハン・ダイナム: Playwright検索 / ワンダーランド: 静的リスト）
      3. X検索「"店舗名" フロアマップ」
      4. X検索「"店舗名" 台配置」（フロアマップ代替キーワード）
      5. 公式X プロフィール（x_url がある場合）
    """
    name  = store.get("name", "")
    x_url = store.get("x_url") or ""
    hp_url = store.get("hp_url") or ""

    # ── Step 1: DMM p-town フロアマップ検索 ──
    # UIにDMMリンクは表示しない。フロアマップ画像データのみローカル保存に使う。
    url = _fetch_floor_map_from_dmm(page, name)
    if url:
        return url

    # ── Step 2: チェーンHP個別店舗ページ ──
    if hp_url:
        domain = hp_url.split("/")[2] if "//" in hp_url else ""
        for chain_domain, cfg in CHAIN_HP_CONFIGS.items():
            if chain_domain in domain:
                try:
                    if cfg["method"] == "js_search":
                        url = _fetch_floor_map_via_chain_hp_js(page, store, cfg)
                    elif cfg["method"] == "static_list" and chain_domain == "wonderland.gr.jp":
                        url = _fetch_floor_map_via_wonderland(page, store)
                    else:
                        url = None
                    if url:
                        return url
                except Exception:
                    pass

    # ── Step 3: X検索「"店舗名" フロアマップ」──
    url = _x_search_floor_map(page, f'"{name}" フロアマップ')
    if url:
        return url

    # ── Step 4: X検索「"店舗名" 台配置」──
    url = _x_search_floor_map(page, f'"{name}" 台配置')
    if url:
        return url

    # ── Step 5: 公式X プロフィール ──
    if x_url:
        url = _x_profile_floor_map(page, x_url)
        if url:
            return url

    return None


def update_stores_metadata(page):
    """stores.json の各店舗に対して is_low_rental とチェーン別X URLを更新する"""
    if not STORES_JSON.exists():
        return

    with open(STORES_JSON, encoding="utf-8") as f:
        stores = json.load(f)

    changed = 0
    for s in stores:
        name = s.get("name", "")
        # 低貸し専門店フラグ
        if not s.get("is_low_rental") and _is_low_rental(name):
            s["is_low_rental"] = True
            changed += 1
        # チェーン別X URL（ミリオン・ワンダーランド等）
        if not s.get("x_url") and name in CHAIN_X_URLS and CHAIN_X_URLS[name]:
            s["x_url"] = CHAIN_X_URLS[name]
            changed += 1
        # ワンダーランド個別HP URL（チェーン本社URLを個別ページURLに更新）
        if name in WONDERLAND_HP_URLS:
            new_hp = WONDERLAND_HP_URLS[name]
            if s.get("hp_url") != new_hp:
                s["hp_url"] = new_hp
                changed += 1

    if changed > 0:
        with open(STORES_JSON, "w", encoding="utf-8") as f:
            json.dump(stores, f, ensure_ascii=False, indent=2)
        log(f"🏪 stores metadata updated: {changed} fields changed")


def _download_floor_map(remote_url: str, store_id: str) -> str | None:
    """
    フロアマップ画像をダウンロードして public/floor_maps/[store_id].jpg に保存する。
    保存成功時は '/floor_maps/[store_id].jpg'（サイト内パス）を返す。
    失敗時は None を返す。
    """
    FLOOR_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".jpg"
    if remote_url.lower().endswith(".png"):
        ext = ".png"
    elif remote_url.lower().endswith(".webp"):
        ext = ".webp"
    local_path = FLOOR_MAPS_DIR / f"{store_id}{ext}"

    try:
        req = urllib.request.Request(
            remote_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        # 最低限のサイズチェック（1KB未満はスキップ）
        if len(data) < 1024:
            return None
        local_path.write_bytes(data)
        return f"/floor_maps/{store_id}{ext}"
    except Exception as e:
        log(f"      ↳ ダウンロード失敗: {e}")
        return None


def fetch_floor_maps(page):
    """
    全店舗のフロアマップを取得・ローカル保存する。
    - HP URLがある全店を対象（制限なし）
    - 毎回全店を再チェックして変更を検知
    - 取得した画像は public/floor_maps/ にダウンロード保存（外部サイト不使用）
    - floor_map_url はサイト内パス（/floor_maps/xxx.jpg）として保存
    - 10件ごとに中間保存
    """
    if not STORES_JSON.exists():
        return

    with open(STORES_JSON, encoding="utf-8") as f:
        stores = json.load(f)

    # 未取得の店舗を event_count 降順で最大 50 件処理（既取得はスキップ）
    no_map = sorted(
        [s for s in stores if s.get("event_count", 0) > 0 and not s.get("floor_map_url")],
        key=lambda s: s.get("event_count", 0),
        reverse=True,
    )
    targets = no_map[:50]
    if not targets:
        log("🗺  フロアマップ未取得店舗なし（全店取得済み）")
        return

    store_map = {s["name"]: s for s in stores}
    log(f"🗺  フロアマップ取得開始: {len(targets)}店舗（X検索方式・未取得優先・最大50件）")
    changed = 0

    for i, s in enumerate(targets, 1):
        name     = s.get("name", "")
        store_id = s.get("id", hashlib.md5(name.encode()).hexdigest()[:10])
        old_local = s.get("floor_map_url")  # 既存のサイト内パス

        # リモート画像URLを取得
        try:
            remote_url = _fetch_floor_map_for_store(page, s)
        except Exception as e:
            log(f"   ⚠️  [{i}/{len(targets)}] {name[:20]}: 取得エラー {e}")
            remote_url = None

        if remote_url:
            # ダウンロードしてローカルに保存
            local_path = _download_floor_map(remote_url, store_id)
            if local_path and local_path != old_local:
                s["floor_map_url"] = local_path
                store_map[name]["floor_map_url"] = local_path
                changed += 1
                status = "更新" if old_local else "新規"
                log(f"   🗺 [{i}/{len(targets)}] {status}: {name[:20]} → {local_path}")
            elif not local_path:
                log(f"   ─  [{i}/{len(targets)}] DL失敗: {name[:20]}")
            else:
                log(f"   ─  [{i}/{len(targets)}] 変化なし: {name[:20]}")
        elif old_local:
            # 以前取得できていたが今回は取れなかった → 既存を保持（消さない）
            log(f"   ─  [{i}/{len(targets)}] 取得不可（既存保持）: {name[:20]}")
        else:
            log(f"   ─  [{i}/{len(targets)}] 未取得: {name[:20]}")

        # 10件ごとに中間保存
        if i % 10 == 0 and changed > 0:
            with open(STORES_JSON, "w", encoding="utf-8") as f:
                json.dump(list(store_map.values()), f, ensure_ascii=False, indent=2)
            log(f"   💾 中間保存 ({i}/{len(targets)}, 更新:{changed}件)")

    # 最終保存
    if changed > 0:
        with open(STORES_JSON, "w", encoding="utf-8") as f:
            json.dump(list(store_map.values()), f, ensure_ascii=False, indent=2)
        log(f"🗺  フロアマップ完了: {changed}件更新 / {len(targets)}店舗")


if __name__ == "__main__":
    main()
