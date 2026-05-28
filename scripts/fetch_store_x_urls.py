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

import json, re, time, argparse, sys, os
from pathlib import Path

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


def search_user_on_x(page, store_name: str, pref: str, city: str) -> dict | None:
    """
    X の People 検索で店舗名を検索し、最も一致するアカウントを返す。
    戻り値: {'x_url', 'handle', 'display_name', 'bio', 'score'} or None
    """
    url = f"https://x.com/search?q={store_name}&f=user"
    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"  ⚠️ ページ遷移エラー: {e}")
        return None

    cells = page.query_selector_all('[data-testid="UserCell"]')
    if not cells:
        # ログアウト状態の場合はリロード
        title = page.title()
        if "ログイン" in title or "Log in" in title or "login" in title.lower():
            print("  ❌ 未ログイン状態")
            return None

    best: dict | None = None
    best_score = 0.0

    for cell in cells[:6]:
        try:
            # 表示名
            name_el  = cell.query_selector('[data-testid="UserName"] span:first-child')
            disp_name = name_el.inner_text().strip() if name_el else ""

            # ハンドル (@xxx)
            all_text = cell.inner_text()
            hm = re.search(r'@([\w]+)', all_text)
            handle = hm.group(1) if hm else ""

            # バイオ
            bio_el = cell.query_selector('[data-testid="UserDescription"]')
            bio    = bio_el.inner_text().strip() if bio_el else ""

            # ロケーション
            loc_el  = cell.query_selector('[data-testid="UserLocation"]')
            location = loc_el.inner_text().strip() if loc_el else ""

            if not disp_name or not handle:
                continue

            # チェーン名のみアカウントはスキップ（"マルハン" だけのアカウント等）
            if _normalize(disp_name) in {_normalize(c) for c in CHAIN_NAMES}:
                continue

            # 名前スコア
            score = _name_score(store_name, disp_name)
            if score < 0.35:
                continue

            combined = bio + " " + location + " " + disp_name

            # パチスロ業界キーワードがあれば必須チェック通過
            has_slot_kw = bool(SLOT_KEYWORDS.search(combined))

            # 都道府県が一致すれば加点
            if pref and pref.replace("県","").replace("府","").replace("都","") in combined:
                score *= 1.15
            if city and city in combined:
                score *= 1.10

            # パチスロキーワードがなく名前一致も弱い場合は除外
            if not has_slot_kw and score < 0.75:
                continue

            if has_slot_kw:
                score *= 1.2

            if score > best_score:
                best_score = score
                best = {
                    "x_url":        f"https://x.com/{handle}",
                    "handle":       handle,
                    "display_name": disp_name,
                    "bio":          bio[:120],
                    "score":        round(score, 3),
                }
        except Exception:
            continue

    # 最低スコアしきい値: 名前が十分に一致している + パチスロ感があるもの
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
        cookies = _get_cookies()
        if cookies:
            ctx.add_cookies(cookies)
        else:
            print("⚠️ クッキーなし — ログイン済み Chrome が必要です")

        page = ctx.new_page()

        # ログイン確認
        page.goto("https://x.com", timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        title = page.title()
        if "X" not in title and "Twitter" not in title:
            print(f"❌ X へのログイン失敗 (title={title!r})")
            browser.close()
            return
        print(f"✅ X ログイン確認 ({title})")

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

            time.sleep(2.0)  # レート制限対策

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
