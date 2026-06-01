#!/usr/bin/env python3
"""
verify_complete_pipeline.py — コンプリート収集パイプライン検証

GitHub Actions Summary + exit code のみで状態を通知。外部通知なし。

exit 0: 全チェック正常
exit 1: 異常あり（GitHub Actions 失敗扱い）

使い方:
  python scripts/verify_complete_pipeline.py                 # 前日 JST を対象
  python scripts/verify_complete_pipeline.py --date 2026-06-01
"""

import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 定数 ────────────────────────────────────────────────────────────────────

JST  = timezone(timedelta(hours=9))
REPO = "gretschsick-lgtm/mesiuma-site"
WORKFLOW = "update_complete.yml"

COMPLETE_JSON = Path(__file__).parent.parent / "public/complete_info.json"
RANKING_JSON  = Path(__file__).parent.parent / "public/complete_ranking.json"

MIN_PREV_FOR_DROP = 5    # 前日 N 件未満は比較しない（休日等）
DROP_THRESHOLD    = 0.30  # 前日比 30% 以下 = 70% 以上減少
GH_STOP_HOURS     = 3.0  # GH Actions 停止疑い閾値（時間）
SILENT_FAIL_HOURS = 3.0  # workflow 成功 → JSON 未更新を疑う閾値（時間）


# ── ユーティリティ ───────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[{datetime.now(JST):%H:%M:%S}] {msg}", flush=True)


