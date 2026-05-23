#!/usr/bin/env python3
"""
X (Twitter) から店舗アカウントが投稿した「コンプリート」情報を収集して
public/complete_info.json を生成する。

店舗が上げているツイートのみ対象:
  - 台番号（○○番台）が含まれる
  - コンプリート機能 発動/作動
  - おめでとうございます + コンプリート
  - 店舗の挨拶パターン

Usage:
    python scripts/fetch_complete_info.py
    python scripts/fetch_complete_info.py --headless
    python scripts/fetch_complete_info.py --date 2026-05-20
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

COMPLETE_JSON      = Path(__file__).parent.parent / "public/complete_info.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"

# ---------------------------------------------------------------------------
# 検索クエリ（店舗投稿に特化）
# ---------------------------------------------------------------------------
COMPLETE_QUERIES = [
    # 台番号 × 機能発動系（最高精度）
    "コンプリート機能発動 番台",
    "コンプリート機能作動 番台",
    "コンプリート達成おめでとう 番台",
    "コンプリート達成 番台 スロット",
    "コンプリート機能 番台 パチスロ",
    "コンプリート おめでとうございます 番台",
    "番台 コンプリート機能発動",
    "番台 コンプリート達成",
    # ハッシュタグ系（店舗は公式タグを使う）
    "#コンプリート 番台 スロット",
    "#スマスロ コンプリート 番台",
    "#パチスロ コンプリート 番台",
    "#コンプリート機能発動",
    "#コンプリート達成 スロット",
    # 全台系
    "全台コンプリート スロット 店",
    "全台コンプリート 番台",
    # スマスロ特化（近年増加）
    "スマスロ コンプリート機能 発動",
    "スマスロ コンプリート おめでとうございます",
    # 機種名 × コンプリート（人気機種）
    "ヴァルヴレイヴ コンプリート機能",
    "北斗 コンプリート機能発動",
    "バジリスク コンプリート機能 番台",
    "炎炎ノ消防隊 コンプリート 番台",
    # ─── チェーン店名 × コンプリート（拾いきれていた店舗対策）───
    "ダイナム コンプリート 番台",
    "ダイナム コンプリート機能",            # 番台なしダイナム
    "ダイナム 金町 コンプリート",           # ダイナム金町南口専用
    "金町 コンプリート スマスロ",
    "楽園 コンプリート 番台",
    "マルハン コンプリート 番台",
    "キコーナ コンプリート 番台",
    "ガーデン コンプリート 番台",
    "メガガイア コンプリート 番台",
    "キャッスル コンプリート 番台",
    "パラッツォ コンプリート 番台",
    "コンコルド コンプリート 番台",
    "ZENT コンプリート 番台",
    "メッセ コンプリート 番台",
    "ガイア コンプリート 番台",
    "ミリオン コンプリート 番台",
    # 番台なし店舗対策（低貸・地域ホール）
    "コンプリート機能発動 店 おめでとう",
    "コンプリート達成 ホール おめでとう",
    "低貸 コンプリート 達成",
    "コンプリート 機能発動 パチンコ店",
    # 追加機種
    "牙狼 コンプリート 番台",
    "攻殻機動隊 コンプリート 番台",
    "チバリヨ コンプリート 番台",
    "東京喰種 コンプリート 番台",
    "吉宗 コンプリート 番台",
    "沖ドキ コンプリート 番台",
    "ゴジラ コンプリート 番台",
    "ブルーロック コンプリート 番台",
    "キン肉マン コンプリート 番台",
    "からくりサーカス コンプリート 番台",
    "モンキーターン コンプリート 番台",
    "カバネリ コンプリート 番台",
    "Re:ゼロ コンプリート 番台",
    "転スラ コンプリート 番台",
    "バイオハザード コンプリート 番台",
    # ─── 画像付き限定（店舗投稿は画像が多い）───
    "コンプリート機能発動 filter:media",
    "コンプリート達成 番台 filter:media",
    "#コンプリート機能発動 filter:media",
    "コンプリート おめでとうございます filter:media",
    # ─── 拡張パターン（番台なし店舗対策）───
    "コンプリート機能 発動 スロット",
    "コンプリート達成 スマスロ",
    "コンプリート機能 おめでとうございます",
    "本日 コンプリート機能 発動",
    "コンプリート 速報 番台",
    "同時コンプリート スロット",
]

# ---------------------------------------------------------------------------
# 店舗ツイート判定: これらのいずれかを含む = 店舗の投稿
# ---------------------------------------------------------------------------
STORE_TWEET_PATTERNS = [
    re.compile(r'\d{2,4}番台'),                              # 台番号（最強シグナル）
    re.compile(r'コンプリート機能(?:が|を)?(?:発動|作動)'),  # 機能発動/作動
    re.compile(r'コンプリート(?:達成)?おめでとうございます'), # 店舗の祝福メッセージ
    re.compile(r'おめでとうございます.*コンプリート', re.DOTALL),
    re.compile(r'こんばんは.{0,20}(?:店|ホール)', re.DOTALL), # 店舗の挨拶
    re.compile(r'こんにちは.{0,20}(?:店|ホール)', re.DOTALL),
    re.compile(r'お知らせ.{0,30}コンプリート', re.DOTALL),   # お知らせ投稿
    re.compile(r'本日.*コンプリート.*機能', re.DOTALL),
    re.compile(r'該当台は明日から'),                          # DMM公式フレーズ
    re.compile(r'明日朝.*ご遊技'),                            # 店舗の翌日案内
    re.compile(r'#コンプリート機能発動'),                     # ハッシュタグ
    re.compile(r'#コンプリート達成'),
    re.compile(r'全台コンプリート'),                          # 全台コンプリート
    re.compile(r'ご来店.*コンプリート|コンプリート.*ご来店', re.DOTALL),
    # 追加: 番台なしでも店舗と判断できるパターン
    re.compile(r'コンプリート(?:達成|機能).{0,50}(?:店|ホール|パーラー)', re.DOTALL),
    re.compile(r'(?:店|ホール|パーラー).{0,50}コンプリート(?:達成|機能)', re.DOTALL),
    re.compile(r'本日.*コンプリート.*達成', re.DOTALL),
    re.compile(r'コンプリート達成.*本日', re.DOTALL),
    re.compile(r'(?:当店|弊店|当ホール).*コンプリート', re.DOTALL),
    re.compile(r'コンプリート.*(?:当店|弊店|当ホール)', re.DOTALL),
    re.compile(r'低貸.*コンプリート|コンプリート.*低貸', re.DOTALL),
]

# ---------------------------------------------------------------------------
# 除外パターン（個人プレイヤーの投稿）
# ---------------------------------------------------------------------------
EXCLUDE_PATTERNS = [
    re.compile(r'youtube\.com', re.IGNORECASE),
    re.compile(r'生配信|ライブ配信'),
    re.compile(r'ブログ'),
    re.compile(r'ミッションコンプリート'),
    re.compile(r'ガチャ.*コンプ|コンプ.*ガチャ'),
    re.compile(r'コンプリート率が基準値'),
    re.compile(r'コレクション.*コンプ'),
]

# ---------------------------------------------------------------------------
# 機種名抽出パターン（優先度順）
# ---------------------------------------------------------------------------
MACHINE_PATTERNS = [
    re.compile(r'[『「【]([^』」】]{3,30})[』」】](?:にて|で|の)?(?:コンプリート|コンプ)'),
    re.compile(r'(?:スマスロ|Lパチスロ|パチスロ|スマパチ)\s*[　]?([^\s　\n#「」【】、。！!]{3,25}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|\d+番台))'),
    re.compile(r'\bL([^\s　\n#「」【】、。！!]{3,20}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|\d+番台))'),
    re.compile(r'\d{2,4}番台\s*(?:の\s*)?[^\s\n]{0,3}?([^\s\n#]{3,25}?)(?=\s*(?:にて|で|が|コンプ|\n))'),
    re.compile(r'(北斗[^\s　\n#「」【】、。！!]{1,15})'),
    re.compile(r'(バジリスク[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(ミリオンゴッド[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(東京喰種[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(ヴァルヴレイヴ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(炎炎ノ消防隊[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(攻殻機動隊[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(カバネリ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(モンスターハンター[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(リコリス[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(ゾンビランドサガ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(ジャグラー[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(牙狼[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(チバリヨ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(吉宗[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(鉄拳[^\s　\n#「」【】、。！!]{0,10})'),
]

# ---------------------------------------------------------------------------
# 店舗名抽出パターン
# ---------------------------------------------------------------------------
STORE_PATTERNS = [
    # 挨拶パターン
    re.compile(r'こんばんは\s*([^\s　\n「」、。！!]{2,20}(?:店|ホール))(?:です|でございます)'),
    re.compile(r'こんにちは\s*([^\s　\n「」、。！!]{2,20}(?:店|ホール))(?:です|でございます)'),
    # 「この後も #店名 で」「#店名 です」形式（店/ホール不要）
    re.compile(r'(?:この後も|当店|当ホール)\s*#([^\s　\n#「」【】、。！!]{2,20})\s*(?:で|です)'),
    re.compile(r'(?:ぜひ|是非)\s*#([^\s　\n#「」【】、。！!]{2,20})\s*(?:へ|に|で)'),
    # ハッシュタグ: 大手チェーン名（店/ホールなし）
    re.compile(r'#((?:キャッスル|ガーデン|マルハン|キコーナ|ダイナム|アミューズ|コンコルド|ワンダーランド|ビックマーチ|ミリオン|楽園|Dステーション|メッセ|クリエ|グランド|ゴールド|スクェア|フェイス|ニューアルファ|ジャパン|コスモ|エスパス|スーパーUSA|ライラック|ガイア|フラミンゴ|ZENT|ゼント)[^\s　\n#「」【】、。！!]{0,15})'),
    # ハッシュタグ: 店/ホール付き
    re.compile(r'#([^\s　\n#「」【】、。！!]{2,20}(?:店|ホール|パーラー))'),
    # 大手チェーン名をテキスト内で直接マッチ
    re.compile(r'(マルハン[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(キコーナ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(楽園[^\s　、。！!\n]{0,15}(?:店|ホール))'),
    re.compile(r'(ダイナム[^\s　、。！!\n]{0,25}(?:店|ホール|南口|北口|東口|西口)?)'),
    re.compile(r'(キャッスル[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(アミューズ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(Ｄステーション|Dステーション[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(コンコルド[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ワンダーランド[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ビックマーチ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ミリオン[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(メッセ[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'(クリエ[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'(グランキコーナ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(メガフェイス[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ZENT|ゼント[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'([^\s　\n「」【】]{2,15}(?:パチンコ|スロット)[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'([^\s　\n「」【】、。！!]{2,15}(?:店|ホール))(?:です|でございます|より|です♪|でした|です！)'),
]

STORE_NG = ["ご来店", "来店", "閉店", "景品", "感謝", "毎日", "通常", "本日の遊技", "空台",
            "ミリオンゴッド", "ゴッド", "ヴァルヴレイヴ", "バジリスク", "北斗の拳", "炎炎ノ消防隊",
            "攻殻機動隊", "カバネリ", "モンスターハンター", "ジャグラー", "牙狼", "吉宗", "鉄拳"]


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _get_cookies() -> list[dict]:
    """
    GitHub Actions: 環境変数 X_AUTH_TOKEN / X_CT0 から取得
    ローカル: Chromeのcookieから取得
    """
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0        = os.environ.get("X_CT0", "")

    if auth_token and ct0:
        log("🔑 環境変数からXのcookieを注入（CI環境）")
        return [
            {"name": "auth_token", "value": auth_token,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0", "value": ct0,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ]

    if not HAS_BROWSER_COOKIE3:
        return []
    result = []
    try:
        jar = browser_cookie3.chrome(domain_name=".x.com")
        for c in jar:
            pw_cookie: dict = {
                "name": c.name, "value": c.value,
                "domain": c.domain if c.domain else ".x.com",
                "path": c.path or "/", "secure": bool(c.secure),
                "httpOnly": False, "sameSite": "None",
            }
            if c.expires:
                pw_cookie["expires"] = int(c.expires)
            result.append(pw_cookie)
        log(f"🍪 Chrome cookie {len(result)}個取得")
    except Exception as e:
        log(f"⚠️  browser_cookie3: {e}")
    return result


def launch_browser(playwright, headless: bool):
    PLAYWRIGHT_PROFILE.mkdir(parents=True, exist_ok=True)
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
    cookies = _get_cookies()
    if cookies:
        ctx.add_cookies(cookies)
        log(f"✅ Cookie {len(cookies)}個注入")
    return ctx


def is_store_tweet(text: str) -> bool:
    """店舗アカウントの投稿かどうか判定"""
    # 除外パターンに引っかかるものはスキップ
    for pat in EXCLUDE_PATTERNS:
        if pat.search(text):
            return False
    # 店舗投稿パターンのどれかにマッチ
    return any(pat.search(text) for pat in STORE_TWEET_PATTERNS)


def extract_machine(text: str) -> str:
    for pat in MACHINE_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if len(name) < 2 or re.match(r'^[#@\s!！]+$', name):
                continue
            if "http" in name.lower():
                continue
            if name in ("スロ", "パチスロ", "スマスロ", "スマパチ", "コンプリート"):
                continue
            return name[:35]
    return ""


def extract_store(text: str) -> str:
    for pat in STORE_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if len(name) < 3:
                continue
            if any(ng in name for ng in STORE_NG):
                continue
            if re.match(r'^\d', name):
                continue
            return name[:28]
    return ""


def extract_slot_number(text: str) -> str:
    """台番号を抽出"""
    m = re.search(r'(\d{2,4})番台', text)
    return m.group(1) if m else ""


def extract_images(article) -> list[str]:
    imgs = []
    for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
        src = img.get_attribute("src") or ""
        if src and src not in imgs:
            src = re.sub(r'\?.*$', '?format=jpg&name=large', src)
            imgs.append(src)
    return imgs


def get_tweet_datetime(article) -> tuple[str, str]:
    """Xの<time datetime="...">からJSTの (date, time) を取得して返す"""
    try:
        time_el = article.query_selector("time")
        if time_el:
            dt = time_el.get_attribute("datetime") or ""
            if dt:
                # "2026-05-20T13:30:00.000Z" → JST date + time
                m = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', dt)
                if m:
                    yr, mo, dy, h, mn = (int(x) for x in m.groups())
                    # UTC → JST (+9h)
                    h += 9
                    if h >= 24:
                        h -= 24
                        # 日付を1日進める
                        from datetime import date as _date, timedelta
                        d = _date(yr, mo, dy) + timedelta(days=1)
                        return d.strftime("%Y-%m-%d"), f"{h:02d}:{mn:02d}"
                    return f"{yr}-{mo:02d}-{dy:02d}", f"{h:02d}:{mn:02d}"
    except Exception:
        pass
    return "", ""


AUTHOR_NG = ["コンプリート", "パチスロ", "スロット", "パチンコ", "スマスロ", "速報", "まとめ", "情報", "bot"]

def _is_store_name(name: str) -> bool:
    """表示名が店舗名っぽいかどうか"""
    if len(name) < 3 or len(name) > 30:
        return False
    if any(ng in name for ng in AUTHOR_NG):
        return False
    return bool(re.search(r'店|ホール|パーラー|PALACE|palace|ランド|マルハン|キコーナ|ダイナム', name))


def parse_tweet(text: str, tweet_url: str, images: list[str],
                today_str: str, tweet_date: str, tweet_time: str,
                author_name: str = "") -> dict | None:
    if not is_store_tweet(text):
        return None

    store = extract_store(text)
    # テキストから取れなければ作者の表示名を使う
    if not store and author_name and _is_store_name(author_name):
        store = author_name[:28]
    # それでも取れなければ表示名をそのまま（2文字以上・URL/記号なし）
    if not store and author_name and 2 <= len(author_name) <= 25 and "http" not in author_name:
        if not re.search(r'^[a-zA-Z0-9@_\-\.]+$', author_name):  # 英数字のみは除外
            store = author_name[:28]
    machine = extract_machine(text)
    slot_number = extract_slot_number(text)

    # 機種名も店舗名も台番号も取れないものは除外
    if not machine and not store and not slot_number:
        return None

    # Xの<time>から取得した日付を使う（取得できなければ収集日）
    if not tweet_date:
        tweet_date = today_str

    entry_id = hashlib.md5(tweet_url.encode()).hexdigest()[:12]

    return {
        "id": entry_id,
        "date": tweet_date,
        "time": tweet_time,                          # JST HH:MM
        "store": store,
        "machine": machine,
        "slot_number": slot_number,                  # 台番号
        "text": text[:250].replace("\n", " "),
        "images": images[:4],
        "image_url": images[0] if images else "",
        "x_url": tweet_url,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def scrape_query(page, query: str, today_str: str, max_tweets: int = 80) -> list[dict]:
    results = []
    seen_urls: set[str] = set()

    # 当日のみに絞る（JST基準）。until は翌日にして23:59のツイートも含む
    from datetime import date as _dt, timedelta
    since_date = today_str                                                     # 当日のみ
    until_date = (_dt.fromisoformat(today_str) + timedelta(days=1)).strftime("%Y-%m-%d")
    # -filter:retweets で RT を除外し、店舗の原投稿に絞る
    date_filter = f" since:{since_date} until:{until_date} -filter:retweets"
    encoded = (query + date_filter).replace(" ", "%20").replace("#", "%23")
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        log(f"  ⏱ Timeout: {query}")
        return results

    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
    except PlaywrightTimeout:
        pass

    for _ in range(30):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(600)

    articles = page.query_selector_all('article[data-testid="tweet"]')

    for article in articles[:max_tweets]:
        try:
            text = ""
            for sel in ['[data-testid="tweetText"]', '[lang]']:
                el = article.query_selector(sel)
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

            tweet_date, tweet_time = get_tweet_datetime(article)
            images = extract_images(article)
            # 作者表示名を取得（ツイートカードのUser-Name）
            author_name = ""
            try:
                author_el = article.query_selector('[data-testid="User-Name"] span')
                if author_el:
                    author_name = author_el.inner_text().strip()
            except Exception:
                pass
            entry = parse_tweet(text, tweet_url, images, today_str, tweet_date, tweet_time, author_name)
            if entry:
                results.append(entry)
                store_label   = entry["store"] or "店舗不明"
                machine_label = entry["machine"] or "機種不明"
                slot          = f" [{entry['slot_number']}番台]" if entry["slot_number"] else ""
                img_count     = len(entry["images"])
                log(f"    ✅ {store_label} / {machine_label}{slot} (画像{img_count}枚) {entry['time']}")

        except Exception:
            continue

    return results


def load_all() -> list[dict]:
    if not COMPLETE_JSON.exists():
        return []
    with open(COMPLETE_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_complete(new_entries: list[dict], target_date: str):
    all_data = load_all()

    # 30日より古いデータを除去（ピンツイート対策）
    cutoff = (date.today() - __import__('datetime').timedelta(days=30)).strftime("%Y-%m-%d")
    all_data = [e for e in all_data if e.get("date", "") >= cutoff]

    # 既存IDセット（全期間）で重複防止
    existing_ids = {e["id"] for e in all_data}

    # 新規エントリー: 既存に無いものだけ追加（日付に関わらず全期間でIDチェック）
    new_only = [e for e in new_entries if e["id"] not in existing_ids]

    # コンプリート日付が30日以上前のものは追加しない（古いピンツイート対策）
    new_only = [e for e in new_only if e.get("date", "") >= cutoff]

    combined = all_data + new_only

    # コンプリートした日付（X datetime由来）→ 時刻 の新しい順でソート
    combined.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    combined = combined[:3000]

    with open(COMPLETE_JSON, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    # 本日（target_date）の合計件数
    today_total = sum(1 for e in combined if e.get("date") == target_date)
    log(f"💾 {len(new_only)}件新規追加 / {target_date}合計{today_total}件 / 全体{len(combined)}件")
    return len(new_only)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    # GH Actions は UTC で動くので JST (+9h) に変換する
    if args.date:
        today = args.date
    else:
        from datetime import timezone, timedelta
        JST = timezone(timedelta(hours=9))
        today = datetime.now(JST).strftime("%Y-%m-%d")

    log("=" * 60)
    log(f"🎰 コンプリート収集開始（店舗投稿のみ）  {today}  クエリ数={len(COMPLETE_QUERIES)}")

    all_new: list[dict] = []

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        try:
            page.goto("https://x.com/home", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            cur_url = page.url.lower()
            title = page.title()
            if "login" in cur_url or "flow" in cur_url:
                log(f"❌ Xにログインできていません (url={page.url})")
                ctx.close()
                return
            # ページタイトルで追加確認
            if title and "home" not in title.lower() and "x" not in title.lower():
                log(f"⚠️  ログインページタイトル異常: {title!r} — 続行")
            else:
                log(f"✅ Xログイン確認OK (title={title!r})")
        except PlaywrightTimeout:
            log("⚠️  ログイン確認タイムアウト — 続行")

        for i, query in enumerate(COMPLETE_QUERIES, 1):
            log(f"  [{i}/{len(COMPLETE_QUERIES)}] 🔍 {query}")
            try:
                results = scrape_query(page, query, today)
                log(f"       → {len(results)} 件（店舗投稿）")
                all_new.extend(results)
                time.sleep(2)
            except Exception as e:
                log(f"  ❌ {e}")

        page.close()
        ctx.close()

    # 重複除去
    seen: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen or seen.add(e["id"]))]  # type: ignore

    log(f"\n📊 収集: {len(deduped)} 件（店舗投稿・重複除去後）")

    if deduped:
        added = save_complete(deduped, today)
        log(f"✅ {added}件を新規追加")
    else:
        log("ℹ️  新規の店舗投稿コンプリートが見つかりませんでした")

    log(f"\n=== {today} 店舗コンプリート一覧 ===")
    today_entries = [e for e in deduped if e.get("date") == today]
    for e in today_entries:
        t = e.get("time", "--:--")
        store = e["store"] or "店舗不明"
        machine = e["machine"] or "機種不明"
        slot = f" [{e['slot_number']}番台]" if e.get("slot_number") else ""
        log(f"  🎰 {t} {store} / {machine}{slot}")

    log("=" * 60)


if __name__ == "__main__":
    main()
