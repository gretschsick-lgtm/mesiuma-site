#!/usr/bin/env python3
"""
stores.json の各店舗の公式 X アカウントを検索して x_url を補完するスクリプト。

検索優先順位:
  1. 店舗公式HP (hp_url) から X リンクを直接取得（最も確実）
  2. X ユーザー検索（x.com/search?f=user）← ログイン済みなら最も直接的
  3. Google 検索（ChromeクッキーでCAPTCHA回避 + webdriver偽装）
  4. DuckDuckGo HTML検索（フォールバック）

Playwright セッションを .browser_session.json に保存するため、
2回目以降は自動でログイン状態が継続する。

使い方:
  python scripts/fetch_store_x_urls.py                  # event>=1 の全未登録店舗
  python scripts/fetch_store_x_urls.py --min-events 5   # event>=5 のみ
  python scripts/fetch_store_x_urls.py --limit 100      # 上位100件だけ
  python scripts/fetch_store_x_urls.py --headless       # ヘッドレス
  python scripts/fetch_store_x_urls.py --dry-run        # 保存しない（確認用）
  python scripts/fetch_store_x_urls.py --hp-only        # 公式HPからのみ取得
  python scripts/fetch_store_x_urls.py --save-session   # Google ログイン画面を開いてセッション保存
"""

from __future__ import annotations
import json, re, time, argparse, sys, os, urllib.parse
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright が未インストールです: pip install playwright && playwright install chromium")
    sys.exit(1)

STORES_JSON      = Path(__file__).parent.parent / "public/stores.json"
X_SESSION_FILE   = Path(__file__).parent / ".x_session.enc"
BROWSER_SESSION  = Path(__file__).parent / ".browser_session.json"   # Playwright セッション保存先

# パチスロ・パチンコ業界キーワード
SLOT_KEYWORDS = re.compile(
    r'パチスロ|パチンコ|スロット|スマスロ|スマパチ|遊技|ぱちんこ|ぱちすろ|'
    r'パチ|スロ|ホール|コンプリート|番台|設定|出玉|新台|遊べる'
)

CHAIN_NAMES = {
    "ダイナム", "マルハン", "キコーナ", "楽園", "ガイア", "キャッスル",
    "ガーデン", "エスパス", "ゼント", "ZENT", "メッセ", "クリエ",
    "ニラク", "ビックマーチ", "コンコルド", "ユーコー", "ラッキー",
}

_SKIP_HANDLES = frozenset([
    "search", "explore", "notifications", "messages", "home",
    "i", "intent", "share", "hashtag", "login", "signup",
    "privacy", "tos", "settings", "compose", "twitter",
    "intent", "about", "help", "en", "ja",
])

_HANDLE_RE = re.compile(r'(?:x\.com|twitter\.com)/([A-Za-z0-9_]{3,50})(?:/|$|\?|%|\s)')


# ══════════════════════════════════════════════════════════════════════
# クッキー取得
# ══════════════════════════════════════════════════════════════════════

def _get_chrome_cookies(domain: str) -> list[dict]:
    """Chrome の保存クッキーを取得してPlaywright形式で返す"""
    try:
        import browser_cookie3
        jar = browser_cookie3.chrome(domain_name=domain)
        cookies = []
        for c in jar:
            cookies.append({
                "name":     c.name,
                "value":    c.value,
                "domain":   c.domain or domain,
                "path":     c.path or "/",
                "secure":   bool(c.secure),
                "httpOnly": False,
                "sameSite": "None",
            })
        return cookies
    except Exception:
        return []


