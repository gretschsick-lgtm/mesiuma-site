#!/usr/bin/env python3
"""
今日のコンプリート情報を X (Twitter) に自動投稿するスクリプト。

public/complete_info.json から当日データを取得し、
まとめツイートとして投稿する。
投稿済みの日付は posted_dates.json に記録し、重複投稿を防ぐ。

Usage:
    python scripts/post_complete_x.py
    python scripts/post_complete_x.py --date 2026-05-25  # 日付指定
    python scripts/post_complete_x.py --dry-run          # 投稿せず内容確認
    python scripts/post_complete_x.py --force            # 投稿済みでも再投稿

Secrets (環境変数):
    X_API_KEY
    X_API_SECRET
    X_ACCESS_TOKEN
    X_ACCESS_TOKEN_SECRET
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import tweepy
except ImportError:
    print("❌ tweepy が必要です: pip install tweepy")
    sys.exit(1)

COMPLETE_JSON   = Path(__file__).parent.parent / "public/complete_info.json"
POSTED_LOG_JSON = Path(__file__).parent.parent / "public/complete_posted_log.json"
SITE_URL        = "https://mesiuma.vercel.app/complete"

JST = timezone(timedelta(hours=9))

DOW_JA = ["月", "火", "水", "木", "金", "土", "日"]


def log(msg: str):
    ts = datetime.now(JST).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_jst_today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def load_complete(date_str: str) -> list[dict]:
    if not COMPLETE_JSON.exists():
        return []
    with open(COMPLETE_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return [e for e in data if e.get("date") == date_str and e.get("machine")]


def load_posted_log() -> dict:
    if not POSTED_LOG_JSON.exists():
        return {}
    with open(POSTED_LOG_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_posted_log(log_data: dict):
    with open(POSTED_LOG_JSON, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)


def build_tweet(entries: list[dict], date_str: str) -> str:
    """コンプリートまとめツイートのテキストを生成する。"""
    # 日付フォーマット
    d = datetime.strptime(date_str, "%Y-%m-%d")
    dow = DOW_JA[d.weekday()]
    date_label = f"{d.month}/{d.day}({dow})"

    total = len(entries)

    # 機種別カウント（上位3機種）
    machine_counter = Counter(e.get("machine", "") for e in entries if e.get("machine"))
    top_machines = machine_counter.most_common(5)

    # パチスロ / パチンコ分類
    slot_count     = sum(1 for e in entries if e.get("machine_type") != "pachinko")
    pachinko_count = sum(1 for e in entries if e.get("machine_type") == "pachinko")

    # ツイート本文組み立て
    lines = []
    lines.append(f"🏆 {date_label} コンプリート速報")
    lines.append(f"本日 {total}件の報告がありました！")
    lines.append("")

    if slot_count and pachinko_count:
        lines.append(f"🎰 パチスロ {slot_count}件 / 🎯 パチンコ {pachinko_count}件")
        lines.append("")

    lines.append("【本日の人気機種】")
    for i, (name, cnt) in enumerate(top_machines[:3]):
        medal = ["🥇", "🥈", "🥉"][i]
        lines.append(f"{medal} {name}（{cnt}件）")

    lines.append("")
    lines.append(f"詳細はこちら👇")
    lines.append(SITE_URL)
    lines.append("")
    lines.append("#スマスロ #コンプリート #パチスロ #メシウマ稼働")

    text = "\n".join(lines)

    # X の文字数制限（280文字）チェック・超過時は機種を減らす
    if len(text) > 270:
        lines_short = []
        lines_short.append(f"🏆 {date_label} コンプリート速報")
        lines_short.append(f"本日 {total}件！")
        lines_short.append("")
        for i, (name, cnt) in enumerate(top_machines[:2]):
            medal = ["🥇", "🥈"][i]
            lines_short.append(f"{medal} {name}（{cnt}件）")
        lines_short.append("")
        lines_short.append(SITE_URL)
        lines_short.append("#スマスロ #コンプリート")
        text = "\n".join(lines_short)

    return text


def post_tweet(text: str) -> str | None:
    """tweepy で X API v2 にポスト。成功したら tweet_id を返す。"""
    api_key    = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    acc_token  = os.environ.get("X_ACCESS_TOKEN", "")
    acc_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    missing = [k for k, v in {
        "X_API_KEY": api_key, "X_API_SECRET": api_secret,
        "X_ACCESS_TOKEN": acc_token, "X_ACCESS_TOKEN_SECRET": acc_secret,
    }.items() if not v]

    if missing:
        log(f"❌ 環境変数が未設定: {', '.join(missing)}")
        return None

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=acc_token,
        access_token_secret=acc_secret,
    )
    try:
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        return tweet_id
    except tweepy.TweepyException as e:
        log(f"❌ ツイート失敗: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=None, help="対象日付 YYYY-MM-DD（省略時は今日JST）")
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容だけ確認")
    parser.add_argument("--force",   action="store_true", help="投稿済みでも再投稿")
    args = parser.parse_args()

    target_date = args.date or get_jst_today()
    log(f"📅 対象日: {target_date}")

    # 投稿済みチェック
    posted_log = load_posted_log()
    if target_date in posted_log and not args.force:
        log(f"✅ {target_date} は投稿済みです（tweet_id: {posted_log[target_date]['tweet_id']}）")
        log("   再投稿する場合は --force を指定してください")
        return

    # データ取得
    entries = load_complete(target_date)
    if not entries:
        log(f"ℹ️  {target_date} のコンプリートデータがありません")
        return

    log(f"📊 {len(entries)}件のコンプリートデータを取得")

    # ツイート本文生成
    tweet_text = build_tweet(entries, target_date)

    log("=" * 50)
    log("📝 投稿内容プレビュー:")
    print(tweet_text)
    log(f"文字数: {len(tweet_text)}")
    log("=" * 50)

    if args.dry_run:
        log("🔍 dry-run モード: 投稿をスキップしました")
        return

    # 投稿
    log("🐦 X に投稿中...")
    tweet_id = post_tweet(tweet_text)

    if tweet_id:
        tweet_url = f"https://x.com/mesiuma77/status/{tweet_id}"
        log(f"✅ 投稿成功！ {tweet_url}")
        # 投稿済みログに記録
        posted_log[target_date] = {
            "tweet_id":  tweet_id,
            "tweet_url": tweet_url,
            "count":     len(entries),
            "posted_at": datetime.now(JST).isoformat(),
        }
        save_posted_log(posted_log)
    else:
        log("❌ 投稿失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
