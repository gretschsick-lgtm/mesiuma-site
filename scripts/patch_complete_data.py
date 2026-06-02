"""
既存の complete_info.json を machine_resolver で一括クレンジングするスクリプト。

処理内容:
  1. public/backups/ にバックアップを作成
  2. 各エントリを machine_resolver.resolve() に通す
  3. 解決済み → official_name / machine_type(DB値) / machine_id で上書き
  4. 未解決 → テキストから再抽出して再試行
  5. それでも未解決 → 除外 + unknown_machines に記録
  6. 台番号の全角→半角変換
  7. complete_info.json 保存 + ランキング再生成

注意: Supabase 環境変数（NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY）が必要。
"""
import sys
import re
import json
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fetch_complete_info import extract_machine, extract_slot_number, update_ranking
from machine_resolver import get_resolver
from store_resolver import get_resolver as get_store_resolver

COMPLETE_JSON = ROOT / "public" / "complete_info.json"
BACKUP_DIR    = ROOT / "public" / "backups"

# 明らかに機種名でない文字列（resolverを呼ぶ前に弾く）
MACHINE_NAME_NG = {
    "不明", "コンプリート達成", "コンプリート機能", "コンプリート", "お客様",
    "ありがとうございます", "発動", "作動", "本日", "達成", "発生",
    "機能", "番台", "スロット", "パチスロ", "スマスロ", "来店",
    "誠におめ", "おめでとう", "おめでとうございます", "ございます",
    "コンプ", "完走", "出玉", "今日", "昨日",
}

_FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def create_backup() -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    bak_path = BACKUP_DIR / f"complete_info_{ts}.json"
    shutil.copy2(COMPLETE_JSON, bak_path)
    print(f"📦 バックアップ作成: {bak_path}")
    return str(bak_path)


def main():
    # ── 前提チェック ───────────────────────────────────────────────────────
    if not COMPLETE_JSON.exists():
        print(f"❌ {COMPLETE_JSON} が存在しません")
        sys.exit(1)

    resolver = get_resolver()
    if not resolver:
        print("❌ Supabase 環境変数未設定。")
        print("   NEXT_PUBLIC_SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定してください")
        sys.exit(1)

    store_resolver = get_store_resolver()

    # ── バックアップ ────────────────────────────────────────────────────────
    bak_path = create_backup()

    # ── データ読み込み ──────────────────────────────────────────────────────
    data: list[dict] = json.loads(COMPLETE_JSON.read_text(encoding="utf-8"))
    before_count = len(data)
    print(f"📂 読み込み: {before_count}件")

    # ── 統計カウンタ ────────────────────────────────────────────────────────
    resolved_count    = 0
    excluded_count    = 0
    unknown_saved     = 0
    slot_fixed        = 0
    type_changed      = 0
    machine_renamed   = 0

    kept: list[dict] = []

    for e in data:
        # ── 台番号全角→半角 ─────────────────────────────────────────────────
        slot = e.get("slot_number") or ""
        new_slot = slot.translate(_FW_DIGITS)
        if new_slot != slot:
            e["slot_number"] = new_slot
            slot_fixed += 1

        raw = (e.get("machine") or "").strip()

        # ── Step 1: 現在の machine 名で resolver.resolve() ─────────────────
        resolved = None
        if raw and raw not in MACHINE_NAME_NG:
            resolved = resolver.resolve(raw)

        # ── Step 2: 未解決ならテキストから再抽出して再試行 ────────────────────
        if resolved is None:
            text = (e.get("text") or "").strip()
            if text:
                re_extracted = extract_machine(text)
                if re_extracted and re_extracted != raw and re_extracted not in MACHINE_NAME_NG:
                    resolved = resolver.resolve(re_extracted)
                    if resolved:
                        print(f"  re-extract [{e.get('date','')}] '{raw}' → '{re_extracted}' → '{resolved['official_name']}'")

        # ── Step 3: 解決結果を適用 ──────────────────────────────────────────
        if resolved:
            old_machine = e.get("machine", "")
            old_type    = e.get("machine_type", "")

            e["machine"]      = resolved["official_name"]
            e["machine_type"] = resolved["machine_type"]
            e["machine_id"]   = resolved["machine_id"]

            if old_machine != resolved["official_name"]:
                machine_renamed += 1
                print(f"  rename  [{e.get('date','')}] '{old_machine}' → '{resolved['official_name']}"
                      f"' ({resolved['match_type']}, {resolved['confidence']:.2f})")

            if old_type and old_type != resolved["machine_type"]:
                type_changed += 1
                print(f"  type    [{e.get('date','')}] '{resolved['official_name']}': "
                      f"{old_type} → {resolved['machine_type']}")

            resolved_count += 1

            # ── Step 4: store_resolver で store_id を設定 ───────────────────
            if store_resolver and not e.get("store_id"):
                _sname = (e.get("store") or "").strip()
                if _sname:
                    _sres = store_resolver.resolve(_sname)
                    if _sres:
                        e["store_id"] = _sres["store_id"]
                    else:
                        store_resolver.save_unknown(_sname, e.get("x_url", ""))

            kept.append(e)
        else:
            # 未解決: unknown_machines に記録して除外
            if raw and raw not in MACHINE_NAME_NG:
                resolver.save_unknown(raw, e.get("x_url", ""))
                unknown_saved += 1
            excluded_count += 1

    after_count = len(kept)

    # ── 保存 ────────────────────────────────────────────────────────────────
    COMPLETE_JSON.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── 最終レポート ────────────────────────────────────────────────────────
    slot_count     = sum(1 for e in kept if e.get("machine_type") == "slot")
    pachinko_count = sum(1 for e in kept if e.get("machine_type") == "pachinko")
    resolve_rate   = f"{100 * resolved_count / before_count:.1f}%" if before_count else "N/A"

    print()
    print("=" * 55)
    print("📊 patch_complete_data 結果")
    print("=" * 55)
    print(f"バックアップ           : {bak_path}")
    print(f"修正前                 : {before_count}件")
    print(f"修正後                 : {after_count}件")
    print(f"除外                   : {excluded_count}件")
    print(f"machine_id 解決率      : {resolved_count}/{before_count} ({resolve_rate})")
    print(f"unknown_machines 追加  : {unknown_saved}件")
    print(f"machine 名称変更       : {machine_renamed}件")
    print(f"machine_type 変更      : {type_changed}件")
    print(f"slot_number 修正       : {slot_fixed}件")
    print(f"スロット               : {slot_count}件")
    print(f"パチンコ               : {pachinko_count}件")

    jun1 = [e for e in kept if e.get("date") == "2026-06-01"]
    print()
    print(f"2026-06-01 の結果: {len(jun1)}件")
    for e in jun1:
        mt = "🎰" if e.get("machine_type") == "slot" else "🎲"
        print(f"  {mt} {e.get('time','?')} {e.get('store','?')} / "
              f"{e.get('machine','?')} [{e.get('slot_number','?')}番台]"
              f"  machine_id={e.get('machine_id','None')}")
    print("=" * 55)

    # ── ランキング再生成 ─────────────────────────────────────────────────────
    print("\n📊 ランキング再生成中...")
    update_ranking()
    print("✅ complete_ranking.json 更新完了")


if __name__ == "__main__":
    main()
