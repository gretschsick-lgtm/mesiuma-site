#!/usr/bin/env python3
"""
stores.json の各店舗の公式 X アカウントを検索して x_url を補完するスクリプト。

使い方:
  python scripts/fetch_store_x_urls.py                  # event>=1 の全未登録店舗
  python scripts/fetch_store_x_urls.py --min-events 5   # event>=5 のみ（約50件）
  python scripts/fetch_store_x_urls.py --limit 100      # 上位100件だけ
  python scripts/fetch_store_x_urls.py --headless       # ヘッドレス
  python scripts/fetch_store_x_urls.py --dry-run        # 保存しない（確認用）
"""

from __future__ import annotations
import json, re, time, argparse, sys, os
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright が未インストールです: pip install playwright && playwright install chromium")
    sys.exit(1)

STORES_JSON  = Path(__file__).parent.parent / "public/stores.json"
SESSION_FILE = Path(__file__).parent / ".x_session.enc"

# パチスロ・パチンコ業界キーワード
SLOT_KEYWORDS = re.compile(
    r'パチスロ|パチンコ|スロット|スマスロ|スマパチ|遊技|ぱちんこ|ぱちすろ|'
    r'パチ|スロ|ホール|コンプリート|番台|設定|出玉|新台|遊べる'
)

# 「チェーン名のみ」は候補として弱い（支店まで特定できない）
CHAIN_NAMES = {
    "ダイナム", "マルハン", "キコーナ", "楽園", "ガイア", "キャッスル",
    "ガーデン", "エスパス", "ゼント", "ZENT", "メッセ", "クリエ",
    "ニラク", "ビックマーチ", "コンコルド", "ユーコー", "ラッキー",
}


def _get_cookies() -> list[dict]:
    """
    fetch_complete_info.py と同じセッションクッキーを取得する。
    優先順位: 環境変数 → 暗号化セッションファイル → browser_cookie3(Chrome)
    """
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
    if SESSION_FILE.exists():
        try:
            import base64, struct
            from cryptography.fernet import Fernet
            raw = SESSION_FILE.read_bytes()
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

    # browser_cookie3 (Chrome)
    try:
        import browser_cookie3
        jar = browser_cookie3.chrome(domain_name=".x.com")
        cookies = []
        for c in jar:
            cookies.append({
                "name": c.name, "value": c.value,
                "domain": c.domain or ".x.com",
                "path": c.path or "/", "secure": bool(c.secure),
                "httpOnly": False, "sameSite": "None",
            })
        if any(c["name"] == "auth_token" for c in cookies):
            print(f"🍪 Chrome cookie {len(cookies)}個取得")
            return cookies
    except Exception:
        pass

    return []


def _normalize(name: str) -> str:
    """表示名から記号・スペース・括弧を除去して比較用文字列に変換"""
    name = re.sub(r'[\s　【】「」〔〕♪★☆◆◇●○・、。！!？?《》≪≫＠@~～－-]', '', name)
    # 全角英数 → 半角
    name = name.translate(str.maketrans(
        'ａ-ｚＡ-Ｚ０-９', 'a-zA-Z0-9'
    ))
    return name.lower()


def _name_score(store_name: str, display_name: str) -> float:
    """店舗名 と X 表示名の一致度（0〜1）"""
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
    # 先頭共通長
    common = 0
    for a, b in zip(s, d):
        if a == b:
            common += 1
        else:
            break
    return common / max(len(s), len(d)) * 0.7


