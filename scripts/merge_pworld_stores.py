#!/usr/bin/env python3
"""
store_machines.json（P-World）の店舗で stores.json にないものを追加するスクリプト。
IDは pw_{pworld_slug} 形式で生成。

Usage:
    python scripts/merge_pworld_stores.py
"""
import hashlib
import json
import re
from pathlib import Path

STORES_JSON  = Path(__file__).parent.parent / "public/stores.json"
MACHINES_JSON = Path(__file__).parent.parent / "public/store_machines.json"

AREA_MAP = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "東京都": "関東", "神奈川県": "関東", "埼玉県": "関東", "千葉県": "関東",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東",
    "愛知県": "東海", "静岡県": "東海", "岐阜県": "東海", "三重県": "東海",
    "新潟県": "北陸", "長野県": "北陸", "石川県": "北陸", "富山県": "北陸",
    "福井県": "北陸", "山梨県": "北陸",
    "大阪府": "近畿", "兵庫県": "近畿", "京都府": "近畿", "奈良県": "近畿",
    "滋賀県": "近畿", "和歌山県": "近畿",
    "広島県": "中国", "岡山県": "中国", "山口県": "中国", "鳥取県": "中国", "島根県": "中国",
    "愛媛県": "四国", "香川県": "四国", "徳島県": "四国", "高知県": "四国",
    "福岡県": "九州", "熊本県": "九州", "鹿児島県": "九州", "宮崎県": "九州",
    "大分県": "九州", "長崎県": "九州", "佐賀県": "九州", "沖縄県": "九州",
}


def main():
    stores = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    sm = json.loads(MACHINES_JSON.read_text(encoding="utf-8"))

    store_names = {s["name"] for s in stores}
    existing_ids = {s["id"] for s in stores}

    added = 0
    for name, data in sm.items():
        if name in store_names:
            continue
        if not data.get("pworld_url"):
            continue

        # pworld_slug from URL
        url = data["pworld_url"]
        slug_m = re.search(r"/([^/]+?)(?:\.htm)?$", url)
        slug = slug_m.group(1) if slug_m else None
        if not slug:
            continue

        store_id = f"pw_{slug}"
        if store_id in existing_ids:
            store_id = f"pw_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        existing_ids.add(store_id)
        store_names.add(name)

        pref = data.get("pref", "")
        area = AREA_MAP.get(pref, "全国")
        address = data.get("address") or None

        stores.append({
            "id": store_id,
            "name": name,
            "pref": pref,
            "area": area,
            "event_count": 0,
            "hp_url": None,
            "x_url": None,
            "address": address,
            "map_url": (
                f"https://www.google.co.jp/maps/search/{address.replace(' ', '+')}"
                if address else None
            ),
            "floor_map_url": None,
            "is_low_rental": False,
            "lottery_time": None,
            "con_pass_url": None,
        })
        added += 1

    print(f"追加: {added}店舗 / 合計: {len(stores)}店舗")
    if added > 0:
        STORES_JSON.write_text(
            json.dumps(stores, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"✅ {STORES_JSON} を更新")


if __name__ == "__main__":
    main()