def _get_x_cookies() -> list[dict]:
    """X (twitter.com) のセッションクッキー取得"""
    # 環境変数
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0        = os.environ.get("X_CT0", "")
    if auth_token and ct0:
        return [
            {"name": "auth_token", "value": auth_token,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0",        "value": ct0,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ]
    # 暗号化セッションファイル
    if X_SESSION_FILE.exists():
        try:
            import base64, struct
            from cryptography.fernet import Fernet
            raw = X_SESSION_FILE.read_bytes()
            key_len = struct.unpack(">I", raw[:4])[0]
            key     = raw[4:4 + key_len]
            payload = raw[4 + key_len:]
            decrypted = json.loads(Fernet(key).decrypt(payload))
            auth = decrypted.get("auth_token", "")
            ct   = decrypted.get("ct0", "")
            if auth and ct:
                return [
                    {"name": "auth_token", "value": auth,
                     "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
                    {"name": "ct0",        "value": ct,
                     "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
                ]
        except Exception:
            pass
    # Chrome クッキー
    cookies = _get_chrome_cookies(".x.com")
    if any(c["name"] == "auth_token" for c in cookies):
        return cookies
    return []


# ══════════════════════════════════════════════════════════════════════
# スコアリング
# ══════════════════════════════════════════════════════════════════════

def _normalize(name: str) -> str:
    name = re.sub(r'[\s　【】「」〔〕♪★☆◆◇●○・、。！!？?《》≪≫＠@~～－\-]', '', name)
    name = name.translate(str.maketrans('ａ-ｚＡ-Ｚ０-９', 'a-zA-Z0-9'))
    return name.lower()


def _name_score(store_name: str, display_name: str) -> float:
    s = _normalize(store_name)
    d = _normalize(display_name)
    if not s or not d:
        return 0.0
    if s == d:
        return 1.0
    if s in d:
        return len(s) / len(d) * 0.95
    if d in s:
        return len(d) / len(s) * 0.85
    common = 0
    for a, b in zip(s, d):
        if a == b:
            common += 1
        else:
            break
    return common / max(len(s), len(d)) * 0.7


# ══════════════════════════════════════════════════════════════════════
# ①  公式HP から X リンク直接取得
# ══════════════════════════════════════════════════════════════════════

def get_x_from_hp(page, hp_url: str, store_name: str, pref: str, city: str) -> Optional[dict]:
    """
    店舗公式サイトにアクセスして X/Twitter リンクを探す。
    チェーン本部サイト（全国共通）は支店特定できないためスキップ。
    """
    # チェーン本部ドメイン（支店ページではないためスキップ）
    CHAIN_DOMAINS = {
        "king-net.co.jp", "luckyplaza.co.jp", "undertree.co.jp",
        "k-kosho.co.jp", "papimo.jp", "maruhan.co.jp", "dainamdainamdainam.co.jp",
        "nittaku.jp", "tsubame-group.jp", "venice.co.jp",
        "dynam.jp", "aeonentertainment.co.jp", "marioad.co.jp",
    }
    try:
        parsed = urllib.parse.urlparse(hp_url)
        domain = parsed.netloc.lstrip("www.")
        if any(d in domain for d in CHAIN_DOMAINS):
            return None   # チェーン本部はスキップ
    except Exception:
        pass

    try:
        page.goto(hp_url, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
    except Exception:
        return None

    # x.com / twitter.com リンクを全て抽出
    handles: list[str] = []
    seen: set[str] = set()
    try:
        links = page.query_selector_all('a')
        for link in links[:80]:
            try:
                href = link.get_attribute("href") or ""
            except Exception:
                continue
            m = _HANDLE_RE.search(href)
            if m:
                h = m.group(1).lower()
                if h not in _SKIP_HANDLES and h not in seen:
                    seen.add(h)
                    handles.append(h)
    except Exception:
        pass

    if not handles:
        return None

    # 最大3ハンドルを検証
    best: Optional[dict] = None
    best_score = 0.0
    for handle in handles[:3]:
        result = _verify_x_profile(page, handle, store_name, pref, city)
        if result and result["score"] > best_score:
            best_score = result["score"]
            best = result

    if best and best["score"] >= 0.45:   # HP直接取得は閾値を少し下げる
        best["source"] = "hp"
        return best
    return None


# ══════════════════════════════════════════════════════════════════════
# ②  X ユーザー検索（ログイン済みセッション利用）
# ══════════════════════════════════════════════════════════════════════

def search_x_users(page, store_name: str, pref: str, city: str) -> Optional[dict]:
    """
    X のツイート検索で店舗名を含むツイートを探し、投稿者を検証する。
    ① People 検索（f=user）で直接一致する店舗アカウントを探す
    ② Latest 検索でツイート投稿者を収集してスコアリングする
    X にログイン済みのセッションが必要。
    """
    seen: set[str] = set()
    all_handles: list[str] = []

    def _add_handle(h: str) -> None:
        h = h.lower()
        if h not in _SKIP_HANDLES and h not in seen:
            seen.add(h)
            all_handles.append(h)

    # ① People 検索（ユーザー名・表示名の直接一致）
    query_str = urllib.parse.quote(store_name)
    people_url = f"https://x.com/search?q={query_str}&f=user&lang=ja"
    try:
        page.goto(people_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        if "login" in page.url or "i/flow" in page.url:
            return None
        try:
            links = page.query_selector_all('[data-testid="UserCell"] a') or []
            for link in links[:10]:
                try:
                    href = link.get_attribute("href") or ""
                except Exception:
                    continue
                m = re.match(r'^/([A-Za-z0-9_]{3,50})$', href)
                if m:
                    _add_handle(m.group(1))
        except Exception:
            pass
    except Exception:
        pass

    # ② Latest ツイート検索（店舗自身のツイートを探す）
    # 引用符なしも試す（スペースで分割した単語で）
    for q_extra in [f'"{store_name}"', store_name]:
        q_enc = urllib.parse.quote(f'{q_extra} パチスロ OR パチンコ')
        latest_url = f"https://x.com/search?q={q_enc}&f=live&lang=ja"
        try:
            page.goto(latest_url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            if "login" in page.url or "i/flow" in page.url:
                break
            # ツイート内のリンクからハンドルを収集
            try:
                links = page.query_selector_all('a[href^="/"][role]') or []
                for link in links[:40]:
                    try:
                        href = link.get_attribute("href") or ""
                    except Exception:
                        continue
                    m = re.match(r'^/([A-Za-z0-9_]{3,50})(?:/status/|$)', href)
                    if m:
                        _add_handle(m.group(1))
            except Exception:
                pass
            if len(all_handles) >= 6:
                break
        except Exception:
            break

    return _best_from_handles(page, all_handles[:8], store_name, pref, city, source="x_search")


# ══════════════════════════════════════════════════════════════════════
# ③  Google 検索（Chromeクッキー付き）
# ══════════════════════════════════════════════════════════════════════

_GOOGLE_CAPTCHA = [False]   # ミュータブルフラグ（CAPTCHA検出後はスキップ）

def search_google(page, store_name: str, pref: str, city: str) -> Optional[dict]:
    """
    Google で「"店舗名" X パチスロ」を検索して X プロフィール URL を抽出・検証する。
    Chrome のクッキーを使うため CAPTCHA が出にくい。
    CAPTCHA が検出された場合は _GOOGLE_CAPTCHA[0] = True にして以後スキップ。
    """
    if _GOOGLE_CAPTCHA[0]:
        return None

    query_str = f'"{store_name}" X パチスロ OR パチンコ'
    google_url = f"https://www.google.com/search?q={urllib.parse.quote(query_str)}&hl=ja&num=5"

    try:
        page.goto(google_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ⚠️ Google遷移エラー: {e}")
        return None

    # CAPTCHA / ブロック検出
    cur_url = page.url
    if "/sorry/" in cur_url or "captcha" in cur_url.lower():
        print("  ⚠️ Google CAPTCHA（以後スキップ）")
        _GOOGLE_CAPTCHA[0] = True
        return None
    try:
        body_snippet = (page.inner_text('body') or "")[:300]
        if "続行するには" in body_snippet or "unusual traffic" in body_snippet.lower():
            print("  ⚠️ Google CAPTCHA（以後スキップ）")
            _GOOGLE_CAPTCHA[0] = True
            return None
    except Exception:
        pass

    handles = _extract_handles_from_page(page)
    return _best_from_handles(page, handles, store_name, pref, city, source="google")


# ══════════════════════════════════════════════════════════════════════
# ④  DuckDuckGo HTML（フォールバック）
# ══════════════════════════════════════════════════════════════════════

def search_ddg(page, store_name: str, pref: str, city: str) -> Optional[dict]:
    """DuckDuckGo HTML版でフォールバック検索"""
    query_str = f'"{store_name}" パチスロ OR パチンコ site:x.com'
    ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query_str)}&kl=jp-jp"

    try:
        page.goto(ddg_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ⚠️ DDG遷移エラー: {e}")
        return None

    if any(kw in page.url for kw in ["challenge", "/sorry/", "captcha"]):
        return None
    try:
        snippet = (page.inner_text('body') or "")[:200]
        if "続行するには" in snippet:
            return None
    except Exception:
        pass

    handles = _extract_handles_from_page(page)
    return _best_from_handles(page, handles, store_name, pref, city, source="ddg")


# ══════════════════════════════════════════════════════════════════════
# 共通ユーティリティ
# ══════════════════════════════════════════════════════════════════════

def _extract_handles_from_page(page) -> list[str]:
    """ページ内の全リンク・テキストから x.com ハンドルを収集する"""
    seen: set[str] = set()
    found: list[str] = []

    def _add(h: str) -> None:
        if h not in _SKIP_HANDLES and h not in seen:
            seen.add(h)
            found.append(h)

    # <a href> から（DDG リダイレクト URL もデコード）
    try:
        for link in (page.query_selector_all('a') or [])[:80]:
            try:
                href = link.get_attribute("href") or ""
            except Exception:
                continue
            # DDG リダイレクト
            if "duckduckgo.com/l/" in href or "uddg=" in href:
                try:
                    parsed = urllib.parse.urlparse(href)
                    uddg = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
                    if uddg:
                        href = urllib.parse.unquote(uddg)
                except Exception:
                    pass
            m = _HANDLE_RE.search(href)
            if m:
                _add(m.group(1).lower())
    except Exception:
        pass

    # ページテキストから
    try:
        page_text = page.inner_text('body') or ""
        for m in re.finditer(r'(?:x|twitter)\.com/([A-Za-z0-9_]{3,50})(?:/|\s|$)', page_text):
            _add(m.group(1).lower())
    except Exception:
        pass

    # /status/ ツイートURLは除く（プロフィールではない）
    # ただし候補ハンドルとして持つ（プロフィール検証で弾く）
    return found


def _verify_x_profile(page, handle: str, store_name: str, pref: str, city: str) -> Optional[dict]:
    """X プロフィールページを訪問してスコアリングする"""
    try:
        page.goto(f"https://x.com/{handle}", timeout=18000, wait_until="domcontentloaded")
        # UserName 要素が現れるまで待つ（最大4秒）
        try:
            page.wait_for_selector('[data-testid="UserName"]', timeout=4000)
        except Exception:
            pass
    except Exception:
        return None

    disp_name = ""
    bio = ""
    location = ""

    # 表示名: ページタイトル優先（"名前 (@handle) / X" 形式）
    try:
        title = page.title()
        m = re.match(r'^(.+?)\s*\(@', title)
        if m:
            disp_name = m.group(1).strip()
    except Exception:
        pass
    # フォールバック: span 要素
    if not disp_name:
        for sel in [
            '[data-testid="UserName"] span',
            'h2[data-testid="UserName"] span',
            'div[data-testid="UserName"] span',
        ]:
            try:
                el = page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t and "@" not in t:
                        disp_name = t
                        break
            except Exception:
                pass

    try:
        el = page.query_selector('[data-testid="UserDescription"]')
        if el:
            bio = el.inner_text().strip()
    except Exception:
        pass
    try:
        el = page.query_selector('[data-testid="UserLocation"]')
        if el:
            location = el.inner_text().strip()
    except Exception:
        pass

    if not disp_name:
        disp_name = handle

    score = _name_score(store_name, disp_name)
    combined = bio + " " + location + " " + disp_name
    has_slot = bool(SLOT_KEYWORDS.search(combined))

    # スロット業界キーワードがなければ基本的に除外
    # （ただし店名完全一致 + 所在地マッチの場合は例外）
    if not has_slot:
        has_pref  = bool(pref  and pref.replace("県","").replace("府","").replace("都","") in combined)
        has_city  = bool(city  and city in combined)
        # スロットキーワードなし・かつ都道府県も一致しない → 除外
        if not (has_pref or has_city):
            return None
        # スロットキーワードなし・地域は一致 → 名前スコアが高い場合のみ許可
        if score < 0.85:
            return None

    if pref and pref.replace("県","").replace("府","").replace("都","") in combined:
        score *= 1.15
    if city and city in combined:
        score *= 1.10
    if has_slot:
        score *= 1.2

    return {
        "x_url":        f"https://x.com/{handle}",
        "handle":       handle,
        "display_name": disp_name,
        "bio":          bio[:120],
        "score":        round(score, 3),
    }


def _best_from_handles(page, handles: list[str], store_name: str,
                        pref: str, city: str, source: str = "") -> Optional[dict]:
    """ハンドル候補リストから最高スコアのものを返す"""
    best: Optional[dict] = None
    best_score = 0.0
    for handle in handles[:4]:
        result = _verify_x_profile(page, handle, store_name, pref, city)
        if result and result["score"] > best_score:
            best_score = result["score"]
            best = result
    if best and best["score"] >= 0.55:
        if source:
            best["source"] = source
        return best
    return None


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="stores.json の x_url を補完")
    ap.add_argument("--min-events", type=int, default=1)
    ap.add_argument("--limit",      type=int, default=0)
    ap.add_argument("--headless",   action="store_true")
    ap.add_argument("--dry-run",    action="store_true", help="stores.json を保存しない")
    ap.add_argument("--hp-only",    action="store_true", help="公式HPからのみ取得（検索なし）")
    ap.add_argument("--min-score",  type=float, default=0.55)
    ap.add_argument("--save-session", action="store_true",
                    help="Google にログインしてセッションを保存（初回のみ）")
    args = ap.parse_args()

    stores: list[dict] = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    store_by_id = {s["id"]: s for s in stores}

    targets = [
        s for s in stores
        if not s.get("x_url") and s.get("event_count", 0) >= args.min_events
    ]
    targets.sort(key=lambda x: (-x.get("event_count", 0), x.get("name", "")))
    if args.limit:
        targets = targets[:args.limit]

    print(f"対象店舗: {len(targets)}件 (event>={args.min_events})")
    if args.dry_run:
        print("  [DRY RUN — stores.json は変更しません]")

    with sync_playwright() as pw:
        # ── コンテキスト作成 ──────────────────────────────────────────────
        launch_opts = {"headless": args.headless}
        browser = pw.chromium.launch(**launch_opts)

        ctx_opts: dict = {
            "locale": "ja-JP",
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        # Playwright セッション（保存済みがあれば読み込む）
        if BROWSER_SESSION.exists() and not args.save_session:
            ctx_opts["storage_state"] = str(BROWSER_SESSION)
            print(f"📂 セッション読み込み: {BROWSER_SESSION}")
        ctx = browser.new_context(**ctx_opts)

        # Chrome の Google クッキーを追加（CAPTCHA 回避）
        google_cookies = _get_chrome_cookies(".google.com")
        if google_cookies:
            ctx.add_cookies(google_cookies)
            print(f"🍪 Google Chrome cookie {len(google_cookies)}個追加")

        # X クッキー（プロフィール閲覧用）
        x_cookies = _get_x_cookies()
        if x_cookies:
            ctx.add_cookies([c for c in x_cookies if c["domain"] in (".x.com", "x.com", ".twitter.com")])
            print(f"🍪 X cookie {len(x_cookies)}個追加")

        page = ctx.new_page()

        # webdriver 検出回避（Google CAPTCHA 対策）
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ja', 'ja-JP', 'en']});
            window.chrome = {runtime: {}};
        """)

        # X セッション確立（プロフィール閲覧に必要）
        if x_cookies:
            try:
                page.goto("https://x.com/home", timeout=30000, wait_until="domcontentloaded")
                # タイトルが設定されるまで最大5秒待つ
                for _ in range(10):
                    title = page.title()
                    if title:
                        break
                    page.wait_for_timeout(500)
                if "X" in title or "Twitter" in title or "Home" in title:
                    print(f"✅ X セッション確立 ({title})")
                elif "login" in page.url.lower() or "i/flow" in page.url:
                    print(f"⚠️ X ログインページ（クッキー無効の可能性）")
                    x_cookies = []   # X 検索を無効化
                else:
                    print(f"⚠️ X セッション未確認 (title={title!r}, url={page.url})")
            except Exception as e:
                print(f"⚠️ X セッション確立スキップ: {e}")

        # ── セッション保存モード ──────────────────────────────────────────
        if args.save_session:
            print("🔑 Google のログイン画面を開きます。ログイン後 Enter を押してください...")
            page.goto("https://accounts.google.com", timeout=30000, wait_until="domcontentloaded")
            input("ログイン完了後 Enter: ")
            ctx.storage_state(path=str(BROWSER_SESSION))
            print(f"✅ セッション保存: {BROWSER_SESSION}")
            browser.close()
            return

        # ── 検索ループ ────────────────────────────────────────────────────
        found_count = 0
        save_interval = 10
        _GOOGLE_CAPTCHA[0] = False   # フラグ初期化

        for idx, store in enumerate(targets):
            name = store.get("name", "")
            pref = store.get("pref", "")
            city = store.get("city", "")
            hp   = store.get("hp_url", "")
            ec   = store.get("event_count", 0)

            print(f"[{idx+1}/{len(targets)}] {name} ({pref}{city}) ec={ec}", end="  ", flush=True)

            result = None

            # ① 公式HP から直接取得
            if hp:
                result = get_x_from_hp(page, hp, name, pref, city)
                if result:
                    result["source"] = "hp"

            # ② X ユーザー検索（ログイン済みセッション利用）
            if not result and not args.hp_only and x_cookies:
                result = search_x_users(page, name, pref, city)

            # ③ Google 検索（CAPTCHA 未発生時のみ）
            if not result and not args.hp_only:
                result = search_google(page, name, pref, city)

            # ④ DDG フォールバック
            if not result and not args.hp_only:
                result = search_ddg(page, name, pref, city)

            if result and result["score"] >= args.min_score:
                src = result.get("source", "?")
                print(f"✅ [{src}] @{result['handle']} score={result['score']:.2f} \"{result['display_name']}\"")
                if not args.dry_run:
                    store_by_id[store["id"]]["x_url"] = result["x_url"]
                found_count += 1
            else:
                print("—")

            # 定期保存
            if not args.dry_run and (idx + 1) % save_interval == 0:
                STORES_JSON.write_text(
                    json.dumps(stores, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                # セッション更新保存（ログイン状態を維持）
                ctx.storage_state(path=str(BROWSER_SESSION))

            # hp_url なし & hp-only モードでは sleep 不要
            if args.hp_only and not hp:
                pass
            else:
                time.sleep(2.5)

        browser.close()

        # セッション最終保存
        try:
            ctx.storage_state(path=str(BROWSER_SESSION))
            print(f"💾 セッション保存: {BROWSER_SESSION}")
        except Exception:
            pass

    # 最終保存
    if not args.dry_run:
        STORES_JSON.write_text(
            json.dumps(stores, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        has_x = sum(1 for s in stores if s.get("x_url"))
        print(f"\n✅ 完了: {found_count}/{len(targets)}件 マッチ / x_url合計 {has_x}/{len(stores)}")
    else:
        print(f"\n[DRY RUN] {found_count}/{len(targets)}件 マッチ（保存なし）")


if __name__ == "__main__":
    main()