def _verify_x_profile(page, handle: str, store_name: str, pref: str, city: str) -> Optional[dict]:
    """
    X プロフィールページを直接訪問してアカウント情報を取得・検証する。
    戻り値: {'x_url', 'handle', 'display_name', 'bio', 'score'} or None
    """
    profile_url = f"https://x.com/{handle}"
    try:
        page.goto(profile_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception:
        return None

    # 表示名
    try:
        name_el = page.query_selector('[data-testid="UserName"] span')
        disp_name = name_el.inner_text().strip() if name_el else ""
    except Exception:
        disp_name = ""

    # バイオ
    try:
        bio_el = page.query_selector('[data-testid="UserDescription"]')
        bio = bio_el.inner_text().strip() if bio_el else ""
    except Exception:
        bio = ""

    # ロケーション
    try:
        loc_el = page.query_selector('[data-testid="UserLocation"]')
        location = loc_el.inner_text().strip() if loc_el else ""
    except Exception:
        location = ""

    if not disp_name:
        disp_name = handle  # フォールバック

    score = _name_score(store_name, disp_name)
    combined = bio + " " + location + " " + disp_name
    has_slot_kw = bool(SLOT_KEYWORDS.search(combined))

    if pref and pref.replace("県", "").replace("府", "").replace("都", "") in combined:
        score *= 1.15
    if city and city in combined:
        score *= 1.10
    if not has_slot_kw and score < 0.75:
        return None
    if has_slot_kw:
        score *= 1.2

    return {
        "x_url":        f"https://x.com/{handle}",
        "handle":       handle,
        "display_name": disp_name,
        "bio":          bio[:120],
        "score":        round(score, 3),
    }


_SKIP_HANDLES = frozenset([
    "search", "explore", "notifications", "messages", "home",
    "i", "intent", "share", "hashtag", "login", "signup",
    "privacy", "tos", "settings", "compose", "twitter",
])


def _extract_handles_from_links(page) -> list[str]:
    """ページ内のリンクと表示テキストから x.com ハンドルを収集する"""
    seen: set[str] = set()
    found: list[str] = []

    # <a href> から抽出
    try:
        links = page.query_selector_all('a[href*="x.com/"], a[href*="twitter.com/"]')
        for link in links[:40]:
            try:
                href = link.get_attribute("href") or ""
            except Exception:
                continue
            m = re.search(r'(?:x\.com|twitter\.com)/([A-Za-z0-9_]{3,50})(?:/|$|\?)', href)
            if m:
                h = m.group(1).lower()
                if h not in _SKIP_HANDLES and h not in seen:
                    seen.add(h)
                    found.append(h)
    except Exception:
        pass

    # ページテキストから抽出（Bing は URL をテキストとして表示する）
    try:
        page_text = page.inner_text('body') or ""
        for m in re.finditer(r'(?:x|twitter)\.com/([A-Za-z0-9_]{3,50})(?:/|\s|$)', page_text):
            h = m.group(1).lower()
            if h not in _SKIP_HANDLES and h not in seen:
                seen.add(h)
                found.append(h)
    except Exception:
        pass

    return found


def search_user_on_x(page, store_name: str, pref: str, city: str) -> Optional[dict]:
    """
    Bing で「"店舗名" site:x.com パチスロ」を検索し、X プロフィールURLを抽出・検証する。
    戻り値: {'x_url', 'handle', 'display_name', 'bio', 'score'} or None
    """
    import urllib.parse
    # site:x.com を外して広く検索（x.com リンクが出るページを探す）
    query_str = f'"{store_name}" パチスロ OR パチンコ OR スロット x.com OR twitter.com'
    bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query_str)}&setlang=ja&cc=JP"

    try:
        page.goto(bing_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"  ⚠️ Bing遷移エラー: {e}")
        return None

    # Bing CAPTCHA 検出（challenge ページへのリダイレクト）
    if "challenge" in page.url or "/sorry/" in page.url:
        print("  ⚠️ Bing CAPTCHA 検出 — スキップ")
        return None

    handles_found = _extract_handles_from_links(page)

    if not handles_found:
        return None

    # 最大3ハンドルを X プロフィールで検証
    best: Optional[dict] = None
    best_score = 0.0

    for handle in handles_found[:3]:
        result = _verify_x_profile(page, handle, store_name, pref, city)
        if result and result["score"] > best_score:
            best_score = result["score"]
            best = result

    if best and best["score"] >= 0.55:
        return best
    return None


def main():
    ap = argparse.ArgumentParser(description="stores.json の x_url を X 検索で補完")
    ap.add_argument("--min-events", type=int, default=1,
                    help="最低イベント数（デフォルト1）")
    ap.add_argument("--limit", type=int, default=0,
                    help="処理件数上限 (0=無制限)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="stores.json を保存しない（確認のみ）")
    ap.add_argument("--min-score", type=float, default=0.55,
                    help="採用する最低スコア（デフォルト0.55）")
    args = ap.parse_args()

    stores: list[dict] = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    store_by_id = {s["id"]: s for s in stores}

    # 対象: x_urlなし × min_events以上
    targets = [
        s for s in stores
        if not s.get("x_url") and s.get("event_count", 0) >= args.min_events
    ]
    targets.sort(key=lambda x: (-x.get("event_count", 0), x.get("name", "")))

    if args.limit:
        targets = targets[:args.limit]

    print(f"対象店舗: {len(targets)}件 (event>={args.min_events})")
    if args.dry_run:
        print("  [DRY RUN モード — stores.json は変更しません]")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        ctx     = browser.new_context(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        # Google検索ベースなので X ログイン不要
        # X プロフィール検証のみ使用（ログイン無しで閲覧可能）
        page = ctx.new_page()

        # Google 疎通確認
        try:
            page.goto("https://www.google.com", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            print(f"✅ Google 接続確認 (title={page.title()!r})")
        except Exception as e:
            print(f"⚠️ Google 接続エラー: {e} — 続行します")

        found_count = 0
        save_interval = 10  # 10件ごとに保存

        for idx, store in enumerate(targets):
            name = store.get("name", "")
            pref = store.get("pref", "")
            city = store.get("city", "")
            ec   = store.get("event_count", 0)

            print(f"[{idx+1}/{len(targets)}] {name} ({pref}{city}) ec={ec}", end="  ", flush=True)

            result = search_user_on_x(page, name, pref, city)

            if result and result["score"] >= args.min_score:
                print(f"✅ @{result['handle']} score={result['score']:.2f} \"{result['display_name']}\"")
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

            time.sleep(3.5)  # Google レート制限対策

        browser.close()

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
