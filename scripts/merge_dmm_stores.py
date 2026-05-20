#!/usr/bin/env python3
"""
areas.json（DMM収集データ）を stores.json にマージするスクリプト。

- stores.json に既存の店舗（名前一致）は更新せず city フィールドのみ補完
- DMM にしか存在しない店舗を新規追加（event_count=0, DMM関連URL は一切含めない）

Usage:
    python scripts/merge_dmm_stores.py          # dryrun（変更数だけ表示）
    python scripts/merge_dmm_stores.py --apply  # 実際に stores.json を更新
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# 店舗名ではなくイベント・演者情報として除外するパターン
_EVENT_PATTERNS = [re.compile(p) for p in [
    r'来店', r'取材', r'収録', r'実[戦践]', r'ライター', r'タレント',
    r'編集部員', r'潜入', r'ぱちタウン', r'スロパチ', r'ジャンバリ',
    r'必勝本', r'きむちゃんねる', r'神の子', r'PS調査員', r'SARUPR',
    r'^[＜＞]', r'^\\\\', r'^※', r'^・', r'^[\|｜]',
]]

def is_valid_store_name(name: str) -> bool:
    return bool(name) and not any(p.search(name) for p in _EVENT_PATTERNS)

STORES_JSON = Path(__file__).parent.parent / "public/stores.json"
AREAS_JSON  = Path(__file__).parent.parent / "public/areas.json"

PREF_TO_AREA: dict[str, str] = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東",
    "埼玉県": "関東", "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部",
    "山梨県": "中部", "長野県": "中部", "岐阜県": "中部", "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿",
    "大阪府": "近畿", "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国・四国", "島根県": "中国・四国", "岡山県": "中国・四国",
    "広島県": "中国・四国", "山口県": "中国・四国",
    "徳島県": "中国・四国", "香川県": "中国・四国", "愛媛県": "中国・四国", "高知県": "中国・四国",
    "福岡県": "九州・沖縄", "佐賀県": "九州・沖縄", "長崎県": "九州・沖縄",
    "熊本県": "九州・沖縄", "大分県": "九州・沖縄", "宮崎県": "九州・沖縄",
    "鹿児島県": "九州・沖縄", "沖縄県": "九州・沖縄",
}

def dmm_id_to_store_id(dmm_id: str) -> str:
    """DMM ID から stores.json と衝突しない一意な ID を生成"""
    return hashlib.md5(f"dmm:{dmm_id}".encode()).hexdigest()[:10]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="実際に stores.json を更新する")
    args = parser.parse_args()

    with open(STORES_JSON, encoding="utf-8") as f:
        stores: list[dict] = json.load(f)

    with open(AREAS_JSON, encoding="utf-8") as f:
        areas: dict = json.load(f)

    # 既存store のインデックス
    by_name: dict[str, dict] = {s["name"]: s for s in stores if s.get("name")}
    existing_ids: set[str] = {s["id"] for s in stores}

    added = 0
    city_updated = 0
    new_stores: list[dict] = []

    for pref, cities in areas.items():
        area_label = PREF_TO_AREA.get(pref, "")
        for city, dmm_list in cities.items():
            for ds in dmm_list:
                name    = ds["name"]
                dmm_id  = ds["dmm_id"]

                if not is_valid_store_name(name):
                    continue

                if name in by_name:
                    # 既存店舗に city と dmm_id を補完
                    existing = by_name[name]
                    if not existing.get("city"):
                        existing["city"] = city
                        city_updated += 1
                    if not existing.get("dmm_id"):
                        existing["dmm_id"] = dmm_id
                    continue

                # 新規追加
                store_id = dmm_id_to_store_id(dmm_id)
                # ID 衝突がある場合は suffix を追加
                while store_id in existing_ids:
                    store_id = dmm_id_to_store_id(dmm_id + "_")
                existing_ids.add(store_id)

                new_store = {
                    "id":           store_id,
                    "name":         name,
                    "pref":         pref,
                    "area":         area_label,
                    "city":         city,
                    "dmm_id":       dmm_id,
                    "event_count":  0,
                    "floor_map_url": None,
                    "is_low_rental": False,
                    "lottery_time": None,
                    "hp_url":       None,
                    "x_url":        None,
                    "address":      None,
                    "map_url":      None,
                }
                new_stores.append(new_store)
                by_name[name] = new_store
                added += 1

    print(f"既存店舗への city 補完: {city_updated} 件")
    print(f"新規追加 (DMM only): {added} 件")
    print(f"マージ後の総店舗数: {len(stores) + added} 件")

    if not args.apply:
        print("\n--apply を付けて実行すると stores.json を更新します")
        sys.exit(0)

    merged = stores + new_stores
    # pref あり・event_count 降順でソート（見た目を整える）
    merged.sort(key=lambda s: (-s.get("event_count", 0), s.get("pref", ""), s.get("city", ""), s.get("name", "")))

    with open(STORES_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n✅ stores.json を更新しました（{len(merged)} 件）")


if __name__ == "__main__":
    main()
