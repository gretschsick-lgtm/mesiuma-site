#!/usr/bin/env python3
"""
DMM p-town から全国の市区町村別店舗データを収集して
public/areas.json を生成するスクリプト。

生成形式:
{
  "東京都": {
    "大田区": [{"name": "楽園蒲田店", "dmm_id": "262"}, ...],
    "世田谷区": [...],
    ...
  },
  ...
}

Playwrightは不要。DMM の市区町村ページは静的HTML。

Usage:
    python scripts/fetch_city_data.py
    python scripts/fetch_city_data.py --pref 東京都   # 1都道府県のみ
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

AREAS_JSON = Path(__file__).parent.parent / "public/areas.json"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  {url}: {e}", file=sys.stderr)
        return ""


def get_city_list(pref_slug: str) -> list[tuple[str, str]]:
    """都道府県ページから [(市区町村名, area_code), ...] を返す"""
    html = fetch(f"https://p-town.dmm.com/shops/{pref_slug}")
    if not html:
        return []
    cities = []
    for m in re.finditer(
        r'href=["\'](?:https://p-town\.dmm\.com)?(/shops/[^/]+/area/(\d+))["\'][^>]*>([^<]{1,30})</a',
        html
    ):
        code = m.group(2)
        name = re.sub(r'\s+', '', m.group(3))
        name = re.sub(r'（\d+）$', '', name)  # 末尾の件数を除去
        if name and code and name not in ("", "トップ"):
            cities.append((name, code))
    return cities


def get_stores_in_city(pref_slug: str, area_code: str) -> list[dict]:
    """市区町村ページから [{"name": ..., "dmm_id": ...}, ...] を返す"""
    html = fetch(f"https://p-town.dmm.com/shops/{pref_slug}/area/{area_code}")
    if not html:
        return []

    seen: set[str] = set()
    stores = []

    # パターン1: /shops/{pref}/{id} のリンクと隣接テキスト
    for m in re.finditer(
        r'href=["\'](?:https://p-town\.dmm\.com)?/shops/[^/]+/(\d+)["\']',
        html
    ):
        dmm_id = m.group(1)
        if dmm_id in seen:
            continue
        # リンクの直後のテキストを取る
        start = m.end()
        chunk = html[start:start + 200]
        name_m = re.search(r'>([^<]{2,40}?)</(?:a|span|div|p|h\d)', chunk)
        if name_m:
            name = re.sub(r'[\n\r\t]+', ' ', name_m.group(1)).strip()
            name = re.sub(r'\s+', '', name)
            if len(name) >= 2 and not name.startswith("http"):
                stores.append({"name": name, "dmm_id": dmm_id})
                seen.add(dmm_id)

    # パターン2: 別の形式（フォールバック）
    if not stores:
        for m in re.finditer(
            r'/shops/[^/]+/(\d+)["\']\s*[^>]*>([^<]{2,40})</a',
            html
        ):
            dmm_id, name = m.group(1), m.group(2).strip()
            name = re.sub(r'[\n\r\t]+', '', name).strip()
            if dmm_id not in seen and len(name) >= 2:
                stores.append({"name": name, "dmm_id": dmm_id})
                seen.add(dmm_id)

    return stores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pref", help="特定の都道府県のみ処理 (例: 東京都)")
    args = parser.parse_args()

    # 既存データをロード（追記モード）
    areas: dict[str, dict[str, list[dict]]] = {}
    if AREAS_JSON.exists():
        with open(AREAS_JSON, encoding="utf-8") as f:
            areas = json.load(f)

    prefs = [args.pref] if args.pref else list(PREF_DMM.keys())
    prefs = [p for p in prefs if p in PREF_DMM]

    total_stores = 0

    for pref in prefs:
        slug = PREF_DMM[pref]
        print(f"\n🗾 {pref}...")

        cities = get_city_list(slug)
        if not cities:
            print(f"   ⚠️  市区町村リスト取得失敗")
            continue
        print(f"   市区町村: {len(cities)}件")

        pref_data: dict[str, list[dict]] = areas.get(pref, {})
        pref_stores = 0

        for city_name, area_code in cities:
            stores = get_stores_in_city(slug, area_code)
            if stores:
                pref_data[city_name] = stores
                pref_stores += len(stores)
                print(f"   {city_name}: {len(stores)}店")
            time.sleep(0.4)

        areas[pref] = pref_data
        total_stores += pref_stores
        print(f"   → {pref_stores}店舗 収録")

        # 都道府県ごとに中間保存
        with open(AREAS_JSON, "w", encoding="utf-8") as f:
            json.dump(areas, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 完了: areas.json に {total_stores}店舗 保存 → {AREAS_JSON}")


if __name__ == "__main__":
    main()
