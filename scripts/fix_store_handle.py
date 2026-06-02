"""
store_handle 空欄補完スクリプト

keyword-search モードで収集されたエントリは store_handle / store_x_url /
source_account_type が未設定のまま保存されている。
本スクリプトは x_url → handle 逆引き → store_handles.json 照合で一括補完する。

処理:
  1. public/complete_20??-??-??.json + complete_info.json を全て読み込む
  2. store_handle 空欄エントリを x_url から handle 抽出 → store_handles.json 照合
  3. store_handle / store_x_url / manager_x_url / source_account_type を補完
  4. 各ファイルを上書き保存
  5. update_ranking() でランキング再生成

使用例:
    python scripts/fix_store_handle.py
    python scripts/fix_store_handle.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

COMPLETE_JSON = ROOT / "public" / "complete_info.json"
STORE_HANDLES_JSON = ROOT / "public" / "store_handles.json"


def extract_handle(url: str) -> str:
    m = re.search(r"x\.com/([^/]+)/status", url or "")
    return m.group(1).lower() if m else ""


def fix_entry(e: dict, handle_info: dict[str, dict]) -> bool:
    """store_handle が空欄のエントリを補完する。補完した場合 True を返す。"""
    if e.get("store_handle"):
        return False
    url = e.get("x_url", "")
    if not url:
        return False
    handle = extract_handle(url)
    if not handle:
        return False

    e["store_handle"] = handle

    info = handle_info.get(handle)
    if info:
        htype = info.get("type", "store")
        x_url = info.get("x_url", f"https://x.com/{handle}")
        if htype == "manager":
            e["source_account_type"] = e.get("source_account_type") or "store_manager"
            e["manager_x_url"] = e.get("manager_x_url") or x_url
        else:
            e["source_account_type"] = e.get("source_account_type") or "store_official"
            e["store_x_url"] = e.get("store_x_url") or x_url
    else:
        e["source_account_type"] = e.get("source_account_type") or "unknown"

    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="ファイルを更新しない")
    args = parser.parse_args()

    # store_handles 読み込み
    handle_info: dict[str, dict] = {}
    if STORE_HANDLES_JSON.exists():
        sh = json.loads(STORE_HANDLES_JSON.read_text(encoding="utf-8"))
        for h, v in sh.items():
            if isinstance(v, dict):
                handle_info[h.lower()] = v
    print(f"📋 store_handles: {len(handle_info)} 件")

    # 対象ファイル一覧
    daily_files = sorted(ROOT.glob("public/complete_20??-??-??.json"))
    target_files = daily_files + [COMPLETE_JSON]
    print(f"📂 対象ファイル: {len(target_files)} 件 (daily={len(daily_files)}, main=1)")

    total_fixed = 0
    total_entries = 0
    stats_by_file: list[tuple[str, int, int, int]] = []  # name, total, fixed, still_empty

    for fpath in target_files:
        if not fpath.exists():
            continue
        entries: list[dict] = json.loads(fpath.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            continue

        before_empty = sum(1 for e in entries if not e.get("store_handle"))
        fixed_this = 0
        for e in entries:
            if fix_entry(e, handle_info):
                fixed_this += 1

        after_empty = sum(1 for e in entries if not e.get("store_handle"))

        stats_by_file.append((fpath.name, len(entries), fixed_this, after_empty))
        total_fixed += fixed_this
        total_entries += len(entries)

        if fixed_this > 0 and not args.dry_run:
            fpath.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # サマリ
    print("\n=== 補完結果 (ファイル別) ===")
    for fname, total, fixed, still in stats_by_file:
        if fixed > 0 or still > 0:
            print(f"  {fname:40s}  total={total:4d}  fixed={fixed:4d}  still_empty={still:4d}")

    print(f"\n補完合計: {total_fixed}/{total_entries} 件")
    if args.dry_run:
        print("dry-run: ファイルは更新しません")
        return

    # ランキング再生成
    print("\n📊 ランキング再生成...")
    from fetch_complete_info import update_ranking
    update_ranking()
    print("✅ complete_ranking.json 更新完了")


if __name__ == "__main__":
    main()
