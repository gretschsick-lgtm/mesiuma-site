#!/usr/bin/env python3
"""
機種カタログ read-only エクスポート（backup 用途）。

ライブ正本は Supabase DB（machines_master / machines_aliases）。本スクリプトは DB を
SELECT のみで読み出し、決定的順序の CSV としてバックアップ出力する。

重要:
  - これは **backup であり Source of Truth ではない**（正本は Supabase DB）。
  - DB へは一切書き込まない（SELECT のみ）。
  - 出力先は明示指定が必須。既定は一時ディレクトリ。
  - public/ の legacy seed CSV（machines_master.csv / machines_aliases.csv）は
    自動上書きしない（明示的に危険な出力先を弾く）。
  - secrets（API キー等）は出力に含めない。

使用例:
  export NEXT_PUBLIC_SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
  python scripts/export_machines_catalog.py --out-dir /tmp/catalog_backup
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import ssl
import sys
import tempfile
import urllib.request

_MASTER_COLS = ["id", "official_name", "normalized_name", "type",
                "manufacturer", "brand", "is_active"]
_ALIAS_COLS = ["id", "machine_id", "alias_name", "normalized_alias", "confidence"]

_FORBIDDEN_BASENAMES = {"machines_master.csv", "machines_aliases.csv"}


def _sb_env() -> tuple[str, str]:
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("❌ NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が未設定です。")
    return url, key


def _sb_get_all(path: str) -> list[dict]:
    """PostgREST から全行を SELECT（ページング・読み取り専用）。"""
    url, key = _sb_env()
    ctx = ssl._create_unverified_context()
    rows: list[dict] = []
    offset, page = 0, 1000
    while True:
        req = urllib.request.Request(
            f"{url}/rest/v1/{path}&limit={page}&offset={offset}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        rows.extend(batch)
        offset += page
        if len(batch) < page:
            break
    return rows


def _to_csv(rows: list[dict], cols: list[str], sort_keys) -> str:
    rows_sorted = sorted(rows, key=sort_keys)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for row in rows_sorted:
        w.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in cols})
    return buf.getvalue()


def _write(out_dir: str, name: str, content: str) -> None:
    if os.path.basename(name) in _FORBIDDEN_BASENAMES and os.path.abspath(out_dir).endswith("public"):
        sys.exit(f"❌ legacy seed の自動上書きは禁止です: {out_dir}/{name}")
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    n = max(0, content.count("\n") - 1)  # ヘッダ除く概算行数
    print(f"  {name}: 行数={n} SHA-256={sha}")
    print(f"    → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="機種カタログ read-only エクスポート（backup）")
    ap.add_argument("--out-dir", default=None,
                    help="出力ディレクトリ（既定: 一時ディレクトリ）。public/ への legacy seed 上書きは不可")
    args = ap.parse_args()

    out_dir = args.out_dir or tempfile.mkdtemp(prefix="machines_catalog_export_")
    os.makedirs(out_dir, exist_ok=True)

    print("=== 機種カタログ export（read-only / backup・正本ではない） ===")
    masters = _sb_get_all("machines_master?select=" + ",".join(_MASTER_COLS))
    aliases = _sb_get_all("machines_aliases?select=" + ",".join(_ALIAS_COLS))
    print(f"machines_master: {len(masters)} 件 / machines_aliases: {len(aliases)} 件")

    _write(out_dir, "machines_master.export.csv",
           _to_csv(masters, _MASTER_COLS, lambda r: (str(r.get("official_name") or ""), str(r.get("id") or ""))))
    _write(out_dir, "machines_aliases.export.csv",
           _to_csv(aliases, _ALIAS_COLS, lambda r: (str(r.get("normalized_alias") or ""), str(r.get("id") or ""))))

    print("注意: これは backup であり Source of Truth ではありません（正本は Supabase DB）。")


if __name__ == "__main__":
    main()
