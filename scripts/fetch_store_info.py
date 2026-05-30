#!/usr/bin/env python3
"""
店舗の個別HPページから店舗情報を収集して stores.json を補完するスクリプト。

収集対象:
  - 住所 (address)
  - パチンコ台数 (pachinko_count)
  - スロット台数 (slot_count)
  - 開店時間 (open_time)
  - 閉店時間 (close_time)

対象: 各店舗が公開している個別 HP のみ（チェーン本部ルートドメインは除外）。
※ 第三者プラットフォームのスクレイピングは一切行わない。

Usage:
  python scripts/fetch_store_info.py                 # event_count>=1 の HP 持ち店舗
  python scripts/fetch_store_info.py --min-events 3
  python scripts/fetch_store_info.py --headless
  python scripts/fetch_store_info.py --dry-run       # 保存しない
  python scripts/fetch_store_info.py --limit 50      # 上位50件だけ
  python scripts/fetch_store_info.py --all-stores    # event_count 関係なく HP 持ち全店舗
"""

from __future__ import annotations
import json, re, time, argparse, sys, urllib.parse
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright が未インストールです: pip install playwright && playwright install chromium")
    sys.exit(1)

STORES_JSON = Path(__file__).parent.parent / "public/stores.json"


# ══════════════════════════════════════════════════════════════════════
# チェーン「ルート」ドメイン（個別店舗ページではないためスキップ）
# ※ wonderland.gr.jp/kashii/ のように store-specific path があれば対象
# ══════════════════════════════════════════════════════════════════════

CHAIN_ROOT_DOMAINS = {
    "king-net.co.jp", "luckyplaza.co.jp", "undertree.co.jp",
    "k-kosho.co.jp", "papimo.jp", "maruhan.co.jp",
    "nittaku.jp", "tsubame-group.jp", "venice.co.jp",
    "dynam.jp", "abc-p.jp", "niraku.co.jp", "gaia-jp.com",
    "concorde-group-lp.jp", "nexus-group.jp", "yume-corp.co.jp",
    "tamaya.gr.jp", "m-king.co.jp", "aeonentertainment.co.jp",
    "marioad.co.jp", "dainamdainamdainam.co.jp",
}


def is_valid_hp(hp_url: str) -> bool:
    """個別店舗ページとして訪問すべきURLか判定する"""
    if not hp_url:
        return False
    try:
        parsed = urllib.parse.urlparse(hp_url)
        domain = parsed.netloc.lstrip("www.")
        # チェーン本部ルートドメイン（パスなしの場合はスキップ）
        if any(c in domain for c in CHAIN_ROOT_DOMAINS):
            if not parsed.path or parsed.path == "/":
                return False
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# テキスト抽出ユーティリティ
# ══════════════════════════════════════════════════════════════════════

