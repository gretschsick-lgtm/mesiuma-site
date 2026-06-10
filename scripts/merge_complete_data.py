"""
複数の complete_partial_*.json を統合して complete_info.json を更新する。

GH Actions matrix 収集完了後に実行:
  python scripts/merge_complete_data.py [--date YYYY-MM-DD]

処理:
  1. public/complete_partial_*.json を全て読み込む
  2. 重複排除 (entry id 基準)
  3. store_handle 空欄を x_url → store_handles.json 逆引きで補完
  4. save_complete() で complete_info.json に統合
  5. update_ranking() でランキング再生成
  6. 部分ファイルを削除
"""
import json
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fetch_complete_info import save_complete, update_ranking


def _load_handle_info() -> dict[str, dict]:
    """store_handles.json を handle.lower() → info dict として返す"""
    path = ROOT / "public" / "store_handles.json"
    if not path.exists():
        return {}
    sh = json.loads(path.read_text(encoding="utf-8"))
    return {h.lower(): v for h, v in sh.items() if isinstance(v, dict)}


def _fix_store_handle(entries: list[dict], handle_info: dict[str, dict]) -> int:
    """store_handle 空欄エントリを x_url から補完。補完件数を返す。"""
    fixed = 0
    for e in entries:
        if e.get("store_handle"):
            continue
        url = e.get("x_url", "")
        if not url:
            continue
        m = re.search(r"x\.com/([^/]+)/status", url)
        if not m:
            continue
        handle = m.group(1).lower()
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
        fixed += 1
    return fixed


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
    # text有のエントリを text空より優先する（handle_a が text空で keyword_b が text有のケース対策）
    best: dict[str, dict] = {}
    for e in all_entries:
        eid = e.get("id", "")
        if not eid:
            continue
        if eid not in best:
            best[eid] = e
        elif not best[eid].get("text") and e.get("text"):
            best[eid] = e  # text空 → text有 に差し替え
    deduped = list(best.values())

    text_upgraded = sum(1 for eid, e in best.items() if e.get("text"))
    print(f"合計: {len(deduped)}件 (重複排除後, 元={len(all_entries)}件, text有優先更新有)")


    # store_handle 空欄を補完（keyword-mode で store_handle が未設定のエントリ向け安全網）
    handle_info = _load_handle_info()
    sh_fixed = _fix_store_handle(deduped, handle_info)
    if sh_fixed:
        print(f"🔗 store_handle 補完: {sh_fixed}件")

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
