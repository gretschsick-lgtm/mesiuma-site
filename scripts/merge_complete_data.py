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

from fetch_complete_info import save_complete, update_ranking, MACHINE_PATTERN_SLUGS, _SERIES_ANCHOR_INDICES

# CC-QUALITY-3E5: series anchor slug一覧（MACHINE_PATTERN_SLUGSからの導出、二重管理しない）
_SERIES_ANCHOR_SLUGS = [MACHINE_PATTERN_SLUGS[i] for i in sorted(_SERIES_ANCHOR_INDICES)]


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


def _print_extraction_telemetry(totals: dict[str, int]) -> None:
    """CC-QUALITY-3E5: L_GENERIC/E_GENERIC/E handle-shape/series boundary/
    extraction pathのtelemetryをstdoutとGITHUB_STEP_SUMMARYに出力する。

    raw candidate文字列・tweet本文・author/handle・URL・画像は一切含めない
    （totalsはCC-QUALITY-3E3で定義したfixed keyの整数カウンタのみ）。
    complete_quality_*.json artifactは約24〜25時間でexpireするため、この
    出力がexpire後に残る唯一の証拠になる（CC-QUALITY-3E4Bで判明した制約への対応）。

    totalsが空dict（quality shard自体が1つも読めなかった）の場合は、
    _print_quality_funnel() と同じ方針で何も出力しない（missing shardを
    0件観測と混同しない。CC-QUALITY-2M-T2の既存fail-open方針を維持）。
    """
    if not totals:
        return

    def g(key: str) -> int:
        return totals.get(key, 0)

    l_rows = [
        ("0_1",   g("EXTRACT_L_GENERIC_RUN_0_1_RESOLVED"),   g("EXTRACT_L_GENERIC_RUN_0_1_UNRESOLVED")),
        ("2plus", g("EXTRACT_L_GENERIC_RUN_2PLUS_RESOLVED"), g("EXTRACT_L_GENERIC_RUN_2PLUS_UNRESOLVED")),
    ]
    e_rows = [
        ("0_2",   g("EXTRACT_E_GENERIC_RUN_0_2_RESOLVED"),   g("EXTRACT_E_GENERIC_RUN_0_2_UNRESOLVED")),
        ("3_5",   g("EXTRACT_E_GENERIC_RUN_3_5_RESOLVED"),   g("EXTRACT_E_GENERIC_RUN_3_5_UNRESOLVED")),
        ("6plus", g("EXTRACT_E_GENERIC_RUN_6PLUS_RESOLVED"), g("EXTRACT_E_GENERIC_RUN_6PLUS_UNRESOLVED")),
    ]
    e_shape_rows = [
        ("underscore",    g("EXTRACT_E_GENERIC_SHAPE_UNDERSCORE_RESOLVED"),    g("EXTRACT_E_GENERIC_SHAPE_UNDERSCORE_UNRESOLVED")),
        ("no_underscore", g("EXTRACT_E_GENERIC_SHAPE_NO_UNDERSCORE_RESOLVED"), g("EXTRACT_E_GENERIC_SHAPE_NO_UNDERSCORE_UNRESOLVED")),
    ]

    # CC-QUALITY-3G1: anchor別のNONE/PRESENT×resolved/unresolvedを合算せず、
    # 4次元をそのまま保持する（3Gで判明した「表示時のみの集約でPRESENT単独の
    # anchor別内訳が失われる」問題への対応）。生カウンタ自体は3E3の時点から
    # anchor×boundary×outcomeで個別に記録済みであり、fetch_complete_info.py側の
    # 変更は不要（producer/parser/resolverは本フェーズで一切touchしない）。
    series_none_r = series_none_u = series_present_r = series_present_u = 0
    anchor_detail_rows: list[tuple[str, int, int, int, int, int]] = []
    for slug in _SERIES_ANCHOR_SLUGS:
        up = slug.upper()
        nr = g(f"EXTRACT_SERIES_{up}_BOUNDARY_NONE_RESOLVED")
        nu = g(f"EXTRACT_SERIES_{up}_BOUNDARY_NONE_UNRESOLVED")
        pr = g(f"EXTRACT_SERIES_{up}_BOUNDARY_PRESENT_RESOLVED")
        pu = g(f"EXTRACT_SERIES_{up}_BOUNDARY_PRESENT_UNRESOLVED")
        series_none_r += nr
        series_none_u += nu
        series_present_r += pr
        series_present_u += pu
        total = nr + nu + pr + pu
        # 固定21anchor全件を毎回表示する（0件も含む）。cardinalityは常に
        # len(_SERIES_ANCHOR_SLUGS)件で確定しており、production textに依存しない。
        anchor_detail_rows.append((slug, nr, nu, pr, pu, total))

    path_rows = [
        ("SINGLE", g("EXTRACTION_PATH_SINGLE")),
        ("MULTI",  g("EXTRACTION_PATH_MULTI")),
    ]

    # CC-QUALITY-3H: valvrave_anchor限定resolver fallback(T3-C)のfixed counter。
    # fetch_complete_info.py側は既にATTEMPTED/RESOLVED/UNRESOLVEDの3keyのみを
    # 記録しており、ここでは表示するだけ(raw candidate/truncated文字列は一切含まない)。
    t3_valvrave_attempted  = g("T3_VALVRAVE_ATTEMPTED")
    t3_valvrave_resolved   = g("T3_VALVRAVE_RESOLVED")
    t3_valvrave_unresolved = g("T3_VALVRAVE_UNRESOLVED")

    lines = ["\n## Extraction Telemetry (CC-QUALITY-3E3/3E5, metadata-only)\n"]
    lines.append("_raw candidate文字列・tweet本文・author/handle・URL・画像は含まれません。"
                  "パターンbucket分類 + resolver結果の整数カウンタのみです。_\n")

    lines.append("### L_GENERIC\n\n| bucket | resolved | unresolved | total |\n|---|---:|---:|---:|")
    for name, r, u in l_rows:
        lines.append(f"| {name} | {r} | {u} | {r + u} |")

    lines.append("\n### E_GENERIC\n\n| bucket | resolved | unresolved | total |\n|---|---:|---:|---:|")
    for name, r, u in e_rows:
        lines.append(f"| {name} | {r} | {u} | {r + u} |")

    lines.append("\n### E_GENERIC Handle Shape\n\n| shape | resolved | unresolved | total |\n|---|---:|---:|---:|")
    for name, r, u in e_shape_rows:
        lines.append(f"| {name} | {r} | {u} | {r + u} |")

    lines.append("\n### Series Boundary (aggregate, %d anchors)\n\n| boundary | resolved | unresolved | total |\n|---|---:|---:|---:|"
                 % len(_SERIES_ANCHOR_SLUGS))
    lines.append(f"| none | {series_none_r} | {series_none_u} | {series_none_r + series_none_u} |")
    lines.append(f"| present | {series_present_r} | {series_present_u} | {series_present_r + series_present_u} |")

    lines.append("\n### Series Anchor Boundary (all %d fixed anchors)\n\n"
                 "| anchor | none_resolved | none_unresolved | present_resolved | present_unresolved | total |\n"
                 "|---|---:|---:|---:|---:|---:|" % len(_SERIES_ANCHOR_SLUGS))
    for slug, nr, nu, pr, pu, total in anchor_detail_rows:
        lines.append(f"| {slug} | {nr} | {nu} | {pr} | {pu} | {total} |")

    lines.append("\n### Extraction Path\n\n| path | count |\n|---|---:|")
    for name, c in path_rows:
        lines.append(f"| {name} | {c} |")

    lines.append("\n### T3 Valvrave Fallback (CC-QUALITY-3H, valvrave_anchor only)\n\n"
                 "| metric | count |\n|---|---:|")
    lines.append(f"| attempted | {t3_valvrave_attempted} |")
    lines.append(f"| resolved | {t3_valvrave_resolved} |")
    lines.append(f"| unresolved | {t3_valvrave_unresolved} |")

    table_md = "\n".join(lines)

    print("🔬 Extraction Telemetry (CC-QUALITY-3E3/3E5, metadata-only):")
    print(f"   l_generic_0_1: resolved={l_rows[0][1]} unresolved={l_rows[0][2]}")
    print(f"   l_generic_2plus: resolved={l_rows[1][1]} unresolved={l_rows[1][2]}")
    print(f"   e_generic_0_2: resolved={e_rows[0][1]} unresolved={e_rows[0][2]}")
    print(f"   e_generic_3_5: resolved={e_rows[1][1]} unresolved={e_rows[1][2]}")
    print(f"   e_generic_6plus: resolved={e_rows[2][1]} unresolved={e_rows[2][2]}")
    print(f"   e_generic_shape_underscore: resolved={e_shape_rows[0][1]} unresolved={e_shape_rows[0][2]}")
    print(f"   e_generic_shape_no_underscore: resolved={e_shape_rows[1][1]} unresolved={e_shape_rows[1][2]}")
    print(f"   series_boundary_none: resolved={series_none_r} unresolved={series_none_u}")
    print(f"   series_boundary_present: resolved={series_present_r} unresolved={series_present_u}")
    for slug, nr, nu, pr, pu, total in anchor_detail_rows:
        print(f"   series[{slug}]: none_resolved={nr} none_unresolved={nu} "
              f"present_resolved={pr} present_unresolved={pu} total={total}")
    print(f"   extraction_path_single: {path_rows[0][1]}")
    print(f"   extraction_path_multi: {path_rows[1][1]}")
    print(f"   t3_valvrave_attempted: {t3_valvrave_attempted}")
    print(f"   t3_valvrave_resolved: {t3_valvrave_resolved}")
    print(f"   t3_valvrave_unresolved: {t3_valvrave_unresolved}")

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        try:
            with open(step_summary_path, "a", encoding="utf-8") as f:
                f.write(table_md)
                f.write("\n")
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

    # CC-QUALITY-2M-T2: quality shard集計は partial_files の有無に関わらず必ず実行する。
    # complete追加が0件のnatural run（全natural runの大半を占める）でも、
    # collectorがどのstageで何件accept/rejectしたかという observation は失われてはいけない。
    # complete_info.json 更新より前に呼ぶため、この時点では added はまだ確定していない
    # （partial_files がある場合は後段で実際の added を使って再度 print する）。
    quality_totals = _merge_quality_summaries(keep=args.keep_partials)

    if not partial_files:
        print("⚠️  部分ファイルが見つかりません: public/complete_partial_*.json")
        _print_quality_funnel(quality_totals, 0)
        _print_extraction_telemetry(quality_totals)
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

    # CC-QUALITY-2M: Quality Funnel（メタデータのみ）を表示。
    # 集計自体は上で partial_files の有無に関わらず既に実行済み（CC-QUALITY-2M-T2）。
    # ここでは実際の added（新規complete_info.json追加件数）を使って再度出力する。
    _print_quality_funnel(quality_totals, added)
    _print_extraction_telemetry(quality_totals)

    # 部分ファイル削除
    if not args.keep_partials:
        for f in partial_files:
            f.unlink()
            print(f"🗑  削除: {f.name}")


if __name__ == "__main__":
    main()
