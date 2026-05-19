#!/usr/bin/env python3
"""
DMM p-town から各店舗の台数・機種・営業時間を収集して
public/store_machines.json を生成する。

生成形式:
{
  "楽園蒲田店": {
    "hours": "10:00～22:40",
    "entry_rule": "抽選",
    "pachinko": [{"rate": "4円", "count": 173}, {"rate": "1円", "count": 63}],
    "slot": [{"rate": "20円", "count": 148}],
    "pachinko_total": 236,
    "slot_total": 148,
    "new_machines": [
      {"name": "スマスロバイオRE:3", "type": "slot"},
      ...
    ],
    "updated_at": "2026-05-20T01:00:00"
  },
  ...
}

Usage:
    python scripts/fetch_machine_data.py              # 全店舗（areas.json 収録分）
    python scripts/fetch_machine_data.py --pref 東京都 # 1都道府県のみ
    python scripts/fetch_machine_data.py --limit 100   # 最大N件
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

    # machine-type-name と machine-rate の対応を取る
    # 複数の machine-rate-area ブロックを順に処理
    blocks = re.findall(
        r'<div class="machine-rate-area">(.*?)(?=<div class="machine-rate-area">|</td>)',
        html, re.DOTALL
    )
    if not blocks:
        # フォールバック: 単一ブロック
        m = re.search(r'遊技金額・台数.*?<td class="td">(.*?)</td>', html, re.DOTALL)
        if m:
            blocks = [m.group(1)]

    for block in blocks:
        ptype_m = re.search(r'machine-type-name (\w+)">\s*<p>([^<]+)</p>', block)
        if not ptype_m:
            continue
        ptype_key = ptype_m.group(1)  # "pachi" or "slot"
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pref", help="特定の都道府県のみ (例: 東京都)。カンマ区切りで複数可")
    parser.add_argument("--limit", type=int, help="処理する最大店舗数")
    args = parser.parse_args()

    with open(AREAS_JSON, encoding="utf-8") as f:
        areas: dict = json.load(f)

    # 既存データをロード
    machines: dict = {}
    if MACHINES_JSON.exists():
        with open(MACHINES_JSON, encoding="utf-8") as f:
            machines = json.load(f)

    if args.pref:
        # カンマ区切りまたは単一
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

    print(f"\n🎉 完了: store_machines.json に {total} 件の店舗情報を保存 → {MACHINES_JSON}")


if __name__ == "__main__":
    main()
