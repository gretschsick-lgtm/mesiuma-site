#!/usr/bin/env python3
"""
P-World (p-world.co.jp) から全国店舗の詳細データを収集する。

収集データ:
  - 台数（パチンコ/スロット）
  - 営業時間
  - 設置機種（新台含む）
  - 店舗写真URL
  - フロアマップURL (ssc ページ)
  - 住所

URL構造:
  店舗一覧: https://www.p-world.co.jp/_machine/kensaku.cgi?is_new_ver=1&dir={pref_dir}&page={n}
  店舗詳細: https://www.p-world.co.jp/{pref_dir}/{slug}.htm
  フロアマップ: https://www.p-world.co.jp/{pref_dir}/ssc/ssc{id}.htm

Encoding: EUC-JP (x-euc-jp)

Usage:
    python scripts/fetch_store_data_pworld.py                  # 全都道府県
    python scripts/fetch_store_data_pworld.py --pref 東京都    # 1都道府県
    python scripts/fetch_store_data_pworld.py --pref 東京都,大阪府
    python scripts/fetch_store_data_pworld.py --limit 5        # テスト用
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MACHINES_JSON = Path(__file__).parent.parent / "public/store_machines.json"
BASE_URL = "https://www.p-world.co.jp"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.p-world.co.jp/",
}

# 都道府県 → P-World ディレクトリ名
PREF_DIR: dict[str, str] = {
    "北海道": "hokkaido",
    "青森県": "aomori",   "岩手県": "iwate",    "宮城県": "miyagi",
    "秋田県": "akita",    "山形県": "yamagata",  "福島県": "fukushima",
    "茨城県": "ibaraki",  "栃木県": "tochigi",   "群馬県": "gunma",
    "埼玉県": "saitama",  "千葉県": "chiba",     "東京都": "tokyo",
    "神奈川県": "kanagawa",
    "新潟県": "niigata",  "富山県": "toyama",    "石川県": "ishikawa",
    "福井県": "fukui",    "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu",     "静岡県": "shizuoka",  "愛知県": "aichi",
    "三重県": "mie",      "滋賀県": "shiga",     "京都府": "kyoto",
    "大阪府": "osaka",    "兵庫県": "hyogo",     "奈良県": "nara",
    "和歌山県": "wakayama",
    "鳥取県": "tottori",  "島根県": "shimane",   "岡山県": "okayama",
    "広島県": "hiroshima","山口県": "yamaguchi",
    "徳島県": "tokushima","香川県": "kagawa",    "愛媛県": "ehime",
    "高知県": "kochi",
    "福岡県": "fukuoka",  "佐賀県": "saga",      "長崎県": "nagasaki",
    "熊本県": "kumamoto", "大分県": "oita",      "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima","沖縄県": "okinawa",
}


def fetch(url: str, encoding: str = "euc-jp", retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                return resp.read().decode(encoding, errors="replace")
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            print(f"  ⚠️  {url}: {e}", file=sys.stderr)
    return ""


# ---------------------------------------------------------------------------
# 都道府県別 店舗リスト取得
# ---------------------------------------------------------------------------
def get_store_list(pref_dir: str) -> list[dict]:
    """
    kensaku.cgi から全店舗の (slug, ssc_id, url) リストを取得。
    ページネーションを追跡して全店舗を収集。

    P-Worldのリスト構造:
      <a class="hallList-item-name-link" href="/tokyo/arrow-ikegami.htm">店舗名</a>
      <a class="hallList-item-ssc ..." href="/tokyo/ssc/ssc017773.htm">...
    各 hallList-item div 内でペアになっている。
    """
    stores: list[dict] = []
    seen_slugs: set[str] = set()
    page = 1

    # 各hallList-itemブロック内でslug+sscペアを取得するパターン
    item_pattern = re.compile(
        rf'class="hallList-item-name-link" href="(/{re.escape(pref_dir)}/([a-z0-9\-]+)\.htm)"'
        rf'.*?(?:class="hallList-item-ssc[^"]*" href="/{re.escape(pref_dir)}/ssc/ssc(\d+)\.htm")?',
        re.DOTALL
    )

    while True:
        url = f"{BASE_URL}/_machine/kensaku.cgi?is_new_ver=1&dir={pref_dir}&page={page}"
        html = fetch(url)
        if not html:
            break

        new_count = 0

        # 位置ベースで slug と SSC IDをペアで取得
        # <a class="hallList-item-name-link" href="/{pref}/slug.htm">
        # その直後に <a class="hallList-item-ssc ..." href="/{pref}/ssc/sscXXXXXX.htm">
        name_link_pat = re.compile(
            rf'class="hallList-item-name-link" href="/{re.escape(pref_dir)}/([a-z0-9\-]+)\.htm"'
        )
        ssc_link_pat = re.compile(
            rf'class="hallList-item-ssc[^"]*" href="/{re.escape(pref_dir)}/ssc/ssc(\d+)\.htm"'
        )
        name_matches = list(name_link_pat.finditer(html))
        for i, m in enumerate(name_matches):
            slug = m.group(1)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # 次のname-linkまでの範囲でSSCを探す
            search_end = name_matches[i + 1].start() if i + 1 < len(name_matches) else m.end() + 1000
            ssc_m = ssc_link_pat.search(html, m.end(), search_end)
            ssc_id = ssc_m.group(1) if ssc_m else None

            stores.append({
                "slug": slug,
                "ssc_id": ssc_id,
                "url": f"{BASE_URL}/{pref_dir}/{slug}.htm",
            })
            new_count += 1

        if new_count == 0:
            break

        # 次ページ確認: page={page+1} リンクがあるか
        if f"page={page + 1}" not in html:
            break

        page += 1
        time.sleep(0.5)
        if page > 100:
            break

    return stores


# ---------------------------------------------------------------------------
# 店舗詳細ページ解析
# ---------------------------------------------------------------------------
def parse_store_page(html: str, store_url: str, pref_dir: str, ssc_id: str | None) -> dict:
    result: dict = {}

    # ── 店舗名 ──
    title_m = re.search(r'<TITLE>([^<]+)</TITLE>', html, re.IGNORECASE)
    if title_m:
        result["store_name_pworld"] = title_m.group(1).strip()

    # ── 台数（メタdescriptionから最も確実に取得）──
    desc_m = re.search(r'<meta name="description" content="([^"]+)"', html, re.IGNORECASE)
    if desc_m:
        desc = desc_m.group(1)
        p_m = re.search(r'パチンコ(\d+)台', desc)
        s_m = re.search(r'スロット(\d+)台', desc)
        if p_m:
            result["pachinko_total"] = int(p_m.group(1))
        if s_m:
            result["slot_total"] = int(s_m.group(1))

    # ── 台数（本文からのフォールバック）──
    if not result.get("pachinko_total"):
        p_m2 = re.search(r'パチンコ台数[^\d]*(\d+)', html)
        if p_m2:
            result["pachinko_total"] = int(p_m2.group(1))
    if not result.get("slot_total"):
        s_m2 = re.search(r'スロット台数[^\d]*(\d+)', html)
        if s_m2:
            result["slot_total"] = int(s_m2.group(1))

    # レート別台数
    pachinko_rates = []
    slot_rates = []
    for m in re.finditer(r'([\d.]+円[^パスス]{0,4}パチンコ|パチンコ[\d.]+円)[^\d]*(\d+)\s*台', html):
        pachinko_rates.append({"rate": m.group(1).strip(), "count": int(m.group(2))})
    for m in re.finditer(r'([\d.]+円[^パスス]{0,4}スロット|スロット[\d.]+円|[\d]+枚交換)[^\d]*(\d+)\s*台', html):
        slot_rates.append({"rate": m.group(1).strip(), "count": int(m.group(2))})
    if pachinko_rates:
        result["pachinko"] = pachinko_rates
    if slot_rates:
        result["slot"] = slot_rates

    # ── 営業時間 ──
    # P-Worldの基本情報テーブル: 営業時間 セルの次TD
    hours_m = re.search(
        r'営業時間</font></td><td[^>]*>\s*([0-9０-９]{1,2}[：:][0-9０-９]{2}[^\n<]{0,20})',
        html, re.DOTALL
    )
    if not hours_m:
        hours_m = re.search(
            r'営業時間[^<]*</[^>]+>\s*(?:</[^>]+>\s*)?<[Tt][Dd][^>]*>\s*([0-9０-９]{1,2}[：:][0-9０-９]{2}[^\n<]{0,20})',
            html, re.DOTALL
        )
    if hours_m:
        result["hours"] = re.sub(r'\s+', ' ', hours_m.group(1).strip())[:60]

    # ── 住所 ──
    # P-World: js-hall-map-link アンカーに住所テキストが入っている
    addr_m = re.search(r'id="js-hall-map-link"[^>]*>([^<]{5,80})</a>', html, re.DOTALL)
    if addr_m:
        result["address"] = re.sub(r'\s+', ' ', addr_m.group(1).strip())[:100]
    else:
        # フォールバック: 住所セルの〒付き
        addr_m2 = re.search(r'住\s*所[^<]*</[^>]+>\s*(?:<[^>]+>\s*)*(〒\d{3}-\d{4}[^<]{5,80})', html, re.DOTALL)
        if addr_m2:
            result["address"] = re.sub(r'\s+', ' ', addr_m2.group(1).strip())[:100]

    # ── 店舗写真 ──
    base_url = store_url.rsplit('/', 1)[0]
    # P-Worldの写真は img/XXXXXX_01.jpg 形式
    photo_m = re.search(r'(?:src|SRC)="img/(\d{6})_0[13]\.jpg', html)
    if photo_m:
        store_num = photo_m.group(1)
        result["photo_url"] = f"{base_url}/img/{store_num}_01.jpg"

    # ── フロアマップURL ──
    if ssc_id:
        result["floor_map_url"] = f"{BASE_URL}/{pref_dir}/ssc/ssc{ssc_id.zfill(6)}.htm"
    else:
        # SSCリンクを本文から探す
        ssc_m = re.search(rf'href="(/{re.escape(pref_dir)}/ssc/ssc\d+\.htm)"', html)
        if ssc_m:
            result["floor_map_url"] = f"{BASE_URL}{ssc_m.group(1)}"

    # ── X (Twitter) URL ──
    x_m = re.search(r'href=["\']?(https?://(?:twitter|x)\.com/([A-Za-z0-9_]+))', html)
    if x_m:
        username = x_m.group(2)
        # 除外ワード（公式ではないアカウント）
        if username.lower() not in {"share", "intent", "hashtag", "search", "home", "i", "compose"}:
            result["x_url"] = f"https://x.com/{username}"

    # ── 公式HP URL ──
    skip_domains = {"p-world.co.jp", "idn.p-world.co.jp", "line.me", "twitter.com", "x.com",
                    "facebook.com", "instagram.com", "youtube.com"}
    for m in re.finditer(r'href=["\']?(https?://([^"\'>\s/]+))', html):
        link_url = m.group(1)
        domain = m.group(2).lower()
        if any(d in domain for d in skip_domains):
            continue
        if not domain.endswith(('.jp', '.com', '.net', '.org', '.co.jp')):
            continue
        # パチンコ店の公式サイトっぽいリンクを優先
        result["hp_url"] = link_url
        break

    # ── LINE URL ──
    line_m = re.search(r'href=["\']?(https://line\.me/[^"\'>\s]+)', html)
    if line_m:
        result["line_url"] = line_m.group(1)

    # ── 設置機種（新台リスト）──
    # P-World の新台情報は JavaScript で動的に生成されることが多いため
    # HTMLに残っているものだけ抽出
    machine_names: list[str] = []
    # 機種名テーブル（旧形式）
    for m in re.finditer(
        r'<(?:td|li|span)[^>]*>([^\s<][^<]{2,30}(?:機|盤|マシン|バスター|ゾンビ|北斗|牙狼|吉宗|バジリスク|ヴァル|チバリヨ|ジャグラー)[^<]{0,20})</',
        html
    ):
        name = m.group(1).strip()
        if len(name) >= 3:
            machine_names.append(name)

    # 重複除去
    seen: set[str] = set()
    machines: list[dict] = []
    for name in machine_names:
        if name not in seen:
            seen.add(name)
            machines.append({"name": name})
    if machines:
        result["new_machines"] = machines[:20]

    return result


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pref",  help="都道府県（カンマ区切り） 例: 東京都,大阪府")
    parser.add_argument("--limit", type=int, help="最大店舗数（テスト用）")
    args = parser.parse_args()

    # 既存データをロード
    machines: dict = {}
    if MACHINES_JSON.exists():
        with open(MACHINES_JSON, encoding="utf-8") as f:
            machines = json.load(f)

    prefs = [p.strip() for p in args.pref.split(",") if p.strip()] if args.pref else list(PREF_DIR.keys())
    prefs = [p for p in prefs if p in PREF_DIR]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_fetched = 0
    processed = 0

    for pref in prefs:
        pref_dir = PREF_DIR[pref]
        print(f"\n🗾 {pref} ({pref_dir}) — 店舗リスト取得中...")

        stores = get_store_list(pref_dir)
        print(f"  → {len(stores)}店舗発見")

        for store_info in stores:
            slug    = store_info["slug"]
            ssc_id  = store_info["ssc_id"]
            url     = store_info["url"]

            html = fetch(url, encoding="euc-jp")
            if not html:
                time.sleep(0.4)
                continue

            data = parse_store_page(html, url, pref_dir, ssc_id)
            if not data:
                processed += 1
                continue

            # 店舗名を取得（P-World名 or タイトル）
            store_name = data.pop("store_name_pworld", slug)
            data["updated_at"]  = now_iso
            data["pref"]        = pref
            data["pworld_url"]  = url
            data["pworld_slug"] = slug

            machines[store_name] = data

            p_total  = data.get("pachinko_total", 0)
            s_total  = data.get("slot_total", 0)
            has_floor = "✓" if data.get("floor_map_url") else "✗"
            has_photo = "✓" if data.get("photo_url") else "✗"
            hours_str = data.get("hours", "")[:20]
            if p_total or s_total:
                print(f"  ✓ {store_name}  パチ{p_total}/スロ{s_total}台  {hours_str}  フロア{has_floor}  写真{has_photo}")
            total_fetched += 1

            processed += 1
            if args.limit and processed >= args.limit:
                break
            time.sleep(0.4)

        # 都道府県ごとに中間保存
        with open(MACHINES_JSON, "w", encoding="utf-8") as f:
            json.dump(machines, f, ensure_ascii=False, indent=2)
        print(f"  💾 中間保存: {len(machines)}店舗")

        if args.limit and processed >= args.limit:
            break

    print(f"\n✅ P-World完了: {total_fetched}店舗 / 全体{len(machines)}店舗")


if __name__ == "__main__":
    main()
