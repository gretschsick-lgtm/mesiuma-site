#!/usr/bin/env python3
"""
パチスロ来店・取材イベント情報を限界まで収集。
X(アカウントタイムライン＋検索) / Yahoo!リアルタイム / Google News /
ぱちタウン / スロパチステーション / ジャンバリ / 必勝本 / パチマガ /
YouTube（コミュニティ投稿 + 動画タイトル + 検索）

GitHub Actions 対応: X_AUTH_TOKEN / X_CT0 環境変数で認証。
JOB で実行モードを切り替え。

Usage:
    python scripts/fetch_events.py --headless --job accounts
    python scripts/fetch_events.py --headless --job search
    python scripts/fetch_events.py --headless --job google
    python scripts/fetch_events.py --headless --job web
    python scripts/fetch_events.py --headless --job youtube
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

EVENTS_JSON  = Path(__file__).parent.parent / "public/events_public.json"
STORES_JSON  = Path(__file__).parent.parent / "public/stores.json"
MACHINES_JSON= Path(__file__).parent.parent / "public/machines.json"

# ===========================================================================
# JOB A: X アカウント タイムライン
# ===========================================================================

# ── メディア・番組（実在が確認されているアカウント優先） ──
MEDIA_ACCOUNTS: dict[str, str] = {
    # 大手メディア・番組
    "PAA_pmportal":      "パチマガスロマガ",
    "suropachi_staff":   "スロパチステーション",
    "janbari_info":      "ジャンバリ",
    "KD_56_PS":          "KD情報",
    "3x3star_slot":      "3×3STAR",
    "gorsei_tv":         "極誓",
    "kaido_adv":         "回胴アドベンチャー",
    "ps_chosain":        "PS調査員",
    "buzzslot_jp":       "バズスロ",
    "slotimes_jp":       "SLOTIMES",
    "asadera_tv":        "あさくら",
    "yume_dori":         "夢ドリ",
    "realdoc_pachi":     "REAL取材",
    "gokumichi_dome":    "限界突破DOME",
    "eyeslot_official":  "アイスロ",
    "gogonet_slot":      "gogoネット",
    "pachi_jouhou":      "パチンコ情報局",
    "slot_matome_jp":    "スロットまとめ",
    "pachitimes_jp":     "パチスロ必勝本",
    "suro_select":       "スロセレ",
    "superslot_tv":      "スーパースロットTV",
    "kakuhen_info":      "確変情報",
    "pachi_tatsujin":    "パチスロ達人",
    "gokuzei_take":      "極誓取材",
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
    "kyushu_slot_event": "九州スロットイベント",
    "okinawa_pachi":     "沖縄パチスロ情報",
    "kanto_slot_info":   "関東スロット情報",
    "koshinetsu_pachi":  "甲信越パチスロ",
    "tohoku_event_ps":   "東北イベント情報",
    # タレント・ライター（実在アカウント）
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
    "saki_slot_jp":      "さき",
    "hana_pachislo":     "はな",
    "yui_slot777":       "ゆい",
    "mana_pachi":        "まな",
    "kana_slot_jp":      "かな",
    "risa_pachi777":     "りさ",
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
    "niraku_official":   "ニラク公式",
    "apollo_pachi":      "アポロ公式",
    "hokuou_pachi":      "北欧公式",
    "messe_official":    "メッセ公式",
    "genkys_official":   "ゲンキー公式",
    "dstation_jp":       "Dステーション公式",
    # ── 有名パチスロ系YouTuber（X も同時運用・ホール撮影告知の主要ソース） ──
    "HamadaBritney":       "浜田ブリトニー",
    "garizou_slot":        "ガリぞう",
    "garizou777":          "ガリぞう(別)",
    "kimurauotaku":        "木村魚拓",
    "batchimatsumoto":     "松本バッチ",
    "uichi_slot":          "ういち",
    "revin_pachi":         "レビン",
    "msa_slot":            "みさお",
    "hikitsuyoman":        "ヒキ強マン",
    "settei_shu":          "設定師シュウ",
    "gen_pachi_tv":        "ゲンさん",
    "orochi_d_slot":       "鬼Dオロチ",
    "mario_slot_ch":       "まりも",
    "nishiyama_daishi":    "西山師匠",
    "aruarutaro_slot":     "パチスロあるある太郎",
    "kyodai_slotter":      "兄弟スロッター",
    "chikinsloter":        "ちきん",
    "staryonslot":         "スタリオン",
    "mokkun_pachi":        "もっくん",
    "tarojiro_slot":       "たろじろう",
    "oklt_kidoutai":       "オカルト機動隊",
    "ryupachi777":         "りゅうパチ",
    "slot_fukugyo_ch":     "スロット副業",
    "chonmage_gb":         "ちょんまげギャンブラー",
    "smapachi_ch":         "スマパチch",
    "slot_jiyujin":        "スロット自由人",
    "pachikichi_slot":     "パチキチ",
    "slot_daini_ch":       "パチスロ第二章",
    "pachi_papa_slot":     "スロパパ",
    "kaz_pachi_ch":        "カズパチ",
    "daimon_ps_ch":        "大門パチスロ",
    "slot_legend_x":       "スロットレジェンド",
}

# ── 個別店舗アカウント（ワンダーランド34 + ミリオン37 + その他） ──
STORE_ACCOUNTS_FIXED: dict[str, str] = {
    # ワンダーランド（九州）
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


def _load_store_accounts_from_json() -> dict[str, str]:
    """stores.jsonのx_urlからアカウント辞書を動的生成"""
    extra: dict[str, str] = {}
    if not STORES_JSON.exists():
        return extra
    with open(STORES_JSON, encoding="utf-8") as f:
        stores = json.load(f)
    for s in stores:
        x_url = s.get("x_url", "")
        name = s.get("name", "")
        if not (x_url and name):
            continue
        # https://x.com/username or https://twitter.com/username
        m = re.search(r'(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)', x_url)
        if m:
            username = m.group(1)
            if username not in STORE_ACCOUNTS_FIXED:
                extra[username] = name
    return extra


# ===========================================================================
# JOB B: X 検索クエリ（動的生成）
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
        "#パチスロイベント",
        "#スロットイベント",
        "#ホールイベント パチスロ",
        "#設定示唆 パチスロ",
        "#全台系 パチスロ",
        "#コンプリート パチスロ",
        # ── 番組・メディア名 ──
        "スロパチステーション 来店",     "スロパチステーション 取材",
        "ジャンバリ 取材",               "ジャンバリ 来店",
        "パチマガスロマガ 来店",         "パチマガスロマガ 取材",
        "KD情報 来店",                   "KD情報 取材",
        "3×3STAR 取材",                  "3×3STAR 来店",
        "極誓 取材",                     "極誓 来店",
        "回胴アドベンチャー 来店",       "PS調査員 取材",
        "バズスロ 来店",                 "SLOTIMES 来店",
        "あさくら 来店",                 "夢ドリ 来店",
        "REAL取材 パチスロ",             "限界突破DOME 取材",
        "アイスロ 来店",                 "必勝本 取材",
        "パチ7 取材",                    "gogoネット 来店",
        # ── イベント種別 ──
        "来店イベント パチスロ 今日",    "来店イベント スロット 今週",
        "来店 スマスロ",                 "取材 パチスロ イベント",
        "撮影 パチスロ 来店",            "実戦取材 パチスロ",
        "収録 パチスロ 来店",            "ライター来店 パチスロ",
        "タレント来店 スロット",         "グラドル来店 スロット",
        "女優来店 パチスロ",             "誕生日イベント スロット",
        "周年記念 パチスロ イベント",    "オープン記念 パチスロ",
        "新台入替 パチスロ イベント",    "特定日 パチスロ 今日",
        "設定示唆 パチスロ イベント",    "全台イベント パチスロ",
        "コンプリートイベント スロット", "ホール イベント 来店 スロット",
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
        "ジャンボ 来店 パチスロ",       "タイヨー 来店 パチスロ",
        "夢屋 来店 パチスロ",           "ビックアップル 来店 パチスロ",
        "ハッピー 来店 パチスロ",       "ホームラン 来店 パチスロ",
        "楽天地 来店 パチスロ",         "平和島 来店 パチスロ",
        "パラッツォ 来店 パチスロ",     "エース 来店 パチスロ",
        "ロイヤル 来店 パチスロ",       "グランド 来店 パチスロ",
        "サンパレス 来店 パチスロ",     "ゴールデン 来店 パチスロ",
        # ── 北海道 ──
        "札幌 来店 OR 取材 パチスロ",   "旭川 来店 OR 取材 パチスロ",
        "函館 来店 OR 取材 パチスロ",   "帯広 来店 OR 取材 パチスロ",
        "北見 来店 OR 取材 パチスロ",   "釧路 来店 OR 取材 パチスロ",
        "小樽 来店 OR 取材 パチスロ",   "苫小牧 来店 OR 取材 パチスロ",
        "室蘭 来店 OR 取材 パチスロ",   "北海道 来店 OR 取材 パチスロ",
        # ── 東北 ──
        "仙台 来店 OR 取材 パチスロ",   "青森 来店 OR 取材 パチスロ",
        "盛岡 来店 OR 取材 パチスロ",   "秋田 来店 OR 取材 パチスロ",
        "山形 来店 OR 取材 パチスロ",   "福島 来店 OR 取材 パチスロ",
        "郡山 来店 OR 取材 パチスロ",   "いわき 来店 OR 取材 パチスロ",
        "弘前 来店 OR 取材 パチスロ",   "八戸 来店 OR 取材 パチスロ",
        "石巻 来店 OR 取材 パチスロ",   "会津若松 来店 OR 取材 パチスロ",
        "一関 来店 OR 取材 パチスロ",   "鶴岡 来店 OR 取材 パチスロ",
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
        "練馬 来店 OR 取材 パチスロ",   "目黒 来店 OR 取材 パチスロ",
        "世田谷 来店 OR 取材 パチスロ", "墨田 来店 OR 取材 パチスロ",
        "荒川 来店 OR 取材 パチスロ",   "杉並 来店 OR 取材 パチスロ",
        # ── 関東・他 ──
        "横浜 来店 OR 取材 パチスロ",   "川崎 来店 OR 取材 パチスロ",
        "相模原 来店 OR 取材 パチスロ", "藤沢 来店 OR 取材 パチスロ",
        "厚木 来店 OR 取材 パチスロ",   "平塚 来店 OR 取材 パチスロ",
        "横須賀 来店 OR 取材 パチスロ", "小田原 来店 OR 取材 パチスロ",
        "茅ヶ崎 来店 OR 取材 パチスロ", "海老名 来店 OR 取材 パチスロ",
        "大宮 来店 OR 取材 パチスロ",   "浦和 来店 OR 取材 パチスロ",
        "川口 来店 OR 取材 パチスロ",   "所沢 来店 OR 取材 パチスロ",
        "越谷 来店 OR 取材 パチスロ",   "熊谷 来店 OR 取材 パチスロ",
        "川越 来店 OR 取材 パチスロ",   "春日部 来店 OR 取材 パチスロ",
        "草加 来店 OR 取材 パチスロ",
        "千葉 来店 OR 取材 パチスロ",   "船橋 来店 OR 取材 パチスロ",
        "柏 来店 OR 取材 パチスロ",     "松戸 来店 OR 取材 パチスロ",
        "市川 来店 OR 取材 パチスロ",   "成田 来店 OR 取材 パチスロ",
        "流山 来店 OR 取材 パチスロ",   "我孫子 来店 OR 取材 パチスロ",
        "水戸 来店 OR 取材 パチスロ",   "つくば 来店 OR 取材 パチスロ",
        "日立 来店 OR 取材 パチスロ",
        "宇都宮 来店 OR 取材 パチスロ", "小山 来店 OR 取材 パチスロ",
        "前橋 来店 OR 取材 パチスロ",   "高崎 来店 OR 取材 パチスロ",
        "伊勢崎 来店 OR 取材 パチスロ", "太田 来店 OR 取材 パチスロ",
        # ── 中部 ──
        "名古屋 来店 OR 取材 パチスロ", "栄 来店 OR 取材 パチスロ",
        "豊橋 来店 OR 取材 パチスロ",   "岡崎 来店 OR 取材 パチスロ",
        "一宮 来店 OR 取材 パチスロ",   "豊田 来店 OR 取材 パチスロ",
        "春日井 来店 OR 取材 パチスロ", "刈谷 来店 OR 取材 パチスロ",
        "浜松 来店 OR 取材 パチスロ",   "静岡 来店 OR 取材 パチスロ",
        "沼津 来店 OR 取材 パチスロ",   "富士 来店 OR 取材 パチスロ",
        "磐田 来店 OR 取材 パチスロ",
        "新潟 来店 OR 取材 パチスロ",   "長岡 来店 OR 取材 パチスロ",
        "上越 来店 OR 取材 パチスロ",   "三条 来店 OR 取材 パチスロ",
        "金沢 来店 OR 取材 パチスロ",   "富山 来店 OR 取材 パチスロ",
        "福井 来店 OR 取材 パチスロ",   "敦賀 来店 OR 取材 パチスロ",
        "長野 来店 OR 取材 パチスロ",   "松本 来店 OR 取材 パチスロ",
        "上田 来店 OR 取材 パチスロ",   "飯田 来店 OR 取材 パチスロ",
        "甲府 来店 OR 取材 パチスロ",
        "岐阜 来店 OR 取材 パチスロ",   "大垣 来店 OR 取材 パチスロ",
        "各務原 来店 OR 取材 パチスロ", "四日市 来店 OR 取材 パチスロ",
        "津 来店 OR 取材 パチスロ",     "鈴鹿 来店 OR 取材 パチスロ",
        "伊勢 来店 OR 取材 パチスロ",
        # ── 近畿 ──
        "大阪 来店 OR 取材 パチスロ",   "難波 来店 OR 取材 パチスロ",
        "梅田 来店 OR 取材 パチスロ",   "天王寺 来店 OR 取材 パチスロ",
        "堺 来店 OR 取材 パチスロ",     "東大阪 来店 OR 取材 パチスロ",
        "吹田 来店 OR 取材 パチスロ",   "枚方 来店 OR 取材 パチスロ",
        "豊中 来店 OR 取材 パチスロ",   "岸和田 来店 OR 取材 パチスロ",
        "八尾 来店 OR 取材 パチスロ",   "茨木 来店 OR 取材 パチスロ",
        "京都 来店 OR 取材 パチスロ",   "宇治 来店 OR 取材 パチスロ",
        "舞鶴 来店 OR 取材 パチスロ",
        "神戸 来店 OR 取材 パチスロ",   "三宮 来店 OR 取材 パチスロ",
        "姫路 来店 OR 取材 パチスロ",   "尼崎 来店 OR 取材 パチスロ",
        "西宮 来店 OR 取材 パチスロ",   "明石 来店 OR 取材 パチスロ",
        "宝塚 来店 OR 取材 パチスロ",   "加古川 来店 OR 取材 パチスロ",
        "奈良 来店 OR 取材 パチスロ",   "橿原 来店 OR 取材 パチスロ",
        "和歌山 来店 OR 取材 パチスロ",
        "大津 来店 OR 取材 パチスロ",   "草津 来店 OR 取材 パチスロ",
        "彦根 来店 OR 取材 パチスロ",   "長浜 来店 OR 取材 パチスロ",
        # ── 中国・四国 ──
        "広島 来店 OR 取材 パチスロ",   "福山 来店 OR 取材 パチスロ",
        "呉 来店 OR 取材 パチスロ",     "尾道 来店 OR 取材 パチスロ",
        "岡山 来店 OR 取材 パチスロ",   "倉敷 来店 OR 取材 パチスロ",
        "津山 来店 OR 取材 パチスロ",
        "山口 来店 OR 取材 パチスロ",   "下関 来店 OR 取材 パチスロ",
        "宇部 来店 OR 取材 パチスロ",
        "鳥取 来店 OR 取材 パチスロ",   "米子 来店 OR 取材 パチスロ",
        "松江 来店 OR 取材 パチスロ",   "出雲 来店 OR 取材 パチスロ",
        "松山 来店 OR 取材 パチスロ",   "今治 来店 OR 取材 パチスロ",
        "新居浜 来店 OR 取材 パチスロ",
        "高松 来店 OR 取材 パチスロ",   "丸亀 来店 OR 取材 パチスロ",
        "高知 来店 OR 取材 パチスロ",   "徳島 来店 OR 取材 パチスロ",
        # ── 九州・沖縄 ──
        "福岡 来店 OR 取材 パチスロ",   "博多 来店 OR 取材 パチスロ",
        "北九州 来店 OR 取材 パチスロ", "久留米 来店 OR 取材 パチスロ",
        "飯塚 来店 OR 取材 パチスロ",   "大牟田 来店 OR 取材 パチスロ",
        "熊本 来店 OR 取材 パチスロ",   "八代 来店 OR 取材 パチスロ",
        "鹿児島 来店 OR 取材 パチスロ", "姶良 来店 OR 取材 パチスロ",
        "長崎 来店 OR 取材 パチスロ",   "佐世保 来店 OR 取材 パチスロ",
        "諫早 来店 OR 取材 パチスロ",
        "大分 来店 OR 取材 パチスロ",   "別府 来店 OR 取材 パチスロ",
        "中津 来店 OR 取材 パチスロ",
        "宮崎 来店 OR 取材 パチスロ",   "都城 来店 OR 取材 パチスロ",
        "佐賀 来店 OR 取材 パチスロ",   "唐津 来店 OR 取材 パチスロ",
        "那覇 来店 OR 取材 パチスロ",   "浦添 来店 OR 取材 パチスロ",
        "宜野湾 来店 OR 取材 パチスロ", "沖縄市 来店 OR 取材 パチスロ",
        "沖縄 来店 OR 取材 パチスロ",
    ]

    # 人気機種 × 来店
    popular = [
        "北斗の拳","バジリスク","ヴァルヴレイヴ","炎炎ノ消防隊","攻殻機動隊",
        "カバネリ","モンスターハンター","リコリス","ゾンビランドサガ","ジャグラー",
        "鉄拳","吉宗","チバリヨ","牙狼","ミリオンゴッド","東京喰種","エヴァ",
        "スマスロ北斗","スマスロバジリスク","スマスロヴァルヴレイヴ",
        "バイオハザード","アクエリオン","まどマギ","化物語","シュタゲ",
        "花火絶景","真北斗無双","北斗天昇","バジリスク絆","沖ドキ",
        "Lジャグラー","マイジャグ","ゴーゴージャグラー","アイムジャグラー",
        "Re:ゼロ","転スラ","鬼滅の刃","ヴァルヴレイヴ","カバネリ",
        "押忍!番長","蒼天の拳","ラブ嬌","ランブルローズ",
    ]
    for m in popular:
        base.append(f"{m} 来店 OR 取材")

    # machines.jsonから追加機種
    for name in machine_names[:50]:
        short = re.sub(r'^(?:スマスロ|Lパチスロ|パチスロ|スマパチ|L)\s*', '', name).strip()
        if len(short) >= 3 and short not in popular:
            base.append(f"{short} 来店 OR 取材")

    return list(dict.fromkeys(base))


# ===========================================================================
# JOB C: Google / Yahoo クエリ
# ===========================================================================
GOOGLE_QUERIES = [
    "パチスロ 来店イベント 今日",        "パチンコ 取材イベント 今週",
    "スロット 来店 関東",                "パチスロ 来店 関西",
    "パチスロ 来店 九州",               "パチスロ 来店 東北",
    "スマスロ 来店 取材",               "パチンコ スロット 来店 イベント",
    "マルハン 来店イベント",            "キコーナ 来店イベント",
    "ダイナム 来店イベント",            "ガイア 来店イベント",
    "パチスロ 取材 北海道",             "パチスロ 取材 中部",
    "パチスロ 取材 中国四国",           "パチスロライター 来店 今日",
    "スロットライター 取材 今週",       "パチンコ グラドル 来店",
    "パチスロ 来店 沖縄",               "スロット 誕生日イベント",
    "パチスロ 周年記念 イベント",       "パチスロ 新台 来店",
    "スロット 特定日 今週",             "パチンコ 来店 芸能人",
    "スロパチステーション 取材予定",    "ジャンバリ 取材予定",
    "パチマガスロマガ 来店予定",        "KD情報 来店スケジュール",
    "パチスロ 来店 中部",               "パチスロ 来店 四国",
    "パチスロ 全台イベント",            "スマスロ 全台系 イベント",
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
    "パチスロ 全台系 イベント",
    "スロット 誕生日 来店",
    "パチスロ 周年 来店",
    "来店取材 スロット",
]

# ===========================================================================
# JOB D: 公式イベントサイト直接スクレイピング
# ===========================================================================
WEB_SOURCES = [
    # ぱちタウンイベント
    {
        "name":    "p-town",
        "urls":    [
            "https://p-town.dmm.com/event/",
            "https://p-town.dmm.com/event/?page=2",
            "https://p-town.dmm.com/event/?page=3",
        ],
        "type":    "p-town",
    },
    # スロパチステーション公式
    {
        "name":    "slotpachi",
        "urls":    [
            "https://www.slotpachi.jp/event/",
            "https://www.slotpachi.jp/event/?page=2",
        ],
        "type":    "news_list",
    },
    # ジャンバリ公式
    {
        "name":    "janbari",
        "urls":    [
            "https://www.janbari.jp/event/",
            "https://www.janbari.jp/event/?page=2",
        ],
        "type":    "news_list",
    },
    # 必勝本
    {
        "name":    "hisshobon",
        "urls":    [
            "https://hisshobon.net/events/",
        ],
        "type":    "news_list",
    },
    # パチマガスロマガ
    {
        "name":    "pachinkovillage",
        "urls":    [
            "https://www.pachinkovillage.net/event/",
        ],
        "type":    "news_list",
    },
    # パチ7
    {
        "name":    "pachi7",
        "urls":    [
            "https://www.pachi7.jp/event/",
        ],
        "type":    "news_list",
    },
    # gogoネット
    {
        "name":    "gogo_net",
        "urls":    [
            "https://www.gogonet.co.jp/event/",
        ],
        "type":    "news_list",
    },
]

# ===========================================================================
# JOB E: YouTube チャンネル（コミュニティ投稿 + 最新動画タイトル）
# ===========================================================================

# @handle形式。コミュニティ投稿 → /community、動画一覧 → /videos を順にスクレイプ
# 存在しないハンドルは 404 で自動スキップされる
YOUTUBE_CHANNELS: list[dict] = [
    # ── トップクラス（チャンネル登録者数100万超・超有名） ──
    {"handle": "HamadaBritney",         "name": "浜田ブリトニー"},
    {"handle": "garizou",               "name": "ガリぞう"},
    {"handle": "garizouslot",           "name": "ガリぞう(別)"},
    {"handle": "kimurauotaku",          "name": "木村魚拓"},
    {"handle": "matsumotobatch",        "name": "松本バッチ"},
    {"handle": "uichihikaru",           "name": "ういちとヒカル"},
    {"handle": "uichi",                 "name": "ういち"},
    {"handle": "misaoTV",               "name": "みさお"},
    {"handle": "misao_slot",            "name": "みさお(別)"},
    {"handle": "REVIN777",              "name": "レビン"},
    {"handle": "revin_slot",            "name": "レビン(別)"},
    {"handle": "hikotsuyoman",          "name": "ヒキ強マン"},
    {"handle": "orochislot",            "name": "鬼Dオロチ"},
    {"handle": "onidorochiTV",          "name": "鬼Dオロチ(別)"},
    # ── 人気ライター・タレント系 ──
    {"handle": "settei_shu",            "name": "設定師シュウ"},
    {"handle": "gensanpachisuro",       "name": "ゲンさん"},
    {"handle": "marimoslot",            "name": "まりも"},
    {"handle": "marimo_slot",           "name": "まりも(別)"},
    {"handle": "nishiyama_daishi",      "name": "西山師匠"},
    {"handle": "kouda_yuki_slot",       "name": "倖田柚希"},
    {"handle": "mochizuki_saki_slot",   "name": "望月咲"},
    {"handle": "hiraki_hikaru",         "name": "煌ひかる"},
    {"handle": "happy_slot_ch",         "name": "ハッピー"},
    {"handle": "motopachi",             "name": "もとパチ"},
    {"handle": "tsujo_slot",            "name": "通常スロット"},
    {"handle": "slot_papa",             "name": "スロパパ"},
    {"handle": "kazupachi_ch",          "name": "カズ"},
    {"handle": "daimon_slot_ch",        "name": "大門"},
    {"handle": "slot_legend",           "name": "スロットレジェンド"},
    # ── 実戦・攻略系（登録者50万クラス） ──
    {"handle": "pachislo_aruaruth",     "name": "パチスロあるある太郎"},
    {"handle": "aruarutaro_slot",       "name": "あるある太郎(別)"},
    {"handle": "slot_jiyujin",          "name": "パチスロ自由人"},
    {"handle": "srotkijudge",           "name": "スロット鬼打ち"},
    {"handle": "kyodaislotter",         "name": "兄弟スロッター"},
    {"handle": "chikinsloter",          "name": "ちきん"},
    {"handle": "staryonpachisuro",      "name": "スタリオン"},
    {"handle": "mokkun_slot",           "name": "もっくん"},
    {"handle": "tarojiroChannel",       "name": "たろじろう"},
    {"handle": "okarutkidoutai",        "name": "オカルト機動隊"},
    {"handle": "slot_tensai_ch",        "name": "スロット天才"},
    {"handle": "pachisuro777ch",        "name": "パチスロ777ch"},
    {"handle": "ryupachi777",           "name": "りゅうパチ"},
    {"handle": "slot_fukugyo",          "name": "スロット副業サラリーマン"},
    {"handle": "chonmage_gambler",      "name": "ちょんまげギャンブラー"},
    {"handle": "pachisuro_daini",       "name": "パチスロ第二章"},
    {"handle": "slot_saikyou",          "name": "最強スロット"},
    {"handle": "pachikichi777",         "name": "パチキチ"},
    {"handle": "smapachi_ch",           "name": "スマパチch"},
    {"handle": "smart_slot_ch",         "name": "スマスロch"},
    {"handle": "slotfree777",           "name": "スロットフリー"},
    {"handle": "pachinko_gyokai",       "name": "パチンコ業界ch"},
    # ── 公式メディア系 ──
    {"handle": "janbari_ch",            "name": "ジャンバリ公式"},
    {"handle": "slotpachi_official",    "name": "スロパチステーション公式"},
    {"handle": "PACHISLO_HISSHOBON",    "name": "パチスロ必勝本公式"},
    {"handle": "hisshobon_slot",        "name": "必勝本(別)"},
    {"handle": "PM_portal",             "name": "パチマガスロマガ公式"},
    {"handle": "pachi7_official",       "name": "パチ7公式"},
    {"handle": "gogonet_official",      "name": "gogoネット公式"},
    {"handle": "KDjoho",                "name": "KD情報"},
    {"handle": "3x3star_official",      "name": "3×3STAR"},
    {"handle": "gokuzei_official",      "name": "極誓"},
    {"handle": "kaidou_adventure",      "name": "回胴アドベンチャー"},
    {"handle": "BuzzSlot",              "name": "バズスロ"},
    {"handle": "eyeslot_ch",            "name": "アイスロ"},
    {"handle": "pachisuro_hisshobon",   "name": "パチスロ必勝本"},
    {"handle": "pachi_taizin",          "name": "パチスロ達人ch"},
    {"handle": "slotimes_official",     "name": "SLOTIMES公式"},
    {"handle": "gokkun_pachi",          "name": "ゴックン"},
    # ── 女性系・グラドル系 ──
    {"handle": "slot_girls_ch",         "name": "スロットガールズ"},
    {"handle": "pachisuro_joshi",       "name": "パチスロ女子"},
    {"handle": "pachi_lady_ch",         "name": "パチレディch"},
    # ── ホール系・チェーン公式 ──
    {"handle": "maruhan_official_yt",   "name": "マルハン公式YT"},
    {"handle": "dynam_official_yt",     "name": "ダイナム公式YT"},
    {"handle": "kikoona_yt",            "name": "キコーナYT"},
    {"handle": "gaia_slot_yt",          "name": "ガイアYT"},
    {"handle": "wonderland_yt",         "name": "ワンダーランドYT"},
    # ── 機種実戦・メーカー系 ──
    {"handle": "konami_slot_official",  "name": "コナミスロット公式"},
    {"handle": "sammy_official_yt",     "name": "サミー公式YT"},
    {"handle": "universal_ent_yt",      "name": "ユニバーサル公式YT"},
    {"handle": "aristocrat_japan",      "name": "アリストクラート"},
    {"handle": "sega_sammy_yt",         "name": "セガサミーYT"},
]

# YouTube 検索クエリ（撮影スケジュール・ホール訪問系）
YOUTUBE_SEARCH_QUERIES: list[str] = [
    "パチスロ ホール撮影 来店",
    "スマスロ ホール 撮影 スケジュール",
    "パチスロ YouTube 撮影 予定",
    "パチスロ 来店 撮影 今週",
    "スロット ホール 取材 YouTube",
    "パチスロ YouTuber 来店 ホール",
    "スマスロ 撮影 来店 告知",
    "パチスロ 実戦 ホール 関東",
    "パチスロ 実戦 ホール 関西",
    "パチスロ 実戦 ホール 九州",
    "パチスロ 全台系 撮影",
    "スロット 高設定 撮影 ホール",
    "パチスロ 誕生日 撮影 来店",
    "スロット 周年 撮影 ホール",
    "パチスロ YouTube 撮影 告知 店名",
    "浜田ブリトニー ホール撮影",
    "ガリぞう ホール 撮影",
    "木村魚拓 ホール 撮影",
    "松本バッチ ホール 撮影",
    "ういち ホール 実戦",
    "みさお スロット ホール",
    "レビン パチスロ ホール",
    "パチスロあるある太郎 ホール",
    "スロット 北斗 撮影 ホール",
    "スマスロ バジリスク ホール 撮影",
    "パチスロ 実戦 東北 撮影",
    "パチスロ 実戦 中部 撮影",
    "パチスロ 実戦 四国 撮影",
    "パチスロ 実戦 沖縄 撮影",
    "パチスロ コラボ撮影 ホール",
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
    r"パラッツォ|スーパーホール|太陽|ガッツ|エムアール|北欧|"
    r"夢夢|キングダム|ガリバー|スロステ|ヴィクトリー|ダービー)"
    r"[^\s　,、。！!\n]{0,20}?(店|ホール|パーラー)"
)

EVENT_LABEL_RE: dict[str, re.Pattern] = {
    "来店":    re.compile(r"来店"),
    "取材":    re.compile(r"取材"),
    "撮影":    re.compile(r"撮影|ロケ"),
    "イベント": re.compile(r"イベント|特定日|設定示唆|周年|誕生日|オープン|新台|全台"),
}

CAST_RE = re.compile(
    r"(?:出演|ゲスト|来店者|MC)[：:\s]*([^\n,、。！!\s]{2,20})|"
    r"([^\s]{2,10}(?:さん|先生|選手|プロ|氏))"
)

EVENT_KEYWORD_RE = re.compile(
    r"来店|取材|撮影|ロケ|イベント|特定日|設定示唆|周年|誕生日|オープン|新台|全台"
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
    # stores.jsonの正確な店舗名で先に一致確認
    for name in store_names:
        if name in text:
            return name
    # チェーン正規表現でのフォールバック
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
    # イベント関連キーワードがなければスキップ
    if not EVENT_KEYWORD_RE.search(text):
        return None
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
        # 8回スクロールで深く取得
        for _ in range(8):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(400)
    except Exception as e:
        log(f"    ⚠️  @{username}: {e}")
        return []
    return _x_scrape_page(page, store_names, 50, f"@{username}")


def scrape_x_search(page, query: str, store_names: set[str]) -> list[dict]:
    encoded = query.replace(" ", "%20").replace("#", "%23")
    try:
        page.goto(f"https://x.com/search?q={encoded}&src=typed_query&f=live", timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=6000)
        except PlaywrightTimeout:
            return []
        # 12回スクロール
        for _ in range(12):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  {query!r}: {e}")
        return []
    return _x_scrape_page(page, store_names, 80, "search")


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
        for _ in range(3):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  Google {query!r}: {e}")
        return results
    for article in page.query_selector_all('article')[:50]:
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
        for _ in range(5):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  Yahoo {query!r}: {e}")
        return results
    for tweet_div in page.query_selector_all('[class*="Tweet_"], .tweetItem, li[class*="tweet"], article')[:80]:
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
# JOB D: 公式イベントサイト スクレイピング
# ---------------------------------------------------------------------------
def scrape_ptown_event(page, url: str, store_names: set[str]) -> list[dict]:
    """ぱちタウンのイベントページをスクレイピング"""
    results: list[dict] = []
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        for _ in range(3):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  p-town {url}: {e}")
        return results

    # ぱちタウンのイベントカード
    selectors = [
        'li[class*="event"]', 'div[class*="event-item"]',
        'div[class*="EventCard"]', 'article[class*="event"]',
        'div[class*="hall-event"]', '.event-list li',
    ]
    for sel in selectors:
        cards = page.query_selector_all(sel)
        if cards:
            for card in cards[:60]:
                try:
                    text = card.inner_text()
                    if len(text) < 10:
                        continue
                    link_el = card.query_selector('a[href]')
                    href = link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://p-town.dmm.com" + href
                    img_el = card.query_selector('img[src]')
                    img = img_el.get_attribute("src") if img_el else ""
                    ev = _make_event(text, href or url, img or "", "p-town", store_names)
                    if ev:
                        results.append(ev)
                        log(f"      🏢 {ev['store'][:18]} [{ev['pref']}] (p-town)")
                except Exception:
                    continue
            if results:
                break

    # フォールバック: 全テキストから抽出
    if not results:
        try:
            body = page.query_selector('main, #main, .main, body')
            if body:
                text = body.inner_text()
                lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 20]
                for line in lines[:100]:
                    ev = _make_event(line, url, "", "p-town", store_names)
                    if ev:
                        results.append(ev)
                        log(f"      🏢 {ev['store'][:18]} [{ev['pref']}] (p-town fallback)")
        except Exception:
            pass
    return results


def scrape_news_list(page, url: str, source_name: str, store_names: set[str]) -> list[dict]:
    """汎用ニュースリスト系イベントサイト"""
    results: list[dict] = []
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        for _ in range(3):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  {source_name} {url}: {e}")
        return results

    # 一般的なニュースリストセレクタ
    selectors = [
        'article', 'li.event', 'div.event', 'div[class*="event"]',
        'li[class*="article"]', 'div[class*="article"]', 'li[class*="news"]',
        'div[class*="news-item"]', 'div[class*="list-item"]',
        '.event-list li', '.news-list li', 'section[class*="event"]',
    ]
    for sel in selectors:
        cards = page.query_selector_all(sel)
        if len(cards) >= 3:
            for card in cards[:60]:
                try:
                    text = card.inner_text()
                    if len(text) < 10:
                        continue
                    link_el = card.query_selector('a[href]')
                    href = link_el.get_attribute("href") if link_el else url
                    if href and href.startswith("/"):
                        base = re.match(r'https?://[^/]+', url)
                        href = (base.group(0) if base else "") + href
                    img_el = card.query_selector('img[src]')
                    img = img_el.get_attribute("src") if img_el else ""
                    ev = _make_event(text, href or url, img or "", source_name, store_names)
                    if ev:
                        results.append(ev)
                        log(f"      🌐 {ev['store'][:18]} [{ev['pref']}] ({source_name})")
                except Exception:
                    continue
            if results:
                break
    return results


# ---------------------------------------------------------------------------
# JOB E: YouTube スクレイピング
# ---------------------------------------------------------------------------
def _yt_extract_from_text(text: str, url: str, img: str, source: str, store_names: set[str]) -> list[dict]:
    """YouTube テキスト（複数行）からイベント情報を抽出"""
    results: list[dict] = []
    # 行単位でパース（動画説明文は長いので段落ごとに）
    blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]
    for block in blocks[:20]:
        ev = _make_event(block, url, img, source, store_names)
        if ev:
            results.append(ev)
    # ブロック分割でヒットしなければ全文で1回試みる
    if not results and len(text) >= 15:
        ev = _make_event(text[:500], url, img, source, store_names)
        if ev:
            results.append(ev)
    return results


def scrape_youtube_community(page, handle: str, ch_name: str, store_names: set[str]) -> list[dict]:
    """YouTubeコミュニティ投稿をスクレイプ（撮影・来店告知が多い）"""
    results: list[dict] = []
    url = f"https://www.youtube.com/@{handle}/community"
    try:
        page.goto(url, timeout=22000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        # コミュニティタブが存在しないチャンネルはスキップ
        if "404" in page.title() or page.url == "https://www.youtube.com/":
            return results
        # スクロールして投稿をロード
        for _ in range(5):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(600)
    except Exception as e:
        log(f"    ⚠️  YT community @{handle}: {e}")
        return results

    # ytd-backstage-post-renderer が各投稿カード
    posts = page.query_selector_all("ytd-backstage-post-renderer, ytd-post-renderer")
    if not posts:
        # フォールバック: テキスト断片を広めに取る
        posts = page.query_selector_all("#content-text, yt-formatted-string[id='content-text']")

    for post in posts[:30]:
        try:
            text = post.inner_text().strip()
            if len(text) < 15:
                continue
            # 投稿リンク
            link_el = post.query_selector('a#permalink, a[href*="/post/"]')
            post_url = ""
            if link_el:
                href = link_el.get_attribute("href") or ""
                post_url = f"https://www.youtube.com{href}" if href.startswith("/") else href
            img_el = post.query_selector('img#img, img[src*="yt3.ggpht"]')
            img = img_el.get_attribute("src") if img_el else ""
            evs = _yt_extract_from_text(text, post_url or url, img, "youtube_community", store_names)
            for ev in evs:
                ev["cast"] = ev.get("cast") or ch_name
                results.append(ev)
                log(f"      🎬 {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({ch_name} community)")
        except Exception:
            continue
    return results


def scrape_youtube_videos(page, handle: str, ch_name: str, store_names: set[str]) -> list[dict]:
    """YouTube最新動画タイトルをスクレイプ（ホール名が含まれることが多い）"""
    results: list[dict] = []
    url = f"https://www.youtube.com/@{handle}/videos"
    try:
        page.goto(url, timeout=22000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "404" in page.title() or page.url == "https://www.youtube.com/":
            return results
        for _ in range(4):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  YT videos @{handle}: {e}")
        return results

    cards = page.query_selector_all("ytd-rich-item-renderer, ytd-grid-video-renderer")
    for card in cards[:40]:
        try:
            title_el = card.query_selector("#video-title, h3 a, a#video-title-link")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            if len(title) < 8:
                continue
            href = title_el.get_attribute("href") or ""
            video_url = f"https://www.youtube.com{href}" if href.startswith("/") else href
            img_el = card.query_selector("img#img, img[src*='ytimg']")
            img = img_el.get_attribute("src") if img_el else ""
            evs = _yt_extract_from_text(title, video_url, img, "youtube_video", store_names)
            for ev in evs:
                ev["cast"] = ev.get("cast") or ch_name
                results.append(ev)
                log(f"      🎥 {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({ch_name})")
        except Exception:
            continue
    return results


def scrape_youtube_search(page, query: str, store_names: set[str]) -> list[dict]:
    """YouTube検索（アップロード順）でホール撮影動画を収集"""
    results: list[dict] = []
    # sp=CAI%3D は「アップロード日時順」フィルタ
    encoded = query.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={encoded}&sp=CAI%3D"
    try:
        page.goto(url, timeout=22000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        for _ in range(4):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  YT search {query!r}: {e}")
        return results

    cards = page.query_selector_all("ytd-video-renderer, ytd-compact-video-renderer")
    for card in cards[:40]:
        try:
            title_el = card.query_selector("#video-title, a#video-title")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            if len(title) < 8:
                continue
            href = title_el.get_attribute("href") or ""
            video_url = f"https://www.youtube.com{href}" if href.startswith("/") else href
            img_el = card.query_selector("img#img, img[src*='ytimg']")
            img = img_el.get_attribute("src") if img_el else ""
            # チャンネル名を cast に
            ch_el = card.query_selector("ytd-channel-name a, #channel-name a")
            ch = ch_el.inner_text().strip() if ch_el else ""
            evs = _yt_extract_from_text(title, video_url, img, "youtube_search", store_names)
            for ev in evs:
                if ch and not ev.get("cast"):
                    ev["cast"] = ch
                results.append(ev)
                log(f"      🔍 {ev['store'][:18]} [{ev['pref']}] {ev['date']} (YT search)")
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
    existing_ids  = {ev["id"] for ev in existing}
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
    return (prepend + existing)[:15000], added  # 上限1.5万件


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--job", choices=["accounts", "search", "google", "web", "youtube", "all"], default="all")
    args = parser.parse_args()

    # stores.jsonから動的アカウント読み込み
    dynamic_store_accounts = _load_store_accounts_from_json()
    STORE_ACCOUNTS = {**STORE_ACCOUNTS_FIXED, **dynamic_store_accounts}
    ALL_ACCOUNTS   = {**MEDIA_ACCOUNTS, **STORE_ACCOUNTS}

    # machines.jsonから機種名取得
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
    log(f"   Webソース:{len(WEB_SOURCES)}サイト  YouTubeチャンネル:{len(YOUTUBE_CHANNELS)}ch  YouTube検索:{len(YOUTUBE_SEARCH_QUERIES)}クエリ")

    # stores.jsonから店舗名セット（短すぎる名前は除外）
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

        # X 認証注入
        if args.job in ("accounts", "search", "all"):
            cookies = _get_x_cookies()
            if cookies:
                ctx.add_cookies(cookies)
                log(f"✅ Cookie {len(cookies)}個注入")

        page = ctx.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        page.set_extra_http_headers({"Accept-Language": "ja-JP,ja;q=0.9"})

        # ── JOB A: X タイムライン ──
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
                        time.sleep(0.8)
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
                        time.sleep(0.7)
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
                        time.sleep(0.7)
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
                    time.sleep(1.5)
                except Exception as e:
                    log(f"    ❌ {e}")

        # ── JOB D: 公式イベントサイト ──
        if args.job in ("web", "all"):
            log(f"\n🌐 公式イベントサイト ({len(WEB_SOURCES)}サイト)")
            for src in WEB_SOURCES:
                log(f"  📖 {src['name']}")
                for url in src["urls"]:
                    try:
                        if src["type"] == "p-town":
                            res = scrape_ptown_event(page, url, store_names)
                        else:
                            res = scrape_news_list(page, url, src["name"], store_names)
                        if res:
                            log(f"       → {len(res)}件")
                        all_new.extend(res)
                        time.sleep(2.0)
                    except Exception as e:
                        log(f"    ❌ {src['name']} {url}: {e}")

        # ── JOB E: YouTube コミュニティ投稿 + 動画タイトル + 検索 ──
        if args.job in ("youtube", "all"):
            log(f"\n🎬 YouTube チャンネル コミュニティ投稿 ({len(YOUTUBE_CHANNELS)}ch)")
            for i, ch in enumerate(YOUTUBE_CHANNELS, 1):
                log(f"  [{i}/{len(YOUTUBE_CHANNELS)}] @{ch['handle']} ({ch['name']})")
                try:
                    # コミュニティ投稿
                    res = scrape_youtube_community(page, ch["handle"], ch["name"], store_names)
                    if res:
                        log(f"       community → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(1.0)
                    # 最新動画タイトル
                    res2 = scrape_youtube_videos(page, ch["handle"], ch["name"], store_names)
                    if res2:
                        log(f"       videos    → {len(res2)}件")
                    all_new.extend(res2)
                    time.sleep(1.0)
                except Exception as e:
                    log(f"    ❌ {ch['name']}: {e}")

            log(f"\n🔍 YouTube 検索 ({len(YOUTUBE_SEARCH_QUERIES)}クエリ)")
            for i, query in enumerate(YOUTUBE_SEARCH_QUERIES, 1):
                log(f"  [{i}] {query}")
                try:
                    res = scrape_youtube_search(page, query, store_names)
                    if res:
                        log(f"       → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(1.5)
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
