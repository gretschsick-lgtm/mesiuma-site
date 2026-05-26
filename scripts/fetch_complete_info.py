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
RANKING_JSON       = Path(__file__).parent.parent / "public/complete_ranking.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"

# ---------------------------------------------------------------------------
# 検索クエリ（店舗投稿に特化）
# ---------------------------------------------------------------------------
COMPLETE_QUERIES = [
    # ══ 【核心クエリ】台番号 × 機能発動系（最高精度）══
    "コンプリート機能発動 番台",
    "コンプリート機能作動 番台",
    "番台 コンプリート達成",
    "コンプリート おめでとうございます 番台",

    # ══ 【ハッシュタグ】店舗は公式タグを使う ══
    "#コンプリート機能発動",
    "#コンプリート達成 スロット",
    "#スマスロ コンプリート 番台",
    "#パチスロ コンプリート 番台",

    # ══ 【スマスロ特化】══
    "スマスロ コンプリート機能 発動",
    "スマスロ コンプリート 達成 番台",

    # ══ 【機種名 × コンプリート】人気上位機種 ══
    "ヴァルヴレイヴ コンプリート 番台",
    "北斗転生 コンプリート 番台",
    "東京喰種 コンプリート 番台",
    "ミリオンゴッド コンプリート 番台",
    "炎炎ノ消防隊 コンプリート 番台",
    "カバネリ コンプリート 番台",
    "攻殻機動隊 コンプリート 番台",
    "バジリスク コンプリート 番台",
    "牙狼 コンプリート 番台",
    "キン肉マン コンプリート 番台",
    "吉宗 コンプリート 番台",
    "チバリヨ コンプリート 番台",
    "沖ドキ コンプリート 番台",
    "からくりサーカス コンプリート 番台",
    "モンキーターン コンプリート 番台",
    "Re:ゼロ コンプリート 番台",
    "バイオハザード コンプリート 番台",

    # ══ 【大手チェーン店名 × コンプリート】店舗直撃 ══
    "ダイナム コンプリート 番台",
    "ダイナム コンプリート機能",
    "マルハン コンプリート 番台",
    "キコーナ コンプリート 番台",
    "楽園 コンプリート 番台",
    "ガーデン コンプリート 番台",
    "キャッスル コンプリート 番台",
    "コンコルド コンプリート 番台",
    "ガイア コンプリート 番台",
    "ミリオン コンプリート 番台",
    "ワンダーランド コンプリート 番台",
    "ビックマーチ コンプリート 番台",
    "パラッツォ コンプリート 番台",

    # ══ 【画像付き検索】══
    "コンプリート機能発動 filter:media",
    "コンプリート達成 番台 filter:media",

    # ══ 【番台なし・店舗文体対策】══
    "コンプリート機能 発動 おめでとう",
    "本日 コンプリート機能 発動",
    "当店 コンプリート機能 発動",
    "コンプリート達成 スマスロ",
]

