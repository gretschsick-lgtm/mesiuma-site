"""
複数の complete_partial_*.json を統合して complete_info.json を更新する。

GH Actions matrix 収集完了後に実行:
  python scripts/merge_complete_data.py [--date YYYY-MM-DD]

処理:
  1. public/complete_partial_*.json を全て読み込む
  2. 重複排除 (entry id 基準)
  3. save_complete() で complete_info.json に統合
  4. update_ranking() でランキング再生成
  5. 部分ファイルを削除
"""
import json
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fetch_complete_info import save_complete, update_ranking


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="統合対象日 (YYYY-MM-DD, 省略時は当日JST)")
    parser.add_argument("--keep-partials", action="store_true", help="部分ファイルを削除しない")
    args = parser.parse_args()

    if args.date:
        today = args.date
    else:
        JST = timezone(timedelta(hours=9))
        today = datetime.now(JST).strftime("%Y-%m-%d")

    partial_files = sorted(ROOT.glob("public/complete_partial_*.json"))
    if not partial_files:
        print("⚠️  部分ファイルが見つかりません: public/complete_partial_*.json")
        return

    print(f"📂 部分ファイル {len(partial_files)}件 を統合 (date={today})")

    all_entries = []
    for f in partial_files:
        entries = json.loads(f.read_text(encoding="utf-8"))
        print(f"  {f.name}: {len(entries)}件")
        all_entries.extend(entries)

    # シャード間重複排除 (同じツイートが複数シャードでヒットする場合)
    seen: set[str] = set()
    deduped: list[dict] = []
    for e in all_entries:
        eid = e.get("id", "")
        if eid and eid not in seen:
            seen.add(eid)
            deduped.append(e)

    print(f"合計: {len(deduped)}件 (重複排除後, 元={len(all_entries)}件)")

    # complete_info.json に統合 (既存データとの重複も除去)
    added = save_complete(deduped, today)
    print(f"✅ 新規追加: {added}件 → complete_info.json")

    # ランキング再生成
    update_ranking()
    print("✅ complete_ranking.json 更新完了")

    # 部分ファイル削除
    if not args.keep_partials:
        for f in partial_files:
            f.unlink()
            print(f"🗑  削除: {f.name}")


if __name__ == "__main__":
    main()
