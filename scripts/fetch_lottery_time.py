#!/usr/bin/env python3
"""
stores.json の各店舗の整列時間・抽選時間を収集するスクリプト。

収集元:
  1. 店舗公式HP (hp_url) → 整列/抽選時間のパターンマッチ
  2. P-Town (DMM) の入場ルール詳細テキスト

Usage:
    python scripts/fetch_lottery_time.py              # 全店舗を対象
    python scripts/fetch_lottery_time.py --limit 50   # テスト用
    python scripts/fetch_lottery_time.py --pref 東京都

Output: public/stores.json の lottery_time フィールドを更新
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

STORES_JSON = Path(__file__).parent.parent / "public/stores.json"
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 整列/抽選時間を抽出するパターン
TIME_PATTERNS = [
    # 「整列：9:00」「整列開始 9:00」「整列時間 9時」
    r'整列(?:開始|時間)?[：:\s]*([0-9０-９]{1,2}[：:][0-9０-９]{2})',
    r'整列(?:開始|時間)?[：:\s]*([0-9０-９]{1,2})時',
    # 「抽選：9:00」「抽選開始 9時30分」
    r'抽選(?:開始|時間|受付)?[：:\s]*([0-9０-９]{1,2}[：:][0-9０-９]{2})',
    r'抽選(?:開始|時間|受付)?[：:\s]*([0-9０-９]{1,2})時(?:([0-9０-９]{2})分)?',
    # 「受付開始 8:30」
    r'受付(?:開始)?[：:\s]*([0-9０-９]{1,2}[：:][0-9０-９]{2})',
    # 「並び開始 8時」
    r'並び(?:開始)?[：:\s]*([0-9０-９]{1,2}[：:][0-9０-９]{2})',
    r'並び(?:開始)?[：:\s]*([0-9０-９]{1,2})時',
    # 「8:30から整列」「9時から抽選」
    r'([0-9０-９]{1,2}[：:][0-9０-９]{2})(?:\s*から)?\s*(?:整列|抽選)',
    r'([0-9０-９]{1,2})時(?:\s*から)?\s*(?:整列|抽選)',
]

def fetch_html(url: str, encoding: str = "utf-8", quiet: bool = False) -> str:
    """URLのHTMLを取得。複数エンコーディングを試みる。"""
    for enc in [encoding, "utf-8", "shift_jis", "euc-jp"]:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                raw = resp.read()
                return raw.decode(enc, errors="replace")
        except Exception as e:
            if enc == "euc-jp" and not quiet:  # 最後の試み
                print(f"  ⚠️  {url}: {e}", file=sys.stderr)
            continue
    return ""

def normalize_time(time_str: str) -> str:
    """時刻文字列を「HH:MM」形式に正規化。"""
    # 全角→半角変換
    t = time_str.translate(str.maketrans('０１２３４５６７８９：', '0123456789:'))
    # 「9」→「09:00」、「9:30」はそのまま
    if ':' not in t:
        t = f"{int(t):02d}:00"
    else:
        parts = t.split(':')
        t = f"{int(parts[0]):02d}:{parts[1]}"
    return t

def extract_lottery_time(html: str) -> str | None:
    """HTMLから整列/抽選時刻を抽出。"""
    # タグを除去してテキスト化
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    for pattern in TIME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            time_val = m.group(1)
            # 分が別グループに入っているパターンを処理
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                time_val = f"{m.group(1)}:{m.group(2)}"
            try:
                return normalize_time(time_val)
            except (ValueError, IndexError):
                continue
    return None

def get_lottery_from_hp(hp_url: str) -> str | None:
    """公式HPから整列/抽選時間を取得。"""
    if not hp_url:
        return None
    html = fetch_html(hp_url)
    if not html:
        return None

    result = extract_lottery_time(html)
    if result:
        return result

    # トップページにない場合はアクセス・店舗情報ページを試みる（静かに）
    sub_paths = ["/access", "/info", "/shop", "/about", "/guide"]
    base = hp_url.rstrip("/")
    for path in sub_paths:
        html2 = fetch_html(base + path, quiet=True)
        if html2:
            result = extract_lottery_time(html2)
            if result:
                return result
        time.sleep(0.3)

    return None

def get_lottery_from_ptown(store_name: str, machines_data: dict) -> str | None:
    """
    store_machines.json の entry_rule テキストから整列時間を試みる。
    entry_rule が「抽選 8:30~」のような形式の場合に対応。
    """
    info = machines_data.get(store_name)
    if not info:
        return None
    entry_rule = info.get("entry_rule", "")
    if not entry_rule:
        return None
    result = extract_lottery_time(entry_rule)
    return result

def main():
    parser = argparse.ArgumentParser(description="整列/抽選時間を収集してstores.jsonを更新")
    parser.add_argument("--pref", help="都道府県（カンマ区切り）例: 東京都,大阪府")
    parser.add_argument("--limit", type=int, help="処理する最大店舗数（テスト用）")
    parser.add_argument("--dry-run", action="store_true", help="更新を行わず結果を表示のみ")
    args = parser.parse_args()

    # データ読み込み
    with open(STORES_JSON, encoding="utf-8") as f:
        stores = json.load(f)

    machines_data: dict = {}
    if MACHINES_JSON.exists():
        with open(MACHINES_JSON, encoding="utf-8") as f:
            machines_data = json.load(f)

    # フィルタリング
    target_stores = stores
    if args.pref:
        prefs = [p.strip() for p in args.pref.split(",")]
        target_stores = [s for s in stores if s.get("pref") in prefs]

    # HP URLを持つ店舗を優先
    hp_stores = [s for s in target_stores if s.get("hp_url") and not s.get("lottery_time")]
    other_stores = [s for s in target_stores if not s.get("hp_url") and not s.get("lottery_time")]

    print(f"対象: {len(target_stores)}店舗")
    print(f"  HP URL あり: {len(hp_stores)}店舗")
    print(f"  HP URL なし: {len(other_stores)}店舗")

    updated = 0
    processed = 0

    # store_machines.json から取得（高速・優先）
    print("\n[1/2] store_machines.json の entry_rule からチェック...")
    for store in target_stores:
        name = store.get("name", "")
        if store.get("lottery_time"):
            continue
        lottery = get_lottery_from_ptown(name, machines_data)
        if lottery:
            print(f"  ✓ {name}: {lottery} (entry_rule)")
            store["lottery_time"] = lottery
            updated += 1

    # 公式HP から取得
    print(f"\n[2/2] 公式HP スクレイピング ({len(hp_stores)}店舗)...")
    count = 0
    for store in hp_stores:
        if store.get("lottery_time"):
            continue
        if args.limit and processed >= args.limit:
            break

        name = store.get("name", "")
        hp_url = store.get("hp_url", "")
        print(f"  [{count+1}/{len(hp_stores)}] {name} ({hp_url})")

        lottery = get_lottery_from_hp(hp_url)
        if lottery:
            print(f"    → 取得: {lottery}")
            store["lottery_time"] = lottery
            updated += 1
        else:
            print(f"    → 見つからず")

        count += 1
        processed += 1
        time.sleep(1.0)

    print(f"\n{'='*60}")
    print(f"✅ 完了: {updated}店舗の整列/抽選時間を取得")

    if not args.dry_run:
        with open(STORES_JSON, "w", encoding="utf-8") as f:
            json.dump(stores, f, ensure_ascii=False, indent=2)
        print(f"✅ {STORES_JSON} を更新しました")
    else:
        print("(dry-run: ファイルは更新していません)")

if __name__ == "__main__":
    main()
