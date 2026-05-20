#!/usr/bin/env python3
"""
パチスロ来店・取材イベント情報を限界まで収集。
X(アカウントタイムライン＋検索) / Yahoo!リアルタイム / Google News

GitHub Actions 対応: X_AUTH_TOKEN / X_CT0 環境変数で認証。
JOB 環境変数で実行モードを切り替え（accounts / search / google）。

Usage:
    python scripts/fetch_events.py --headless --job accounts
    python scripts/fetch_events.py --headless --job search
    python scripts/fetch_events.py --headless --job google
    python scripts/fetch_events.py --headless           # 全実行（ローカル用）
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ pip install playwright && playwright install chromium")
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

EVENTS_JSON = Path(__file__).parent.parent / "public/events_public.json"
STORES_JSON = Path(__file__).parent.parent / "public/stores.json"
MACHINES_JSON = Path(__file__).parent.parent / "public/machines.json"

# ===========================================================================
# JOB A: X アカウント タイムライン（メディア80件 + 個別店舗71件 = 計151件）
# ===========================================================================

# ── 大手メディア・番組・地域情報・タレント（80件） ──
MEDIA_ACCOUNTS: dict[str, str] = {
    # 大手メディア・番組
    "PAA_pmportal":      "パチマガスロマガ",
    "KD_56_PS":          "KD情報",
    "suropachi_staff":   "スロパチステーション",
    "janbari_info":      "ジャンバリ",
    "3x3star_slot":      "3×3STAR",
    "gorsei_tv":         "極誓",
    "kaido_adv":         "回胴アドベンチャー",
    "suro_select":       "スロセレ",
    "ps_chosain":        "PS調査員",
    "gokuzei_take":      "極誓取材",
    "buzzslot_jp":       "バズ・スロ",
    "Slotol777":         "スロット情報",
    "asadera_tv":        "あさくら",
    "yume_dori":         "夢ドリ",
    "slotimes_jp":       "SLOTIMES",
    "realdoc_pachi":     "REAL取材",
    "gokumichi_dome":    "限界突破DOME",
    "superslot_tv":      "スーパースロットTV",
    "eyeslot_official":  "アイスロ",
    "gogonet_slot":      "gogoネット",
    "pachi_jouhou":      "パチンコ情報局",
    "slot_matome_jp":    "スロットまとめ",
    "kakuhen_info":      "確変情報",
    "pachitimes_jp":     "パチスロ必勝本",
    "pachi_tatsujin":    "パチスロ達人",
    # 地域イベント集約
    "minrepo_tohoku":    "東北みんレポ",
    "p_info_kanto":      "関東パチスロ情報",
    "chiba_pachislo":    "千葉パチスロ情報",
    "pachi_schedule":    "パチスロスケジュール",
    "uratencho777":      "裏店長",
    "rkmrn55":           "ロクマル",
    "kansai_event_ps":   "関西パチスロイベント",
    "chubu_slot_event":  "中部スロットイベント",
    "kyushu_pachi_info": "九州パチスロ情報",
    "hokkaido_slot_ps":  "北海道スロット情報",
    "tohoku_slot_info":  "東北スロット情報",
    "shikoku_pachi":     "四国パチンコ情報",
    "chugoku_slot":      "中国地方スロット",
    "tokai_slot_event":  "東海スロットイベント",
    "kinki_pachi_info":  "近畿パチスロ情報",
    "koshinetsu_pachi":  "甲信越パチスロ",
    "kyushu_slot_event": "九州スロットイベント",
    "okinawa_pachi":     "沖縄パチスロ情報",
    "tohoku_event_ps":   "東北イベント情報",
    "kanto_slot_info":   "関東スロット情報",
    # タレント・ライター
    "mochizukisaki":     "望月咲",
    "kira_hikaru88":     "煌ひかる",
    "yuuki_kouda":       "倖田柚希",
    "happy_atsudori":    "ハッピー",
    "KarkunRR":          "カルクン",
    "hanakawa65":        "花川",
    "motsu_pachi":       "モツ",
    "matsuitaxi":        "マツイ",
    "sakiko_slot":       "沙姫",
    "yuki_suwa":         "諏訪幸",
    "ai_pachislo":       "あいちゃん",
    "nami_slot":         "なみ",
    "hinata_slot":       "ひなた",
    "megu_pachi":        "めぐ",
    "sara_slot777":      "サラ",
    "reina_pachislo":    "レイナ",
    "miho_slot_tv":      "みほ",
    "luna_pachi":        "ルナ",
    "shiho_slot":        "しほ",
    "yuna_pachi777":     "ゆな",
    "rio_slot_jp":       "リオ",
    "kotone_pachi":      "琴音",
    "haruka_slot777":    "はるか",
    "akane_pachi":       "あかね",
    # チェーン公式
    "maruhan_pachislo":  "マルハン公式",
    "kikoona_official":  "キコーナ公式",
    "gaia_slot_info":    "ガイア公式",
    "dynam_official":    "ダイナム公式",
    "pia_group_jp":      "PIA公式",
    "wonderland_slot":   "ワンダーランド公式",
    "millon_pachi":      "ミリオン公式",
    "zent_official":     "ZENT公式",
    "concorde_ps":       "コンコルド公式",
    "rakuten_pachi":     "楽園公式",
    "espas_official":    "エスパス公式",
    "bigmarch_ps":       "ビックマーチ公式",
    "amuse_pachi":       "アミューズ公式",
    "castle_pachi":      "キャッスル公式",
}

# ── 個別店舗アカウント（ワンダーランド34店 + ミリオン37店 = 71件） ──
STORE_ACCOUNTS: dict[str, str] = {
    # ワンダーランド（九州・熊本・大分・長崎・佐賀・宮崎・鹿児島）
    "wl_kashii":        "ワンダーランド香椎本館",
    "wl_kashii2":       "ワンダーランド香椎Ⅱ",
    "wl_nishijin":      "ワンダーランド西新",
    "wl_hyakunenbashi": "ワンダーランド百年橋店",
    "wl__minamigaoka":  "ワンダーランド南ヶ丘店",
    "wl_sue":           "ワンダーランド須恵店",
    "wl_fkhigashi":     "ワンダーランド1188福岡東店",
    "wl_ukihab":        "ワンダーランドうきはバイパス店",
    "wl_yanagawa":      "ワンダーランド柳川",
    "wl_mizuma":        "ワンダーランド三潴店",
    "wl_takada":        "ワンダーランド高田店",
    "wl_ookawa":        "ワンダーランド大川店",
    "wl_770aikawa":     "ワンダーランド770東合川店",
    "wl_yoshii":        "ワンダーランド吉井店",
    "wl_ogoori":        "ワンダーランド小郡三沢店",
    "wl_hachie":        "ワンダーランド八江店",
    "wl_metalpolice":   "ワンダーランドメタルポリス",
    "wl_hinodemachi":   "ワンダーランド日出町店",
    "wl_imari":         "ワンダーランド伊万里店",
    "wl_kouhoku":       "ワンダーランド江北店",
    "wl_takeo":         "ワンダーランド武雄店",
    "wl_kashima":       "ワンダーランド鹿島店",
    "wl_nakatsu":       "ワンダーランド中津米山店",
    "wl_minaharu":      "ワンダーランド大分皆春店",
    "wl_o_minami":      "ワンダーランド1177大分南店",
    "wl_usuki":         "ワンダーランド臼杵店",
    "wl_hikarinomori":  "ワンダーランド光の森店",
    "wl_s_sasebo":      "ワンダーランド佐世保白岳店",
    "wl__isahaya":      "ワンダーランド諫早店",
    "wl_kshinei":       "ワンダーランド1188鹿児島新栄店",
    "wl_taniyama":      "ワンダーランド1177谷山店",
    "wl_imo1188":       "ワンダーランド1188宮崎芳士店",
    "wl_odo":           "ワンダーランド小戸本館",
    "wl_od2":           "ワンダーランド小戸Ⅱ",
    # ミリオン（徳島・香川・高知・兵庫・千葉）
    "mn_kawauchi":      "ミリオン川内店",
    "mn_syowa":         "ミリオン昭和店",
    "mn_okinohama":     "ミリオン沖浜店",
    "mn_naruto_ps":     "ミリオン鳴門店",
    "mn_kanonji":       "ミリオン観音寺店",
    "mn_shimada":       "ミリオン島田店",
    "mn_ikeda_ps":      "ミリオン池田店",
    "mn_mikamo_ps":     "ミリオン三加茂店",
    "mn__mima":         "ミリオン美馬店",
    "mn_awa":           "ミリオン阿波店",
    "mn_ichiba":        "ミリオン市場店",
    "mn_kamojima":      "ミリオン鴨島店",
    "mn_ishii":         "ミリオン石井店",
    "mn_kokufu":        "ミリオン国府店",
    "mn_aizumi_ps":     "ミリオン藍住店",
    "mn_kitajima":      "ミリオン北島店",
    "mn_nakayoshino":   "ミリオン中吉野店",
    "mn_sako":          "ミリオン佐古店",
    "mn_ekimae":        "ミリオン駅前店",
    "mn_suehiro":       "ミリオン末広店",
    "mn_ronden_ps":     "ミリオン論田店",
    "mn_kanaiso":       "ミリオン金磯店",
    "mn_hanoura":       "ミリオン羽浦店",
    "mn_tsunomine":     "ミリオン津峰店",
    "mn_kainan":        "ミリオン海南店",
    "mn_utazu":         "ミリオン宇多津店",
    "mn_takamatsu":     "ミリオン高松東店",
    "mn_k_yoshioka":    "ミリオン観音寺吉岡店",
    "mn_tosadoro":      "ミリオン土佐道路店",
    "mn_ikku":          "ミリオン一宮店",
    "mn_noichi":        "ミリオン野市店",
    "mn_otsu_ps":       "ミリオン大津店",
    "mn_nankoku":       "ミリオン南国店",
    "mn_osone_ps":      "ミリオン南国おおそね店",
    "mn_akashi":        "ミリオン明石店",
    "mn_narashino":     "ミリオン習志野店",
    # その他個別店舗
    "lio_yokohama":     "Lio横浜",
    "hokuou_slot":      "北欧スロット",
    "newtokyoslot":     "ニュートーキョー",
}

ALL_ACCOUNTS = {**MEDIA_ACCOUNTS, **STORE_ACCOUNTS}

# ===========================================================================
# JOB B: X 検索クエリ（250件）
# ===========================================================================
def _build_queries(machine_names: list[str]) -> list[str]:
    base = [
        # ── ハッシュタグ ──
        "#来店イベント パチスロ",
        "#取材 パチスロ",
        "#来店取材 スロット",
        "#パチスロ取材",
        "#スロット来店",
        "#来店情報 パチスロ",
        "#イベント パチスロ 今日",
        "#特定日 パチスロ",
        "#スマスロ来店",
        "#パチンコ来店",
        "#誕生日イベント パチスロ",
        "#周年記念 スロット",
        "#新台入替 パチスロ",
        "#オープン記念 スロット",
        # ── 番組・メディア名 ──
        "スロパチステーション 来店",
        "ジャンバリ 取材",
        "パチマガスロマガ 来店",
        "KD情報 来店",
        "3×3STAR 取材",
        "極誓 取材",
        "回胴アドベンチャー 来店",
        "スロセレ 来店",
        "PS調査員 取材",
        "バズスロ 来店",
        "SLOTIMES 来店",
        "あさくら 来店",
        "夢ドリ 来店",
        "REAL取材 パチスロ",
        "限界突破DOME 取材",
        "アイスロ 来店",
        # ── イベント種別 ──
        "来店イベント パチスロ 今日",
        "来店イベント スロット 今週",
        "来店 スマスロ",
        "取材 パチスロ イベント",
        "撮影 パチスロ 来店",
        "実戦取材 パチスロ",
        "収録 パチスロ 来店",
        "ライター来店 パチスロ",
        "タレント来店 スロット",
        "グラドル来店 スロット",
        "女優来店 パチスロ",
        "誕生日イベント スロット",
        "周年記念 パチスロ イベント",
        "オープン記念 パチスロ",
        "新台入替 パチスロ イベント",
        "特定日 パチスロ 今日",
        "設定示唆 パチスロ イベント",
        # ── チェーン別 ──
        "マルハン 来店 パチスロ",       "マルハン 取材 スロット",
        "キコーナ 来店 パチスロ",       "キコーナ 取材 スロット",
        "ガイア 来店 パチスロ",         "ガイア 取材 スロット",
        "ダイナム 来店 パチスロ",       "ダイナム 取材 スロット",
        "楽園 来店 パチスロ",           "エスパス 来店 パチスロ",
        "PIA 来店 パチスロ",            "PIA 取材 スロット",
        "ニラク 来店 パチスロ",         "ワンダーランド 来店 スロット",
        "ミリオン 来店 スロット",       "ZENT 来店 パチスロ",
        "コンコルド 来店 パチスロ",     "ビックマーチ 来店 パチスロ",
        "アミューズ 来店 パチスロ",     "メッセ 来店 パチスロ",
        "アポロ 来店 パチスロ",         "キャッスル 来店 パチスロ",
        "Dステーション 来店 パチスロ",  "ゲンキー 来店 パチスロ",
        # ── 北海道 ──
        "札幌 来店 OR 取材 パチスロ",   "旭川 来店 OR 取材 パチスロ",
        "函館 来店 OR 取材 パチスロ",   "帯広 来店 OR 取材 パチスロ",
        "北見 来店 OR 取材 パチスロ",   "釧路 来店 OR 取材 パチスロ",
        "小樽 来店 OR 取材 パチスロ",   "北海道 来店 OR 取材 パチスロ",
        # ── 東北 ──
        "仙台 来店 OR 取材 パチスロ",   "青森 来店 OR 取材 パチスロ",
        "盛岡 来店 OR 取材 パチスロ",   "秋田 来店 OR 取材 パチスロ",
        "山形 来店 OR 取材 パチスロ",   "福島 来店 OR 取材 パチスロ",
        "郡山 来店 OR 取材 パチスロ",   "いわき 来店 OR 取材 パチスロ",
        "弘前 来店 OR 取材 パチスロ",   "八戸 来店 OR 取材 パチスロ",
        # ── 関東・東京 ──
        "新宿 来店 OR 取材 パチスロ",   "渋谷 来店 OR 取材 パチスロ",
        "池袋 来店 OR 取材 パチスロ",   "蒲田 来店 OR 取材 パチスロ",
        "大森 来店 OR 取材 パチスロ",   "秋葉原 来店 OR 取材 パチスロ",
        "立川 来店 OR 取材 パチスロ",   "八王子 来店 OR 取材 パチスロ",
        "町田 来店 OR 取材 パチスロ",   "錦糸町 来店 OR 取材 パチスロ",
        "上野 来店 OR 取材 パチスロ",   "吉祥寺 来店 OR 取材 パチスロ",
        "葛飾 来店 OR 取材 パチスロ",   "足立 来店 OR 取材 パチスロ",
        "江戸川 来店 OR 取材 パチスロ", "品川 来店 OR 取材 パチスロ",
        "中野 来店 OR 取材 パチスロ",   "板橋 来店 OR 取材 パチスロ",
        # ── 関東・他 ──
        "横浜 来店 OR 取材 パチスロ",   "川崎 来店 OR 取材 パチスロ",
        "相模原 来店 OR 取材 パチスロ", "藤沢 来店 OR 取材 パチスロ",
        "厚木 来店 OR 取材 パチスロ",   "平塚 来店 OR 取材 パチスロ",
        "横須賀 来店 OR 取材 パチスロ", "小田原 来店 OR 取材 パチスロ",
        "大宮 来店 OR 取材 パチスロ",   "浦和 来店 OR 取材 パチスロ",
        "川口 来店 OR 取材 パチスロ",   "所沢 来店 OR 取材 パチスロ",
        "越谷 来店 OR 取材 パチスロ",   "熊谷 来店 OR 取材 パチスロ",
        "川越 来店 OR 取材 パチスロ",   "春日部 来店 OR 取材 パチスロ",
        "千葉 来店 OR 取材 パチスロ",   "船橋 来店 OR 取材 パチスロ",
        "柏 来店 OR 取材 パチスロ",     "松戸 来店 OR 取材 パチスロ",
        "市川 来店 OR 取材 パチスロ",   "水戸 来店 OR 取材 パチスロ",
        "宇都宮 来店 OR 取材 パチスロ", "前橋 来店 OR 取材 パチスロ",
        "高崎 来店 OR 取材 パチスロ",   "伊勢崎 来店 OR 取材 パチスロ",
        # ── 中部 ──
        "名古屋 来店 OR 取材 パチスロ", "栄 来店 OR 取材 パチスロ",
        "豊橋 来店 OR 取材 パチスロ",   "岡崎 来店 OR 取材 パチスロ",
        "一宮 来店 OR 取材 パチスロ",   "豊田 来店 OR 取材 パチスロ",
        "浜松 来店 OR 取材 パチスロ",   "静岡 来店 OR 取材 パチスロ",
        "沼津 来店 OR 取材 パチスロ",   "富士 来店 OR 取材 パチスロ",
        "新潟 来店 OR 取材 パチスロ",   "長岡 来店 OR 取材 パチスロ",
        "上越 来店 OR 取材 パチスロ",   "金沢 来店 OR 取材 パチスロ",
        "富山 来店 OR 取材 パチスロ",   "福井 来店 OR 取材 パチスロ",
        "長野 来店 OR 取材 パチスロ",   "松本 来店 OR 取材 パチスロ",
        "甲府 来店 OR 取材 パチスロ",   "岐阜 来店 OR 取材 パチスロ",
        "大垣 来店 OR 取材 パチスロ",   "四日市 来店 OR 取材 パチスロ",
        # ── 近畿 ──
        "大阪 来店 OR 取材 パチスロ",   "難波 来店 OR 取材 パチスロ",
        "梅田 来店 OR 取材 パチスロ",   "天王寺 来店 OR 取材 パチスロ",
        "堺 来店 OR 取材 パチスロ",     "東大阪 来店 OR 取材 パチスロ",
        "吹田 来店 OR 取材 パチスロ",   "枚方 来店 OR 取材 パチスロ",
        "豊中 来店 OR 取材 パチスロ",   "京都 来店 OR 取材 パチスロ",
        "神戸 来店 OR 取材 パチスロ",   "三宮 来店 OR 取材 パチスロ",
        "姫路 来店 OR 取材 パチスロ",   "尼崎 来店 OR 取材 パチスロ",
        "西宮 来店 OR 取材 パチスロ",   "明石 来店 OR 取材 パチスロ",
        "奈良 来店 OR 取材 パチスロ",   "和歌山 来店 OR 取材 パチスロ",
        "大津 来店 OR 取材 パチスロ",   "草津 来店 OR 取材 パチスロ",
        "彦根 来店 OR 取材 パチスロ",   "津 来店 OR 取材 パチスロ",
        "鈴鹿 来店 OR 取材 パチスロ",
        # ── 中国・四国 ──
        "広島 来店 OR 取材 パチスロ",   "福山 来店 OR 取材 パチスロ",
        "呉 来店 OR 取材 パチスロ",     "岡山 来店 OR 取材 パチスロ",
        "倉敷 来店 OR 取材 パチスロ",   "山口 来店 OR 取材 パチスロ",
        "下関 来店 OR 取材 パチスロ",   "鳥取 来店 OR 取材 パチスロ",
        "松江 来店 OR 取材 パチスロ",   "米子 来店 OR 取材 パチスロ",
        "松山 来店 OR 取材 パチスロ",   "今治 来店 OR 取材 パチスロ",
        "高松 来店 OR 取材 パチスロ",   "丸亀 来店 OR 取材 パチスロ",
        "高知 来店 OR 取材 パチスロ",   "徳島 来店 OR 取材 パチスロ",
        # ── 九州・沖縄 ──
        "福岡 来店 OR 取材 パチスロ",   "博多 来店 OR 取材 パチスロ",
        "北九州 来店 OR 取材 パチスロ", "久留米 来店 OR 取材 パチスロ",
        "飯塚 来店 OR 取材 パチスロ",   "熊本 来店 OR 取材 パチスロ",
        "鹿児島 来店 OR 取材 パチスロ", "長崎 来店 OR 取材 パチスロ",
        "佐世保 来店 OR 取材 パチスロ", "大分 来店 OR 取材 パチスロ",
        "宮崎 来店 OR 取材 パチスロ",   "佐賀 来店 OR 取材 パチスロ",
        "那覇 来店 OR 取材 パチスロ",   "沖縄 来店 OR 取材 パチスロ",
        "浦添 来店 OR 取材 パチスロ",   "沖縄中部 来店 OR 取材 パチスロ",
    ]

    # 人気機種 × 来店（machines.jsonから上位機種）
    popular = [
        "北斗の拳","バジリスク","ヴァルヴレイヴ","炎炎ノ消防隊","攻殻機動隊",
        "カバネリ","モンスターハンター","リコリス","ゾンビランドサガ","ジャグラー",
        "鉄拳","吉宗","チバリヨ","牙狼","ミリオンゴッド","東京喰種","エヴァ",
        "スマスロ北斗","スマスロバジリスク","スマスロヴァルヴレイヴ",
        "バイオハザード","アクエリオン","まどマギ","化物語","シュタゲ",
    ]
    for m in popular:
        base.append(f"{m} 来店 OR 取材")

    # 追加機種（machines.jsonの機種名を短縮して追加）
    for name in machine_names[:30]:
        short = re.sub(r'^(?:スマスロ|Lパチスロ|パチスロ|スマパチ|L)\s*', '', name).strip()
        if len(short) >= 3 and short not in popular:
            base.append(f"{short} 来店 OR 取材")

    return list(dict.fromkeys(base))  # 重複除去


# ===========================================================================
# Google / Yahoo クエリ
# ===========================================================================
GOOGLE_QUERIES = [
    "パチスロ 来店イベント 今日",    "パチンコ 取材イベント 今週",
    "スロット 来店 関東",            "パチスロ 来店 関西",
    "パチスロ 来店 九州",            "パチスロ 来店 東北",
    "スマスロ 来店 取材",            "パチンコ スロット 来店 イベント",
    "マルハン 来店イベント",         "キコーナ 来店イベント",
    "ダイナム 来店イベント",         "ガイア 来店イベント",
    "パチスロ 取材 北海道",          "パチスロ 取材 中部",
    "パチスロ 取材 中国四国",        "パチスロライター 来店 今日",
    "スロットライター 取材 今週",    "パチンコ グラドル 来店",
    "パチスロ 来店 沖縄",            "スロット 誕生日イベント",
    "パチスロ 周年記念 イベント",    "パチスロ 新台 来店",
    "スロット 特定日 今週",          "パチンコ 来店 芸能人",
]

YAHOO_RT_QUERIES = [
    "パチスロ 来店",
    "スロット 取材",
    "パチスロ 来店イベント",
    "スマスロ 来店",
    "パチンコ 取材イベント",
    "来店 スロット 今日",
    "パチスロ ライター来店",
    "スロット タレント来店",
]

# ===========================================================================
# 都道府県マッピング
# ===========================================================================
CITY_PREF: dict[str, str] = {
    "蒲田":"東京都","大森":"東京都","新宿":"東京都","渋谷":"東京都","池袋":"東京都",
    "秋葉原":"東京都","立川":"東京都","八王子":"東京都","町田":"東京都","吉祥寺":"東京都",
    "上野":"東京都","錦糸町":"東京都","葛飾":"東京都","足立":"東京都","江戸川":"東京都",
    "品川":"東京都","目黒":"東京都","世田谷":"東京都","中野":"東京都","杉並":"東京都",
    "板橋":"東京都","練馬":"東京都","墨田":"東京都","荒川":"東京都",
    "横浜":"神奈川県","川崎":"神奈川県","相模原":"神奈川県","藤沢":"神奈川県",
    "厚木":"神奈川県","小田原":"神奈川県","茅ヶ崎":"神奈川県","海老名":"神奈川県",
    "平塚":"神奈川県","横須賀":"神奈川県","綾瀬":"神奈川県",
    "大宮":"埼玉県","浦和":"埼玉県","川口":"埼玉県","所沢":"埼玉県",
    "越谷":"埼玉県","熊谷":"埼玉県","川越":"埼玉県","春日部":"埼玉県","草加":"埼玉県",
    "千葉":"千葉県","船橋":"千葉県","柏":"千葉県","松戸":"千葉県","市川":"千葉県",
    "我孫子":"千葉県","流山":"千葉県","八千代":"千葉県","成田":"千葉県",
    "水戸":"茨城県","つくば":"茨城県","日立":"茨城県",
    "宇都宮":"栃木県","小山":"栃木県","足利":"栃木県",
    "前橋":"群馬県","高崎":"群馬県","伊勢崎":"群馬県","太田":"群馬県",
    "札幌":"北海道","旭川":"北海道","函館":"北海道","帯広":"北海道",
    "北見":"北海道","釧路":"北海道","小樽":"北海道","苫小牧":"北海道","室蘭":"北海道",
    "仙台":"宮城県","石巻":"宮城県",
    "青森":"青森県","弘前":"青森県","八戸":"青森県",
    "盛岡":"岩手県","一関":"岩手県",
    "秋田":"秋田県","大仙":"秋田県",
    "山形":"山形県","鶴岡":"山形県",
    "福島":"福島県","郡山":"福島県","いわき":"福島県","会津若松":"福島県",
    "名古屋":"愛知県","栄":"愛知県","豊橋":"愛知県","岡崎":"愛知県",
    "一宮":"愛知県","豊田":"愛知県","春日井":"愛知県","刈谷":"愛知県",
    "静岡":"静岡県","浜松":"静岡県","沼津":"静岡県","富士":"静岡県","磐田":"静岡県",
    "新潟":"新潟県","長岡":"新潟県","上越":"新潟県","三条":"新潟県",
    "金沢":"石川県","富山":"富山県","福井":"福井県","敦賀":"福井県",
    "長野":"長野県","松本":"長野県","上田":"長野県","飯田":"長野県",
    "甲府":"山梨県","岐阜":"岐阜県","大垣":"岐阜県","各務原":"岐阜県",
    "津":"三重県","四日市":"三重県","鈴鹿":"三重県","伊勢":"三重県",
    "大阪":"大阪府","難波":"大阪府","梅田":"大阪府","天王寺":"大阪府",
    "堺":"大阪府","東大阪":"大阪府","吹田":"大阪府","枚方":"大阪府",
    "豊中":"大阪府","岸和田":"大阪府","八尾":"大阪府","茨木":"大阪府",
    "京都":"京都府","宇治":"京都府","舞鶴":"京都府",
    "神戸":"兵庫県","三宮":"兵庫県","姫路":"兵庫県","尼崎":"兵庫県",
    "西宮":"兵庫県","明石":"兵庫県","宝塚":"兵庫県","加古川":"兵庫県",
    "奈良":"奈良県","橿原":"奈良県",
    "和歌山":"和歌山県","田辺":"和歌山県",
    "大津":"滋賀県","草津":"滋賀県","彦根":"滋賀県","長浜":"滋賀県",
    "広島":"広島県","福山":"広島県","呉":"広島県","尾道":"広島県",
    "岡山":"岡山県","倉敷":"岡山県","津山":"岡山県",
    "山口":"山口県","下関":"山口県","宇部":"山口県",
    "鳥取":"鳥取県","米子":"鳥取県","松江":"島根県","出雲":"島根県",
    "松山":"愛媛県","今治":"愛媛県","新居浜":"愛媛県",
    "高松":"香川県","丸亀":"香川県","高知":"高知県","徳島":"徳島県",
    "福岡":"福岡県","博多":"福岡県","北九州":"福岡県","久留米":"福岡県",
    "飯塚":"福岡県","大牟田":"福岡県","直方":"福岡県",
    "熊本":"熊本県","八代":"熊本県",
    "鹿児島":"鹿児島県","姶良":"鹿児島県",
    "長崎":"長崎県","佐世保":"長崎県","諫早":"長崎県",
    "大分":"大分県","別府":"大分県","中津":"大分県",
    "宮崎":"宮崎県","都城":"宮崎県",
    "佐賀":"佐賀県","唐津":"佐賀県",
    "那覇":"沖縄県","沖縄":"沖縄県","浦添":"沖縄県","宜野湾":"沖縄県","沖縄市":"沖縄県",
}

PREF_AREA: dict[str, str] = {
    "北海道":"北海道",
    "青森県":"東北","岩手県":"東北","宮城県":"東北","秋田県":"東北","山形県":"東北","福島県":"東北",
    "茨城県":"関東","栃木県":"関東","群馬県":"関東","埼玉県":"関東","千葉県":"関東","東京都":"関東","神奈川県":"関東",
    "新潟県":"中部","富山県":"中部","石川県":"中部","福井県":"中部","山梨県":"中部",
    "長野県":"中部","岐阜県":"中部","静岡県":"中部","愛知県":"中部",
    "三重県":"近畿","滋賀県":"近畿","京都府":"近畿","大阪府":"近畿","兵庫県":"近畿","奈良県":"近畿","和歌山県":"近畿",
    "鳥取県":"中国・四国","島根県":"中国・四国","岡山県":"中国・四国","広島県":"中国・四国","山口県":"中国・四国",
    "徳島県":"中国・四国","香川県":"中国・四国","愛媛県":"中国・四国","高知県":"中国・四国",
    "福岡県":"九州・沖縄","佐賀県":"九州・沖縄","長崎県":"九州・沖縄","熊本県":"九州・沖縄",
    "大分県":"九州・沖縄","宮崎県":"九州・沖縄","鹿児島県":"九州・沖縄","沖縄県":"九州・沖縄",
}

STORE_CHAIN_RE = re.compile(
    r"(マルハン|キコーナ|ガイア|PIA|ピア|楽園|エスパス|ジャンボ|ニラク|ハッピー|"
    r"ダイナム|ビックアップル|アビバ|夢屋|メガガイア|プレイランド|タイヨー|"
    r"ヴィーナス|ミリオン|ホームラン|エース|ゴールデン|サンパレス|"
    r"ワンダーランド|グランド|クイーン|ドリーム|マックス|ベガス|ロイヤル|"
    r"フレスポ|ニューキング|コンコルド|アミューズ|キャッスル|"
    r"Ｄステーション|Dステーション|メッセ|ビックマーチ|ZENT|ゼント|"
    r"楽天地|平和島|ゲンキー|アポロ|ひまわり|ニュートーキョー|"
    r"パラッツォ|スーパーホール|太陽|ガッツ|エムアール)"
    r"[^\s　,、。！!\n]{0,20}?(店|ホール|パーラー)"
)

EVENT_LABEL_RE: dict[str, re.Pattern] = {
    "来店":    re.compile(r"来店"),
    "取材":    re.compile(r"取材"),
    "撮影":    re.compile(r"撮影|ロケ"),
    "イベント": re.compile(r"イベント|特定日|設定示唆|周年|誕生日|オープン|新台"),
}

CAST_RE = re.compile(
    r"(?:出演|ゲスト|来店者|MC)[：:\s]*([^\n,、。！!\s]{2,20})|"
    r"([^\s]{2,10}(?:さん|先生|選手|プロ|氏))"
)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ---------------------------------------------------------------------------
# 認証・ブラウザ
# ---------------------------------------------------------------------------
def _get_x_cookies() -> list[dict]:
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0", "")
    if auth_token and ct0:
        log("🔑 CI: 環境変数からcookie注入")
        return [
            {"name":"auth_token","value":auth_token,"domain":".x.com","path":"/","secure":True,"httpOnly":True,"sameSite":"None"},
            {"name":"ct0","value":ct0,"domain":".x.com","path":"/","secure":True,"httpOnly":False,"sameSite":"Lax"},
        ]
    if HAS_BROWSER_COOKIE3:
        try:
            jar = browser_cookie3.chrome(domain_name=".x.com")
            result = []
            for c in jar:
                pw: dict = {"name":c.name,"value":c.value,"domain":c.domain or ".x.com",
                            "path":c.path or "/","secure":bool(c.secure),"httpOnly":False,"sameSite":"None"}
                if c.expires:
                    pw["expires"] = int(c.expires)
                result.append(pw)
            log(f"🍪 Chrome cookie {len(result)}個")
            return result
        except Exception as e:
            log(f"⚠️  browser_cookie3: {e}")
    return []


def launch_ctx(playwright, headless: bool):
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        locale="ja-JP",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    return ctx


# ---------------------------------------------------------------------------
# パース共通
# ---------------------------------------------------------------------------
def _guess_date(text: str) -> str:
    m = re.search(r'(\d{1,2})[/／](\d{1,2})', text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{mo:02d}/{dy:02d}"
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{mo:02d}/{dy:02d}"
    today = date.today()
    return f"{today.month:02d}/{today.day:02d}"


def _guess_pref_area(text: str) -> tuple[str, str]:
    for city, pref in CITY_PREF.items():
        if city in text:
            return pref, PREF_AREA.get(pref, "全国")
    for pref, area in PREF_AREA.items():
        if pref in text or pref.rstrip("県都府") in text:
            return pref, area
    return "不明", "全国"


def _guess_store(text: str, store_names: set[str]) -> str:
    for name in store_names:
        if name in text:
            return name
    m = STORE_CHAIN_RE.search(text)
    return m.group(0).strip() if m else ""


def _guess_event(text: str) -> str:
    for label, pat in EVENT_LABEL_RE.items():
        if pat.search(text):
            return label
    return "イベント"


def _guess_cast(text: str) -> str:
    m = CAST_RE.search(text)
    if m:
        return (m.group(1) or m.group(2) or "").strip()[:40]
    return ""


def _make_id(store: str, date_str: str, url: str) -> str:
    return hashlib.md5(f"{store}|{date_str}|{url}".encode()).hexdigest()[:12]


def _make_event(text: str, url: str, image_url: str, source: str, store_names: set[str]) -> dict | None:
    store = _guess_store(text, store_names)
    if not store:
        return None
    date_str = _guess_date(text)
    pref, area = _guess_pref_area(text)
    return {
        "id":        _make_id(store, date_str, url),
        "date":      date_str,
        "store":     store,
        "pref":      pref,
        "area":      area,
        "event":     _guess_event(text),
        "detail":    text[:300].replace("\n", " "),
        "cast":      _guess_cast(text),
        "highlight": "",
        "image_url": image_url,
        "x_url":     url if "x.com" in url else "",
        "url":       url,
        "source":    source,
    }


# ---------------------------------------------------------------------------
# X スクレイピング
# ---------------------------------------------------------------------------
def _x_images(article) -> list[str]:
    imgs = []
    for img in article.query_selector_all('img[src*="pbs.twimg.com/media"]'):
        src = img.get_attribute("src") or ""
        if src and src not in imgs:
            imgs.append(src)
    return imgs


def _x_url(article) -> str:
    time_el = article.query_selector("time")
    if time_el:
        href = time_el.evaluate("el => el.closest('a') ? el.closest('a').href : ''")
        if href and "status" in href:
            return href
    for lnk in article.query_selector_all('a[href*="/status/"]'):
        href = lnk.get_attribute("href") or ""
        if "/status/" in href:
            return f"https://x.com{href}" if href.startswith("/") else href
    return ""


def _x_scrape_page(page, store_names: set[str], max_tweets: int, source_label: str) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for article in page.query_selector_all('article[data-testid="tweet"]')[:max_tweets]:
        try:
            el = article.query_selector('[data-testid="tweetText"]')
            if not el:
                continue
            text = el.inner_text()
            if len(text) < 15:
                continue
            url = _x_url(article)
            if not url or url in seen:
                continue
            seen.add(url)
            imgs = _x_images(article)
            ev = _make_event(text, url, imgs[0] if imgs else "", "x", store_names)
            if ev:
                results.append(ev)
                log(f"      ✅ {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({source_label})")
        except Exception:
            continue
    return results


def scrape_x_timeline(page, username: str, store_names: set[str]) -> list[dict]:
    try:
        page.goto(f"https://x.com/{username}", timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=6000)
        except PlaywrightTimeout:
            return []
        for _ in range(4):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  @{username}: {e}")
        return []
    return _x_scrape_page(page, store_names, 30, f"@{username}")


def scrape_x_search(page, query: str, store_names: set[str]) -> list[dict]:
    encoded = query.replace(" ", "%20").replace("#", "%23")
    try:
        page.goto(f"https://x.com/search?q={encoded}&src=typed_query&f=live", timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=6000)
        except PlaywrightTimeout:
            return []
        for _ in range(7):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(600)
    except Exception as e:
        log(f"    ⚠️  {query!r}: {e}")
        return []
    return _x_scrape_page(page, store_names, 50, "search")


# ---------------------------------------------------------------------------
# Google News / Yahoo!リアルタイム
# ---------------------------------------------------------------------------
def scrape_google_news(page, query: str, store_names: set[str]) -> list[dict]:
    results: list[dict] = []
    try:
        page.goto(
            f"https://news.google.com/search?q={query.replace(' ', '+')}&hl=ja&gl=JP&ceid=JP:ja",
            timeout=18000, wait_until="domcontentloaded"
        )
        page.wait_for_timeout(2500)
        for _ in range(2):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  Google {query!r}: {e}")
        return results
    for article in page.query_selector_all('article')[:40]:
        try:
            title_el = article.query_selector('h3, h4')
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            if len(title) < 8:
                continue
            link_el = article.query_selector('a[href]')
            href = link_el.get_attribute("href") if link_el else ""
            if not href:
                continue
            if href.startswith("./"):
                href = "https://news.google.com/" + href[2:]
            elif href.startswith("/"):
                href = "https://news.google.com" + href
            ev = _make_event(title, href, "", "google", store_names)
            if ev:
                results.append(ev)
                log(f"      📰 {ev['store'][:18]} [{ev['pref']}]")
        except Exception:
            continue
    return results


def scrape_yahoo_realtime(page, query: str, store_names: set[str]) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    try:
        page.goto(
            f"https://search.yahoo.co.jp/realtime/search?p={query.replace(' ', '+')}&ei=UTF-8",
            timeout=18000, wait_until="domcontentloaded"
        )
        page.wait_for_timeout(3000)
        for _ in range(3):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  Yahoo {query!r}: {e}")
        return results
    for tweet_div in page.query_selector_all('[class*="Tweet_"], .tweetItem, li[class*="tweet"], article')[:50]:
        try:
            text_el = tweet_div.query_selector('[class*="body"], [class*="text"], p, span')
            if not text_el:
                continue
            text = text_el.inner_text()
            if len(text) < 15:
                continue
            link_el = tweet_div.query_selector('a[href*="x.com"], a[href*="twitter.com"]')
            url = link_el.get_attribute("href") if link_el else ""
            if url in seen:
                continue
            if url:
                seen.add(url)
            ev = _make_event(text, url or f"yrt-{_make_id('', '', text)}", "", "yahoo_rt", store_names)
            if ev:
                results.append(ev)
                log(f"      📡 {ev['store'][:18]} [{ev['pref']}]")
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# 保存・マージ
# ---------------------------------------------------------------------------
def load_events() -> tuple[list[dict], dict | None]:
    if not EVENTS_JSON.exists():
        return [], None
    with open(EVENTS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("events", []), data
    return data, None


def save_events(events: list[dict], original: dict | None):
    out = original if isinstance(original, dict) else {}
    out["events"] = events
    with open(EVENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"💾 events_public.json: {len(events)}件")


def merge_events(existing: list[dict], new_events: list[dict]) -> tuple[list[dict], int]:
    existing_ids = {ev["id"] for ev in existing}
    existing_urls = {ev.get("url", "") for ev in existing if ev.get("url")}
    added = 0
    prepend: list[dict] = []
    for ev in new_events:
        if ev["id"] in existing_ids:
            continue
        if ev.get("url") and ev["url"] in existing_urls:
            continue
        prepend.append(ev)
        existing_ids.add(ev["id"])
        if ev.get("url"):
            existing_urls.add(ev["url"])
        added += 1
    return (prepend + existing)[:10000], added  # 上限1万件


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--job", choices=["accounts", "search", "google", "all"], default="all")
    args = parser.parse_args()

    # machines.jsonから人気機種名取得
    machine_names: list[str] = []
    if MACHINES_JSON.exists():
        with open(MACHINES_JSON, encoding="utf-8") as f:
            mdata = json.load(f)
        machine_names = [m["name"] for m in mdata.get("machines", []) if m.get("name")]

    X_QUERIES = _build_queries(machine_names)

    log("=" * 70)
    log(f"🚀 fetch_events  job={args.job}")
    log(f"   メディアアカウント:{len(MEDIA_ACCOUNTS)}  店舗アカウント:{len(STORE_ACCOUNTS)}")
    log(f"   検索クエリ:{len(X_QUERIES)}  Google:{len(GOOGLE_QUERIES)}  Yahoo:{len(YAHOO_RT_QUERIES)}")

    # stores.jsonから店舗名セット
    store_names: set[str] = set()
    if STORES_JSON.exists():
        with open(STORES_JSON, encoding="utf-8") as f:
            for s in json.load(f):
                name = s.get("name", "")
                if name and len(name) >= 4:
                    store_names.add(name)
    log(f"📦 store_names: {len(store_names)}店舗")

    existing, original = load_events()
    log(f"📦 既存イベント: {len(existing)}件")

    all_new: list[dict] = []

    with sync_playwright() as pw:
        ctx = launch_ctx(pw, args.headless)

        # X 認証
        if args.job in ("accounts", "search", "all"):
            cookies = _get_x_cookies()
            if cookies:
                ctx.add_cookies(cookies)
                log(f"✅ Cookie {len(cookies)}個注入")

        page = ctx.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ── JOB A: X タイムライン（メディア + 店舗） ──
        if args.job in ("accounts", "all"):
            try:
                page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                logged_in = "login" not in page.url.lower()
            except Exception:
                logged_in = False

            if logged_in:
                log("✅ Xログイン OK")

                log(f"\n📋 メディアアカウント ({len(MEDIA_ACCOUNTS)}件)")
                for i, (username, label) in enumerate(MEDIA_ACCOUNTS.items(), 1):
                    log(f"  [{i}/{len(MEDIA_ACCOUNTS)}] @{username}")
                    try:
                        res = scrape_x_timeline(page, username, store_names)
                        if res:
                            log(f"       → {len(res)}件")
                        all_new.extend(res)
                        time.sleep(1.0)
                    except Exception as e:
                        log(f"    ❌ {e}")

                log(f"\n🏪 個別店舗アカウント ({len(STORE_ACCOUNTS)}件)")
                for i, (username, label) in enumerate(STORE_ACCOUNTS.items(), 1):
                    log(f"  [{i}/{len(STORE_ACCOUNTS)}] @{username} ({label})")
                    try:
                        res = scrape_x_timeline(page, username, store_names)
                        if res:
                            log(f"       → {len(res)}件")
                        all_new.extend(res)
                        time.sleep(0.8)
                    except Exception as e:
                        log(f"    ❌ {e}")
            else:
                log("❌ Xにログインできていません")

        # ── JOB B: X 検索 ──
        if args.job in ("search", "all"):
            if args.job == "search":
                try:
                    page.goto("https://x.com/home", timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    logged_in = "login" not in page.url.lower()
                except Exception:
                    logged_in = False
            else:
                logged_in = True

            if logged_in:
                log(f"\n🔍 X 検索クエリ ({len(X_QUERIES)}件)")
                for i, query in enumerate(X_QUERIES, 1):
                    log(f"  [{i}/{len(X_QUERIES)}] {query}")
                    try:
                        res = scrape_x_search(page, query, store_names)
                        if res:
                            log(f"       → {len(res)}件")
                        all_new.extend(res)
                        time.sleep(0.8)
                    except Exception as e:
                        log(f"    ❌ {e}")

        # ── JOB C: Yahoo + Google ──
        if args.job in ("google", "all"):
            log(f"\n📡 Yahoo!リアルタイム ({len(YAHOO_RT_QUERIES)}件)")
            for i, query in enumerate(YAHOO_RT_QUERIES, 1):
                log(f"  [{i}] {query}")
                try:
                    res = scrape_yahoo_realtime(page, query, store_names)
                    if res:
                        log(f"       → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(1.5)
                except Exception as e:
                    log(f"    ❌ {e}")

            log(f"\n📰 Google News ({len(GOOGLE_QUERIES)}件)")
            for i, query in enumerate(GOOGLE_QUERIES, 1):
                log(f"  [{i}] {query}")
                try:
                    res = scrape_google_news(page, query, store_names)
                    if res:
                        log(f"       → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(1.8)
                except Exception as e:
                    log(f"    ❌ {e}")

        page.close()
        ctx.close()

    seen_ids: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen_ids or seen_ids.add(e["id"]))]  # type: ignore
    log(f"\n📊 収集: {len(deduped)}件（重複除去後）")

    merged, added = merge_events(existing, deduped)
    log(f"➕ 新規: {added}件 / 累計: {len(merged)}件")

    if added > 0:
        save_events(merged, original)

    log("=" * 70)


if __name__ == "__main__":
    main()
