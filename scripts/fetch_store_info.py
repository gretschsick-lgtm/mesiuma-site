#!/usr/bin/env python3
"""
店舗の個別HPページから店舗情報を収集して stores.json を補完するスクリプト。

収集対象:
  - 住所 (address)
  - パチンコ台数 (pachinko_count)
  - スロット台数 (slot_count)
  - 開店時間 (open_time)
  - 閉店時間 (close_time)

対象: 店舗独自HP または チェーン内の個別店舗ページ (グループのルートドメインは除く)

Usage:
  python scripts/fetch_store_info.py                  # event>=1 の全店舗
  python scripts/fetch_store_info.py --min-events 3   # event>=3 のみ
  python scripts/fetch_store_info.py --headless
  python scripts/fetch_store_info.py --dry-run        # 保存しない
  python scripts/fetch_store_info.py --limit 50       # 上位50件だけ
"""

from __future__ import annotations
import json, re, time, argparse, sys, urllib.parse, urllib.request, ssl
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright が未インストールです: pip install playwright && playwright install chromium")
    sys.exit(1)

STORES_JSON = Path(__file__).parent.parent / "public/stores.json"

# ══════════════════════════════════════════════════════════════════════
# DMM p-town: 都道府県 → slug マッピング
# ══════════════════════════════════════════════════════════════════════

PREF_DMM: dict[str, str] = {
    "北海道": "hokkaido",
    "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima",
    "茨城県": "ibaraki", "栃木県": "tochigi", "群馬県": "gunma",
    "埼玉県": "saitama", "千葉県": "chiba", "東京都": "tokyo",
    "神奈川県": "kanagawa",
    "新潟県": "niigata", "富山県": "toyama", "石川県": "ishikawa",
    "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi",
    "三重県": "mie", "滋賀県": "shiga", "京都府": "kyoto",
    "大阪府": "osaka", "兵庫県": "hyogo", "奈良県": "nara",
    "和歌山県": "wakayama",
    "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama",
    "広島県": "hiroshima", "山口県": "yamaguchi",
    "徳島県": "tokushima", "香川県": "kagawa", "愛媛県": "ehime",
    "高知県": "kochi",
    "福岡県": "fukuoka", "佐賀県": "saga", "長崎県": "nagasaki",
    "熊本県": "kumamoto", "大分県": "oita", "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_DMM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def _fetch_url(url: str, timeout: int = 12) -> str:
    """urllib で URL を取得してHTMLを返す（失敗時は空文字）"""
    try:
        req = urllib.request.Request(url, headers=_DMM_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            charset = "utf-8"
            ct = r.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].strip().split(";")[0]
            return r.read().decode(charset, errors="replace")
    except Exception:
        return ""


def scrape_dmm_info(html: str) -> dict:
    """DMM p-town 店舗ページ (https://p-town.dmm.com/shops/{pref}/{id}) から情報抽出"""
    result: dict = {}

    # ── JSON-LD から住所・営業時間を優先取得 ──────────────────────────
    jl = _extract_from_jsonld(html)
    result.update(jl)

    # DMM openingHours 形式: "9:00　～　22:45" (全角スペース・波ダッシュ)
    if not result.get("open_time"):
        m = re.search(r'"openingHours"\s*:\s*"(\d{1,2}):(\d{2})[^"]*?(\d{1,2}):(\d{2})"', html)
        if m:
            h1, m1, h2, m2 = m.groups()
            result["open_time"]  = f"{int(h1):02d}:{m1}"
            result["close_time"] = f"{int(h2):02d}:{m2}"

    # ── 機台数: HTML の machine-sum div (新形式) ──────────────────────
    # 構造:
    #   <div class="machine-rate-pachi|slot">...</div>
    #   → <div class="machine-sum">計XXX台</div>
    # パチンコセクション
    if not result.get("pachinko_count"):
        m = re.search(
            r'machine-rate-pachi.*?<div class="machine-sum">計(\d{2,4})台</div>',
            html, re.S
        )
        if m:
            result["pachinko_count"] = int(m.group(1))

    # スロットセクション
    if not result.get("slot_count"):
        m = re.search(
            r'machine-rate-slot.*?<div class="machine-sum">計(\d{2,4})台</div>',
            html, re.S
        )
        if m:
            result["slot_count"] = int(m.group(1))

    # machine-sum が pachi/slot 順に 2 個ある場合 (ラベルが先に来ない場合のフォールバック)
    if not result.get("pachinko_count") and not result.get("slot_count"):
        sums = re.findall(r'<div class="machine-sum">計(\d{2,4})台</div>', html)
        if len(sums) >= 1:
            result["pachinko_count"] = int(sums[0])
        if len(sums) >= 2:
            result["slot_count"] = int(sums[1])

    # ── 機台数: テキスト形式 (旧形式 or 他HP) ──────────────────────────
    # タグ除去済みテキスト
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)

    for pat, kind in _MACHINE_PATTERNS:
        if result.get(f"{kind}_count"):
            continue
        m = pat.search(text)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 9999:
                result[f"{kind}_count"] = val

    # ── 住所: テキスト抽出フォールバック ─────────────────────────────
    if not result.get("address"):
        m = _ADDR_PATTERN.search(text)
        if m:
            addr = re.sub(r'\s+', '', m.group(1)).strip()
            if 10 <= len(addr) <= 80:
                result["address"] = addr
    if not result.get("address"):
        m = _ADDR_SIMPLE.search(text)
        if m:
            addr = re.sub(r'\s+', '', m.group(1)).strip()
            if 10 <= len(addr) <= 80:
                result["address"] = addr

    # ── 営業時間: テキスト抽出フォールバック ──────────────────────────
    if not result.get("open_time"):
        m = _TIME_PATTERN.search(text)
        if m:
            h, mn = int(m.group(1)), m.group(2) or "00"
            result["open_time"] = f"{h:02d}:{mn:0>2}"
            if m.group(3):
                hc, mc = int(m.group(3)), m.group(4) or "00"
                result["close_time"] = f"{hc:02d}:{mc:0>2}"
    if not result.get("close_time"):
        m = _CLOSE_PATTERN.search(text)
        if m:
            hc, mc = int(m.group(1)), m.group(2) or "00"
            result["close_time"] = f"{hc:02d}:{mc:0>2}"

    return result