# ---------------------------------------------------------------------------
# 店舗ツイート判定: これらのいずれかを含む = 店舗の投稿
# ---------------------------------------------------------------------------
STORE_TWEET_PATTERNS = [
    re.compile(r'\d{2,4}番台'),                               # 台番号（最強シグナル）
    re.compile(r'コンプリート機能(?:が|を)?(?:発動|作動)'),   # 機能発動/作動（「機能」あり）
    re.compile(r'コンプリート(?:が|を)?(?:発動|作動)'),       # 機能発動/作動（「機能」なし）
    re.compile(r'コンプリート(?:達成)?おめでとうございます'),  # 店舗の祝福メッセージ
    re.compile(r'おめでとうございます.{0,60}コンプリート', re.DOTALL),
    re.compile(r'コンプリート.{0,60}おめでとう', re.DOTALL),  # おめでとうまでの範囲拡大
    re.compile(r'こんばんは.{0,20}(?:店|ホール)', re.DOTALL), # 店舗の挨拶
    re.compile(r'こんにちは.{0,20}(?:店|ホール)', re.DOTALL),
    re.compile(r'お知らせ.{0,30}コンプリート', re.DOTALL),    # お知らせ投稿
    re.compile(r'本日.*コンプリート', re.DOTALL),              # 本日+コンプリート（機能なし対応）
    re.compile(r'該当台は明日から'),                           # DMM公式フレーズ
    re.compile(r'明日朝.*ご遊技'),                             # 店舗の翌日案内
    re.compile(r'#コンプリート機能発動'),                      # ハッシュタグ
    re.compile(r'#コンプリート達成'),
    re.compile(r'全台コンプリート'),                           # 全台コンプリート
    re.compile(r'同時コンプリート'),                           # 同時コンプリート
    re.compile(r'ご来店.*コンプリート|コンプリート.*ご来店', re.DOTALL),
    re.compile(r'コンプリート.{0,80}(?:店|ホール|パーラー)', re.DOTALL),
    re.compile(r'(?:店|ホール|パーラー).{0,80}コンプリート', re.DOTALL),
    re.compile(r'コンプリート達成.*本日|本日.*コンプリート達成', re.DOTALL),
    re.compile(r'(?:当店|弊店|当ホール|自店).{0,50}コンプリート', re.DOTALL),
    re.compile(r'コンプリート.{0,50}(?:当店|弊店|当ホール|自店)', re.DOTALL),
    re.compile(r'低貸.*コンプリート|コンプリート.*低貸', re.DOTALL),
    re.compile(r'2台(?:同時)?.*コンプリート|コンプリート.*2台(?:同時)?', re.DOTALL),
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
    # ── パチスロ以外のコンプリートを除外 ──────────────────────────────
    re.compile(r'オリパ.*コンプ|コンプ.*オリパ'),             # TCGオリパ完売
    re.compile(r'トレカ|カードゲーム|TCG'),                   # トレカ店
    re.compile(r'金箱報酬|金箱.*コンプ'),                     # モバイルゲーム系
    re.compile(r'コンプリートまであと\d'),                     # 個人「あと○枚」未達成
    re.compile(r'アーカイブで視聴|配信.*コンプリートおめ'),     # VTuber視聴者コメント
    re.compile(r'プレイヤーLv|ランクアップ|レベルアップ.*コンプ'), # ソシャゲ/ゲーム系
    re.compile(r'フィギュア.*コンプ|コンプ.*フィギュア'),       # フィギュアコレクション
    re.compile(r'スタンプ.*コンプ|コンプ.*スタンプ'),           # スタンプカード
    re.compile(r'読了|クリア.*コンプリート'),                  # 読書・ゲームクリア
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


# ---------------------------------------------------------------------------
# 機種タイプ判定（パチスロ / パチンコ）
# ---------------------------------------------------------------------------

# L/Ｌ プレフィックス = スマスロ（パチスロ）
_SMASLO_PREFIX = re.compile(r'^[LＬ][^\s]')

# e/ｅ プレフィックス = スマパチ（パチンコ）
_SMAPACHI_PREFIX = re.compile(r'^[eｅ][^\s]')

# CR プレフィックス = パチンコ
_CR_PREFIX = re.compile(r'^CR')

# パチスロキーワード（L/eプレフィックスなしの機種名に使用）
_SLOT_KEYWORDS = [
    "スマスロ", "Lパチスロ", "パチスロ", "北斗", "ヴァルヴレイヴ", "ミリオンゴッド",
    "攻殻機動隊", "炎炎ノ消防隊", "東京喰種", "カバネリ", "バジリスク",
    "モンスターハンター", "リコリス", "ゾンビランドサガ", "ジャグラー",
    "チバリヨ", "吉宗", "鉄拳", "まどマギ", "鬼武者", "エウレカ",
    "Re:ゼロ", "転スラ", "バイオハザード", "ブルーロック",
]

# パチンコキーワード（eプレフィックスなしでも判定できるもの）
_PACHINKO_KEYWORDS = [
    "牙狼", "スマパチ", "大当たり", "確変", "甘デジ",
    "ミドル", "ライトミドル", "右打ち",
]


def get_machine_type(machine: str) -> str:
    """機種名からパチスロ(slot) / パチンコ(pachinko) を判定する。デフォルト: slot。

    優先順位:
    1. L/Ｌ プレフィックス → スマスロ (slot)
    2. e/ｅ プレフィックス → スマパチ (pachinko)
    3. CR プレフィックス  → パチンコ (pachinko)
    4. パチンコキーワード → pachinko
    5. スロットキーワード → slot
    6. デフォルト        → slot
    """
    if not machine:
        return "slot"
    m = machine.strip()

    # 1. L/Ｌ プレフィックス = スマスロ（スロット）
    if _SMASLO_PREFIX.match(m):
        return "slot"

    # 2. e/ｅ プレフィックス = スマパチ（パチンコ）
    if _SMAPACHI_PREFIX.match(m):
        return "pachinko"

    # 3. CR プレフィックス = パチンコ
    if _CR_PREFIX.match(m):
        return "pachinko"

    # 4. パチンコキーワード
    for kw in _PACHINKO_KEYWORDS:
        if kw in m:
            return "pachinko"

    # 5. スロットキーワード
    for kw in _SLOT_KEYWORDS:
        if kw in m:
            return "slot"

    return "slot"


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
            # 末尾の不要語・助詞を除去
            name = re.sub(
                r'(です|でした|でございます|ございます|より|ます|ました|ください|'
                r'させていただ|から|へ|では|として|にて|でお|は創業|周年).*$',
                '', name
            ).strip()
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


def extract_date_from_text(text: str, posting_date: str) -> str:
    """
    ツイートテキスト内の「5/24(日)」「5月24日(土)」形式の日付を抽出し、
    ツイート投稿日と近ければ（±3日）その日付を返す。
    抽出できなければ posting_date をそのまま返す。
    """
    if not posting_date:
        return posting_date
    # 曜日付きパターン優先（確実性が高い）: "5/24(日)" "5月24日(土)" 等
    # 曜日なしも許容するが括弧なし単独数字は誤検知しやすいので曜日必須
    m = re.search(r'(\d{1,2})[/月](\d{1,2})(?:日)?[（(][日月火水木金土][）)]', text)
    if not m:
        return posting_date
    mo_text, dy_text = int(m.group(1)), int(m.group(2))
    # 基準年: ツイート投稿年
    post_yr = int(posting_date[:4])
    for yr in [post_yr, post_yr - 1]:
        try:
            from datetime import date as _date, timedelta
            candidate = _date(yr, mo_text, dy_text)
            posting   = _date.fromisoformat(posting_date)
            if abs((posting - candidate).days) <= 3:
                return candidate.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return posting_date


def get_tweet_datetime(article) -> tuple[str, str]:
    """Xの<time datetime="...">からJSTの (date, time) を取得して返す"""
    from datetime import date as _date, timedelta as _td
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
                        d = _date(yr, mo, dy) + _td(days=1)
                        return d.strftime("%Y-%m-%d"), f"{h:02d}:{mn:02d}"
                    return f"{yr}-{mo:02d}-{dy:02d}", f"{h:02d}:{mn:02d}"
    except Exception:
        pass

    # <time> 取得失敗時: 相対時間テキスト（"1時間前"等）から推定
    try:
        time_el = article.query_selector("time")
        if time_el:
            rel = time_el.inner_text().strip()  # 例: "1時間前", "昨日", "5月26日"
            from datetime import timezone as _tz
            JST = _tz(_td(hours=9))
            now_jst = datetime.now(JST)
            # "昨日" → yesterday
            if "昨日" in rel:
                d = (now_jst - _td(days=1)).date()
                return d.strftime("%Y-%m-%d"), ""
            # "N時間前" (N=1..23) → same day or yesterday
            m2 = re.search(r'(\d+)時間前', rel)
            if m2:
                hours_ago = int(m2.group(1))
                d = (now_jst - _td(hours=hours_ago)).date()
                return d.strftime("%Y-%m-%d"), (now_jst - _td(hours=hours_ago)).strftime("%H:%M")
            # "N分前" → same day
            m3 = re.search(r'(\d+)分前', rel)
            if m3:
                mins_ago = int(m3.group(1))
                d = (now_jst - _td(minutes=mins_ago)).date()
                return d.strftime("%Y-%m-%d"), (now_jst - _td(minutes=mins_ago)).strftime("%H:%M")
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


def parse_tweet(text: str, tweet_url: str,
                today_str: str, tweet_date: str, tweet_time: str,
                author_name: str = "") -> dict | None:
    if not is_store_tweet(text):
        return None

    store = extract_store(text)

    # ── チェーン名のみ（支店名なし）で取れた場合は author_name を優先 ──
    # 例: "#ダイナム" → "ダイナム" のみ → author_name "ダイナム長野上田店" を使う
    CHAIN_ONLY = {"ダイナム", "マルハン", "キコーナ", "楽園", "ガイア", "キャッスル",
                  "アミューズ", "コンコルド", "ワンダーランド", "ビックマーチ", "ミリオン",
                  "エスパス", "ガーデン", "ゼント", "ZENT", "メッセ", "クリエ"}
    if store in CHAIN_ONLY and author_name and len(author_name) > len(store):
        if _is_store_name(author_name) or re.search(r'店|ホール', author_name):
            store = author_name[:28]

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

    # Xの<time>から取得した日付を使う（取得できなければ収集日を推定）
    if not tweet_date:
        # 深夜（JST 00:00-05:59）に実行中の場合は前日の方が確率が高い
        from datetime import timezone as _tz, timedelta as _td
        JST = _tz(_td(hours=9))
        now_jst = datetime.now(JST)
        if now_jst.hour < 6:
            from datetime import date as _d
            tweet_date = (_d.fromisoformat(today_str) - _td(days=1)).strftime("%Y-%m-%d")
        else:
            tweet_date = today_str

    # テキスト内に「5/24(日)」等の曜日付き日付があればそちらを優先
    # （日付変わり後に前日のコンプリートを投稿するケースに対応）
    tweet_date = extract_date_from_text(text, tweet_date)

    entry_id = hashlib.md5(tweet_url.encode()).hexdigest()[:12]

    return {
        "id": entry_id,
        "date": tweet_date,
        "time": tweet_time,                          # JST HH:MM
        "store": store,
        "machine": machine,
        "machine_type": get_machine_type(machine),   # "slot" or "pachinko"
        "slot_number": slot_number,                  # 台番号
        "text": text[:250].replace("\n", " "),
        "x_url": tweet_url,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def scrape_query(page, query: str, today_str: str, max_tweets: int = 200) -> list[dict]:
    results = []
    seen_urls: set[str] = set()

    # 前日 + 当日を収集（夜間の投稿漏れ・前回実行のこぼし分をカバー）
    from datetime import date as _dt, timedelta
    since_date = (_dt.fromisoformat(today_str) - timedelta(days=1)).strftime("%Y-%m-%d")
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

    # ページ初期レンダリング完了まで少し待つ
    page.wait_for_timeout(2000)

    # 80回スクロール: wheel距離4000px × 80回 = 合計320,000px分
    # 1回あたりの移動距離を大きくすることで短時間でより深くロード
    for _ in range(80):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(500)

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
            # 作者表示名を取得（ツイートカードのUser-Name）
            author_name = ""
            try:
                author_el = article.query_selector('[data-testid="User-Name"] span')
                if author_el:
                    author_name = author_el.inner_text().strip()
            except Exception:
                pass
            entry = parse_tweet(text, tweet_url, today_str, tweet_date, tweet_time, author_name)
            if entry:
                # 画像URL取得（pbs.twimg.com の画像のみ・プロフィール画像除外）
                images: list[str] = []
                try:
                    img_els = article.query_selector_all('img[src*="pbs.twimg.com"]')
                    for img_el in img_els[:4]:
                        src = img_el.get_attribute("src") or ""
                        if not src or "profile_images" in src:
                            continue
                        # クエリパラメータを高解像度に統一
                        src = re.sub(r'\?.*$', '', src) + "?format=jpg&name=large"
                        if src not in images:
                            images.append(src)
                except Exception:
                    pass
                if images:
                    entry["images"]    = images
                    entry["image_url"] = images[0]

                results.append(entry)
                store_label   = entry["store"] or "店舗不明"
                machine_label = entry["machine"] or "機種不明"
                slot          = f" [{entry['slot_number']}番台]" if entry["slot_number"] else ""
                img_flag      = " 🖼" if images else ""
                log(f"    ✅ {store_label} / {machine_label}{slot} {entry['time']}{img_flag}")

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

    # 30日より古いデータを除去（ピンツイート対策）― JST基準
    from datetime import timezone as _tz, timedelta as _td
    _JST = _tz(_td(hours=9))
    cutoff = (datetime.now(_JST) - _td(days=30)).strftime("%Y-%m-%d")
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


# ---------------------------------------------------------------------------
# Supabase ヘルパー（書き込み失敗時もスクリプトを止めない設計）
# ---------------------------------------------------------------------------
import urllib.request
import urllib.error
import ssl as _ssl


def _sb_env() -> tuple[str, str] | None:
    """環境変数からSupabase接続情報を取得。未設定なら None を返す（書き込みをスキップ）。"""
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return url, key


def _sb_request(method: str, path: str,
                body: list | dict | None = None,
                prefer: str | None = None) -> tuple[int, bytes]:
    """
    Supabase REST API へリクエストを送る低レベル関数。
    戻り値: (http_status_code, response_body_bytes)
    例外は呼び出し元で握りつぶすこと。
    """
    env = _sb_env()
    if not env:
        return 0, b""
    sb_url, sb_key = env

    ctx = _ssl._create_unverified_context()   # macOS + GitHub Actions 両対応
    headers: dict[str, str] = {
        "apikey":        sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type":  "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def supabase_log_start(job_name: str) -> int | None:
    """
    fetch_logs に実行開始レコードを INSERT し、生成された id を返す。
    失敗しても None を返してスクリプトは継続。
    """
    if not _sb_env():
        return None
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        status, body = _sb_request(
            "POST", "fetch_logs",
            body={
                "job_name":       job_name,
                "started_at":     now,
                "status":         "failed",   # 万が一スクリプトが途中終了した場合も failed になる
                "fetched_count":  0,
                "new_count":      0,
                "duplicate_count": 0,
                "error_count":    0,
            },
            prefer="return=representation",
        )
        if status in (200, 201) and body:
            rows = json.loads(body)
            if isinstance(rows, list) and rows:
                return rows[0].get("id")
    except Exception as e:
        log(f"⚠️  Supabase log_start エラー: {e}")
    return None


def supabase_log_end(log_id: int | None, status: str,
                     fetched: int, new_count: int,
                     dupes: int, errors: int,
                     error_detail: str | None = None) -> None:
    """fetch_logs の実行結果を PATCH で更新する。log_id が None の場合はスキップ。"""
    if log_id is None or not _sb_env():
        return
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        patch_body: dict = {
            "finished_at":    now,
            "status":         status,
            "fetched_count":  fetched,
            "new_count":      new_count,
            "duplicate_count": dupes,
            "error_count":    errors,
        }
        if error_detail:
            patch_body["error_detail"] = error_detail[:1000]
        _sb_request(
            "PATCH", f"fetch_logs?id=eq.{log_id}",
            body=patch_body,
            prefer="return=minimal",
        )
    except Exception as e:
        log(f"⚠️  Supabase log_end エラー: {e}")


def supabase_update_fetch_state(job_name: str) -> None:
    """fetch_state の last_success_at / last_run_at を現在時刻に更新する。"""
    if not _sb_env():
        return
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _sb_request(
            "PATCH", f"fetch_state?job_name=eq.{job_name}",
            body={"last_success_at": now, "last_run_at": now, "updated_at": now},
            prefer="return=minimal",
        )
    except Exception as e:
        log(f"⚠️  Supabase fetch_state 更新エラー: {e}")


def supabase_write_complete(entries: list[dict]) -> tuple[int, int]:
    """
    complete_reports テーブルに INSERT（ON CONFLICT DO NOTHING）。

    ・保存するフィールド: id, date, report_time, store_name, machine, slot_number, x_url, collected_at
    ・保存しないフィールド: text（本文）, images（画像配列）, image_url（画像URL）← 転載禁止
    ・重複 ID は INSERT をスキップし duplicate_count に加算
    ・Supabase 書き込み失敗時は (0, 0) を返してスクリプトを継続

    戻り値: (new_count, duplicate_count)
    """
    if not entries or not _sb_env():
        return 0, 0

    total_new = 0
    total_dup = 0
    BATCH_SIZE = 100

    for i in range(0, len(entries), BATCH_SIZE):
        batch = entries[i : i + BATCH_SIZE]

        rows: list[dict] = []
        for e in batch:
            x_url = (e.get("x_url") or "").strip()
            if not x_url:
                continue   # x_url は NOT NULL のため空行はスキップ
            rows.append({
                "id":           e["id"],
                "date":         e.get("date") or None,
                "report_time":  e.get("time") or None,       # "time" → DB の "report_time"
                "store_name":   e.get("store") or None,      # "store" → DB の "store_name"
                "machine":      e.get("machine") or None,
                "slot_number":  e.get("slot_number") or None,
                "x_url":        x_url,
                "collected_at": e.get("collected_at")
                                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                # text / images / image_url は意図的に送信しない
            })

        if not rows:
            continue

        try:
            status, body = _sb_request(
                "POST", "complete_reports",
                body=rows,
                # ignore-duplicates = ON CONFLICT DO NOTHING（既存データを書き換えない）
                # return=representation で実際に INSERT された行数を取得
                prefer="resolution=ignore-duplicates,return=representation",
            )
            if status in (200, 201):
                inserted = len(json.loads(body)) if body else 0
                total_new += inserted
                total_dup += len(rows) - inserted
            else:
                err_text = body.decode(errors="replace")[:200] if body else ""
                log(f"⚠️  Supabase complete_reports HTTP {status}: {err_text}")
                # Supabase エラーでもスクリプトは継続
        except Exception as e:
            log(f"⚠️  Supabase complete_reports 書き込みエラー: {e}")
            # スクリプトは継続

    if total_new or total_dup:
        log(f"☁️  Supabase: 新規{total_new}件 / 重複skip{total_dup}件")

    return total_new, total_dup


def update_ranking():
    """
    complete_info.json から月間・トータルランキングを集計して
    complete_ranking.json を更新する。
    店舗別・機種別のTOP5を月ごとに保持し、全期間集計も持つ。
    """
    from collections import Counter
    from datetime import timezone, timedelta

    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    this_month = now_jst.strftime("%Y-%m")

    all_data = load_all()

    # ── 機種名NG（誤抽出されやすい非機種名文字列）────────────────────────
    MACHINE_NAME_NG = {
        "コンプリート達成", "コンプリート機能", "コンプリート", "お客様",
        "ありがとうございます", "発動", "作動", "本日", "達成", "発生",
        "機能", "番台", "スロット", "パチスロ", "スマスロ", "来店",
        "誠におめ", "おめでとう", "おめでとうございます", "おめでとうございます！", "ございます",
        "コンプ", "完走", "出玉", "今日", "昨日",
        # 誤抽出フレーズ
        "コンプリート達成しました", "コンプリートおめ", "コンプリート達成おめ",
        "にてコンプリート達成されました", "にてコンプリート達成しました",
        "はコンプリート機能発動", "よりコンプリート達成", "、コンプリート",
        "は本日の遊技は終了となりました…",
        "コンプリート機能発動の為、本日は停止となります。",
    }

    # ── 機種名の表記ゆれ正規化マップ ────────────────────────────────────
    # キー: 元の表記（部分一致でOK）→ 値: 統一後の正式名称
    # 長いパターンを先に書くこと（「ヴァルヴレイヴ2」より先に「革命機ヴァルヴレイヴ」）
    MACHINE_NORMALIZE: list[tuple[str, str]] = [
        # スマスロ北斗の拳転生の章2（先に書く：「転生」より長いパターンを優先）
        ("転生の章2",             "スマスロ北斗の拳転生の章2"),
        ("転生の章Ⅱ",            "スマスロ北斗の拳転生の章2"),
        ("転生の章２",            "スマスロ北斗の拳転生の章2"),
        ("転生2",                 "スマスロ北斗の拳転生の章2"),
        ("転生２",                "スマスロ北斗の拳転生の章2"),
        ("転生の章",              "スマスロ北斗の拳転生の章2"),   # 章番号省略も2に統一
        # 北斗転生系の表記ゆれ（番号なしも2026年時点では転生の章2）
        ("北斗の拳転生",          "スマスロ北斗の拳転生の章2"),
        ("北斗転生",              "スマスロ北斗の拳転生の章2"),
        # スマスロ革命機ヴァルヴレイヴ2
        ("革命機ヴァルヴレイヴ２", "革命機ヴァルヴレイヴ2"),
        ("革命機ヴァルヴレイヴ2",  "革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ２",       "革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ2",        "革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ",         "革命機ヴァルヴレイヴ2"),
        # L炎炎ノ消防隊2
        ("Ｌ炎炎ノ消防隊２",      "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊2",          "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊２",         "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊",           "L炎炎ノ消防隊2"),
        # ミリオンゴッド神々の軌跡
        ("ミリオンゴッド神々の軌跡", "ミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド-神々",    "ミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド",         "ミリオンゴッド神々の軌跡"),
        # 甲鉄城のカバネリ
        ("甲鉄城のカバネリ",       "甲鉄城のカバネリ"),
        ("カバネリ",               "甲鉄城のカバネリ"),
        ("甲鉄城",                 "甲鉄城のカバネリ"),
        # L東京喰種
        ("東京喰種",               "L東京喰種"),
        # スマスロ北斗の拳
        ("北斗の拳",               "スマスロ北斗の拳"),
        ("北斗",                   "スマスロ北斗の拳"),
        # スマスロ攻殻機動隊
        ("攻殻機動隊",             "スマスロ攻殻機動隊"),
        # バジリスク絆2
        ("バジリスク絆２",         "バジリスク絆2"),
        ("バジリスク絆",           "バジリスク絆2"),
        ("バジリスク",             "バジリスク絆2"),
        # L吉宗
        ("吉宗",                   "L吉宗"),
        # ゴッドイーター
        ("ゴッドイーター",         "スマスロゴッドイーター"),
        # 牙狼シリーズ（全バリエーションを牙狼12に統一）
        ("牙狼",                   "牙狼12"),
        # Lチバリヨ2ZB（全角・括弧表記ゆれを統一）
        ("チバリヨ２ＺＢ",         "Lチバリヨ2ZB"),
        ("チバリヨ２ZB",           "Lチバリヨ2ZB"),
        ("チバリヨ2ZB",            "Lチバリヨ2ZB"),
        ("チバリヨ2",              "Lチバリヨ2ZB"),
        ("チバリヨ",               "Lチバリヨ2ZB"),
        # eバイオハザード6（型番・括弧ゆれ統一）
        ("eバイオハザード6",        "eバイオハザード6"),
        ("ｅバイオハザード６",      "eバイオハザード6"),
        ("eバイオ",                "eバイオハザード6"),
        # eフィーバーキン肉マン（eFキン肉マン統一）
        ("eFキン肉マン",           "eフィーバーキン肉マン"),
        ("eＦキン肉マン",          "eフィーバーキン肉マン"),
        ("eフィーバーキン肉マン",   "eフィーバーキン肉マン"),
        # シャーマンキング
        ("シャーマンキング",        "Lシャーマンキング"),
        # 新鬼武者3
        ("新鬼武者3",              "L新鬼武者3"),
        ("鬼武者3",                "L新鬼武者3"),
        # かぐや様
        ("かぐや様",               "Lかぐや様は告らせたい"),
        # スマスロバイオハザードRE:3
        ("バイオハザードRe",        "スマスロバイオハザードRE:3"),
        ("バイオハザードRE:3",      "スマスロバイオハザードRE:3"),
        ("LバイオハザードRe",       "スマスロバイオハザードRE:3"),
        # Re:ゼロ
        ("Re:ゼロ",               "Re:ゼロから始める異世界生活"),
        ("リゼロ",                 "Re:ゼロから始める異世界生活"),
        # ゴジラ
        ("ゴジラ",                 "Lゴジラ"),
    ]

    def normalize_machine(name: str) -> str | None:
        """機種名を正規化。NG文字列はNoneを返す。"""
        name = name.strip()
        # 短すぎ・空はスキップ
        if len(name) < 2:
            return None
        # NG文字列チェック
        if name in MACHINE_NAME_NG:
            return None
        # 数字のみ・記号のみはスキップ
        if re.match(r'^[\d\s]+$', name):
            return None
        # e/ｅ プレフィックス（パチンコ）の機種は、L/スマスロ名への正規化を適用しない
        is_pachinko_prefix = bool(re.match(r'^[eｅ]', name))
        # 正規化マップ適用（前方一致）
        for pattern, normalized in MACHINE_NORMALIZE:
            if pattern in name:
                # パチンコ機種をスロット名（L/スマスロ）に誤変換しない
                if is_pachinko_prefix and (
                    normalized.startswith("L") or normalized.startswith("Ｌ")
                    or normalized.startswith("スマスロ")
                ):
                    continue
                return normalized
        return name

    # ── store_x_urls.json を読み込み（ランキングのX URLリンク用）
    STORE_X_URLS_JSON = Path(__file__).parent.parent / "public/store_x_urls.json"
    store_x_urls_map: dict = {}
    if STORE_X_URLS_JSON.exists():
        try:
            store_x_urls_map = json.loads(STORE_X_URLS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── 店舗名の表記ゆれ正規化マップ（ランキング集計用）
    STORE_NORMALIZE: list[tuple[str, str]] = [
        ("楽園ハッピーロード大山 店長石川＠アカウント", "楽園ハッピーロード大山店"),
    ]

    # x_url のアカウントハンドル → 正式店舗名（スペース区切りの支店名対応）
    X_URL_STORE_OVERRIDE: dict[str, str] = {
        "rakuenikebukuro": "楽園池袋店ゲートウェイ",
        "Rakuen_GS":       "楽園池袋店グリーンサイド",
        "rakuen_gs":       "楽園池袋店グリーンサイド",
    }

    def normalize_store(name: str, x_url: str = "") -> str:
        # x_url ベースの補正（優先）
        if x_url:
            handle = x_url.split("/status/")[0].rstrip("/").split("/")[-1]
            if handle in X_URL_STORE_OVERRIDE:
                return X_URL_STORE_OVERRIDE[handle]
        for pattern, normalized in STORE_NORMALIZE:
            if name == pattern:
                return normalized
        return name

    # ── 既存ランキングJSONを読み込み（月別データを蓄積するため）
    # ※ monthly は配列形式・辞書形式どちらでも読み込めるよう対応
    existing: dict = {}
    if RANKING_JSON.exists():
        try:
            with open(RANKING_JSON, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # monthly を内部処理用の辞書に変換
    raw_monthly = existing.get("monthly", {})
    if isinstance(raw_monthly, list):
        monthly_data: dict = {m["month"]: m for m in raw_monthly if isinstance(m, dict) and "month" in m}
    else:
        monthly_data: dict = raw_monthly if isinstance(raw_monthly, dict) else {}

    # ── 月別の store/machine カウント
    month_store_counter:            dict[str, Counter] = {}
    month_slot_machine_counter:     dict[str, Counter] = {}
    month_pachinko_machine_counter: dict[str, Counter] = {}

    for e in all_data:
        d = e.get("date", "")
        if not d or len(d) < 7:
            continue
        ym = d[:7]  # "YYYY-MM"
        store   = normalize_store((e.get("store") or "").strip(), e.get("x_url") or "")
        machine = normalize_machine(e.get("machine") or "")
        mt      = e.get("machine_type") or get_machine_type(e.get("machine") or "")

        if store and store not in ("店舗不明",):
            month_store_counter.setdefault(ym, Counter())[store] += 1
        if machine:
            if mt == "pachinko":
                month_pachinko_machine_counter.setdefault(ym, Counter())[machine] += 1
            else:
                month_slot_machine_counter.setdefault(ym, Counter())[machine] += 1

    # ── 月別ランキングを更新（過去12ヶ月分保持）
    from datetime import timedelta as _td2
    months_to_keep = set()
    for i in range(12):
        m_date = now_jst.replace(day=1) - _td2(days=i * 28)
        months_to_keep.add(m_date.strftime("%Y-%m"))

    for ym in [k for k in list(monthly_data.keys()) if k not in months_to_keep]:
        del monthly_data[ym]

    def _make_store_items(counter: Counter) -> list:
        items = []
        for i, (name, cnt) in enumerate(counter.most_common(10)):
            item: dict = {"rank": i + 1, "name": name, "count": cnt}
            x_url = store_x_urls_map.get(name)
            if x_url:
                item["x_url"] = x_url
            items.append(item)
        return items

    def _make_machine_items(counter: Counter) -> list:
        return [{"rank": i + 1, "name": name, "count": cnt}
                for i, (name, cnt) in enumerate(counter.most_common(10))]

    for ym in month_store_counter:
        if ym not in months_to_keep:
            continue
        y_part, m_part = ym.split("-")
        monthly_data[ym] = {
            "month":             ym,
            "label":             f"{y_part}年{int(m_part)}月",
            "total_count":       sum(month_store_counter[ym].values()),
            "stores":            _make_store_items(month_store_counter[ym]),
            "slot_machines":     _make_machine_items(month_slot_machine_counter.get(ym, Counter())),
            "pachinko_machines": _make_machine_items(month_pachinko_machine_counter.get(ym, Counter())),
        }

    # ── 月別を配列形式に変換（新しい月順）
    monthly_array = sorted(
        [v for v in monthly_data.values() if isinstance(v, dict) and "month" in v],
        key=lambda x: x["month"],
        reverse=True,
    )

    # ── トータルランキング（全データから集計）
    total_store_counter:            Counter = Counter()
    total_slot_machine_counter:     Counter = Counter()
    total_pachinko_machine_counter: Counter = Counter()
    for e in all_data:
        store   = normalize_store((e.get("store") or "").strip(), e.get("x_url") or "")
        machine = normalize_machine(e.get("machine") or "")
        mt      = e.get("machine_type") or get_machine_type(e.get("machine") or "")
        if store and store not in ("店舗不明",):
            total_store_counter[store] += 1
        if machine:
            if mt == "pachinko":
                total_pachinko_machine_counter[machine] += 1
            else:
                total_slot_machine_counter[machine] += 1

    total_stores_top         = _make_store_items(total_store_counter)
    total_slot_machines_top  = _make_machine_items(total_slot_machine_counter)
    total_pachinko_machines_top = _make_machine_items(total_pachinko_machine_counter)

    # ── store_complete_counts（店舗ページ用）
    store_complete_counts = dict(total_store_counter.most_common())

    ranking = {
        "generated_at": now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "monthly":       monthly_array,
        "total": {
            "stores":            total_stores_top,
            "slot_machines":     total_slot_machines_top,
            "pachinko_machines": total_pachinko_machines_top,
            "total_count":       len(all_data),
        },
        "store_complete_counts": store_complete_counts,
    }

    with open(RANKING_JSON, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

    log(f"🏆 ランキング更新: 月別{len(monthly_array)}ヶ月分 / トータル店舗TOP{len(total_stores_top)} / スロット機種TOP{len(total_slot_machines_top)}")


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

    # ── Supabase: 実行開始を記録 ──────────────────────────────────────────
    sb_log_id = supabase_log_start("complete")

    all_new: list[dict] = []
    query_errors = 0   # クエリ単位のエラー数

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
                supabase_log_end(sb_log_id, "failed", 0, 0, 0, 1, "Xログイン失敗")
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
                time.sleep(1)
            except Exception as e:
                log(f"  ❌ {e}")
                query_errors += 1

        page.close()
        ctx.close()

    # 重複除去
    seen: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen or seen.add(e["id"]))]  # type: ignore

    log(f"\n📊 収集: {len(deduped)} 件（店舗投稿・重複除去後）")

    # ── JSON 保存（既存の動作をそのまま維持）────────────────────────────────
    json_added = 0
    if deduped:
        json_added = save_complete(deduped, today)
        log(f"✅ {json_added}件を新規追加")
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

    # ── Supabase 書き込み（JSON保存の後・失敗してもスクリプトは継続）────────
    sb_new, sb_dup = supabase_write_complete(deduped)

    # ── Supabase: 実行結果を記録 ──────────────────────────────────────────
    sb_status = "success" if query_errors == 0 else "partial"
    supabase_log_end(
        sb_log_id, sb_status,
        fetched=len(deduped),
        new_count=sb_new,
        dupes=sb_dup,
        errors=query_errors,
    )
    if deduped:  # 何か収集できていれば fetch_state を更新
        supabase_update_fetch_state("complete")

    # ランキング更新
    update_ranking()

    log("=" * 60)


if __name__ == "__main__":
    main()