# 台数パターン
_MACHINE_PATTERNS = [
    (re.compile(r'パチンコ[^\d\n]{0,10}?(\d{2,4})\s*台', re.S), "pachinko"),
    (re.compile(r'パチ[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),      "pachinko"),
    (re.compile(r'P台[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),       "pachinko"),
    (re.compile(r'スロット[^\d\n]{0,10}?(\d{2,4})\s*台', re.S),  "slot"),
    (re.compile(r'スロ[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),      "slot"),
    (re.compile(r'S台[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),       "slot"),
    (re.compile(r'スマスロ[^\d\n]{0,10}?(\d{2,4})\s*台', re.S),  "slot"),
]

# 時間パターン
_TIME_PATTERN = re.compile(
    r'(?:開店|営業開始|OPEN)[^\d\n]{0,10}?(\d{1,2})[：:時](\d{0,2})'
    r'(?:[^\d\n]{0,20}(?:閉店|終了|CLOSE)[^\d\n]{0,10}?(\d{1,2})[：:時](\d{0,2}))?',
    re.S
)
_CLOSE_PATTERN = re.compile(
    r'(?:閉店|終了|CLOSE)[^\d\n]{0,10}?(\d{1,2})[：:時](\d{0,2})', re.S
)

# 住所パターン
_PREFS = ("北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|"
          "茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|"
          "新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|"
          "三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|"
          "鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|"
          "福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県")
_ADDR_PATTERN = re.compile(
    r'(?:住所|所在地|アドレス|address)[^\w\n]{0,10}'
    + r'((?:' + _PREFS + r')[^\n]{5,80})',
    re.S | re.I
)
_ADDR_SIMPLE = re.compile(r'((?:' + _PREFS + r')[^\n、。<>]{5,80})')


def _extract_from_jsonld(page_text: str) -> dict:
    """JSON-LD (schema.org) から住所・営業時間を抽出する"""
    result: dict = {}
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_text, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@graph"):
                items = item["@graph"]
                break
        for item in items:
            if not isinstance(item, dict):
                continue
            # 住所
            addr = item.get("address") or {}
            if isinstance(addr, str) and len(addr) > 10:
                result.setdefault("address", addr)
            elif isinstance(addr, dict):
                parts = [
                    addr.get("addressRegion",""),
                    addr.get("addressLocality",""),
                    addr.get("streetAddress",""),
                ]
                full = "".join(p for p in parts if p)
                if full:
                    result.setdefault("address", full)
            # 営業時間
            ohs = item.get("openingHoursSpecification") or item.get("openingHours")
            if ohs and not result.get("open_time"):
                if isinstance(ohs, list) and ohs:
                    ohs = ohs[0]
                if isinstance(ohs, dict):
                    opens = ohs.get("opens","")
                    closes = ohs.get("closes","")
                    if opens:
                        result["open_time"] = opens[:5]
                    if closes:
                        result["close_time"] = closes[:5]
                elif isinstance(ohs, str):
                    t = re.search(r'(\d{1,2}):(\d{2})[^\d]+(\d{1,2}):(\d{2})', ohs)
                    if t:
                        result["open_time"]  = f"{int(t.group(1)):02d}:{t.group(2)}"
                        result["close_time"] = f"{int(t.group(3)):02d}:{t.group(4)}"
            # X / Twitter URL
            if not result.get("x_url"):
                same_as = item.get("sameAs", [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                if isinstance(same_as, list):
                    for u in same_as:
                        if isinstance(u, str) and re.search(r'(?:x\.com|twitter\.com)/[A-Za-z0-9_]+', u):
                            result["x_url"] = u
                            break
    return result


def scrape_store_page(page_text: str) -> dict:
    """ページテキスト（タグ除去済み）から住所・営業時間・台数を抽出"""
    result: dict = {}
    # 台数
    for pat, kind in _MACHINE_PATTERNS:
        if result.get(f"{kind}_count"):
            continue
        m = pat.search(page_text)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 9999:
                result[f"{kind}_count"] = val

    # 住所
    if not result.get("address"):
        m = _ADDR_PATTERN.search(page_text)
        if m:
            addr = re.sub(r'\s+', '', m.group(1)).strip()
            if 10 <= len(addr) <= 80:
                result["address"] = addr
    if not result.get("address"):
        m = _ADDR_SIMPLE.search(page_text)
        if m:
            addr = re.sub(r'\s+', '', m.group(1)).strip()
            if 10 <= len(addr) <= 80:
                result["address"] = addr

    # 営業時間
    if not result.get("open_time"):
        m = _TIME_PATTERN.search(page_text)
        if m:
            h, mn = int(m.group(1)), m.group(2) or "00"
            result["open_time"] = f"{h:02d}:{mn:0>2}"
            if m.group(3):
                hc, mc = int(m.group(3)), m.group(4) or "00"
                result["close_time"] = f"{hc:02d}:{mc:0>2}"
    if not result.get("close_time"):
        m = _CLOSE_PATTERN.search(page_text)
        if m:
            hc, mc = int(m.group(1)), m.group(2) or "00"
            result["close_time"] = f"{hc:02d}:{mc:0>2}"

    return result


def fetch_store_info(page, hp_url: str, store_name: str = "") -> dict:
    """1店舗HPをスクレイプして情報を返す"""
    try:
        page.goto(hp_url, timeout=20000, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            page.wait_for_timeout(2500)
    except Exception:
        return {}

    try:
        html = page.content()
    except Exception:
        return {}

    # サイトの妥当性チェック
    SLOT_VALIDATE = re.compile(
        r'パチンコ|スロット|パチ|スロ|ホール|遊技|コンプリート|設置台数|営業時間'
    )
    html_preview = html[:5000]
    if not SLOT_VALIDATE.search(html_preview):
        try:
            title = page.title()
            if not SLOT_VALIDATE.search(title):
                if store_name and store_name[:4] not in html_preview:
                    return {}
        except Exception:
            pass

    # HTML をテキストに変換
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # テキスト抽出 + JSON-LD
    info = scrape_store_page(text)
    jl_info = _extract_from_jsonld(html)
    for k, v in jl_info.items():
        if v and not info.get(k):
            info[k] = v

    # X リンクが HTML 内にあれば取得（フッタや SNS リンクから）
    if not info.get("x_url"):
        m = re.search(r'href="(https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+)"', html)
        if m and "/share?" not in m.group(1) and "/intent/" not in m.group(1):
            info["x_url"] = m.group(1).replace("twitter.com", "x.com")

    return info


def main():
    ap = argparse.ArgumentParser(description="店舗HPから住所・台数・X URLを収集")
    ap.add_argument("--min-events", type=int, default=1)
    ap.add_argument("--limit",      type=int, default=0)
    ap.add_argument("--headless",   action="store_true")
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--overwrite",  action="store_true", help="既存データも上書き")
    ap.add_argument("--all-stores", action="store_true", help="event_count 関係なく HP 持ち全店舗対象")
    args = ap.parse_args()

    stores: list[dict] = json.loads(STORES_JSON.read_text(encoding="utf-8"))

    # 対象店舗の決定（有効な HP を持つ店舗のみ）
    targets = []
    for s in stores:
        if not is_valid_hp(s.get("hp_url") or ""):
            continue
        if not args.all_stores and s.get("event_count", 0) < args.min_events:
            continue
        # 全フィールド取得済みならスキップ
        if not args.overwrite:
            missing = [
                not s.get("address"),
                not s.get("pachinko_count"),
                not s.get("slot_count"),
                not s.get("x_url"),
            ]
            if not any(missing):
                continue
        targets.append(s)

    targets.sort(key=lambda s: (-s.get("event_count", 0), s.get("name", "")))
    if args.limit:
        targets = targets[:args.limit]

    print(f"対象店舗: {len(targets)}件（有効 HP のみ）")
    if args.dry_run:
        print("  [DRY RUN — stores.json は変更しません]")

    store_by_id = {s["id"]: s for s in stores}

    found_count = 0
    save_interval = 20
    _SAVE_FIELDS = ("address", "pachinko_count", "slot_count", "open_time", "close_time", "x_url")

    def _apply_info(store: dict, info: dict) -> list[str]:
        updated = []
        for key in _SAVE_FIELDS:
            if info.get(key) and (args.overwrite or not store.get(key)):
                if key == "address":
                    updated.append(f"住所={info[key][:30]}")
                elif key == "pachinko_count":
                    updated.append(f"パチ={info[key]}台")
                elif key == "slot_count":
                    updated.append(f"スロ={info[key]}台")
                elif key == "open_time":
                    t = info[key]
                    if info.get("close_time"):
                        t += f"〜{info['close_time']}"
                    updated.append(f"時間={t}")
                elif key == "x_url":
                    updated.append(f"X={info[key]}")
        return updated

    def _commit_info(store: dict, info: dict):
        s = store_by_id[store["id"]]
        for key in _SAVE_FIELDS:
            if info.get(key) and (args.overwrite or not s.get(key)):
                s[key] = info[key]

    def _save():
        STORES_JSON.write_text(
            json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        for idx, store in enumerate(targets):
            name = store.get("name", "")
            hp   = store.get("hp_url", "")
            ec   = store.get("event_count", 0)
            print(f"[{idx+1}/{len(targets)}] {name} (ec={ec})", end="  ", flush=True)

            info = fetch_store_info(page, hp, name)
            updated_fields = _apply_info(store, info)
            if updated_fields:
                print(f"✅ {', '.join(updated_fields)}")
                if not args.dry_run:
                    _commit_info(store, info)
                found_count += 1
            else:
                print("—")

            # サイトに負荷をかけない（1.5秒インターバル）
            time.sleep(1.5)

            if not args.dry_run and (idx + 1) % save_interval == 0:
                _save()

        browser.close()

    if not args.dry_run:
        _save()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}完了: {found_count}/{len(targets)}件 更新")


if __name__ == "__main__":
    main()
