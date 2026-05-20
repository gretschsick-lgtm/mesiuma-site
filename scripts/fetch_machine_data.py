#!/usr/bin/env python3
"""
店舗の新台・機種・台数・営業時間を収集して public/store_machines.json を生成する。

ソース:
  ptown  DMM p-town 店舗ページ（デフォルト）
  x      X(Twitter) の新台ツイートから機種名を補完

Usage:
    python scripts/fetch_machine_data.py                  # 全店舗（p-town）
    python scripts/fetch_machine_data.py --pref 東京都    # 1都道府県のみ
    python scripts/fetch_machine_data.py --source x       # X補完モード
    python scripts/fetch_machine_data.py --limit 100      # 最大N件
"""

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AREAS_JSON   = Path(__file__).parent.parent / "public/areas.json"
MACHINES_JSON = Path(__file__).parent.parent / "public/store_machines.json"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

PREF_SLUG: dict[str, str] = {
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


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  {url}: {e}", file=sys.stderr)
        return ""


def parse_store_page(html: str) -> dict:
    """DMM店舗ページHTMLから台数・機種・営業時間を抽出"""
    result: dict = {}

    # 営業時間
    h = re.search(r'<h3>営業時間</h3></th>\s*<td[^>]*>([^<]+)', html)
    if h:
        result["hours"] = h.group(1).strip().replace("　", "").replace(" ", "")

    # 入場ルール
    e = re.search(r'<h3>入場ルール</h3></th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
    if e:
        result["entry_rule"] = re.sub(r'<[^>]+>', '', e.group(1)).strip()

    # 住所
    addr = re.search(r'<h3>住所</h3></th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
    if addr:
        txt = re.sub(r'<[^>]+>', '', addr.group(1)).strip()
        if txt and txt != "-":
            result["address"] = txt

    # 遊技金額・台数（パチ/スロ別・レート別）
    pachinko: list[dict] = []
    slot: list[dict] = []

    # パターン1: machine-rate-area ブロック（旧形式）
    blocks = re.findall(
        r'<div class="machine-rate-area">(.*?)(?=<div class="machine-rate-area">|</td>)',
        html, re.DOTALL
    )
    for block in blocks:
        ptype_m = re.search(r'machine-type-name (\w+)">\s*<p>([^<]+)</p>', block)
        if not ptype_m:
            continue
        ptype_key = ptype_m.group(1)
        rates = re.findall(
            r'<span class="machine-rate-\w+">(.*?)</span>\s*<span>(\d+)台</span>',
            block
        )
        total_m = re.search(r'計(\d+)台', block)
        total = int(total_m.group(1)) if total_m else 0
        entries = [{"rate": r, "count": int(c)} for r, c in rates]
        if not entries and total:
            entries = [{"rate": "不明", "count": total}]
        if ptype_key == "pachi":
            pachinko = entries
            result["pachinko_total"] = total or sum(e["count"] for e in entries)
        else:
            slot = entries
            result["slot_total"] = total or sum(e["count"] for e in entries)

    # パターン2: テキスト形式「4円パチンコ:240台\n46枚スロット:374台」（新形式）
    if not pachinko and not slot:
        td_m = re.search(
            r'(?:遊技金額・台数|台数)</h3></th>\s*<td[^>]*>\s*<p[^>]*>(.*?)</p>',
            html, re.DOTALL
        )
        if td_m:
            td_text = re.sub(r'<[^>]+>', '\n', td_m.group(1))
            # パチンコ: 「4円パチンコ:240台」「1円パチンコ:120台」など
            for m2 in re.finditer(r'([^\n:：]+パチンコ)[：:]\s*(\d+)台', td_text):
                rate, count = m2.group(1).strip(), int(m2.group(2))
                pachinko.append({"rate": rate, "count": count})
            # スロット: 「46枚スロット:374台」「20枚スロット:100台」など
            for m2 in re.finditer(r'([^\n:：]*スロット)[：:]\s*(\d+)台', td_text):
                rate, count = m2.group(1).strip(), int(m2.group(2))
                slot.append({"rate": rate, "count": count})
            # どちらも取れなければ総台数だけ
            if not pachinko and not slot:
                all_counts = re.findall(r'(\d+)台', td_text)
                if all_counts:
                    total = sum(int(c) for c in all_counts)
                    pachinko = [{"rate": "不明", "count": total}]
            if pachinko:
                result["pachinko_total"] = sum(e["count"] for e in pachinko)
            if slot:
                result["slot_total"] = sum(e["count"] for e in slot)

    if pachinko:
        result["pachinko"] = pachinko
    if slot:
        result["slot"] = slot

    # 新台機種リスト（カルーセル）
    machine_names = re.findall(r'<h3 class="machine-name">([^<]+)</h3>', html)
    machine_types_raw = re.findall(
        r'<h3 class="machine-name">([^<]+)</h3>.*?<span class="text-icon[^"]*">(.*?)</span>',
        html, re.DOTALL
    )
    # name → type マップ
    type_map: dict[str, str] = {}
    for name, mtype in machine_types_raw:
        t = mtype.strip()
        if "パチンコ" in t:
            type_map[name] = "pachinko"
        elif "パチスロ" in t or "スロ" in t:
            type_map[name] = "slot"

    new_machines = []
    for name in machine_names:
        name = name.strip()
        if name:
            entry: dict = {"name": name}
            if name in type_map:
                entry["type"] = type_map[name]
            new_machines.append(entry)

    if new_machines:
        result["new_machines"] = new_machines

    return result


# ---------------------------------------------------------------------------
# X 新台補完
# ---------------------------------------------------------------------------
# X で「新台」ツイートから機種名を抽出するための正規表現
_MACHINE_NAME_RE = re.compile(
    r'「([^」\n]{3,30})」'            # 「機種名」形式
    r'|(?:スマスロ|スマパチ|Lパチスロ|Lスロ)\s*([^\s、。！\n]{3,20})'  # プレフィックス付き
    r'|((?:バジリスク|ヴァルヴレイヴ|炎炎|カバネリ|北斗|エヴァンゲリオン|ジャグラー'
    r'|牙狼|吉宗|まどマギ|バイオ|リゼロ|転スラ|鬼滅|チバリヨ|沖ドキ|番長'
    r'|花火絶景|ルパン|ゴッド)[^\s、。！\n]{0,12})'  # 有名シリーズ
)
_MACHINE_TYPE_RE = re.compile(r'パチンコ|パチ(?!スロ|スラ)|Pスロ')
_SLOT_TYPE_RE    = re.compile(r'スロット|スロ|パチスロ|スマスロ')
_NG_MACHINE      = {"今日", "本日", "明日", "来店", "取材", "イベント", "開店", "来週", "先週",
                    "パチンコ", "スロット", "パチスロ", "新台", "入替", "告知", "情報"}

_STORE_NAME_RE = re.compile(
    r"(マルハン|キコーナ|ガイア|PIA|ピア|楽園|エスパス|ニラク|ハッピー|ダイナム"
    r"|ワンダーランド|ミリオン|コンコルド|ZENT|メッセ|アポロ|Dステーション"
    r"|グランキコーナ|ビックマーチ|アミューズ)[^\s　,、。！!\n]{0,20}?(店|ホール|パーラー)"
)

# 新台関連クエリ（X検索用）
_X_NEW_MACHINE_QUERIES = [
    "新台入替 スロット 今日",
    "新台入替 パチンコ 今日",
    "スマスロ 新台 入替",
    "新台 パチスロ ホール",
    "本日より 新台 スロット",
    "導入 スマスロ ホール",
    "新台入替 スマパチ",
    "パチスロ新台 入替日",
    "本日入替 パチスロ",
    "新台 入れ替え スロット",
]


def _extract_machines_from_text(text: str) -> list[dict]:
    """ツイートテキストから機種名を抽出"""
    results: list[dict] = []
    seen: set[str] = set()
    for m in _MACHINE_NAME_RE.finditer(text):
        name = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not name or name in _NG_MACHINE or len(name) < 3:
            continue
        if name in seen:
            continue
        seen.add(name)
        # タイプ判定（ツイート全体から）
        if _MACHINE_TYPE_RE.search(text):
            mtype = "pachinko"
        elif _SLOT_TYPE_RE.search(text) or "スマスロ" in name or "スマパチ" not in name:
            mtype = "slot"
        else:
            mtype = "pachinko"
        results.append({"name": name, "type": mtype})
    return results


def run_x_source(machines: dict, store_names: set) -> int:
    """Xから新台情報を収集して machines dict を更新する。返り値は更新店舗数。"""
    try:
        from playwright.sync_api import sync_playwright
        try:
            from playwright_stealth import Stealth
            has_stealth = True
        except ImportError:
            has_stealth = False
    except ImportError:
        print("playwright 未インストール、Xスキップ", file=sys.stderr)
        return 0

    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0        = os.environ.get("X_CT0", "")
    if not (auth_token and ct0):
        print("X_AUTH_TOKEN/X_CT0 未設定、Xスキップ", file=sys.stderr)
        return 0

    updated = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_cookies([
            {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0",        "value": ct0,        "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ])
        page = ctx.new_page()
        if has_stealth:
            Stealth().apply_stealth_sync(page)
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        for query in _X_NEW_MACHINE_QUERIES:
            try:
                encoded = query.replace(" ", "%20")
                page.goto(f"https://x.com/search?q={encoded}&f=live", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                for _ in range(2):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)

                for article in page.query_selector_all('article[data-testid="tweet"]')[:30]:
                    try:
                        el = article.query_selector('[data-testid="tweetText"]')
                        if not el:
                            continue
                        text = el.inner_text()
                        if "新台" not in text and "入替" not in text and "導入" not in text:
                            continue

                        # 店舗名マッチ
                        store = ""
                        for sn in store_names:
                            if sn in text:
                                store = sn
                                break
                        if not store:
                            m = _STORE_NAME_RE.search(text)
                            if m:
                                store = m.group(0).strip()
                        if not store:
                            continue

                        new_machines = _extract_machines_from_text(text)
                        if not new_machines:
                            continue

                        existing = machines.get(store, {})
                        ex_names = {m["name"] for m in existing.get("new_machines", [])}
                        added = [m for m in new_machines if m["name"] not in ex_names]
                        if added:
                            if store not in machines:
                                machines[store] = {"updated_at": now_iso}
                            machines[store].setdefault("new_machines", [])
                            machines[store]["new_machines"] = added + machines[store]["new_machines"]
                            print(f"  X補完 {store}: {[m['name'] for m in added]}")
                            updated += 1

                    except Exception:
                        continue

                time.sleep(1.5)

            except Exception as e:
                print(f"  X検索エラー [{query}]: {e}", file=sys.stderr)

        page.close()
        ctx.close()

    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pref",   help="都道府県 (例: 東京都)。カンマ区切り複数可")
    parser.add_argument("--limit",  type=int, help="最大店舗数")
    parser.add_argument("--source", choices=["ptown", "x", "both"], default="ptown",
                        help="データソース: ptown(デフォルト) / x / both")
    args = parser.parse_args()

    with open(AREAS_JSON, encoding="utf-8") as f:
        areas: dict = json.load(f)

    # 既存データをロード
    machines: dict = {}
    if MACHINES_JSON.exists():
        with open(MACHINES_JSON, encoding="utf-8") as f:
            machines = json.load(f)

    # ── p-town スクレイプ ──────────────────────────────────────
    if args.source in ("ptown", "both"):
        if args.pref:
            prefs = [p.strip() for p in args.pref.split(",") if p.strip()]
        else:
            prefs = list(areas.keys())
        prefs = [p for p in prefs if p in areas and p in PREF_SLUG]

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        total = 0
        processed = 0

        for pref in prefs:
            slug = PREF_SLUG[pref]
            print(f"\n🗾 {pref}...")

            for city, stores in areas[pref].items():
                for store in stores:
                    name   = store["name"]
                    dmm_id = store["dmm_id"]
                    url    = f"https://p-town.dmm.com/shops/{slug}/{dmm_id}"

                    html = fetch(url)
                    if not html:
                        time.sleep(0.3)
                        continue

                    data = parse_store_page(html)
                    if data:
                        data["updated_at"] = now_iso
                        machines[name] = data
                        has_machine = "pachinko_total" in data or "slot_total" in data
                        has_new = "new_machines" in data
                        p_total = data.get("pachinko_total", 0)
                        s_total = data.get("slot_total", 0)
                        if has_machine or has_new:
                            suffix = f" パチ{p_total}台/スロ{s_total}台" if has_machine else ""
                            new_cnt = len(data.get("new_machines", []))
                            print(f"  ✓ {name}{suffix} 新台{new_cnt}件")
                        total += 1

                    processed += 1
                    if args.limit and processed >= args.limit:
                        break
                    time.sleep(0.35)

                if args.limit and processed >= args.limit:
                    break

            # 都道府県ごとに中間保存
            with open(MACHINES_JSON, "w", encoding="utf-8") as f:
                json.dump(machines, f, ensure_ascii=False, indent=2)

            if args.limit and processed >= args.limit:
                break

        print(f"\n✅ p-town完了: {total}件 → {MACHINES_JSON}")

    # ── X 補完 ──────────────────────────────────────────────────
    if args.source in ("x", "both"):
        # stores.json から店舗名セット
        stores_json = Path(__file__).parent.parent / "public/stores.json"
        store_names: set = set()
        if stores_json.exists():
            with open(stores_json, encoding="utf-8") as f:
                for s in json.load(f):
                    n = s.get("name", "")
                    if n and len(n) >= 4:
                        store_names.add(n)
        print(f"\n🐦 X新台補完開始 (店舗名{len(store_names)}件)")
        x_updated = run_x_source(machines, store_names)
        if x_updated > 0:
            with open(MACHINES_JSON, "w", encoding="utf-8") as f:
                json.dump(machines, f, ensure_ascii=False, indent=2)
        print(f"✅ X補完完了: {x_updated}店舗更新")

    print(f"\n🎉 store_machines.json 合計 {len(machines)} 店舗 → {MACHINES_JSON}")


if __name__ == "__main__":
    main()
