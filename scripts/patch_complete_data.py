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

    # ── manager_handles.json から handle → associated_store_id マップ読み込み ──
    mgr_handle_to_sid: dict[str, str] = {}
    mgr_handles_path = ROOT / "public" / "manager_handles.json"
    if mgr_handles_path.exists():
        try:
            _mgr_data = json.loads(mgr_handles_path.read_text(encoding="utf-8"))
            for _h, _info in _mgr_data.items():
                if isinstance(_info, dict) and _info.get("associated_store_id"):
                    mgr_handle_to_sid[_h.lower()] = _info["associated_store_id"]
            print(f"📋 manager_handles: {len(mgr_handle_to_sid)}件の store_id マッピング読み込み")
        except Exception as _me:
            print(f"⚠️  manager_handles.json 読み込みエラー: {_me}")

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
                _shandle = (e.get("store_handle") or "").lower()
                _sres = store_resolver.resolve(_sname) if _sname else None

                # フォールバック1: 名前解決失敗時はハンドルで x_url 直引き
                if not _sres and _shandle:
                    try:
                        _rows = store_resolver._sb_get(
                            f"stores?select=id,name&x_url=ilike.*{_shandle}*&limit=1"
                        )
                        if _rows:
                            e["store_id"] = _rows[0]["id"]
                            _sres = {"store_id": _rows[0]["id"]}
                    except Exception:
                        pass

                # フォールバック2: manager_handles.json の associated_store_id
                if not _sres and _shandle and _shandle in mgr_handle_to_sid:
                    e["store_id"] = mgr_handle_to_sid[_shandle]
                    _sres = {"store_id": mgr_handle_to_sid[_shandle]}

                if _sres:
                    e["store_id"] = _sres["store_id"]
                elif _sname:
                    store_resolver.save_unknown(_sname, e.get("x_url", ""))

            kept.append(e)
        else:
            # 未解決: unknown_machines に記録して除外
            if raw and raw not in MACHINE_NAME_NG:
                resolver.save_unknown(raw, e.get("x_url", ""))
                unknown_saved += 1
            excluded_count += 1

    after_count = len(kept)

    # ── store_handles.json から store_x_url / source_account_type を付与 ────
    store_handles_path = ROOT / "public" / "store_handles.json"
    handle_to_info: dict[str, dict] = {}
    if store_handles_path.exists():
        try:
            sh_data = json.loads(store_handles_path.read_text(encoding="utf-8"))
            for h, info in sh_data.items():
                if isinstance(info, dict):
                    handle_to_info[h.lower()] = info
        except Exception as _she2:
            print(f"⚠️ store_handles.json 読み込みエラー: {_she2}")

    store_x_enriched = 0
    for e in kept:
        x_url_e = e.get("x_url", "")
        if not x_url_e:
            continue
        m_h = re.search(r'x\.com/([^/]+)/status', x_url_e)
        if not m_h:
            continue
        handle_e = m_h.group(1).lower()
        e["store_handle"] = e.get("store_handle") or handle_e
        info_e = handle_to_info.get(handle_e)
        if info_e:
            htype_e = info_e.get("type", "store")
            hxurl_e = info_e.get("x_url", f"https://x.com/{handle_e}")
            if htype_e == "manager":
                if not e.get("manager_x_url"):
                    e["manager_x_url"] = hxurl_e
                e["source_account_type"] = "store_manager"
            else:
                if not e.get("store_x_url"):
                    e["store_x_url"] = hxurl_e
                    store_x_enriched += 1
                e["source_account_type"] = "store_official"
        elif not e.get("source_account_type"):
            e["source_account_type"] = "unknown"

    print(f"🔗 store_x_url 付与: {store_x_enriched}件")

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