def _parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _write_summary(text: str) -> None:
    """GitHub Actions Step Summary へ書き出す（ローカル実行時は無視）。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


# ── GitHub API ───────────────────────────────────────────────────────────────

def _get_last_run() -> dict | None:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        log("⚠️  GITHUB_TOKEN 未設定 — GitHub API スキップ")
        return None
    url = (
        f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}"
        f"/runs?per_page=1&branch=main"
    )
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("workflow_runs", [None])[0]
    except Exception as e:
        log(f"❌ GitHub API 失敗: {e}")
        return None


# ── メイン ───────────────────────────────────────────────────────────────────

def main() -> bool:
    import argparse
    ap = argparse.ArgumentParser(description="コンプリートパイプライン検証")
    ap.add_argument("--date", default=None, help="検証対象日 YYYY-MM-DD (省略=前日 JST)")
    args = ap.parse_args()

    now_jst = datetime.now(JST)
    now_utc = datetime.now(timezone.utc)

    target = args.date or (now_jst - timedelta(days=1)).strftime("%Y-%m-%d")
    prev   = (datetime.fromisoformat(target) - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"=== 検証開始  target={target}  prev={prev} ===")

    anomalies:  list[str]             = []
    info_rows:  list[tuple[str, str]] = []

    # ── 1. complete_info.json ─────────────────────────────────────────────────

    total_count      = 0
    t_count          = 0
    p_count          = 0
    latest_collected = ""

    if not COMPLETE_JSON.exists():
        anomalies.append("complete_info.json が存在しない")
        info_rows.append(("complete_info.json", "❌ 存在しない"))
    else:
        with open(COMPLETE_JSON, encoding="utf-8") as f:
            entries: list[dict] = json.load(f)

        total_count      = len(entries)
        counts           = Counter(e.get("date", "")[:10] for e in entries)
        t_count          = counts.get(target, 0)
        p_count          = counts.get(prev,   0)
        latest_collected = max((e.get("collected_at", "") for e in entries), default="")

        log(f"  総件数: {total_count}件  /  {target}: {t_count}件  /  {prev}: {p_count}件")
        log(f"  最終収集: {latest_collected}")

        info_rows += [
            ("complete_info.json 総件数",     f"{total_count} 件"),
            (f"対象日件数 ({target})",         f"{t_count} 件"),
            (f"前日件数 ({prev})",             f"{p_count} 件"),
            ("最終収集 `collected_at`",        latest_collected or "不明"),
        ]

        if total_count == 0:
            anomalies.append("complete_info.json の総件数が 0 件")

        if t_count == 0:
            anomalies.append(f"{target} の件数が 0 件（収集漏れまたは未投稿）")
        elif p_count >= MIN_PREV_FOR_DROP:
            ratio = t_count / p_count
            if ratio < DROP_THRESHOLD:
                drop_pct = (1 - ratio) * 100
                anomalies.append(
                    f"前日比 {drop_pct:.0f}% 減少  "
                    f"({prev}: {p_count} 件 → {target}: {t_count} 件)"
                )

    # ── 2. complete_ranking.json ──────────────────────────────────────────────

    if not RANKING_JSON.exists():
        anomalies.append("complete_ranking.json が存在しない")
        info_rows.append(("complete_ranking.json", "❌ 存在しない"))
    else:
        with open(RANKING_JSON, encoding="utf-8") as f:
            gen_at = json.load(f).get("generated_at", "不明")
        log(f"  ranking generated_at: {gen_at}")
        info_rows.append(("complete_ranking.json", f"✅ 存在  generated_at: `{gen_at}`"))

    # ── 3. GitHub Actions 最終実行 ────────────────────────────────────────────

    last_run = _get_last_run()
    if last_run:
        run_conclusion = last_run.get("conclusion") or last_run.get("status", "unknown")
        run_updated_at = last_run.get("updated_at", "")
        run_url        = last_run.get("html_url", "")

        log(f"  GH 最終 run: {run_updated_at} ({run_conclusion})")
        info_rows.append((
            "最終 workflow run",
            f"[{run_updated_at}]({run_url}) — `{run_conclusion}`",
        ))

        if run_updated_at:
            try:
                run_dt      = _parse_utc(run_updated_at)
                hours_since = (now_utc - run_dt).total_seconds() / 3600
                log(f"  最終 run から {hours_since:.1f}h 経過")
                info_rows.append(("最終 run からの経過", f"{hours_since:.1f} 時間"))

                if hours_since > GH_STOP_HOURS:
                    anomalies.append(
                        f"GitHub Actions 停止疑い: 最終 run から {hours_since:.1f}h 経過"
                        f" (閾値 {GH_STOP_HOURS}h)"
                    )

                if run_conclusion == "success" and latest_collected:
                    json_dt     = _parse_utc(latest_collected)
                    staleness_h = (run_dt - json_dt).total_seconds() / 3600
                    if staleness_h > SILENT_FAIL_HOURS:
                        log(f"  ⚠️  JSON と run の乖離: {staleness_h:.1f}h")
                        anomalies.append(
                            f"workflow 成功なのに complete_info.json が未更新 "
                            f"(乖離 {staleness_h:.1f}h — X スクレイピング失敗の疑い)"
                        )
            except Exception as e:
                log(f"  時刻比較エラー: {e}")
    else:
        info_rows.append(("最終 workflow run", "取得不可 — GITHUB_TOKEN を確認"))

    # ── 結果の組み立て ────────────────────────────────────────────────────────

    ok      = len(anomalies) == 0
    verdict = "✅ OK" if ok else "❌ NG"

    # stdout サマリー
    log(f"=== 検証完了: {verdict} ({'異常なし' if ok else f'{len(anomalies)}件の異常'}) ===")

    # Markdown（GitHub Actions Summary / ローカル確認用）
    md_lines = [
        f"# 🎰 コンプリートパイプライン検証 — {verdict}",
        "",
        f"**対象日**: `{target}`　**確認時刻**: {now_jst:%Y-%m-%d %H:%M} JST",
        "",
        "## 確認結果",
        "",
        "| 項目 | 値 |",
        "|------|-----|",
    ]
    for label, value in info_rows:
        md_lines.append(f"| {label} | {value} |")
    md_lines.append("")

    if ok:
        md_lines += [
            "## 判定: ✅ 正常",
            "",
            "すべてのチェックが正常です。",
        ]
    else:
        md_lines += [
            "## 判定: ❌ 異常あり",
            "",
            "| # | 異常内容 |",
            "|---|---------|",
        ]
        for i, a in enumerate(anomalies, 1):
            md_lines.append(f"| {i} | {a} |")

        md_lines += [
            "",
            "## 修正候補",
            "",
            "| 状況 | 対応 |",
            "|------|------|",
            "| 対象日 0件 | `gh workflow run update_complete.yml -f date=YYYY-MM-DD` |",
            "| GH Actions 停止 | Actions タブで手動 `workflow_dispatch` |",
            "| 件数急減 | X API 制限 or セッション切れの疑い。`fetch_logs` テーブルを確認 |",
            "| JSON 未更新（サイレント失敗） | `fetch_logs` の `error_detail` を確認 |",
            "| JSON 存在しない | Vercel デプロイ失敗の可能性。デプロイログを確認 |",
        ]

    summary = "\n".join(md_lines)
    print("\n" + summary + "\n")
    _write_summary(summary)

    return not ok


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