def fetch_dmm_info(dmm_id: str, pref: str) -> dict:
    """DMM p-town の店舗ページから情報を取得する"""
    slug = PREF_DMM.get(pref)
    if not slug or not dmm_id:
        return {}
    url = f"https://p-town.dmm.com/shops/{slug}/{dmm_id}"
    html = _fetch_url(url)
    if not html:
        return {}
    # p-townページにパチスロ関連語があるか確認
    if not re.search(r'パチンコ|スロット|ホール|設置台数', html[:3000]):
        return {}
    return scrape_dmm_info(html)


# ══════════════════════════════════════════════════════════════════════
# チェーン「ルート」ドメイン（個別店舗ページではないためスキップ）
# ※ wonderland.gr.jp/kashii/ のように store-specific path があれば対象
# ══════════════════════════════════════════════════════════════════════

# ルートドメインのみ（パスなし）でスキップするドメインリスト
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
        # チェーン本部ルートドメイン
        if any(c in domain for c in CHAIN_ROOT_DOMAINS):
            return False
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# テキスト抽出ユーティリティ
# ══════════════════════════════════════════════════════════════════════

# 台数パターン
_MACHINE_PATTERNS = [
    # パチンコ: "パチンコ ○台" 系
    (re.compile(r'パチンコ[^\d\n]{0,10}?(\d{2,4})\s*台', re.S), "pachinko"),
    (re.compile(r'パチ[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),      "pachinko"),
    (re.compile(r'P台[^\d\n]{0,5}?(\d{2,4})\s*台', re.S),       "pachinko"),
    # スロット: "スロット ○台" 系
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

# 住所パターン（都道府県から始まる）
_ADDR_PATTERN = re.compile(
    r'(?:住所|所在地|アドレス|address)[^\w\n]{0,10}'
    r'((?:北海道|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|東京|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|京都|大阪|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)[都道府県]))'
    r'[^\n]{5,80}',
    re.S | re.I
)
_ADDR_SIMPLE = re.compile(
    r'((?:北海道|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|東京|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|京都|大阪|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)[都道府県]\S+(?:[市区町村]\S+){1,3}\d+[-－\d]*(?:番地|丁目|番|\-|\d)*[\d\-]*\d*))',
)


def _extract_from_jsonld(page_text: str) -> dict:
    """JSON-LD (schema.org) から住所・営業時間を抽出する"""
    result: dict = {}
    # <script type="application/ld+json"> を全部取り出す
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_text, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        # @graph 対応
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
                result["address"] = addr
            elif isinstance(addr, dict):
                parts = [
                    addr.get("addressRegion",""),
                    addr.get("addressLocality",""),
                    addr.get("streetAddress",""),
                ]
                full = "".join(p for p in parts if p)
                if full:
                    result["address"] = full
            # 営業時間 openingHoursSpecification
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
                    # "Mo-Su 10:00-23:00" 形式
                    tm = re.search(r'(\d{2}:\d{2})-(\d{2}:\d{2})', ohs)
                    if tm:
                        result["open_time"]  = tm.group(1)
                        result["close_time"] = tm.group(2)
    return result


def scrape_store_page(page_text: str) -> dict:
    """ページテキストから店舗情報を抽出する"""
    result: dict = {}

    # JSON-LD から優先取得
    jl = _extract_from_jsonld(page_text)
    result.update(jl)

    # 台数抽出
    for pattern, kind in _MACHINE_PATTERNS:
        if result.get(f"{kind}_count"):
            continue
        m = pattern.search(page_text)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 9999:   # 合理的な台数
                result[f"{kind}_count"] = val

    # 営業時間（まだ未取得なら）
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

    # 住所（まだ未取得なら）
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

    return result


def fetch_store_info(page, hp_url: str, store_name: str = "") -> dict:
    """1店舗HPをスクレイプして情報を返す"""
    try:
        page.goto(hp_url, timeout=20000, wait_until="domcontentloaded")
        # JS レンダリング完了を待つ（最大4秒）
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            page.wait_for_timeout(3000)
    except Exception:
        return {}

    try:
        html = page.content()
    except Exception:
        return {}

    # サイトの妥当性チェック（パチンコ/スロット関連か）
    SLOT_VALIDATE = re.compile(
        r'パチンコ|スロット|パチ|スロ|ホール|遊技|コンプリート|設置台数|営業時間'
    )
    html_preview = html[:5000]
    if not SLOT_VALIDATE.search(html_preview):
        # ページタイトルでも確認
        try:
            title = page.title()
            if not SLOT_VALIDATE.search(title):
                if store_name and store_name[:4] not in html_preview:
                    return {}   # パチスロ無関係なサイト
        except Exception:
            pass

    # HTML をテキストに変換（タグ除去）
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # HTML から JSON-LD を含むスクレイプ
    info = scrape_store_page(text)
    # JSON-LDはHTML全体から取る
    jl_info = _extract_from_jsonld(html)
    for k, v in jl_info.items():
        if v and not info.get(k):
            info[k] = v

    return info


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="店舗HPおよびDMM p-townから住所・台数などを収集")
    ap.add_argument("--min-events", type=int, default=1)
    ap.add_argument("--limit",      type=int, default=0)
    ap.add_argument("--headless",   action="store_true")
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--overwrite",  action="store_true", help="既存データも上書き")
    ap.add_argument("--skip-dmm",   action="store_true", help="DMM p-town をスキップ")
    ap.add_argument("--dmm-only",   action="store_true", help="DMM p-town のみ（HP スキップ）")
    ap.add_argument("--all-stores", action="store_true", help="event_count 関係なく全店舗対象（dmm_id あり）")
    args = ap.parse_args()

    stores: list[dict] = json.loads(STORES_JSON.read_text(encoding="utf-8"))

    # 対象店舗の決定
    targets = []
    for s in stores:
        hp = s.get("hp_url") or ""
        dmm_id = s.get("dmm_id") or ""
        has_valid_hp = is_valid_hp(hp)
        has_dmm = bool(dmm_id)

        # --all-stores: dmm_id があれば全店舗対象
        if args.all_stores:
            if not (has_valid_hp or has_dmm):
                continue
        else:
            # 通常: 有効なHP か dmm_id のどちらかが必要
            if not (has_valid_hp or has_dmm):
                continue
            if s.get("event_count", 0) < args.min_events:
                continue

        # 全フィールド取得済みならスキップ（--overwrite なし）
        if not args.overwrite:
            missing = [
                not s.get("address"),
                not s.get("pachinko_count"),
                not s.get("slot_count"),
            ]
            if not any(missing):
                continue
        targets.append(s)

    targets.sort(key=lambda s: (-s.get("event_count", 0), s.get("name", "")))
    if args.limit:
        targets = targets[:args.limit]

    hp_count  = sum(1 for s in targets if is_valid_hp(s.get("hp_url","")))
    dmm_count = sum(1 for s in targets if s.get("dmm_id"))
    print(f"対象店舗: {len(targets)}件  (HP有={hp_count}, DMM有={dmm_count})")
    if args.dry_run:
        print("  [DRY RUN — stores.json は変更しません]")
    if args.dmm_only:
        print("  [DMM専用モード — HP はスキップ]")
    if args.skip_dmm:
        print("  [DMM スキップ]")

    store_by_id = {s["id"]: s for s in stores}

    found_count = 0
    save_interval = 20
    _SAVE_FIELDS = ("address", "pachinko_count", "slot_count", "open_time", "close_time")

    # DMM-only モードは Playwright 不要
    need_browser = not args.dmm_only and hp_count > 0

    def _apply_info(store: dict, info: dict) -> list[str]:
        """info を store に適用し、更新フィールド名リストを返す"""
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

    def _run(page_or_none):
        nonlocal found_count
        for idx, store in enumerate(targets):
            name   = store.get("name", "")
            hp     = store.get("hp_url", "")
            dmm_id = store.get("dmm_id", "")
            pref   = store.get("pref", "")
            ec     = store.get("event_count", 0)
            print(f"[{idx+1}/{len(targets)}] {name} (ec={ec})", end="  ", flush=True)

            combined: dict = {}

            # ── ① HP スクレイプ ─────────────────────────────────
            if not args.dmm_only and is_valid_hp(hp) and page_or_none:
                hp_info = fetch_store_info(page_or_none, hp, name)
                combined.update(hp_info)
                if hp_info:
                    print(f"[HP] ", end="", flush=True)
                time.sleep(1.0)

            # ── ② DMM p-town フォールバック ──────────────────────
            needs_dmm = not args.skip_dmm and dmm_id and pref and (
                not combined.get("pachinko_count") or
                not combined.get("slot_count") or
                not combined.get("address")
            )
            if needs_dmm:
                dmm_info = fetch_dmm_info(dmm_id, pref)
                for k, v in dmm_info.items():
                    if v and (args.overwrite or not combined.get(k)):
                        combined[k] = v
                if dmm_info:
                    print(f"[DMM] ", end="", flush=True)
                time.sleep(0.8)

            # ── 結果表示・保存 ────────────────────────────────────
            updated_fields = _apply_info(store, combined)
            if updated_fields:
                print(f"✅ {', '.join(updated_fields)}")
                if not args.dry_run:
                    _commit_info(store, combined)
                found_count += 1
            else:
                print("—")

            # 定期保存
            if not args.dry_run and (idx + 1) % save_interval == 0:
                _save()

    if need_browser:
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
            _run(page)
            browser.close()
    else:
        # DMM-only: Playwright 不要
        _run(None)

    if not args.dry_run:
        _save()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}完了: {found_count}/{len(targets)}件 更新")


if __name__ == "__main__":
    main()
