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
import os
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fetch_complete_info import save_complete, update_ranking


def _merge_quality_summaries(keep: bool = False) -> dict[str, int]:
    """CC-QUALITY-2M: 各 matrix job が書き出した complete_quality_*.json
    （メタデータのみ・raw text/画像/生ハンドル一切なし）を合算する。

    失敗しても呼び出し元（complete_info.json の更新）には一切影響しない
    （fail-open。quality ファイルが1つもなくても空dictを返すだけ）。
    """
    totals: dict[str, int] = {}
    try:
        quality_files = sorted(ROOT.glob("public/complete_quality_*.json"))
        for f in quality_files:
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            # 新形式 {"counts": {...}, "meta": {...}} / 旧形式（counts が無い場合）どちらも許容
            counts = payload.get("counts", payload)
            if not isinstance(counts, dict):
                continue
            for k, v in counts.items():
                if isinstance(v, int):
                    totals[k] = totals.get(k, 0) + v
        if not keep:
            for f in quality_files:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️  Quality summary 集計エラー（complete_info.json 更新には影響なし）: {e}")
    return totals


def _print_quality_funnel(totals: dict[str, int], added: int) -> None:
    """Quality Funnel を人間可読な表として stdout と GITHUB_STEP_SUMMARY に出力する。

    ここに raw tweet 本文・画像・生ハンドルは一切含めない（totals は整数カウンタのみ）。
    これは Complete Precision/Recall の算出ではない（ground truth 不在のため測定不可）。
    あくまで「どの段階で何件がどう分岐したか」の funnel 可視化。
    """
    if not totals and not added:
        return
    rows = [
        ("collected",                totals.get("COLLECTED", 0)),
        ("excluded_pattern",         totals.get("EXCLUDED_PATTERN", 0)),
        ("no_store_pattern",         totals.get("NO_STORE_PATTERN", 0)),
        ("store_pattern_matched",    totals.get("STORE_PATTERN_MATCHED", 0)),
        ("store_extraction_failed",  totals.get("STORE_EXTRACTION_FAILED", 0)),
        ("no_extractable_data",      totals.get("NO_EXTRACTABLE_DATA", 0)),
        ("machine_extraction_failed", totals.get("MACHINE_EXTRACTION_FAILED", 0)),
        ("slot_not_found",           totals.get("SLOT_NOT_FOUND", 0)),
        ("multi_machine",            totals.get("MULTI_MACHINE", 0)),
        ("slot_machine_mismatch",    totals.get("SLOT_MACHINE_MISMATCH", 0)),
        ("parsed_ok",                totals.get("PARSED_OK", 0)),
        ("store_resolved",           totals.get("STORE_RESOLVED", 0)),
        ("store_unresolved",         totals.get("STORE_UNRESOLVED", 0)),
        ("machine_resolved",         totals.get("MACHINE_RESOLVED", 0)),
        ("machine_unresolved",       totals.get("MACHINE_UNRESOLVED", 0)),
        ("duplicate_supabase",       totals.get("DUPLICATE", 0)),
        ("saved_supabase",           totals.get("SAVED_SUPABASE", 0)),
        ("saved_json",               added),
    ]
    lines = ["| metric | count |", "|---|---:|"]
    for name, val in rows:
        lines.append(f"| {name} | {val} |")
    table_md = "\n".join(lines)

    print("📊 Quality Funnel (CC-QUALITY-2M, metadata-only, not Precision/Recall):")
    for name, val in rows:
        print(f"   {name}: {val}")

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        try:
            with open(step_summary_path, "a", encoding="utf-8") as f:
                f.write("\n## Complete Quality Funnel (metadata-only)\n\n")
                f.write(table_md)
                f.write("\n\n_raw tweet text / images / handles は含まれません。"
                        "Complete Precision/Recall そのものではありません。_\n")
        except Exception as e:
            print(f"⚠️  GITHUB_STEP_SUMMARY 書き込みエラー（無視して継続）: {e}")


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

    # CC-QUALITY-2M: Quality Funnel（メタデータのみ）を集計・表示
    # complete_info.json 更新が既に完了した後に実行するため、失敗しても本体処理には影響しない
    quality_totals = _merge_quality_summaries(keep=args.keep_partials)
    _print_quality_funnel(quality_totals, added)

    # 部分ファイル削除
    if not args.keep_partials:
        for f in partial_files:
            f.unlink()
            print(f"🗑  削除: {f.name}")


if __name__ == "__main__":
    main()
