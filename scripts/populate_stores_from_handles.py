#!/usr/bin/env python3
"""
populate_stores_from_handles.py

store_handles.json から Supabase stores テーブルへ店舗を一括登録するスクリプト。
register_stores.py の --input 形式 JSON を生成してドライランまたは実行。

使い方:
    python scripts/populate_stores_from_handles.py --dry-run   # 確認のみ
    python scripts/populate_stores_from_handles.py             # 実際に登録
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

# ─── NG 判定パターン ──────────────────────────────────────────────────────────

NG_PATTERNS = re.compile(
    r"店長|スタッフ|アプリ|もぐ美|サラリーマン|マルハンアプリ|No\.1|大阪No|ダースー|中の人"
    r"|^\s*山田|^\s*はま店|スタッフブログ"
)


def is_ng_store(name: str) -> bool:
    """NG パターンに一致する店舗名かどうかを返す。"""
    return bool(NG_PATTERNS.search(name))


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def load_store_handles(handles_path: str) -> dict:
    with open(handles_path, encoding="utf-8") as f:
        return json.load(f)


def build_store_entries(handles: dict) -> tuple[list[dict], dict[str, int]]:
    """
    store_handles.json からフィルタリングして register_stores.py 用 JSON リストを生成。

    Returns:
        entries: 登録対象の店舗リスト
        stats: スキップ理由別カウント
    """
    entries: list[dict] = []
    stats: dict[str, int] = {
        "total":       0,
        "accepted":    0,
        "skip_manager":0,
        "skip_short":  0,
        "skip_ng":     0,
        "skip_no_name":0,
    }

    for handle, info in handles.items():
        stats["total"] += 1

        # type == "manager" はスキップ（店長個人アカウント）
        if info.get("type") == "manager":
            stats["skip_manager"] += 1
            continue

        store_name: str = (info.get("store") or "").strip()

        # 店舗名が空
        if not store_name:
            stats["skip_no_name"] += 1
            continue

        # 3文字未満
        if len(store_name) < 3:
            stats["skip_short"] += 1
            continue

        # NG パターン
        if is_ng_store(store_name):
            stats["skip_ng"] += 1
            continue

        x_url: str = (info.get("x_url") or "").strip() or None

        entries.append({
            "name":      store_name,
            "x_url":     x_url,
            "is_active": True,
        })
        stats["accepted"] += 1

    return entries, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="store_handles.json から Supabase stores テーブルへ一括登録"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB に書き込まず内容確認のみ（register_stores.py に --dry-run を渡す）",
    )
    parser.add_argument(
        "--handles",
        metavar="FILE",
        default=None,
        help="store_handles.json のパス（省略時はプロジェクトルートの public/store_handles.json）",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="生成した JSON を保存するファイルパス（省略時は tmp_stores_list.json）",
    )
    args = parser.parse_args()

    # パス解決
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    handles_path = args.handles or os.path.join(root_dir, "public", "store_handles.json")
    output_path  = args.output  or os.path.join(root_dir, "tmp_stores_list.json")

    # ── 1. store_handles.json を読み込む ──────────────────────────────────────
    if not os.path.exists(handles_path):
        print(f"[ERROR] ファイルが見つかりません: {handles_path}", file=sys.stderr)
        sys.exit(1)

    print(f"読み込み: {handles_path}")
    handles = load_store_handles(handles_path)

    # ── 2. エントリ生成・フィルタリング ──────────────────────────────────────
    entries, stats = build_store_entries(handles)

    print()
    print("=== フィルタリング結果 ===")
    print(f"  入力合計:              {stats['total']} 件")
    print(f"  登録対象:              {stats['accepted']} 件")
    print(f"  スキップ (manager):    {stats['skip_manager']} 件")
    print(f"  スキップ (名前3字未満):{stats['skip_short']} 件")
    print(f"  スキップ (NG パターン):{stats['skip_ng']} 件")
    print(f"  スキップ (名前なし):   {stats['skip_no_name']} 件")
    print()

    if not entries:
        print("[WARN] 登録対象が 0 件です。終了します。")
        sys.exit(0)

    # ── 3. JSON ファイルに保存 ────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"中間ファイルを保存: {output_path}  ({len(entries)} 件)")
    print()

    # ── 4. register_stores.py を呼び出す ─────────────────────────────────────
    register_script = os.path.join(root_dir, "scripts", "register_stores.py")
    cmd = [sys.executable, register_script, "--input", output_path]
    if args.dry_run:
        cmd.append("--dry-run")

    mode_label = "DRY RUN" if args.dry_run else "本番登録"
    print(f"register_stores.py を実行 ({mode_label})...")
    print(f"  コマンド: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=root_dir)

    print()
    if result.returncode == 0:
        print(f"[OK] register_stores.py 正常終了 (exit 0)")
    else:
        print(f"[ERROR] register_stores.py が exit {result.returncode} で終了しました", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
