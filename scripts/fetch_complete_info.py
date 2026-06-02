#!/usr/bin/env python3
from __future__ import annotations
"""
X (Twitter) から店舗アカウントが投稿した「コンプリート」情報を収集して
public/complete_info.json を生成する。

店舗が上げているツイートのみ対象:
  - 台番号（○○番台）が含まれる
  - コンプリート機能 発動/作動
  - おめでとうございます + コンプリート
  - 店舗の挨拶パターン

Usage:
    python scripts/fetch_complete_info.py
    python scripts/fetch_complete_info.py --headless
    python scripts/fetch_complete_info.py --date 2026-05-20
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

COMPLETE_JSON      = Path(__file__).parent.parent / "public/complete_info.json"
RANKING_JSON       = Path(__file__).parent.parent / "public/complete_ranking.json"
PLAYWRIGHT_PROFILE = Path(__file__).parent / ".x_auth_profile"
SESSION_FILE       = Path(__file__).parent / ".x_session.enc"

# ---------------------------------------------------------------------------
# 検索クエリ（店舗投稿に特化）
# ---------------------------------------------------------------------------
COMPLETE_QUERIES = [
    # ══ 【核心クエリ】台番号 × 機能発動系（最高精度）══
    "コンプリート機能発動 番台",
    "コンプリート機能作動 番台",
    "番台 コンプリート機能発動",
    "番台 コンプリート達成",
    "コンプリート達成 番台 スロット",
    "コンプリート おめでとうございます 番台",
    "コンプリート達成おめでとう 番台",

    # ══ 【ハッシュタグ】店舗は公式タグを使う ══
    "#コンプリート機能発動",
    "#コンプリート達成 スロット",
    "#コンプリート機能発動 filter:media",
    "#スマスロ コンプリート 番台",
    "#パチスロ コンプリート 番台",

    # ══ 【スマスロ特化】近年の主流 ══
    "スマスロ コンプリート機能 発動",
    "スマスロ コンプリート おめでとうございます",
    "スマスロ コンプリート 達成 番台",
    "コンプリート機能発動 スマスロ filter:media",

    # ══ 【機種名 × コンプリート】人気上位機種を個別指定 ══
    "東京喰種 コンプリート 番台",
    "からくりサーカス コンプリート 番台",
    "モンキーターン コンプリート 番台",
    "カバネリ コンプリート 番台",
    "ヴァルヴレイヴ コンプリート 番台",
    "北斗転生 コンプリート 番台",
    "北斗 コンプリート機能発動",
    "バジリスク コンプリート 番台",
    "炎炎ノ消防隊 コンプリート 番台",
    "ミリオンゴッド コンプリート 番台",
    "Re:ゼロ コンプリート 番台",
    "転スラ コンプリート 番台",
    "バイオハザード コンプリート 番台",
    "キン肉マン コンプリート 番台",
    "ブルーロック コンプリート 番台",
    "牙狼 コンプリート 番台",
    "攻殻機動隊 コンプリート 番台",
    "チバリヨ コンプリート 番台",
    "吉宗 コンプリート 番台",
    "沖ドキ コンプリート 番台",
    "ゴジラ コンプリート 番台",
    "シャーマンキング コンプリート 番台",
    "ゴッドイーター コンプリート 番台",
    "かぐや様 コンプリート 番台",
    "化物語 コンプリート 番台",
    "アズールレーン コンプリート 番台",
    "戦国乙女 コンプリート 番台",
    "鬼武者 コンプリート 番台",
    "賭ケグルイ コンプリート 番台",

    # ══ 【大手チェーン店名 × コンプリート】店舗直撃 ══
    "ダイナム コンプリート 番台",
    "ダイナム コンプリート機能",
    "#ダイナム コンプリート 番台",
    "ダイナム コンプリート おめでとうございます",
    "マルハン コンプリート 番台",
    "マルハン コンプリート機能発動",
    "キコーナ コンプリート 番台",
    "楽園 コンプリート 番台",
    "ガーデン コンプリート 番台",
    "メガガイア コンプリート 番台",
    "キャッスル コンプリート 番台",
    "コンコルド コンプリート 番台",
    "ZENT コンプリート 番台",
    "メッセ コンプリート 番台",
    "ガイア コンプリート 番台",
    "ミリオン コンプリート 番台",
    "エスパス コンプリート 番台",
    "ワンダーランド コンプリート 番台",
    "ビックマーチ コンプリート 番台",
    "パラッツォ コンプリート 番台",
    "クリエ コンプリート 番台",
    "ジャパン コンプリート 番台",
    "ニューアルファ コンプリート 番台",

    # ══ 【画像付き検索】店舗は必ず画像を添付する ══
    "コンプリート機能発動 filter:media",
    "コンプリート達成 番台 filter:media",
    "コンプリート おめでとうございます filter:media",

    # ══ 【全台・複数台系】 ══
    "全台コンプリート スロット",
    "全台コンプリート 番台",
    "同時コンプリート スロット",

    # ══ 【番台なし・店舗文体対策】 ══
    "コンプリート機能 発動 おめでとう",
    "本日 コンプリート機能 発動",
    "コンプリート 速報 番台",
    "当店 コンプリート機能 発動",
    "当ホール コンプリート 達成",
    "コンプリート達成 スマスロ",
    "コンプリート機能 おめでとうございます",
]

# ---------------------------------------------------------------------------
# 店舗ツイート判定: これらのいずれかを含む = 店舗の投稿
# ---------------------------------------------------------------------------
STORE_TWEET_PATTERNS = [
    re.compile(r'\d{2,4}番台'),                               # 台番号（最強シグナル）
    re.compile(r'コンプリート機能(?:が|を)?(?:発動|作動)'),   # 機能発動/作動（「機能」あり）
    re.compile(r'コンプリート(?:が|を)?(?:発動|作動)'),       # 機能発動/作動（「機能」なし）
    re.compile(r'コンプリート(?:達成)?おめでとうございます'),  # 店舗の祝福メッセージ
    re.compile(r'おめでとうございます.{0,60}コンプリート', re.DOTALL),
    re.compile(r'コンプリート.{0,60}おめでとう', re.DOTALL),  # おめでとうまでの範囲拡大
    re.compile(r'こんばんは.{0,20}(?:店|ホール)', re.DOTALL), # 店舗の挨拶
    re.compile(r'こんにちは.{0,20}(?:店|ホール)', re.DOTALL),
    re.compile(r'お知らせ.{0,30}コンプリート', re.DOTALL),    # お知らせ投稿
    re.compile(r'本日.*コンプリート', re.DOTALL),              # 本日+コンプリート（機能なし対応）
    re.compile(r'該当台は明日から'),                           # DMM公式フレーズ
    re.compile(r'明日朝.*ご遊技'),                             # 店舗の翌日案内
    re.compile(r'#コンプリート機能発動'),                      # ハッシュタグ
    re.compile(r'#コンプリート達成'),
    re.compile(r'全台コンプリート'),                           # 全台コンプリート
    re.compile(r'同時コンプリート'),                           # 同時コンプリート
    re.compile(r'ご来店.*コンプリート|コンプリート.*ご来店', re.DOTALL),
    re.compile(r'コンプリート.{0,80}(?:店|ホール|パーラー)', re.DOTALL),
    re.compile(r'(?:店|ホール|パーラー).{0,80}コンプリート', re.DOTALL),
    re.compile(r'コンプリート達成.*本日|本日.*コンプリート達成', re.DOTALL),
    re.compile(r'(?:当店|弊店|当ホール|自店).{0,50}コンプリート', re.DOTALL),
    re.compile(r'コンプリート.{0,50}(?:当店|弊店|当ホール|自店)', re.DOTALL),
    re.compile(r'低貸.*コンプリート|コンプリート.*低貸', re.DOTALL),
    re.compile(r'2台(?:同時)?.*コンプリート|コンプリート.*2台(?:同時)?', re.DOTALL),
]

# ---------------------------------------------------------------------------
# 除外パターン（個人プレイヤーの投稿）
# ---------------------------------------------------------------------------
EXCLUDE_PATTERNS = [
    re.compile(r'youtube\.com', re.IGNORECASE),
    re.compile(r'生配信|ライブ配信'),
    re.compile(r'ブログ'),
    re.compile(r'ミッションコンプリート'),
    re.compile(r'ガチャ.*コンプ|コンプ.*ガチャ'),
    re.compile(r'コンプリート率が基準値'),
    re.compile(r'コレクション.*コンプ'),
    # ── パチンコ・パチスロ以外のコンプリートを除外 ──────────────────────
    re.compile(r'オリパ.*コンプ|コンプ.*オリパ'),             # TCGオリパ完売
    re.compile(r'トレカ|カードゲーム|TCG'),                   # トレカ店
    re.compile(r'金箱報酬|金箱.*コンプ'),                     # モバイルゲーム系
    re.compile(r'コンプリートまであと\d'),                     # 個人「あと○枚」未達成
    re.compile(r'アーカイブで視聴|配信.*コンプリートおめ'),     # VTuber視聴者コメント
    re.compile(r'プレイヤーLv|ランクアップ|レベルアップ.*コンプ'), # ソシャゲ/ゲーム系
    re.compile(r'フィギュア.*コンプ|コンプ.*フィギュア'),       # フィギュアコレクション
    re.compile(r'スタンプ.*コンプ|コンプ.*スタンプ'),           # スタンプカード
    re.compile(r'読了|クリア.*コンプリート'),                  # 読書・ゲームクリア
    # ── 追加: 明らかにパチンコ・スロット無関係 ───────────────────────────
    re.compile(r'ポケモン|モンスターボール|ポケカ'),            # ポケモン系
    re.compile(r'アイドル.*コンプ|コンプ.*アイドル'),           # アイドルコレクション
    re.compile(r'麻雀.*コンプ|コンプ.*麻雀'),                  # 麻雀
    re.compile(r'メダルゲーム(?!.*パチ)'),                     # メダルゲーム（パチ関係なし）
    re.compile(r'クレーンゲーム|UFOキャッチャー'),              # クレーンゲーム
    re.compile(r'ダーツ.*コンプ|ビリヤード.*コンプ'),           # ダーツ等
    re.compile(r'カプセル.*コンプ|ガチャポン.*コンプ'),         # カプセルトイ
    re.compile(r'(?:^|\s)RT\s'),                               # RTで始まるリツイートっぽい投稿
    # ── 個人の不満・皮肉投稿を除外 ───────────────────────────────────────────
    re.compile(r'逆コンプリート'),                                      # 「逆コンプリート達成」= 個人の負け自虐投稿
    # ── コンプリート未達成を除外 ────────────────────────────────────────────
    re.compile(r'コンプリートならず|コンプリートできず|コンプリートしなかった|惜しくもコンプ'),
    re.compile(r'あと一歩.*コンプリート|コンプリート.*あと一歩'),
    re.compile(r'コンプリートまで惜しかった|惜しかったですね.{0,10}コンプ|コンプリートは惜しくも'),
    re.compile(r'コンプリートまで あと|コンプリートまであと少し|あと少しでコンプリート|コンプリートまで少し'),
    # ── 過去日まとめ・ランキング紹介投稿を除外 ─────────────────────────────
    re.compile(r'\d+万発.*まとめ|\d+/\d+[|｜].*まとめ'),      # 「05/07｜5万発まとめ」等
    re.compile(r'\d+月\d+日.*出玉ランキング|出玉ランキング.*\d+位'), # 出玉ランキングまとめ
    re.compile(r'ランキングをご紹介|週目までのランキング|今週のコンプリートランキング'),  # 週次まとめ紹介
]

# ---------------------------------------------------------------------------
# 機種名抽出パターン（優先度順）
# ---------------------------------------------------------------------------
MACHINE_PATTERNS = [
    # 【機種名】コンプリート 形式（括弧内）
    re.compile(r'[『「【]([^』」】]{3,30})[』」】](?:にて|で|の)?(?:コンプリート|コンプ)'),
    # ASCII角括弧 [L機種名] / [e機種名] の全文抽出（L鋼鉄城のカバネリ 海門決戦 等）
    re.compile(r'\[([LＬeｅ][^\]\n]{4,35})\]'),
    # スマスロ【機種名】 形式（括弧付き）
    re.compile(r'(?:スマスロ|Lパチスロ|パチスロ|スマパチ)\s*[【「]([^】」]{3,25})[】」]'),
    # スマスロ 機種名 形式
    re.compile(r'(?:スマスロ|Lパチスロ|パチスロ|スマパチ)\s*[　]?([^\s　\n#「」【】、。]{3,25}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|\d+番台))'),
    # L北斗の拳転生（汎用Lパターンは「の」で早期停止するため先に専用パターンを置く）
    re.compile(r'([LＬ]北斗の拳[　\s]*転生(?:の章[２2Ⅱ]?)?)'),
    # L機種名（半角・全角両対応 — プレフィックス込みでキャプチャ）
    re.compile(r'([LＬ][^\s　\n#「」【】、。]{2,19}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|\d+番台|』|」|】))'),
    # e機種名（プレフィックス込み — 『e機種名』・【e機種名】・e機種名\s全形式対応）
    re.compile(r'([eｅ][^\s　\n#「」【】、。（(』]{2,19}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|（|\d+番台|』|」|】))'),
    # e機種名 バージョン番号 番台 形式（例: eカケグルイ 7500ver 219番台）
    re.compile(r'([eｅ][^\s　\n#「」【】、。（(』]{2,20})\s+\S{2,10}\s+(?=\d{2,4}番台)'),
    # e機種名　バージョン がコンプリート形式（全角スペース区切り: eカケグルイ　7500ver がコンプリート）
    re.compile(r'([eｅ][^\s　\n#「」【】、。（(』]{2,20})[　\s]\S{2,15}[　\s]が(?:コンプリート|コンプ|達成)'),
    # e機種名（スペースあり、スペース込みで取れない場合の補完）
    re.compile(r'[eｅ]\s+([^\s　\n#「」【】、。（(』]{3,25}?)(?=\s*(?:にて|で|の|が|コンプ|達成|機能|\n|$|（|\d+番台))'),
    re.compile(r'\d{2,4}番台\s*(?:の\s*)?[^\s\n]{0,3}?([^\s\n#]{3,25}?)(?=\s*(?:にて|で|が|コンプ|\n))'),
    re.compile(r'(北斗[^\s　\n#「」【】、。！!]{1,15})'),
    re.compile(r'(バジリスク[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(ミリオンゴッド[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(東京喰種[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(ヴァルヴレイヴ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(炎炎ノ消防隊[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(攻殻機動隊[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(カバネリ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(モンスターハンター[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(リコリス[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(ゾンビランドサガ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(ジャグラー[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(牙狼[^\s　\n#「」【】、。！!]{0,15})'),
    re.compile(r'(チバリヨ[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(真打吉宗[^\s　\n#「」【】、。！!]{0,5})'),  # 真打吉宗（より長いパターンを先に）
    re.compile(r'(吉宗[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(鉄拳[^\s　\n#「」【】、。！!]{0,10})'),
    re.compile(r'(からくりサーカス[^\s　\n#「」【】、。！!]{0,10})'),
]

# ---------------------------------------------------------------------------
# 店舗名抽出パターン
# ---------------------------------------------------------------------------
STORE_PATTERNS = [
    # 挨拶パターン
    re.compile(r'こんばんは\s*([^\s　\n「」、。！!]{2,20}(?:店|ホール))(?:です|でございます)'),
    re.compile(r'こんにちは\s*([^\s　\n「」、。！!]{2,20}(?:店|ホール))(?:です|でございます)'),
    # 「この後も #店名 で」「#店名 です」形式（店/ホール不要）
    re.compile(r'(?:この後も|当店|当ホール)\s*#([^\s　\n#「」【】、。！!]{2,20})\s*(?:で|です)'),
    re.compile(r'(?:ぜひ|是非)\s*#([^\s　\n#「」【】、。！!]{2,20})\s*(?:へ|に|で)'),
    # ハッシュタグ: 大手チェーン名（店/ホールなし）
    re.compile(r'#((?:キャッスル|ガーデン|マルハン|キコーナ|ダイナム|アミューズ|コンコルド|ワンダーランド|ビックマーチ|ミリオン|楽園|Dステーション|メッセ|クリエ|グランド|ゴールド|スクェア|フェイス|ニューアルファ|ジャパン|コスモ|エスパス|スーパーUSA|ライラック|ガイア|フラミンゴ|ZENT|ゼント)[^\s　\n#「」【】、。！!]{0,15})'),
    # ハッシュタグ: 店/ホール付き
    re.compile(r'#([^\s　\n#「」【】、。！!]{2,20}(?:店|ホール|パーラー))'),
    # 大手チェーン名をテキスト内で直接マッチ
    re.compile(r'(マルハン[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(キコーナ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(楽園[^\s　、。！!\n]{0,15}(?:店|ホール))'),
    re.compile(r'(ダイナム[^\s　、。！!\n]{0,25}(?:店|ホール|南口|北口|東口|西口)?)'),
    re.compile(r'(キャッスル[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(アミューズ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(Ｄステーション|Dステーション[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(コンコルド[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ワンダーランド[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ビックマーチ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ミリオン[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(メッセ[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'(クリエ[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'(グランキコーナ[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(メガフェイス[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'(ZENT|ゼント[^\s　、。！!\n]{0,15}(?:店|ホール)?)'),
    re.compile(r'([^\s　\n「」【】]{2,15}(?:パチンコ|スロット)[^\s　、。！!\n]{0,10}(?:店|ホール))'),
    re.compile(r'([^\s　\n「」【】、。！!]{2,15}(?:店|ホール))(?:です|でございます|より|です♪|でした|です！)'),
]

STORE_NG = ["ご来店", "来店", "閉店", "景品", "感謝", "毎日", "通常", "本日の遊技", "空台",
            "ミリオンゴッド", "ゴッド", "ヴァルヴレイヴ", "バジリスク", "北斗の拳", "炎炎ノ消防隊",
            "攻殻機動隊", "カバネリ", "モンスターハンター", "ジャグラー", "牙狼", "吉宗", "鉄拳"]


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _fernet_key(raw_key: str) -> bytes:
    import base64, hashlib
    return base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest())


def _save_session(ctx) -> None:
    """ブラウザコンテキストから auth_token / ct0 を取り出し、暗号化してファイルに保存する。"""
    encrypt_key = os.environ.get("COOKIE_ENCRYPT_KEY", "")
    if not encrypt_key:
        return
    try:
        from cryptography.fernet import Fernet
        cookies = ctx.cookies("https://x.com")
        session = {c["name"]: c["value"] for c in cookies if c["name"] in ("auth_token", "ct0")}
        if len(session) < 2:
            log("⚠️  セッション保存スキップ（auth_token / ct0 が取得できず）")
            return
        encrypted = Fernet(_fernet_key(encrypt_key)).encrypt(json.dumps(session).encode())
        SESSION_FILE.write_bytes(encrypted)
        log(f"🔐 セッションを暗号化して保存: {SESSION_FILE.name}")
    except Exception as e:
        log(f"⚠️  セッション保存エラー: {e}")


def _load_session_cookies() -> list[dict]:
    """暗号化されたセッションファイルからクッキーを復元する。"""
    encrypt_key = os.environ.get("COOKIE_ENCRYPT_KEY", "")
    if not encrypt_key or not SESSION_FILE.exists():
        return []
    try:
        from cryptography.fernet import Fernet
        decrypted = json.loads(Fernet(_fernet_key(encrypt_key)).decrypt(SESSION_FILE.read_bytes()))
        auth_token = decrypted.get("auth_token", "")
        ct0        = decrypted.get("ct0", "")
        if not auth_token or not ct0:
            return []
        log("🔑 暗号化セッションファイルからクッキーを復元")
        return [
            {"name": "auth_token", "value": auth_token,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0", "value": ct0,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ]
    except Exception as e:
        log(f"⚠️  セッション復元エラー: {e}")
        return []


def _get_cookies() -> list[dict]:
    """
    優先順位: 環境変数(X_AUTH_TOKEN/X_CT0) → 暗号化セッションファイル → Chrome cookie
    """
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0        = os.environ.get("X_CT0", "")

    if auth_token and ct0:
        log("🔑 環境変数からXのcookieを注入（CI環境）")
        return [
            {"name": "auth_token", "value": auth_token,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
            {"name": "ct0", "value": ct0,
             "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"},
        ]

    # 暗号化セッションファイルから復元
    session_cookies = _load_session_cookies()
    if session_cookies:
        return session_cookies

    if not HAS_BROWSER_COOKIE3:
        return []
    result = []
    try:
        jar = browser_cookie3.chrome(domain_name=".x.com")
        for c in jar:
            pw_cookie: dict = {
                "name": c.name, "value": c.value,
                "domain": c.domain if c.domain else ".x.com",
                "path": c.path or "/", "secure": bool(c.secure),
                "httpOnly": False, "sameSite": "None",
            }
            if c.expires:
                pw_cookie["expires"] = int(c.expires)
            result.append(pw_cookie)
        log(f"🍪 Chrome cookie {len(result)}個取得")
    except Exception as e:
        log(f"⚠️  browser_cookie3: {e}")
    return result


def _login_with_credentials(page, username: str, password: str) -> bool:
    """
    X_AUTH_TOKEN/X_CT0 が切れた場合にユーザー名+パスワードで再ログインする。
    成功したら True を返す。
    """
    log("🔐 クッキー切れ検出 — ユーザー名/パスワードで再ログインを試みます...")
    try:
        page.goto("https://x.com/i/flow/login", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # ① ユーザー名入力
        user_input = page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
        user_input.fill(username)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        # ② 「不審なアクティビティ」確認 (電話/メール入力) が挟まる場合
        verify_input = page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
        if verify_input:
            log("⚠️  追加確認画面を検出 — ユーザー名で突破を試みます")
            verify_input.fill(username)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)

        # ③ パスワード入力
        pw_input = page.wait_for_selector('input[name="password"]', timeout=10000)
        pw_input.fill(password)
        page.keyboard.press("Enter")
        page.wait_for_timeout(6000)

        cur_url = page.url.lower()
        if "login" not in cur_url and "flow" not in cur_url:
            log("✅ 再ログイン成功")
            return True
        log(f"❌ 再ログイン失敗 (url={page.url})")
        return False
    except Exception as e:
        log(f"❌ 再ログインエラー: {e}")
        return False


def launch_browser(playwright, headless: bool):
    PLAYWRIGHT_PROFILE.mkdir(parents=True, exist_ok=True)
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        locale="ja-JP",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    cookies = _get_cookies()
    if cookies:
        ctx.add_cookies(cookies)
        log(f"✅ Cookie {len(cookies)}個注入")
    return ctx


def is_store_tweet(text: str) -> bool:
    """店舗アカウントの投稿かどうか判定"""
    # 改行を空白に正規化（除外パターンが改行をまたいで効かない問題を防ぐ）
    normalized = text.replace("\n", " ").replace("\r", " ")
    # 除外パターンに引っかかるものはスキップ
    for pat in EXCLUDE_PATTERNS:
        if pat.search(normalized):
            return False
    # 店舗投稿パターンのどれかにマッチ
    return any(pat.search(normalized) for pat in STORE_TWEET_PATTERNS)


# ---------------------------------------------------------------------------
# 機種タイプ判定（パチスロ / パチンコ）
# ---------------------------------------------------------------------------

# L/Ｌ プレフィックス = スマスロ（パチスロ）
_SMASLO_PREFIX = re.compile(r'^[LＬ][^\s]')

# e/ｅ プレフィックス = スマパチ（パチンコ）
_SMAPACHI_PREFIX = re.compile(r'^[eｅ][^\s]')

# CR プレフィックス = パチンコ
_CR_PREFIX = re.compile(r'^CR')

# パチスロキーワード（L/eプレフィックスなしの機種名に使用）
_SLOT_KEYWORDS = [
    "スマスロ", "Lパチスロ", "パチスロ", "北斗", "ヴァルヴレイヴ", "ミリオンゴッド",
    "攻殻機動隊", "炎炎ノ消防隊", "東京喰種", "カバネリ", "バジリスク",
    "モンスターハンター", "リコリス", "ゾンビランドサガ", "ジャグラー",
    "チバリヨ", "吉宗", "鉄拳", "まどマギ", "鬼武者", "エウレカ",
    "Re:ゼロ", "転スラ", "バイオハザード", "ブルーロック", "からくりサーカス",
]

# パチンコキーワード（eプレフィックスなしでも判定できるもの）
_PACHINKO_KEYWORDS = [
    "牙狼", "スマパチ", "大当たり", "確変", "甘デジ",
    "ミドル", "ライトミドル", "右打ち",
]


def get_machine_type(machine: str) -> str:
    """機種名からパチスロ(slot) / パチンコ(pachinko) を判定する。デフォルト: slot。

    優先順位:
    1. L/Ｌ プレフィックス → スマスロ (slot)
    2. e/ｅ プレフィックス → スマパチ (pachinko)
    3. CR プレフィックス  → パチンコ (pachinko)
    4. パチンコキーワード → pachinko
    5. スロットキーワード → slot
    6. デフォルト        → slot
    """
    if not machine:
        return "slot"
    # 括弧類（『「【〔[(）を先頭から除いてプレフィックスを判定
    m = re.sub(r'^[『「【〔\[\(（]+', '', machine.strip())

    # 1. L/Ｌ プレフィックス = スマスロ（スロット）
    if _SMASLO_PREFIX.match(m):
        return "slot"

    # 2. e/ｅ プレフィックス = スマパチ（パチンコ）
    if _SMAPACHI_PREFIX.match(m):
        return "pachinko"

    # 3. CR プレフィックス = パチンコ
    if _CR_PREFIX.match(m):
        return "pachinko"

    # 4. パチンコキーワード
    for kw in _PACHINKO_KEYWORDS:
        if kw in m:
            return "pachinko"

    # 5. スロットキーワード
    for kw in _SLOT_KEYWORDS:
        if kw in m:
            return "slot"

    return "slot"


def extract_machine(text: str) -> str:
    # 前処理: 「北斗の拳」と「転生」の間の空白（半角・全角）を除去
    # 例: "スマスロ北斗の拳　転生の章２" → "スマスロ北斗の拳転生の章２"
    text = re.sub(r'(北斗の拳)[　\s]+(転生)', r'\1\2', text)
    # 炎炎の消防隊（ひらがなの・半角ﾉ → カタカナノ）
    text = re.sub(r'炎炎[のﾉ]消防隊', '炎炎ノ消防隊', text)
    for pat in MACHINE_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if len(name) < 2 or re.match(r'^[#@\s!！]+$', name):
                continue
            if "http" in name.lower():
                continue
            if name in ("スロ", "パチスロ", "スマスロ", "スマパチ", "コンプリート"):
                continue
            # 英数字・記号のみ（日本語文字なし）はXのユーザー名等の誤抽出として除外
            if re.match(r'^[a-zA-Z0-9_\-\.\@\#\s]+$', name):
                continue
            # 先頭の開き括弧を除去（例: 【炎炎ノ消防隊2 → 炎炎ノ消防隊2）
            name = re.sub(r'^[『「【（(]+', '', name).strip()
            # 末尾の閉じ括弧を除去（例: 牙狼12黄金騎士極限』 → 牙狼12黄金騎士極限）
            name = re.sub(r'[』」】）)]+$', '', name).strip()
            if len(name) < 2:
                continue
            # 末尾の助詞・接続詞を除去（例: カバネリ海門決戦から → カバネリ海門決戦）
            name = re.sub(r'(から|にて|より|での|への|として|まで|にて|っ|て|が|は|で|に|を|も|と|の)+$', '', name).strip()
            # 「から一撃」「から速報」等の余分なテキストを除去
            name = re.sub(r'から[一-龠ぁ-んァ-ン]{1,4}$', '', name).strip()
            if len(name) < 2:
                continue
            # ポイント・枚数・玉数の混入を除去（例: 攻殻機動隊/19,010Pt.）
            name = re.sub(r'[/／]\s*[\d,]+(?:Pt\.|pt\.|枚|点|玉).*$', '', name).strip()
            name = re.sub(r'\s+[\d,]+(?:Pt\.|pt\.|枚|点|玉).*$', '', name).strip()
            name = re.sub(r'[\s/／]+$', '', name).strip()
            # 末尾のバージョン番号を除去（例: eカケグルイ7500ver → eカケグルイ）
            name = re.sub(r'\d{3,6}[Vvｖ][Eeｅ][Rrｒ]$', '', name).strip()
            name = re.sub(r'[Vvｖ][Eeｅ][Rrｒ]\d{1,4}$', '', name).strip()
            if len(name) < 2:
                continue
            # 「コンプリート達成」等が機種名に混入した場合に除去（例: 牙狼コンプリート達成 → 牙狼）
            name = re.sub(r'コンプリート.*$', '', name).strip()
            if len(name) < 2:
                continue
            # 明らかに機種名でない語句を除外（番台パターン等の誤抽出防止）
            _MACHINE_EXTRACT_NG = {
                "お客様", "お客様より", "閉店間際になんと", "なんと２台同時",
                "18000枚Over", "18,000枚Over", "お客様も大変", "不明",
            }
            if name in _MACHINE_EXTRACT_NG:
                continue
            # 「おめでとうございます」「オススメ機種」等の非機種名フレーズを除外
            _MACHINE_NG_PATTERNS = [
                re.compile(r'^おめでとう'),
                re.compile(r'オススメ機種|おすすめ機種|今週のオススメ|今週おすすめ'),
                re.compile(r'^本日.*台目$|^本日もコンプ|^本日のMVP'),
                re.compile(r'誠におめ|ございます[！!]*$'),
            ]
            if any(p.search(name) for p in _MACHINE_NG_PATTERNS):
                continue
            return name[:35]
    return ""


def extract_store(text: str) -> str:
    for pat in STORE_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            # ── 先頭の【公式】【NEW】等メタデータを除去
            name = re.sub(r'^【[^】]{0,8}】\s*', '', name).strip()
            # ── 末尾の【公式】【チェーン名】等を除去
            name = re.sub(r'\s*【[^】]{0,12}】$', '', name).strip()
            # ── "つじちゃん店長@店舗名" 形式: @以降の店舗名を優先
            at_match = re.search(r'@([^\s@]{3,20}(?:店|ホール|パーラー|ランド))', name)
            if at_match:
                name = at_match.group(1)
            else:
                # ── @ハンドル・@タグを削除（"聖地ウエスタン西葛西店@新店長" → "ウエスタン西葛西店"）
                name = re.sub(r'@\S+', '', name).strip()
                # ── 先頭の役職・ニックネーム部分を除去（"聖地"等の余分なプレフィックス）
                name = re.sub(r'^[^\s]{1,4}(?=\S+(?:店|ホール|パーラー))', '', name).strip() \
                       if re.search(r'(?:店|ホール|パーラー)', name) else name
            # ── 末尾の不要語・助詞を除去
            name = re.sub(
                r'(です|でした|でございます|ございます|より|ます|ました|ください|'
                r'させていただ|から|へ|では|として|にて|でお|は創業|周年).*$',
                '', name
            ).strip()
            if len(name) < 3:
                continue
            if any(ng in name for ng in STORE_NG):
                continue
            if re.match(r'^\d', name):
                continue
            return name[:28]
    return ""


def extract_slot_number(text: str) -> str:
    """台番号を抽出（全角数字も対応）"""
    m = re.search(r'(\d{2,4})番台', text)
    if not m:
        return ""
    s = m.group(1)
    return s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))


def extract_date_from_text(text: str, posting_date: str) -> str:
    """
    ツイートテキスト内の「5/24(日)」「5月24日(土)」形式の日付を抽出し、
    ツイート投稿日と近ければ（±3日）その日付を返す。
    抽出できなければ posting_date をそのまま返す。
    """
    if not posting_date:
        return posting_date
    # 曜日付きパターン優先（確実性が高い）: "5/24(日)" "5月24日(土)" 等
    # 曜日なしも許容するが括弧なし単独数字は誤検知しやすいので曜日必須
    m = re.search(r'(\d{1,2})[/月](\d{1,2})(?:日)?[（(][日月火水木金土][）)]', text)
    if not m:
        return posting_date
    mo_text, dy_text = int(m.group(1)), int(m.group(2))
    # 基準年: ツイート投稿年
    post_yr = int(posting_date[:4])
    for yr in [post_yr, post_yr - 1]:
        try:
            from datetime import date as _date, timedelta
            candidate = _date(yr, mo_text, dy_text)
            posting   = _date.fromisoformat(posting_date)
            if abs((posting - candidate).days) <= 3:
                return candidate.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return posting_date


def get_tweet_datetime(article) -> tuple[str, str]:
    """Xの<time datetime="...">からJSTの (date, time) を取得して返す"""
    from datetime import date as _date, timedelta as _td
    try:
        time_el = article.query_selector("time")
        if time_el:
            dt = time_el.get_attribute("datetime") or ""
            if dt:
                # "2026-05-20T13:30:00.000Z" → JST date + time
                m = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', dt)
                if m:
                    yr, mo, dy, h, mn = (int(x) for x in m.groups())
                    # UTC → JST (+9h)
                    h += 9
                    if h >= 24:
                        h -= 24
                        d = _date(yr, mo, dy) + _td(days=1)
                        return d.strftime("%Y-%m-%d"), f"{h:02d}:{mn:02d}"
                    return f"{yr}-{mo:02d}-{dy:02d}", f"{h:02d}:{mn:02d}"
    except Exception:
        pass

    # <time> 取得失敗時: 相対時間テキスト（"1時間前"等）から推定
    try:
        time_el = article.query_selector("time")
        if time_el:
            rel = time_el.inner_text().strip()  # 例: "1時間前", "昨日", "5月26日"
            from datetime import timezone as _tz
            JST = _tz(_td(hours=9))
            now_jst = datetime.now(JST)
            # "昨日" → yesterday
            if "昨日" in rel:
                d = (now_jst - _td(days=1)).date()
                return d.strftime("%Y-%m-%d"), ""
            # "N時間前" (N=1..23) → same day or yesterday
            m2 = re.search(r'(\d+)時間前', rel)
            if m2:
                hours_ago = int(m2.group(1))
                d = (now_jst - _td(hours=hours_ago)).date()
                return d.strftime("%Y-%m-%d"), (now_jst - _td(hours=hours_ago)).strftime("%H:%M")
            # "N分前" → same day
            m3 = re.search(r'(\d+)分前', rel)
            if m3:
                mins_ago = int(m3.group(1))
                d = (now_jst - _td(minutes=mins_ago)).date()
                return d.strftime("%Y-%m-%d"), (now_jst - _td(minutes=mins_ago)).strftime("%H:%M")
    except Exception:
        pass

    return "", ""


AUTHOR_NG = ["コンプリート", "パチスロ", "スロット", "パチンコ", "スマスロ", "速報", "まとめ", "情報", "bot"]

# ── ハンドル → 正規店舗名マップ（main()で store_handles.json から読み込む）
_HANDLE_TO_STORE: dict[str, str] = {}
# ── ハンドル → 店舗info dict（type/x_url/store等 — store_handles.json の全フィールド）
_HANDLE_TO_INFO: dict[str, dict] = {}


def _clean_author_name(name: str) -> str:
    """Twitter表示名から余分な装飾を除去して店舗名を取り出す"""
    # ── "ニックネーム＠店舗名" 形式: ＠以降が店舗名っぽければそちらを優先 ──
    at_store = re.search(r'[＠@]([^\s＠@]{3,20}(?:店|ホール|パーラー|ランド|スペース|パレス|センター))', name)
    if at_store:
        return at_store.group(1)[:28]
    # 先頭の【公式】等を除去
    name = re.sub(r'^【[^】]{0,10}】\s*', '', name).strip()
    # 末尾の【公式】【NEW】等を除去
    name = re.sub(r'\s*【[^】]{0,12}】\s*$', '', name).strip()
    # ＠役職X / @役職X などの役職タグを除去
    name = re.sub(r'[＠@]\S*(役職|担当|担|公式|official|Official)\S*', '', name, flags=re.IGNORECASE).strip()
    # 「@Since.1991」「 SINCE 2005.01.22」「【公式】SINCE...」「～Since～YYYY」形式を除去
    # 【...】SINCE... / @Since... / (space)SINCE... / ～Since～... のいずれかを除去
    name = re.sub(r'(?:【[^】]{0,12}】|[＠@]|[　\s])\s*(?:SINCE|Since|since)[\s\.\-/\d]+.*$', '', name).strip()
    name = re.sub(r'[　\s]*～Since～.*$', '', name).strip()
    # 末尾の「@xxx」「＠xxx」を除去（Since除去後の残存@含む）
    name = re.sub(r'[＠@]\S+$', '', name).strip()
    name = re.sub(r'[＠@]\s*$', '', name).strip()
    # アプリ宣伝系フレーズを除去
    name = re.sub(r'(アプリ|データ確認|はこちら|登録は|ご利用).{0,30}$', '', name).strip()
    # 先頭の絵文字を除去
    name = re.sub(r'^[\U0001F300-\U0001FFFF\U00002600-\U000027FF]+\s*', '', name).strip()
    # 末尾の【公式】等を再度除去（SINCE除去後に残った場合のため）
    name = re.sub(r'\s*【[^】]{0,12}】\s*$', '', name).strip()
    return name[:28]


def _is_store_name(name: str) -> bool:
    """表示名が店舗名っぽいかどうか"""
    if len(name) < 3 or len(name) > 30:
        return False
    if any(ng in name for ng in AUTHOR_NG):
        return False
    return bool(re.search(r'店|ホール|パーラー|PALACE|palace|ランド|マルハン|キコーナ|ダイナム', name))


def parse_tweet(text: str, tweet_url: str,
                today_str: str, tweet_date: str, tweet_time: str,
                author_name: str = "") -> dict | None:
    if not is_store_tweet(text):
        return None

    # ── ハンドルから既知店舗名を優先使用（最高精度・誤抽出ゼロ）
    store = ""
    is_known_store_handle = False
    handle_match = re.search(r'x\.com/([^/]+)/status', tweet_url)
    if handle_match:
        handle = handle_match.group(1).lower()
        if handle in _HANDLE_TO_STORE:
            store = _HANDLE_TO_STORE[handle]
            is_known_store_handle = True

    if not store:
        store = extract_store(text)

    # author_name の装飾を除去（既知ハンドルから店舗名を取得した場合はスキップ）
    clean_author = _clean_author_name(author_name) if author_name else ""

    # ── チェーン名のみ（支店名なし）で取れた場合は author_name を優先 ──
    # 例: "#ダイナム" → "ダイナム" のみ → author_name "ダイナム長野上田店" を使う
    CHAIN_ONLY = {"ダイナム", "マルハン", "キコーナ", "楽園", "ガイア", "キャッスル",
                  "アミューズ", "コンコルド", "ワンダーランド", "ビックマーチ", "ミリオン",
                  "エスパス", "ガーデン", "ゼント", "ZENT", "メッセ", "クリエ"}
    if store in CHAIN_ONLY and clean_author and len(clean_author) > len(store):
        if _is_store_name(clean_author) or re.search(r'店|ホール', clean_author):
            store = clean_author

    # テキストから取れなければ作者の表示名を使う（店舗名と確認できる場合のみ）
    if not store and clean_author and _is_store_name(clean_author):
        store = clean_author

    # ── 未知ハンドル × 店舗名未確定 → お客様・PR投稿として除外 ────────────────
    # 既知店舗ハンドル以外からのツイートは、店舗名がテキスト/author_name から
    # 確実に特定できた場合のみ受け入れる（個人アカウント・インフルエンサー対策）
    if not store and not is_known_store_handle:
        return None
    # 既知ハンドルだが store が未設定の場合は _HANDLE_TO_STORE から補完
    if not store and is_known_store_handle and handle_match:
        resolved = _HANDLE_TO_STORE.get(handle_match.group(1).lower(), "")
        if resolved:
            store = resolved
    machine = extract_machine(text)
    slot_number = extract_slot_number(text)

    # 機種名も店舗名も台番号も取れないものは除外
    if not machine and not store and not slot_number:
        return None

    # Xの<time>から取得した日付を使う（取得できなければ収集日を推定）
    if not tweet_date:
        # 深夜（JST 00:00-05:59）に実行中の場合は前日の方が確率が高い
        from datetime import timezone as _tz, timedelta as _td
        JST = _tz(_td(hours=9))
        now_jst = datetime.now(JST)
        if now_jst.hour < 6:
            from datetime import date as _d
            tweet_date = (_d.fromisoformat(today_str) - _td(days=1)).strftime("%Y-%m-%d")
        else:
            tweet_date = today_str

    # テキスト内に「5/24(日)」等の曜日付き日付があればそちらを優先
    # （日付変わり後に前日のコンプリートを投稿するケースに対応）
    tweet_date = extract_date_from_text(text, tweet_date)

    # 深夜0〜5時の投稿はテキスト内に日付言及がなければ前日扱い
    # 例: 5/28 00:04 投稿 → 5/27 のコンプリート報告
    if tweet_time and tweet_date:
        h_str = tweet_time.split(":")[0]
        if h_str.isdigit() and 0 <= int(h_str) < 6:
            from datetime import date as _d2, timedelta as _td2
            backdated = (_d2.fromisoformat(tweet_date) - _td2(days=1)).strftime("%Y-%m-%d")
            # テキストに日付の明示がなければバックデート
            if not re.search(r'\d+[/月]\d+', text):
                tweet_date = backdated

    # テキストに「昨日」が含まれ、コンプリートと近接する場合は前日扱い
    # 例: 「昨日 252番台 eカケグルイ がコンプリート達成」→ 投稿日の前日
    if tweet_date and not re.search(r'\d+[/月]\d+', text):
        if re.search(r'昨日.{0,60}(?:コンプリート|コンプ|番台)', text, re.DOTALL) or \
           re.search(r'(?:コンプリート|コンプ|番台).{0,60}昨日', text, re.DOTALL):
            from datetime import date as _d3, timedelta as _td3
            tweet_date = (_d3.fromisoformat(tweet_date) - _td3(days=1)).strftime("%Y-%m-%d")

    entry_id = hashlib.md5(tweet_url.encode()).hexdigest()[:12]

    # ── 投稿元アカウント種別 + 店舗 X リンクを解決 ──────────────────────────
    # 優先順: store_official(公式) > store_manager(店長) > unknown
    source_account_type = "unknown"
    store_x_url_val     = ""
    manager_x_url_val   = ""
    store_handle_val    = ""
    if handle_match:
        _h = handle_match.group(1).lower()
        store_handle_val = _h
        _info = _HANDLE_TO_INFO.get(_h)
        if _info:
            _htype = _info.get("type", "store")
            _hxurl = _info.get("x_url", f"https://x.com/{_h}")
            if _htype == "manager":
                source_account_type = "store_manager"
                manager_x_url_val   = _hxurl
            else:
                source_account_type = "store_official"
                store_x_url_val     = _hxurl

    return {
        "id": entry_id,
        "date": tweet_date,
        "time": tweet_time,                          # JST HH:MM
        "store": store,
        "machine": machine,
        "machine_type": get_machine_type(machine),   # "slot" or "pachinko"
        "slot_number": slot_number,                  # 台番号
        "text": text[:250].replace("\n", " "),
        "x_url": tweet_url,
        "store_handle":         store_handle_val,
        "store_x_url":          store_x_url_val,
        "manager_x_url":        manager_x_url_val,
        "source_account_type":  source_account_type,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def scrape_query(page, query: str, today_str: str, max_tweets: int = 400) -> list[dict]:
    results = []
    seen_urls: set[str] = set()

    # 7日前〜翌日を収集（GitHub Actions 停止・週末・深夜・インデックス漏れを広くカバー）
    from datetime import date as _dt, timedelta
    since_date = (_dt.fromisoformat(today_str) - timedelta(days=7)).strftime("%Y-%m-%d")
    until_date = (_dt.fromisoformat(today_str) + timedelta(days=1)).strftime("%Y-%m-%d")
    # -filter:retweets で RT を除外し、店舗の原投稿に絞る
    date_filter = f" since:{since_date} until:{until_date} -filter:retweets"
    encoded = (query + date_filter).replace(" ", "%20").replace("#", "%23")
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        log(f"  ⏱ Timeout: {query}")
        return results

    # ─── ログインページへのリダイレクト検出 ───────────────────────────────
    redir_url = page.url.lower()
    if "login" in redir_url or "/flow/" in redir_url or "twitter.com/i/flow" in redir_url:
        raise RuntimeError("LOGIN_REQUIRED")

    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
    except PlaywrightTimeout:
        pass

    # ページ初期レンダリング完了まで少し待つ
    page.wait_for_timeout(1500)

    # 30回スクロール: wheel距離5000px × 30回 = 合計150,000px分
    for _ in range(30):
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(200)

    articles = page.query_selector_all('article[data-testid="tweet"]')

    for article in articles[:max_tweets]:
        try:
            text = ""
            for sel in ['[data-testid="tweetText"]', '[lang]']:
                el = article.query_selector(sel)
                if el:
                    t = el.inner_text()
                    if len(t) > 10:
                        text = t
                        break

            tweet_url = ""
            time_el = article.query_selector("time")
            if time_el:
                href = time_el.evaluate("el => el.closest('a') ? el.closest('a').href : ''")
                if href and "status" in href:
                    tweet_url = href
            if not tweet_url:
                for lnk in article.query_selector_all('a[href*="/status/"]'):
                    href = lnk.get_attribute("href") or ""
                    if "/status/" in href:
                        tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                        break

            if not tweet_url or tweet_url in seen_urls:
                continue
            seen_urls.add(tweet_url)

            tweet_date, tweet_time = get_tweet_datetime(article)
            # 作者表示名を取得（ツイートカードのUser-Name）
            author_name = ""
            try:
                author_el = article.query_selector('[data-testid="User-Name"] span')
                if author_el:
                    author_name = author_el.inner_text().strip()
            except Exception:
                pass
            entry = parse_tweet(text, tweet_url, today_str, tweet_date, tweet_time, author_name)
            if entry:
                # 画像URL取得（pbs.twimg.com の画像のみ・プロフィール画像除外）
                images: list[str] = []
                try:
                    img_els = article.query_selector_all('img[src*="pbs.twimg.com"]')
                    for img_el in img_els[:4]:
                        src = img_el.get_attribute("src") or ""
                        if not src or "profile_images" in src:
                            continue
                        # クエリパラメータを高解像度に統一
                        src = re.sub(r'\?.*$', '', src) + "?format=jpg&name=large"
                        if src not in images:
                            images.append(src)
                except Exception:
                    pass
                if images:
                    entry["images"]    = images
                    entry["image_url"] = images[0]

                results.append(entry)
                store_label   = entry["store"] or "店舗不明"
                machine_label = entry["machine"] or "機種不明"
                slot          = f" [{entry['slot_number']}番台]" if entry["slot_number"] else ""
                img_flag      = " 🖼" if images else ""
                log(f"    ✅ {store_label} / {machine_label}{slot} {entry['time']}{img_flag}")

        except Exception:
            continue

    return results


def scrape_timeline(page, handle: str, today_str: str) -> list[dict]:
    """店舗アカウントのタイムラインを直接収集（X search のインデックス漏れ補完）。

    X検索は全ツイートをインデックスしていないため、検索経由では漏れが生じる。
    タイムライン直接収集は検索インデックスに依存しないので、実績店舗からの漏れを防ぐ。
    """
    from datetime import date as _dt, timedelta
    results = []
    seen_urls: set[str] = set()

    url = f"https://x.com/{handle}"
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        log(f"  ⏱ Timeout timeline: @{handle}")
        return results

    redir_url = page.url.lower()
    if "login" in redir_url or "/flow/" in redir_url:
        raise RuntimeError("LOGIN_REQUIRED")

    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
    except PlaywrightTimeout:
        return results

    page.wait_for_timeout(1000)

    # 7日前を下限として、それより古いツイートが出てきたら停止
    cutoff_date = (_dt.fromisoformat(today_str) - timedelta(days=7)).strftime("%Y-%m-%d")

    # 30回スクロール（タイムラインは日付逆順で深掘りが必要）
    for scroll_i in range(30):
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(200)

        # 10回ごとに古すぎるツイートが出ていないか確認して早期終了
        if scroll_i > 0 and scroll_i % 10 == 0:
            articles_check = page.query_selector_all('article[data-testid="tweet"]')
            too_old = 0
            for art in articles_check[-5:]:  # 末尾5件だけチェック
                try:
                    t_el = art.query_selector("time")
                    if t_el:
                        dt_attr = t_el.get_attribute("datetime") or ""
                        if dt_attr:
                            from datetime import datetime as _dtt, timezone as _tz
                            JST = _tz(timedelta(hours=9))
                            tweet_dt = _dtt.fromisoformat(dt_attr.replace("Z", "+00:00")).astimezone(JST)
                            tweet_date_str = tweet_dt.strftime("%Y-%m-%d")
                            if tweet_date_str < cutoff_date:
                                too_old += 1
                except Exception:
                    pass
            if too_old >= 3:
                break  # 古いツイートが増えてきたら打ち切り

    articles = page.query_selector_all('article[data-testid="tweet"]')
    store_name = _HANDLE_TO_STORE.get(handle.lower(), "")

    for article in articles[:150]:
        try:
            text = ""
            for sel in ['[data-testid="tweetText"]', '[lang]']:
                el = article.query_selector(sel)
                if el:
                    t = el.inner_text()
                    if len(t) > 10:
                        text = t
                        break

            if not text:
                continue

            # コンプリート関連ツイートだけを対象（タイムライン全件の中からフィルタ）
            if not any(kw in text for kw in ["コンプリート", "コンプ"]):
                continue
            # 除外パターンチェック
            if any(p.search(text) for p in EXCLUDE_PATTERNS):
                continue

            tweet_url = ""
            time_el = article.query_selector("time")
            if time_el:
                href = time_el.evaluate("el => el.closest('a') ? el.closest('a').href : ''")
                if href and "status" in href:
                    tweet_url = href
            if not tweet_url:
                for lnk in article.query_selector_all('a[href*="/status/"]'):
                    href = lnk.get_attribute("href") or ""
                    if "/status/" in href:
                        tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                        break

            if not tweet_url or tweet_url in seen_urls:
                continue
            seen_urls.add(tweet_url)

            tweet_date, tweet_time = get_tweet_datetime(article)

            # 収集対象日より古いものは除外
            if tweet_date and tweet_date < cutoff_date:
                continue

            # タイムライン収集ではハンドルが確定しているので、直接 store_name を使用
            entry = parse_tweet(text, tweet_url, today_str, tweet_date, tweet_time,
                                author_name=store_name)
            if entry:
                # 店舗名が取れなかった場合もタイムライン収集では handle から補完
                if not entry.get("store") and store_name:
                    entry["store"] = store_name

                # 画像取得
                images: list[str] = []
                try:
                    img_els = article.query_selector_all('img[src*="pbs.twimg.com"]')
                    for img_el in img_els[:4]:
                        src = img_el.get_attribute("src") or ""
                        if not src or "profile_images" in src:
                            continue
                        src = re.sub(r'\?.*$', '', src) + "?format=jpg&name=large"
                        if src not in images:
                            images.append(src)
                except Exception:
                    pass
                if images:
                    entry["images"]    = images
                    entry["image_url"] = images[0]

                results.append(entry)

        except Exception:
            continue

    if results:
        log(f"    ✅ timeline @{handle}: {len(results)}件")
    return results


def load_all() -> list[dict]:
    if not COMPLETE_JSON.exists():
        return []
    with open(COMPLETE_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_complete(new_entries: list[dict], target_date: str):
    all_data = load_all()

    # 30日より古いデータを除去（ピンツイート対策）― JST基準
    from datetime import timezone as _tz, timedelta as _td
    _JST = _tz(_td(hours=9))
    cutoff = (datetime.now(_JST) - _td(days=30)).strftime("%Y-%m-%d")
    all_data = [e for e in all_data if e.get("date", "") >= cutoff]

    # 既存IDセット（全期間）で重複防止
    existing_ids = {e["id"] for e in all_data}

    # 新規エントリー: 既存に無いものだけ追加（日付に関わらず全期間でIDチェック）
    new_only = [e for e in new_entries if e["id"] not in existing_ids]

    # コンプリート日付が30日以上前のものは追加しない（古いピンツイート対策）
    new_only = [e for e in new_only if e.get("date", "") >= cutoff]

    # ── 日付ズレ防止: target_date より未来のエントリは保存しない ──────────
    # X検索の until: を target_date+1 に設定しているため、翌日ツイートが
    # 混入する場合がある。日付は X の <time datetime> から UTC→JST 変換した
    # 正確な値を使っているが、誤パース・深夜0時前後の境界で1日ズレが起きた
    # 場合に備え、target_date 以前のエントリのみ受け入れる。
    skipped_future = [e for e in new_only if e.get("date", "") > target_date]
    if skipped_future:
        log(f"⚠️  日付ズレ除外: {len(skipped_future)}件 (target={target_date}): "
            + ", ".join(f"{e['date']} {e.get('store','?')}" for e in skipped_future[:3]))
    new_only = [e for e in new_only if e.get("date", "") <= target_date]

    # ── machine_resolver でフィルタリング（machine_id 未解決は JSON に保存しない）──
    # Supabase 環境変数が設定されている場合のみ有効（ローカル・未設定時はスキップ）
    try:
        import sys as _sys2, os as _os2
        _sd = _os2.path.dirname(_os2.path.abspath(__file__))
        if _sd not in _sys2.path:
            _sys2.path.insert(0, _sd)
        from machine_resolver import get_resolver as _get_resolver
        _save_resolver = _get_resolver()
    except (ImportError, Exception):
        _save_resolver = None

    if _save_resolver:
        _filtered, _skipped_unresolved = [], 0
        for _e in new_only:
            _raw = (_e.get("machine") or "").strip()
            if not _raw or _raw == "不明":
                _skipped_unresolved += 1
                continue
            _resolved = _save_resolver.resolve(_raw)
            if _resolved:
                _e["machine"]      = _resolved["official_name"]
                _e["machine_type"] = _resolved["machine_type"]
                _e["machine_id"]   = _resolved["machine_id"]
                _filtered.append(_e)
            else:
                _save_resolver.save_unknown(_raw, _e.get("x_url", ""))
                _skipped_unresolved += 1
        if _skipped_unresolved:
            log(f"⚠️  machine_id 未解決 {_skipped_unresolved}件を除外（unknown_machines に記録）")
        new_only = _filtered
    else:
        log("⚠️  machine_resolver 未初期化 — フィルタリングをスキップ（Supabase 環境変数を確認）")

    # ── store_resolver でフィルタリング（store_id 未解決は JSON に保存しない）──
    try:
        from store_resolver import get_resolver as _get_store_resolver
        _store_resolver = _get_store_resolver()
    except (ImportError, Exception):
        _store_resolver = None

    if _store_resolver:
        _store_resolver._ensure_loaded()
        _store_count = len(_store_resolver._stores)
        # stores DBが本番データとして充実している場合のみハードフィルタ有効
        # (テストデータのみ = 100件未満の場合はenrichmentモード: store_id付与のみ)
        _store_filter_enabled = _store_count >= 100
        if not _store_filter_enabled:
            log(f"ℹ️  store_resolver: stores DB={_store_count}件（100件未満）→ enrichmentモード（除外なし）")
        _s_filtered, _s_resolved, _s_unresolved = [], 0, 0
        for _e in new_only:
            _store_name = (_e.get("store") or "").strip()
            if _store_name:
                _resolved_store = _store_resolver.resolve(_store_name)
                if _resolved_store:
                    _e["store_id"] = _resolved_store["store_id"]
                    _s_resolved += 1
                else:
                    _store_resolver.save_unknown(_store_name, _e.get("x_url", ""))
                    _s_unresolved += 1
                    if _store_filter_enabled:
                        continue  # stores DB充実時のみ除外
            _s_filtered.append(_e)
        if _s_unresolved:
            log(f"{'⚠️  store_id 未解決 除外' if _store_filter_enabled else 'ℹ️  store_id 未解決（保存継続）'}: {_s_unresolved}件 → unknown_stores")
        if _s_resolved:
            log(f"✅ store_id 解決: {_s_resolved}件")
        new_only = _s_filtered
    else:
        log("⚠️  store_resolver 未初期化 — store_id 解決をスキップ")

    combined = all_data + new_only

    # コンプリートした日付（X datetime由来）→ 時刻 の新しい順でソート
    combined.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    combined = combined[:3000]

    # ── 日付別ファイルに保存（public/complete_YYYY-MM-DD.json）───────────────
    # 各日のデータを独立したファイルに保存することで:
    # 1. GH Actions の git push コンフリクトを軽減（今日のファイルしか変わらない）
    # 2. フロントエンドが特定日のデータだけを軽量ロードできる
    # 3. git log で日別の変化が追いやすくなる
    import tempfile
    dates_in_new = {e["date"] for e in new_only if e.get("date")}
    for day in dates_in_new:
        day_entries = [e for e in combined if e.get("date") == day]
        day_path = COMPLETE_JSON.parent / f"complete_{day}.json"
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=COMPLETE_JSON.parent, delete=False, suffix=".tmp"
        ) as tf:
            json.dump(day_entries, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name
        os.replace(tmp_path, day_path)

    # 古い日付ファイルを削除（cutoff より古いもの）
    for p in COMPLETE_JSON.parent.glob("complete_20??-??-??.json"):
        day_str = p.stem.replace("complete_", "")
        if day_str < cutoff:
            p.unlink(missing_ok=True)
            log(f"  🗑 古い日付ファイル削除: {p.name}")

    # ── complete_info.json（全件統合ファイル・後方互換性維持）─────────────────
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=COMPLETE_JSON.parent, delete=False, suffix=".tmp"
    ) as tf:
        json.dump(combined, tf, ensure_ascii=False, indent=2)
        tmp_path = tf.name
    os.replace(tmp_path, COMPLETE_JSON)

    # 本日（target_date）の合計件数
    today_total = sum(1 for e in combined if e.get("date") == target_date)
    log(f"💾 {len(new_only)}件新規追加 / {target_date}合計{today_total}件 / 全体{len(combined)}件")
    return len(new_only)


# ---------------------------------------------------------------------------
# Supabase ヘルパー（書き込み失敗時もスクリプトを止めない設計）
# ---------------------------------------------------------------------------
import urllib.request
import urllib.error
import ssl as _ssl


def _sb_env() -> tuple[str, str] | None:
    """環境変数からSupabase接続情報を取得。未設定なら None を返す（書き込みをスキップ）。"""
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return url, key


def _sb_request(method: str, path: str,
                body: list | dict | None = None,
                prefer: str | None = None) -> tuple[int, bytes]:
    """
    Supabase REST API へリクエストを送る低レベル関数。
    戻り値: (http_status_code, response_body_bytes)
    例外は呼び出し元で握りつぶすこと。
    """
    env = _sb_env()
    if not env:
        return 0, b""
    sb_url, sb_key = env

    ctx = _ssl._create_unverified_context()   # macOS + GitHub Actions 両対応
    headers: dict[str, str] = {
        "apikey":        sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type":  "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def supabase_log_start(job_name: str) -> int | None:
    """
    fetch_logs に実行開始レコードを INSERT し、生成された id を返す。
    失敗しても None を返してスクリプトは継続。
    """
    if not _sb_env():
        return None
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        status, body = _sb_request(
            "POST", "fetch_logs",
            body={
                "job_name":       job_name,
                "started_at":     now,
                "status":         "failed",   # 万が一スクリプトが途中終了した場合も failed になる
                "fetched_count":  0,
                "new_count":      0,
                "duplicate_count": 0,
                "error_count":    0,
            },
            prefer="return=representation",
        )
        if status in (200, 201) and body:
            rows = json.loads(body)
            if isinstance(rows, list) and rows:
                return rows[0].get("id")
    except Exception as e:
        log(f"⚠️  Supabase log_start エラー: {e}")
    return None


def supabase_log_end(log_id: int | None, status: str,
                     fetched: int, new_count: int,
                     dupes: int, errors: int,
                     error_detail: str | None = None) -> None:
    """fetch_logs の実行結果を PATCH で更新する。log_id が None の場合はスキップ。"""
    if log_id is None or not _sb_env():
        return
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        patch_body: dict = {
            "finished_at":    now,
            "status":         status,
            "fetched_count":  fetched,
            "new_count":      new_count,
            "duplicate_count": dupes,
            "error_count":    errors,
        }
        if error_detail:
            patch_body["error_detail"] = error_detail[:1000]
        _sb_request(
            "PATCH", f"fetch_logs?id=eq.{log_id}",
            body=patch_body,
            prefer="return=minimal",
        )
    except Exception as e:
        log(f"⚠️  Supabase log_end エラー: {e}")


def supabase_update_fetch_state(job_name: str) -> None:
    """fetch_state の last_success_at / last_run_at を現在時刻に更新する。"""
    if not _sb_env():
        return
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _sb_request(
            "PATCH", f"fetch_state?job_name=eq.{job_name}",
            body={"last_success_at": now, "last_run_at": now, "updated_at": now},
            prefer="return=minimal",
        )
    except Exception as e:
        log(f"⚠️  Supabase fetch_state 更新エラー: {e}")


def supabase_write_complete(entries: list[dict]) -> tuple[int, int]:
    """
    complete_reports テーブルに INSERT（ON CONFLICT DO NOTHING）。

    ・保存するフィールド: id, date, report_time, store_name, machine, machine_id,
                          slot_number, x_url, collected_at
    ・保存しないフィールド: text（本文）, images（画像配列）, image_url（画像URL）← 転載禁止
    ・DB保存前に machine_resolver で機種名を正規化・解決する（CLAUDE.md 参照）
    ・重複 ID は INSERT をスキップし duplicate_count に加算
    ・Supabase 書き込み失敗時は (0, 0) を返してスクリプトを継続

    戻り値: (new_count, duplicate_count)
    """
    if not entries or not _sb_env():
        return 0, 0

    # DB保存前に機種名を解決するリゾルバを初期化（失敗時は None で継続）
    resolver = None
    try:
        import os as _os, sys as _sys
        _scripts_dir = _os.path.dirname(_os.path.abspath(__file__))
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from machine_resolver import get_resolver
        resolver = get_resolver()
    except (ImportError, Exception):
        pass  # machine_resolver 未インストール時はスキップ（スクリプトは継続）

    total_new = 0
    total_dup = 0
    BATCH_SIZE = 100

    for i in range(0, len(entries), BATCH_SIZE):
        batch = entries[i : i + BATCH_SIZE]

        rows: list[dict] = []
        for e in batch:
            x_url = (e.get("x_url") or "").strip()
            if not x_url:
                continue   # x_url は NOT NULL のため空行はスキップ

            # DB保存前に機種名正規化・解決（CLAUDE.md: DB保存前に必ず正規化）
            raw_machine = e.get("machine") or ""
            official_machine: str | None = raw_machine or None
            machine_id: str | None = None
            if resolver and raw_machine and raw_machine != "不明":
                resolved = resolver.resolve(raw_machine)
                if resolved:
                    official_machine = resolved["official_name"]
                    machine_id       = resolved["machine_id"]
                else:
                    # 85% 未満 → unknown_machines に保存（AI 推測のみでは確定しない）
                    resolver.save_unknown(raw_machine, x_url)

            rows.append({
                "id":           e["id"],
                "date":         e.get("date") or None,
                "report_time":  e.get("time") or None,       # "time" → DB の "report_time"
                "store_name":   e.get("store") or None,      # "store" → DB の "store_name"
                "machine":      official_machine,
                "machine_id":   machine_id,
                "slot_number":  e.get("slot_number") or None,
                "x_url":        x_url,
                "collected_at": e.get("collected_at")
                                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                # text / images / image_url は意図的に送信しない
            })

        if not rows:
            continue

        try:
            status, body = _sb_request(
                "POST", "complete_reports",
                body=rows,
                # ignore-duplicates = ON CONFLICT DO NOTHING（既存データを書き換えない）
                # return=representation で実際に INSERT された行数を取得
                prefer="resolution=ignore-duplicates,return=representation",
            )
            if status in (200, 201):
                inserted = len(json.loads(body)) if body else 0
                total_new += inserted
                total_dup += len(rows) - inserted
            else:
                err_text = body.decode(errors="replace")[:200] if body else ""
                log(f"⚠️  Supabase complete_reports HTTP {status}: {err_text}")
                # Supabase エラーでもスクリプトは継続
        except Exception as e:
            log(f"⚠️  Supabase complete_reports 書き込みエラー: {e}")
            # スクリプトは継続

    if total_new or total_dup:
        log(f"☁️  Supabase: 新規{total_new}件 / 重複skip{total_dup}件")

    return total_new, total_dup


def update_ranking():
    """
    complete_info.json から月間・トータルランキングを集計して
    complete_ranking.json を更新する。
    店舗別・機種別のTOP5を月ごとに保持し、全期間集計も持つ。
    """
    from collections import Counter
    from datetime import timezone, timedelta

    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    this_month = now_jst.strftime("%Y-%m")

    all_data = load_all()

    # ── 機種名NG（誤抽出されやすい非機種名文字列）────────────────────────
    MACHINE_NAME_NG = {
        "不明",  # 機種名が特定できなかったエントリ（フィードには表示するがランキング除外）
        "コンプリート達成", "コンプリート機能", "コンプリート", "お客様",
        "ありがとうございます", "発動", "作動", "本日", "達成", "発生",
        "機能", "番台", "スロット", "パチスロ", "スマスロ", "来店",
        "誠におめ", "おめでとう", "おめでとうございます", "おめでとうございます！", "ございます",
        "コンプ", "完走", "出玉", "今日", "昨日",
        # 誤抽出フレーズ
        "コンプリート達成しました", "コンプリートおめ", "コンプリート達成おめ",
        "にてコンプリート達成されました", "にてコンプリート達成しました",
        "はコンプリート機能発動", "よりコンプリート達成", "、コンプリート",
        "は本日の遊技は終了となりました…",
        "コンプリート機能発動の為、本日は停止となります。",
        # 投稿文の断片・X username・その他誤抽出
        "お客様より", "真打じゃない方の吉宗より",
        "から、、、", "にて...", "にて…", "コーナー", "オススメ機種",
        "閉店間際になんと", "なんと２台同時",
        "▶︎▶︎▶︎▶︎", ")じゃないよね????", "・スマスロは", "TT-KR",
        "18000枚Over", "コンプおめ", "誠におめ",
        "コンプリート機能発動", "今週のオススメ機種", "でコンプリート～",
        "カバネリ4台", "コーナー",
        "にて...", "にて…", "から、、、",
        "おめでとうございます！！！！！！", "おめでとうございます！！！！！",
    }

    # ── 機種名の表記ゆれ正規化マップ ────────────────────────────────────
    # キー: 元の表記（部分一致でOK）→ 値: 統一後の正式名称
    # 長いパターンを先に書くこと（「ヴァルヴレイヴ2」より先に「革命機ヴァルヴレイヴ」）
    MACHINE_NORMALIZE: list[tuple[str, str]] = [
        # スマスロ北斗の拳転生の章2（先に書く：「転生」より長いパターンを優先）
        ("転生の章2",             "スマスロ北斗の拳転生の章2"),
        ("転生の章Ⅱ",            "スマスロ北斗の拳転生の章2"),
        ("転生の章２",            "スマスロ北斗の拳転生の章2"),
        ("転生2",                 "スマスロ北斗の拳転生の章2"),
        ("転生２",                "スマスロ北斗の拳転生の章2"),
        ("転生の章",              "スマスロ北斗の拳転生の章2"),   # 章番号省略も2に統一
        # 北斗転生系の表記ゆれ（番号なしも2026年時点では転生の章2）
        ("北斗の拳転生",          "スマスロ北斗の拳転生の章2"),
        ("北斗転生",              "スマスロ北斗の拳転生の章2"),
        # L革命機ヴァルヴレイヴ2
        ("革命機ヴァルヴレイヴ２", "L革命機ヴァルヴレイヴ2"),
        ("革命機ヴァルヴレイヴ2",  "L革命機ヴァルヴレイヴ2"),
        ("Lヴァルヴレイヴ2",       "L革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ２",       "L革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ2",        "L革命機ヴァルヴレイヴ2"),
        ("ヴァルヴレイヴ",         "L革命機ヴァルヴレイヴ2"),
        # L炎炎ノ消防隊2
        ("Ｌ炎炎ノ消防隊２",      "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊2",          "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊２",         "L炎炎ノ消防隊2"),
        ("炎炎ノ消防隊",           "L炎炎ノ消防隊2"),
        ("炎炎の消防隊",           "L炎炎ノ消防隊2"),
        ("炎炎ﾉ消防隊",            "L炎炎ノ消防隊2"),  # 半角ﾉ variant
        # Lミリオンゴッド神々の軌跡
        ("Lミリオンゴッド神々の軌跡", "Lミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド神々の軌跡",  "Lミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド‐神々",    "Lミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド-神々",    "Lミリオンゴッド神々の軌跡"),
        ("ミリオンゴッド",         "Lミリオンゴッド神々の軌跡"),
        # L甲鉄城のカバネリ海門決戦（長いパターンを先に書く）
        ("L甲鉄城のカバネリ海門決戦", "L甲鉄城のカバネリ海門決戦"),
        ("甲鉄城のカバネリ海門決戦",  "L甲鉄城のカバネリ海門決戦"),
        ("甲鉄城のカバネリ",          "L甲鉄城のカバネリ海門決戦"),
        ("カバネリ海門決戦",          "L甲鉄城のカバネリ海門決戦"),
        ("カバネリ",                  "L甲鉄城のカバネリ海門決戦"),
        ("甲鉄城",                    "L甲鉄城のカバネリ海門決戦"),
        # L東京喰種
        ("東京喰種",               "L東京喰種"),
        # スマスロ北斗の拳（転生パターンの後に書く）
        ("北斗の拳",               "スマスロ北斗の拳"),
        ("北斗",                   "スマスロ北斗の拳"),
        # スマスロ攻殻機動隊
        ("攻殻機動隊",             "スマスロ攻殻機動隊"),
        # バジリスク絆2
        ("バジリスク絆２",         "バジリスク絆2"),
        ("バジリスク絆",           "バジリスク絆2"),
        ("バジリスク",             "バジリスク絆2"),
        # 吉宗（真打を先に書く・別機種）
        ("真打吉宗",               "L真打吉宗"),
        ("L吉宗",                  "L吉宗"),
        ("吉宗",                   "L吉宗"),
        # ゴッドイーター
        ("ゴッドイーター",         "スマスロゴッドイーター"),
        # 牙狼シリーズ（長いパターン先・e牙狼12黄金騎士極限は保持）
        ("e牙狼12黄金騎士極限",    "e牙狼12黄金騎士極限"),
        ("牙狼",                   "e牙狼12"),
        # L沖ドキDUO アンコール
        ("L沖ドキDUO アンコール",  "L沖ドキDUO アンコール"),
        ("沖ドキ！DUOアンコール",  "L沖ドキDUO アンコール"),
        ("沖ドキDUOアンコール",    "L沖ドキDUO アンコール"),
        ("沖ドキDUO アンコール",   "L沖ドキDUO アンコール"),
        ("沖ドキDUO",              "L沖ドキDUO アンコール"),
        ("沖ドキ",                 "L沖ドキDUO アンコール"),
        # Lチバリヨ2ZB（全角・括弧表記ゆれを統一）
        ("チバリヨ２ＺＢ",         "Lチバリヨ2ZB"),
        ("チバリヨ２ZB",           "Lチバリヨ2ZB"),
        ("チバリヨ2ZB",            "Lチバリヨ2ZB"),
        ("チバリヨ2",              "Lチバリヨ2ZB"),
        ("チバリヨ",               "Lチバリヨ2ZB"),
        # eバイオハザード6（型番・括弧ゆれ統一）
        ("eバイオハザード6APN",     "eバイオハザード6"),   # APN型番ゆれ
        ("eバイオハザード6",        "eバイオハザード6"),
        ("ｅバイオハザード６",      "eバイオハザード6"),
        ("eバイオ",                "eバイオハザード6"),
        # eフィーバーキン肉マン（eFキン肉マン / eFEVERキン肉マン / eキン肉マン 統一）
        ("eFEVERキン肉マン",        "eフィーバーキン肉マン"),
        ("eFキン肉マン",            "eフィーバーキン肉マン"),
        ("eＦキン肉マン",           "eフィーバーキン肉マン"),
        ("eフィーバーキン肉マン",    "eフィーバーキン肉マン"),
        ("eキン肉マン",             "eフィーバーキン肉マン"),
        # シャーマンキング
        ("シャーマンキング",        "Lシャーマンキング"),
        # 新鬼武者3
        ("新鬼武者3",              "L新鬼武者3"),
        ("鬼武者3",                "L新鬼武者3"),
        # かぐや様
        ("かぐや様",               "Lかぐや様は告らせたい"),
        # スマスロバイオハザードRE:3
        ("バイオハザードRe：3",     "スマスロバイオハザードRE:3"),   # 全角コロン
        ("バイオハザードRe",        "スマスロバイオハザードRE:3"),
        ("バイオハザードRE:3",      "スマスロバイオハザードRE:3"),
        ("LバイオハザードRe",       "スマスロバイオハザードRE:3"),
        # Re:ゼロ
        ("Re:ゼロ",               "Re:ゼロから始める異世界生活"),
        ("リゼロ",                 "Re:ゼロから始める異世界生活"),
        # ゴジラ
        ("ゴジラ",                 "Lゴジラ"),
        # eフィーバーもののがたり系（Fが付く甘デジは別機種なので先に書いて保護する）
        ("eフィーバーもののがたりF", "eフィーバーもののがたりF"),  # 甘デジ・別機種（先に書く）
        ("eフィーバーもののがたり",  "eフィーバーもののがたり"),
        ("eFEVERもののがたり",       "eフィーバーもののがたり"),
        ("eもののがたり",           "eフィーバーもののがたり"),
        # eひきこまり吸血姫の悶々（「鬼」→「姫」誤記を統一）
        ("eひきこまり吸血鬼の悶々",     "eひきこまり吸血姫の悶々"),  # 鬼は誤字
        ("eひきこまり吸血姫の悶々FHV",  "eひきこまり吸血姫の悶々"),  # FHVバリアント
        ("eひきこまり吸血姫の悶々",     "eひきこまり吸血姫の悶々"),
        ("eひきこまり",                "eひきこまり吸血姫の悶々"),
        # eカケグルイ（型番・サブタイトルゆれを統一）
        ("eカケグルイ",                "eカケグルイ"),
        # e転生したらスライムだった件2
        ("転生したらスライムだった件",  "e転生したらスライムだった件2"),
        ("転スラ",                     "e転生したらスライムだった件2"),
        # Lからくりサーカス
        ("からくりサーカス",            "Lからくりサーカス"),
        # L鉄拳6（「鉄拳6から一撃」等の余分なテキストは extract_machine で除去済）
        ("鉄拳6",                      "L鉄拳6"),
        ("鉄拳",                       "L鉄拳6"),
    ]

    def normalize_machine(name: str) -> str | None:
        """機種名を正規化。NG文字列はNoneを返す。"""
        name = name.strip()
        # 短すぎ・空はスキップ
        if len(name) < 2:
            return None
        # NG文字列チェック
        if name in MACHINE_NAME_NG:
            return None
        # 数字のみ・記号のみはスキップ
        if re.match(r'^[\d\s]+$', name):
            return None
        # e/ｅ プレフィックス（パチンコ）の機種は、L/スマスロ名への正規化を適用しない
        # 「【e東京喰種】」のように括弧で囲まれた場合も e プレフィックスを正しく検出する
        name_stripped = re.sub(r'^[『「【〔\[\(（\s]+', '', name)
        is_pachinko_prefix = bool(re.match(r'^[eｅ]', name_stripped))
        # 正規化マップ適用（前方一致）
        for pattern, normalized in MACHINE_NORMALIZE:
            if pattern in name:
                # パチンコ機種をスロット名（L/スマスロ）に誤変換しない
                if is_pachinko_prefix and (
                    normalized.startswith("L") or normalized.startswith("Ｌ")
                    or normalized.startswith("スマスロ")
                ):
                    continue
                return normalized
        return name

    # ── store_x_urls.json を読み込み（ランキングのX URLリンク用）
    STORE_X_URLS_JSON = Path(__file__).parent.parent / "public/store_x_urls.json"
    store_x_urls_map: dict = {}
    if STORE_X_URLS_JSON.exists():
        try:
            store_x_urls_map = json.loads(STORE_X_URLS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    # store_handles.json も store_name→x_url マップとして使用（store_x_urls.json を補完）
    STORE_HANDLES_JSON2 = Path(__file__).parent.parent / "public/store_handles.json"
    if STORE_HANDLES_JSON2.exists():
        try:
            _sh2 = json.loads(STORE_HANDLES_JSON2.read_text(encoding="utf-8"))
            for _h2, _info2 in _sh2.items():
                if isinstance(_info2, dict) and _info2.get("store") and _info2.get("x_url"):
                    _sname2 = _info2["store"]
                    if _sname2 not in store_x_urls_map:
                        store_x_urls_map[_sname2] = _info2["x_url"]
        except Exception:
            pass

    # ── 店舗名の表記ゆれ正規化マップ（ランキング集計用）
    STORE_NORMALIZE: list[tuple[str, str]] = [
        ("楽園ハッピーロード大山 店長石川＠アカウント", "楽園ハッピーロード大山店"),
    ]

    # x_url のアカウントハンドル → 正式店舗名（スペース区切りの支店名対応）
    X_URL_STORE_OVERRIDE: dict[str, str] = {
        "rakuenikebukuro": "楽園池袋店ゲートウェイ",
        "Rakuen_GS":       "楽園池袋店グリーンサイド",
        "rakuen_gs":       "楽園池袋店グリーンサイド",
    }

    def normalize_store(name: str, x_url: str = "") -> str:
        # x_url ベースの補正（優先）
        if x_url:
            handle = x_url.split("/status/")[0].rstrip("/").split("/")[-1]
            if handle in X_URL_STORE_OVERRIDE:
                return X_URL_STORE_OVERRIDE[handle]
        for pattern, normalized in STORE_NORMALIZE:
            if name == pattern:
                return normalized
        return name

    # ── 既存ランキングJSONを読み込み（月別データを蓄積するため）
    # ※ monthly は配列形式・辞書形式どちらでも読み込めるよう対応
    existing: dict = {}
    if RANKING_JSON.exists():
        try:
            with open(RANKING_JSON, encoding="utf-8") as f:
                loaded = json.load(f)
                # 旧形式（単純配列）の場合はリセット
                existing = loaded if isinstance(loaded, dict) else {}
        except Exception:
            existing = {}

    # monthly を内部処理用の辞書に変換
    raw_monthly = existing.get("monthly", {})
    if isinstance(raw_monthly, list):
        monthly_data: dict = {m["month"]: m for m in raw_monthly if isinstance(m, dict) and "month" in m}
    else:
        monthly_data: dict = raw_monthly if isinstance(raw_monthly, dict) else {}

    # ── 月別の store/machine カウント
    month_store_counter:            dict[str, Counter] = {}
    month_slot_machine_counter:     dict[str, Counter] = {}
    month_pachinko_machine_counter: dict[str, Counter] = {}

    for e in all_data:
        d = e.get("date", "")
        if not d or len(d) < 7:
            continue
        ym = d[:7]  # "YYYY-MM"
        store   = normalize_store((e.get("store") or "").strip(), e.get("x_url") or "")
        machine = normalize_machine(e.get("machine") or "")
        mt      = e.get("machine_type") or get_machine_type(e.get("machine") or "")

        if store and store not in ("店舗不明",):
            month_store_counter.setdefault(ym, Counter())[store] += 1
        if machine:
            if mt == "pachinko":
                month_pachinko_machine_counter.setdefault(ym, Counter())[machine] += 1
            else:
                month_slot_machine_counter.setdefault(ym, Counter())[machine] += 1

    # ── 月別ランキングを更新（過去12ヶ月分保持）
    from datetime import timedelta as _td2
    months_to_keep = set()
    for i in range(12):
        m_date = now_jst.replace(day=1) - _td2(days=i * 28)
        months_to_keep.add(m_date.strftime("%Y-%m"))

    for ym in [k for k in list(monthly_data.keys()) if k not in months_to_keep]:
        del monthly_data[ym]

    def _make_store_items(counter: Counter) -> list:
        items = []
        for i, (name, cnt) in enumerate(counter.most_common(10)):
            item: dict = {"rank": i + 1, "name": name, "count": cnt}
            x_url = store_x_urls_map.get(name)
            if x_url:
                item["x_url"] = x_url
            items.append(item)
        return items

    def _make_machine_items(counter: Counter) -> list:
        return [{"rank": i + 1, "name": name, "count": cnt}
                for i, (name, cnt) in enumerate(counter.most_common(10))]

    for ym in month_store_counter:
        if ym not in months_to_keep:
            continue
        y_part, m_part = ym.split("-")
        monthly_data[ym] = {
            "month":             ym,
            "label":             f"{y_part}年{int(m_part)}月",
            "total_count":       sum(month_store_counter[ym].values()),
            "stores":            _make_store_items(month_store_counter[ym]),
            "slot_machines":     _make_machine_items(month_slot_machine_counter.get(ym, Counter())),
            "pachinko_machines": _make_machine_items(month_pachinko_machine_counter.get(ym, Counter())),
        }

    # ── 月別を配列形式に変換（新しい月順）
    monthly_array = sorted(
        [v for v in monthly_data.values() if isinstance(v, dict) and "month" in v],
        key=lambda x: x["month"],
        reverse=True,
    )

    # ── トータルランキング（全データから集計）
    total_store_counter:            Counter = Counter()
    total_slot_machine_counter:     Counter = Counter()
    total_pachinko_machine_counter: Counter = Counter()
    for e in all_data:
        store   = normalize_store((e.get("store") or "").strip(), e.get("x_url") or "")
        machine = normalize_machine(e.get("machine") or "")
        mt      = e.get("machine_type") or get_machine_type(e.get("machine") or "")
        if store and store not in ("店舗不明",):
            total_store_counter[store] += 1
        if machine:
            if mt == "pachinko":
                total_pachinko_machine_counter[machine] += 1
            else:
                total_slot_machine_counter[machine] += 1

    total_stores_top         = _make_store_items(total_store_counter)
    total_slot_machines_top  = _make_machine_items(total_slot_machine_counter)
    total_pachinko_machines_top = _make_machine_items(total_pachinko_machine_counter)

    # ── store_complete_counts（店舗ページ用）
    store_complete_counts = dict(total_store_counter.most_common())

    ranking = {
        "generated_at": now_jst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "monthly":       monthly_array,
        "total": {
            "stores":            total_stores_top,
            "slot_machines":     total_slot_machines_top,
            "pachinko_machines": total_pachinko_machines_top,
            "total_count":       len(all_data),
        },
        "store_complete_counts": store_complete_counts,
    }

    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=RANKING_JSON.parent, delete=False, suffix=".tmp"
    ) as tf:
        json.dump(ranking, tf, ensure_ascii=False, indent=2)
        tmp_path = tf.name
    os.replace(tmp_path, RANKING_JSON)

    log(f"🏆 ランキング更新: 月別{len(monthly_array)}ヶ月分 / トータル店舗TOP{len(total_stores_top)} / スロット機種TOP{len(total_slot_machines_top)}")

    # ── store_handles.json を最新データで更新（新規ハンドルの自動登録）───────────
    STORE_HANDLES_JSON = Path(__file__).parent.parent / "public/store_handles.json"
    try:
        existing_handles: dict = {}
        if STORE_HANDLES_JSON.exists():
            existing_handles = json.loads(STORE_HANDLES_JSON.read_text(encoding="utf-8"))

        # 全エントリから handle を抽出してカウント
        handle_count: dict[str, int] = {}
        handle_store: dict[str, str] = {}
        for e in all_data:
            url = e.get("x_url", "")
            store = (e.get("store") or "").strip()
            if url and "/status/" in url:
                handle = url.split("/status/")[0].rstrip("/").split("/")[-1].lower()
                if handle:
                    handle_count[handle] = handle_count.get(handle, 0) + 1
                    if store and len(store) >= 3:
                        # クリーン済み店舗名を優先（装飾なし・より長い）
                        cur_store = handle_store.get(handle, "")
                        if not cur_store or len(store) >= len(cur_store):
                            handle_store[handle] = store

        # 既存ハンドルを更新・新規追加
        added = 0
        for handle, count in handle_count.items():
            if handle not in existing_handles:
                sname = handle_store.get(handle, "")
                if not sname:
                    continue  # 店舗名不明のハンドルは追加しない（個人アカウント混入防止）
                existing_handles[handle] = {
                    "store": sname,
                    "x_url": f"https://x.com/{handle}",
                    "count": count,
                }
                added += 1
            else:
                existing_handles[handle]["count"] = count
                # 店舗名も更新（装飾除去後により良い名称があれば）
                cur = existing_handles[handle].get("store", "")
                new = handle_store.get(handle, "")
                if new:
                    new_clean = _clean_author_name(new)
                    cur_clean = _clean_author_name(cur) if cur else ""
                    # クリーン名が既存より良い（より具体的・装飾なし）場合のみ更新
                    if new_clean and new_clean != cur_clean and len(new_clean) >= len(cur_clean):
                        existing_handles[handle]["store"] = new_clean

        # count降順でソート
        sorted_handles = dict(sorted(existing_handles.items(), key=lambda x: -(x[1].get("count", 0) if isinstance(x[1], dict) else 0)))

        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=STORE_HANDLES_JSON.parent, delete=False, suffix=".tmp"
        ) as tf2:
            json.dump(sorted_handles, tf2, ensure_ascii=False, indent=2)
            tmp2 = tf2.name
        os.replace(tmp2, STORE_HANDLES_JSON)
        if added:
            log(f"📋 store_handles.json 更新: {added}件新規追加 / 計{len(sorted_handles)}店舗")
    except Exception as _she:
        log(f"⚠️ store_handles.json 更新エラー: {_she}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    # GH Actions は UTC で動くので JST (+9h) に変換する
    if args.date:
        today = args.date
    else:
        from datetime import timezone, timedelta
        JST = timezone(timedelta(hours=9))
        today = datetime.now(JST).strftime("%Y-%m-%d")

    # ── 既知店舗の from:handle クエリを生成（キーワード検索より高精度・0%フォールスポジティブ）
    STORE_HANDLES_JSON = Path(__file__).parent.parent / "public/store_handles.json"
    handle_queries: list[str] = []
    store_handles_data: dict = {}   # タイムライン収集フェーズでも参照する
    if STORE_HANDLES_JSON.exists():
        try:
            store_handles_data: dict = json.loads(STORE_HANDLES_JSON.read_text(encoding="utf-8"))
            # ハンドル → 店舗名マップをグローバルに登録（parse_tweet で使用）
            for h, info in store_handles_data.items():
                if isinstance(info, dict) and info.get("store"):
                    _HANDLE_TO_STORE[h.lower()] = info["store"]
                    _HANDLE_TO_INFO[h.lower()] = info
            log(f"📋 ハンドル→店舗名マップ {len(_HANDLE_TO_STORE)}件 登録")
            # count >= 1 の実績ある店舗アカウントを対象（上位100件まで）
            active_handles = [
                (h, info) for h, info in store_handles_data.items()
                if isinstance(info, dict) and info.get("count", 0) >= 1
            ]
            active_handles.sort(key=lambda x: -x[1].get("count", 0))
            handle_queries = [f"from:{h} コンプリート" for h, _ in active_handles[:100]]
            log(f"📋 from:handle クエリ {len(handle_queries)}件 追加")
        except Exception as _he:
            log(f"⚠️ store_handles.json 読み込みエラー: {_he}")

    # キーワードクエリを先頭に置き、from:handle クエリは補完として後置
    # 理由: キーワードクエリは全X検索なので投稿がある限り必ずヒットする
    #       from:handle クエリは特定店舗のみのため投稿がない日は全て0件になり
    #       先頭に置くと早期終了でキーワードクエリが実行されなくなるため
    all_queries = list(COMPLETE_QUERIES) + handle_queries

    log("=" * 60)
    log(f"🎰 コンプリート収集開始（店舗投稿のみ）  {today}  クエリ数={len(all_queries)} (keyword:{len(COMPLETE_QUERIES)} + handle:{len(handle_queries)})")

    # ── Supabase: 実行開始を記録 ──────────────────────────────────────────
    sb_log_id = supabase_log_start("complete")

    all_new: list[dict] = []
    query_errors = 0   # クエリ単位のエラー数

    # ── 時間制限: 28分で強制終了（GH Actions ステップタイムアウト35分の余裕を確保）
    MAX_RUNTIME_MIN = 28
    # ── 連続0件での早期終了: X側のレート制限検出
    # キーワードクエリを全件実行し終わってから from:handle クエリで連続0件が続いた場合のみ終了
    # ※ 半数判定（//2）だとキーワード後半〜from:handle が全スキップされるバグがあったため修正
    MAX_CONSECUTIVE_ZEROS = 12
    MIN_QUERIES_BEFORE_EARLY_STOP = len(COMPLETE_QUERIES)  # キーワード全件実行後に有効化
    consecutive_zeros = 0
    script_start = time.monotonic()

    with sync_playwright() as pw:
        ctx = launch_browser(pw, headless=args.headless)
        page = ctx.new_page()

        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)

        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        try:
            page.goto("https://x.com/home", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            cur_url = page.url.lower()
            title = page.title()
            LOGGED_OUT_TITLES = ["いま", "what's happening", "happening now", "sign in", "log in"]
            is_logged_out = (
                "login" in cur_url or "flow" in cur_url or
                (title and any(t in title.lower() for t in LOGGED_OUT_TITLES))
            )
            if is_logged_out:
                log(f"⚠️  クッキー認証失敗 (url={page.url}, title={title!r})")
                x_user = os.environ.get("X_USERNAME", "")
                x_pass = os.environ.get("X_PASSWORD", "")
                if x_user and x_pass:
                    if not _login_with_credentials(page, x_user, x_pass):
                        log("❌ 再ログイン失敗。収集を中止します")
                        ctx.close()
                        supabase_log_end(sb_log_id, "failed", 0, 0, 0, 1, "Xログイン失敗")
                        return
                    _save_session(ctx)
                else:
                    log("❌ X_USERNAME/X_PASSWORD 未設定。収集を中止します")
                    ctx.close()
                    supabase_log_end(sb_log_id, "failed", 0, 0, 0, 1, "Xログイン失敗（credentials未設定）")
                    return
            else:
                log(f"✅ Xログイン確認OK (title={title!r})")
                _save_session(ctx)  # 成功のたびに最新クッキーを保存
        except PlaywrightTimeout:
            log("⚠️  ログイン確認タイムアウト — 続行")

        login_lost = False

        # ── フェーズ0: タイムライン直接収集（X search インデックス漏れ補完）────────────
        # count >= 3 の実績豊富な上位アカウントのタイムラインを直接訪問して収集
        # X search は全ツイートをインデックスしないため、これが最も確実な収集手段
        timeline_handles = [
            h for h, info in store_handles_data.items()
            if isinstance(info, dict) and info.get("count", 0) >= 3
        ]
        timeline_handles.sort(key=lambda h: -store_handles_data.get(h, {}).get("count", 0))
        timeline_handles = timeline_handles[:50]  # 上位50アカウント

        if timeline_handles and not login_lost:
            log(f"📡 タイムライン直接収集フェーズ: {len(timeline_handles)}アカウント")
            tl_total = 0
            for tl_handle in timeline_handles:
                elapsed_min = (time.monotonic() - script_start) / 60
                if elapsed_min >= MAX_RUNTIME_MIN - 5:  # 残り5分以上残す
                    log("⏰ タイムライン収集を打ち切り（残り時間不足）")
                    break
                try:
                    tl_results = scrape_timeline(page, tl_handle, today)
                    all_new.extend(tl_results)
                    tl_total += len(tl_results)
                except RuntimeError as e:
                    if "LOGIN_REQUIRED" in str(e):
                        log("❌ タイムライン収集中にセッション切れ")
                        login_lost = True
                        break
                except Exception as e:
                    log(f"  ⚠️ timeline @{tl_handle} エラー: {e}")
            log(f"📡 タイムライン収集完了: 計{tl_total}件")

        for i, query in enumerate(all_queries, 1):
            # ── 時間制限チェック ──────────────────────────────────────────────
            elapsed_min = (time.monotonic() - script_start) / 60
            if elapsed_min >= MAX_RUNTIME_MIN:
                log(f"⏰ {MAX_RUNTIME_MIN}分の時間制限に達しました "
                    f"({i-1}/{len(all_queries)}クエリ完了) — 保存して終了")
                break

            log(f"  [{i}/{len(all_queries)}] 🔍 {query}  (経過{elapsed_min:.1f}分)")

            # ── クエリ実行（失敗時1回リトライ）─────────────────────────────
            query_result_count = 0
            for attempt in range(2):
                try:
                    results = scrape_query(page, query, today)
                    query_result_count = len(results)
                    log(f"       → {query_result_count} 件（店舗投稿）")
                    all_new.extend(results)
                    time.sleep(1)
                    break
                except RuntimeError as e:
                    if "LOGIN_REQUIRED" in str(e):
                        log("❌ Xのログインセッション切れを検出 — 収集を中止します")
                        login_lost = True
                        break
                    if attempt == 0:
                        log(f"  ⚠️ リトライします: {e}")
                        time.sleep(3)
                    else:
                        log(f"  ❌ スキップ: {e}")
                        query_errors += 1
                except Exception as e:
                    if attempt == 0:
                        log(f"  ⚠️ リトライします: {e}")
                        time.sleep(3)
                    else:
                        log(f"  ❌ スキップ: {e}")
                        query_errors += 1

            if login_lost:
                break

            # ── 連続0件チェック（X側のレート制限検出）────────────────────────
            # キーワードクエリ先頭のため、半数以上実行後に連続12件0件で終了
            if query_result_count == 0:
                consecutive_zeros += 1
                if i >= MIN_QUERIES_BEFORE_EARLY_STOP and consecutive_zeros >= MAX_CONSECUTIVE_ZEROS:
                    log(f"⚠️ {consecutive_zeros}クエリ連続0件を検出 "
                        f"({i}/{len(all_queries)}クエリ完了) — X側制限の可能性、保存して終了")
                    break
            else:
                consecutive_zeros = 0

        page.close()
        ctx.close()

        if login_lost:
            # セッション切れでも収集済み分は保存して終了（supabase_log_end は後で呼ぶ）
            log(f"⚠️ セッション切れのため中断。収集済み{len(all_new)}件は保存します")

    # 重複除去
    seen: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen or seen.add(e["id"]))]  # type: ignore

    log(f"\n📊 収集: {len(deduped)} 件（店舗投稿・重複除去後）")

    # ── JSON 保存（既存の動作をそのまま維持）────────────────────────────────
    json_added = 0
    if deduped:
        json_added = save_complete(deduped, today)
        log(f"✅ {json_added}件を新規追加")
    else:
        log("ℹ️  新規の店舗投稿コンプリートが見つかりませんでした")

    log(f"\n=== {today} 店舗コンプリート一覧 ===")
    today_entries = [e for e in deduped if e.get("date") == today]
    for e in today_entries:
        t = e.get("time", "--:--")
        store = e["store"] or "店舗不明"
        machine = e["machine"] or "機種不明"
        slot = f" [{e['slot_number']}番台]" if e.get("slot_number") else ""
        log(f"  🎰 {t} {store} / {machine}{slot}")

    # ── Supabase 書き込み（JSON保存の後・失敗してもスクリプトは継続）────────
    sb_new, sb_dup = supabase_write_complete(deduped)

    # ── Supabase: 実行結果を記録 ──────────────────────────────────────────
    sb_status = "failed" if login_lost else ("success" if query_errors == 0 else "partial")
    supabase_log_end(
        sb_log_id, sb_status,
        fetched=len(deduped),
        new_count=sb_new,
        dupes=sb_dup,
        errors=query_errors,
    )
    if deduped:  # 何か収集できていれば fetch_state を更新
        supabase_update_fetch_state("complete")

    # ランキング更新（クラッシュしても収集データは保存済み→必ずexitコード0で終わらせる）
    try:
        update_ranking()
    except Exception as _rank_err:
        log(f"⚠️ ランキング更新エラー（収集データは保存済み）: {_rank_err}")

    log("=" * 60)


if __name__ == "__main__":
    main()
