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
import subprocess
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
    # ── くり系 ──
    "kurimaru_slot":       "くりまる",
    "kurimaru777":         "くりまる(別)",
    "kuri_pachi_ch":       "くり",
    # ── 有名女性演者・YouTuber（X） ──
    "nanatoru_slot":       "なな徹",
    "nanatoru_pachi":      "なな徹(別)",
    "nanase_umi":          "七瀬美海",
    "kagamino_himari":     "鏡野ひまり",
    "yabuki_yurina":       "矢吹ゆりな",
    "ogino_megumi":        "荻野倫",
    "yukinnko_pachi":      "ゆきんこ",
    "seseragi_slot":       "せせらぎ",
    "pachiko_slot_x":      "ぱちこ",
    "pero_slot_x":         "ぺろ",
    "rinka_pachi_x":       "りんか",
    "ami_slot_x":          "あみ",
    "masuda_erina":        "枡田絵理奈",
    "ekoda_nana_pachi":    "江古田なな",
    "ayakawa_nemu_x":      "綾川音夢",
    # ── 追加：確認済み来店系演者アカウント ──
    "kuroki_nene_ps":      "黒木ねね",
    "sakura_quin_ps":      "桜キュイン",
    "amakusa_yae_ps":      "天草やえ",
    "tenno_minami_ps":     "天乃みなみ",
    "komiya_ruka_ps":      "小宮流花",
    "maeda_hinano_ps":     "前田ひなの",
    "suwa_miyuki_ps":      "諏訪幸",
    "koda_yuzuki_ps":      "倖田柚希",
    "mochizuki_saki_ps":   "望月咲",
    "kirara_hikaru_ps":    "煌ひかる",
    "karukun_ps":          "カルクン",
    "hanakawa_ps":         "花川",
    "super_slopri_ps":     "超スロプリ",
    # ── 追加：地域来店情報まとめ系（実在が高いアカウント） ──
    "keiji_raiten":        "KD来店情報",
    "kansai_raiten_ps":    "関西来店情報",
    "tohoku_raiten_info":  "東北来店情報",
    "kanto_raiten_ps":     "関東来店情報",
    "kyushu_raiten_info":  "九州来店情報",
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
def _build_queries(machine_names: list[str], top_stores: list[str] | None = None) -> list[str]:
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
        "スロセレ 来店",                 "スロセレ 取材",
        "わんだふる 取材",               "超キノコ狩り 取材",
        "SS取材",                        "スロパチガール 来店",
        "ぱちタウンコレクション",        "キノコ狩り 取材",
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

    # ── 演者名 × 来店/取材（メイン収集源） ──────────────────────────────────
    cast_names = [
        # 人気男性ライター・演者
        "浜田ブリトニー", "ガリぞう", "木村魚拓", "松本バッチ", "ういち",
        "レビン", "みさお", "鬼Dオロチ", "ヒキ強マン", "設定師シュウ",
        "ゲンさん", "パチスロあるある太郎", "兄弟スロッター", "ちきん",
        "もっくん", "たろじろう", "くりまる", "スタリオン",
        "チョンボ", "大崎一万発", "チェリ男", "涼野ゆい",
        "スロドル", "オカルト機動隊", "りゅうパチ", "ガンちゃん",
        "カズパチ", "大門パチスロ", "スロット自由人", "パチキチ",
        "スロット副業", "ちょんまげギャンブラー", "パチスロ第二章",
        "スロパパ", "スロットレジェンド", "西山師匠",
        # 人気女性演者・タレント（来店系）
        "鏡野ひまり", "矢吹ゆりな", "荻野倫", "ゆきんこ",
        "七瀬美海", "江古田なな", "枡田絵理奈", "煌ひかる",
        "倖田柚希", "望月咲", "諏訪幸", "せせらぎ",
        "綾川音夢", "花川", "沙姫", "カルクン",
        "あみ", "りんか", "ぺろ", "ぱちこ",
        "リノ", "宮崎梨乃", "べるたん", "高橋日菜",
        "なな徹", "まりも", "りさ", "はるか",
        "黒木ねね", "天草やえ", "桜キュイン", "ありすぎ",
        "天乃みなみ", "あいり", "小宮流花", "前田ひなの",
        "超スロプリ", "スロパチガール", "スロパチ来店",
        # 取材番組名（演者的に使われるブランド）
        "スロパチステーション", "ジャンバリ", "KD情報", "3×3STAR",
        "極誓", "回胴アドベンチャー", "PS調査員", "バズスロ",
        "SLOTIMES", "REAL取材", "限界突破DOME", "アイスロ",
        "スロセレ", "gogoネット", "パチ7取材",
        "わんだふる取材", "超キノコ狩り", "キノコ狩り",
    ]
    for c in cast_names:
        base.append(f"{c} 来店 OR 取材")

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
        "からくりサーカス","北斗転生","モンキーターンV",
    ]
    for m in popular:
        base.append(f"{m} 来店 OR 取材")

    # machines.jsonから追加機種
    for name in machine_names[:50]:
        short = re.sub(r'^(?:スマスロ|Lパチスロ|パチスロ|スマパチ|L)\s*', '', name).strip()
        if len(short) >= 3 and short not in popular:
            base.append(f"{short} 来店 OR 取材")

    # イベントが多い店舗名を個別クエリ追加
    _store_ng = re.compile(r'^(?:10時|通常|開催|注目|沖縄注目|特攻|景品)')
    if top_stores:
        for store in top_stores[:80]:
            if len(store) >= 4 and not _store_ng.match(store):
                base.append(f"{store} 来店 OR 取材")

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
    # ホールナビ（来店・取材スケジュール）
    {
        "name":    "horunavi",
        "urls":    [
            "https://www.horunavi.jp/schedule/",
        ],
        "type":    "news_list",
    },
    # スロセレ（スロット取材選手権）
    {
        "name":    "slotselection",
        "urls":    [
            "https://www.slot-selection.com/schedule/",
        ],
        "type":    "news_list",
    },
]

# ===========================================================================
# JOB E: YouTube チャンネル（最新動画タイトル + コミュニティ投稿）
# ===========================================================================

# url: YouTube チャンネル URL（@handle または /channel/ID 形式）
# 実在が確認済みのチャンネルのみ登録。URLに /videos や /community は付けない。
YOUTUBE_CHANNELS: list[dict] = [
    # ── 公式メディア・取材番組（来店・取材画像の主要ソース）──
    {"url": "https://www.youtube.com/@janbaritv",                              "name": "ジャンバリ"},
    {"url": "https://www.youtube.com/@BuzzSlot",                               "name": "バズスロ"},
    {"url": "https://www.youtube.com/@hisshobon",                              "name": "パチスロ必勝本"},
    {"url": "https://www.youtube.com/channel/UC8yYqoMOYO_Q755YLJ-teoQ",       "name": "スロパチステーション"},
    {"url": "https://www.youtube.com/@kd56tv",                                 "name": "KD情報"},
    {"url": "https://www.youtube.com/@3x3star_slot",                           "name": "3×3STAR"},
    {"url": "https://www.youtube.com/@gokumichi_dome",                         "name": "限界突破DOME"},
    {"url": "https://www.youtube.com/@eyeslot_official",                       "name": "アイスロ"},
    {"url": "https://www.youtube.com/@realdoc_pachi",                          "name": "REAL取材"},
    {"url": "https://www.youtube.com/@ps_chosain",                             "name": "PS調査員"},
    {"url": "https://www.youtube.com/@suro_select",                            "name": "スロセレ"},
    {"url": "https://www.youtube.com/@kaido_adv",                              "name": "回胴アドベンチャー"},
    {"url": "https://www.youtube.com/@gorsei_tv",                              "name": "極誓"},
    {"url": "https://www.youtube.com/@pachi7_official",                        "name": "パチ7"},
    # ── 確認済み 人気 YouTuber ──
    {"url": "https://www.youtube.com/@bri47ha",                                "name": "浜田ブリトニー"},
    {"url": "https://www.youtube.com/@garizo1",                                "name": "ガリぞう"},
    {"url": "https://www.youtube.com/@kimurauotaku",                           "name": "木村魚拓"},
    {"url": "https://www.youtube.com/@batchimatsumoto",                        "name": "松本バッチ"},
    {"url": "https://www.youtube.com/@uichi_slot",                             "name": "ういち"},
    {"url": "https://www.youtube.com/@nanatoru_official",                      "name": "なな徹"},
    {"url": "https://www.youtube.com/@yukinnko",                               "name": "ゆきんこ"},
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
    r"来店|取材|撮影|ロケ|イベント|特定日|設定示唆|周年|誕生日|オープン|新台|全台|実戦店舗|ホール実戦|収録"
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
    # YYYY/MM/DD 形式を優先マッチ（年部分を誤検知しないよう先に処理）
    m = re.search(r'\d{4}[/／](\d{1,2})[/／](\d{1,2})', text)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{mo:02d}/{dy:02d}"
    # MM/DD 形式（数字に挟まれた場合を除外）
    m = re.search(r'(?<!\d)(\d{1,2})[/／](\d{1,2})(?!\d)', text)
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
    # stores.jsonの正確な店舗名: 最長一致優先（短い名前の誤マッチを防ぐ）
    best = ""
    for name in store_names:
        if len(name) < 5:          # 4文字以下は誤マッチが多いのでスキップ
            continue
        if name in text and len(name) > len(best):
            best = name
    if best:
        return best
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


def _x_scrape_page(
    page, store_names: set[str], max_tweets: int, source_label: str,
    store_hint: str = "",  # 店舗アカウントのタイムラインは店舗名を強制指定
) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for article in page.query_selector_all('article[data-testid="tweet"]')[:max_tweets]:
        try:
            el = article.query_selector('[data-testid="tweetText"]')
            if not el:
                # 画像のみツイートも画像だけ取る（店舗アカウント限定）
                if not store_hint:
                    continue
                text = ""
            else:
                text = el.inner_text()
            if not store_hint and len(text) < 15:
                continue
            url = _x_url(article)
            if not url or url in seen:
                continue
            seen.add(url)
            imgs = _x_images(article)
            img_url = imgs[0] if imgs else ""

            if store_hint:
                # 店舗自身のアカウント: store_hintを強制使用 + イベントキーワードなくてもOK（画像ありなら）
                if not EVENT_KEYWORD_RE.search(text) and not img_url:
                    continue  # キーワードも画像もなければスキップ
                date_str = _guess_date(text)
                pref, area = _guess_pref_area(text)
                ev = {
                    "id":        _make_id(store_hint, date_str, url),
                    "date":      date_str,
                    "store":     store_hint,
                    "pref":      pref,
                    "area":      area,
                    "event":     _guess_event(text) if text else "イベント",
                    "detail":    text[:300].replace("\n", " "),
                    "cast":      _guess_cast(text),
                    "highlight": "",
                    "image_url": img_url,
                    "x_url":     url if "x.com" in url else "",
                    "url":       url,
                    "source":    "x",
                }
            else:
                ev = _make_event(text, url, img_url, "x", store_names)
            if ev:
                results.append(ev)
                log(f"      ✅ {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({source_label})")
        except Exception:
            continue
    return results


def scrape_x_timeline(page, username: str, store_names: set[str], store_hint: str = "") -> list[dict]:
    try:
        page.goto(f"https://x.com/{username}", timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=6000)
        except PlaywrightTimeout:
            return []
        # 50回スクロール（Publicリポジトリ=無制限）
        for _ in range(50):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(500)
    except Exception as e:
        log(f"    ⚠️  @{username}: {e}")
        return []
    return _x_scrape_page(page, store_names, 200, f"@{username}", store_hint=store_hint)


def scrape_x_search(page, query: str, store_names: set[str]) -> list[dict]:
    encoded = query.replace(" ", "%20").replace("#", "%23")
    try:
        page.goto(f"https://x.com/search?q={encoded}&src=typed_query&f=live", timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=6000)
        except PlaywrightTimeout:
            return []
        # 80回スクロール（Publicリポジトリ=無制限）
        for _ in range(80):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(700)
    except Exception as e:
        log(f"    ⚠️  {query!r}: {e}")
        return []
    return _x_scrape_page(page, store_names, 200, "search")


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
def scrape_pttown_schedules_http(
    store_pref_map: dict[str, tuple[str, str]],
    store_names: set[str],
    max_pages: int = 30,
) -> list[dict]:
    """DMM p-town /schedules を urllib で直接スクレイプ（Playwright不要）。
    alt テキスト「{店名} {YYYY/MM/DD}/（曜日）の来店イベント情報「{取材名}」」を解析。
    """
    import ssl
    import urllib.request as _ureq

    _NG_EVENTS = {"通常稼働", "景品入荷", "開店情報", "傾向分析", "勝率ランキング", "看板スタッフ"}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
    }
    # <img> タグ全体を取得して属性を個別に解析（属性順序不問）
    img_tag_re = re.compile(r'<img\s([^>]*?)/?>', re.DOTALL)
    alt_event_re = re.compile(
        r'(.+?)\s+(\d{4}/\d{1,2}/\d{1,2})/[（(].+?[）)][のの]来店イベント情報[「「](.+?)[」」]'
    )
    ptown_src_re = re.compile(r'data-src="(https://cdn\.p-town\.dmm\.com/[^"]+)"')
    ptown_alt_re = re.compile(r'alt="([^"]+)"')
    # フォールバック：alt のみのパターン（画像なし・後方互換）
    alt_re = re.compile(
        r'alt="(.+?)\s+(\d{4}/\d{1,2}/\d{1,2})/[（(].+?[）)][のの]来店イベント情報[「「](.+?)[」」]"'
    )

    results: list[dict] = []
    log(f"\n🏢 p-town schedules HTTP スクレイプ (最大{max_pages}ページ)")

    for page_no in range(1, max_pages + 1):
        url = f"https://p-town.dmm.com/schedules?page={page_no}"
        req = _ureq.Request(url, headers=_headers)
        try:
            with _ureq.urlopen(req, timeout=15, context=ctx) as r:
                html = r.read().decode("utf-8", errors="replace")
        except Exception as e:
            log(f"  ⚠️  page={page_no}: {e}")
            break

        found = 0
        # <img>タグごとにdata-srcとalt属性を抽出（属性順序不問）
        img_matches: dict[tuple, str] = {}
        for tag_m in img_tag_re.finditer(html):
            attrs = tag_m.group(1)
            src_m = ptown_src_re.search(attrs)
            alt_m = ptown_alt_re.search(attrs)
            if not src_m or not alt_m:
                continue
            ev_m = alt_event_re.search(alt_m.group(1))
            if ev_m:
                key = (ev_m.group(1).strip(), ev_m.group(2), ev_m.group(3).strip())
                img_matches[key] = src_m.group(1)

        for m in alt_re.finditer(html):
            store = m.group(1).strip()
            date_raw = m.group(2)       # "2026/05/21"
            event_name = m.group(3).strip()
            # 対応する画像URLを取得（高解像度化）
            img_src = img_matches.get((store, date_raw, event_name), "")
            if img_src:
                img_src = img_src.replace("/fit-in/150x0/", "/fit-in/600x0/").split("?")[0]

            # 通常稼働など非イベントを除外
            if any(ng in event_name for ng in _NG_EVENTS):
                continue

            # 日付: MM/DD（ゼロ埋め）
            parts = date_raw.split("/")
            if len(parts) == 3:
                date_str = f"{int(parts[1]):02d}/{int(parts[2]):02d}"
            else:
                date_str = date_raw

            # pref/area: 店名で直接引くかフォールバック
            pref, area = store_pref_map.get(store, ("不明", "全国"))
            if pref == "不明":
                pref, area = _guess_pref_area(store)

            # event type
            if any(k in event_name for k in ["来店", "実践", "出演", "訪問"]):
                ev_type = "来店"
            elif any(k in event_name for k in ["取材", "撮影", "ロケ", "収録"]):
                ev_type = "取材"
            elif any(k in event_name for k in ["周年", "誕生日", "オープン", "新台"]):
                ev_type = "イベント"
            else:
                ev_type = "取材"

            ev = {
                "id":        _make_id(store, date_str, f"ptown-sch-{page_no}"),
                "date":      date_str,
                "store":     store,
                "pref":      pref,
                "area":      area,
                "event":     ev_type,
                "detail":    event_name,
                "cast":      event_name[:40],
                "highlight": "",
                "image_url": img_src,
                "x_url":     "",
                "url":       f"https://p-town.dmm.com/schedules?page={page_no}",
                "source":    "p-town",
            }
            results.append(ev)
            found += 1

        log(f"  page={page_no}: {found}件")
        if found == 0:
            log("  → ページなし、終了")
            break
        time.sleep(0.35)

    log(f"  p-town schedules 合計: {len(results)}件")
    return results


# P-World URL スラッグ → 都道府県マッピング
_PWORLD_SLUG_TO_PREF: dict[str, str] = {
    "hokkaido": "北海道", "aomori": "青森県", "iwate": "岩手県",
    "miyagi": "宮城県", "akita": "秋田県", "yamagata": "山形県",
    "fukushima": "福島県", "ibaraki": "茨城県", "tochigi": "栃木県",
    "gunma": "群馬県", "saitama": "埼玉県", "chiba": "千葉県",
    "tokyo": "東京都", "kanagawa": "神奈川県", "niigata": "新潟県",
    "toyama": "富山県", "ishikawa": "石川県", "fukui": "福井県",
    "yamanashi": "山梨県", "nagano": "長野県", "shizuoka": "静岡県",
    "aichi": "愛知県", "mie": "三重県", "shiga": "滋賀県",
    "kyoto": "京都府", "osaka": "大阪府", "hyogo": "兵庫県",
    "nara": "奈良県", "wakayama": "和歌山県", "tottori": "鳥取県",
    "shimane": "島根県", "okayama": "岡山県", "hiroshima": "広島県",
    "yamaguchi": "山口県", "tokushima": "徳島県", "kagawa": "香川県",
    "ehime": "愛媛県", "kochi": "高知県", "fukuoka": "福岡県",
    "saga": "佐賀県", "nagasaki": "長崎県", "kumamoto": "熊本県",
    "oita": "大分県", "miyazaki": "宮崎県", "kagoshima": "鹿児島県",
    "okinawa": "沖縄県",
}


def scrape_pworld_interviews_http(
    store_pref_map: dict[str, tuple[str, str]],
    store_names: set[str],
    max_pages: int = 50,
) -> list[dict]:
    """P-World 全国取材来店情報ページをHTTPスクレイプ（Playwright不要・EUC-JP）。
    https://www.p-world.co.jp/hall/interviews/prefs を全ページ巡回し、
    取材・来店イベント情報を画像付きで取得する。
    """
    import ssl
    import urllib.request as _ureq

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Referer": "https://www.p-world.co.jp/",
    }

    # ── Regex ──────────────────────────────────────────────────────────────
    # 取材サムネイル画像（idn.p-world.co.jp = 画像サーバー）
    img_re = re.compile(
        r'src=["\']?(https://idn\.p-world\.co\.jp/hall/\d+/images/interviews/[^"\'>\s]+)'
    )
    # 店舗詳細ページリンク + 店名
    store_link_re = re.compile(
        r'href=["\']?(https://www\.p-world\.co\.jp/([a-z]+)/[^"\'>\s]+\.htm)["\']?'
        r'[^>]*>([^<]{2,40})</a>'
    )
    # 日付: MM/DD(曜日) または MM/DD（曜日）
    date_re = re.compile(r'(\d{1,2})/(\d{1,2})[（(]?[月火水木金土日][）)]?')
    # イベント種別キーワード
    ev_type_kw = [
        ("来店", "来店"), ("出演", "来店"), ("実践", "来店"),
        ("取材", "取材"), ("撮影", "取材"), ("ロケ", "取材"), ("収録", "取材"),
    ]
    # タグ内テキスト（キャスト名候補）
    tag_text_re = re.compile(r'<(?:h[1-4]|p|span|div|li)[^>]{0,80}>([^<]{4,80})</(?:h[1-4]|p|span|div|li)>')
    # タグ除去用
    strip_tags_re = re.compile(r'<[^>]+>')

    results: list[dict] = []
    seen_ids: set[str] = set()
    log(f"\n📸 P-World 取材来店情報 HTTP スクレイプ (最大{max_pages}ページ)")

    for page_no in range(1, max_pages + 1):
        url = (
            "https://www.p-world.co.jp/hall/interviews/prefs"
            if page_no == 1
            else f"https://www.p-world.co.jp/hall/interviews/prefs?page={page_no}"
        )
        req = _ureq.Request(url, headers=_headers)
        try:
            with _ureq.urlopen(req, timeout=20, context=ctx) as r:
                raw = r.read()
            try:
                html = raw.decode("euc-jp", errors="replace")
            except Exception:
                html = raw.decode("utf-8", errors="replace")
        except Exception as e:
            log(f"  ⚠️  page={page_no}: {e}")
            break

        # 画像URLの出現位置を全取得
        img_matches = [(m.start(), m.group(1)) for m in img_re.finditer(html)]
        if not img_matches:
            if page_no == 1:
                log("  ⚠️  page=1: 画像URLなし（構造変更の可能性）")
            else:
                log(f"  page={page_no}: 画像なし → 終了")
            break

        found = 0
        for idx, (img_pos, img_url) in enumerate(img_matches):
            # このカードの範囲: 前後のカードの中間あたり（店名リンクが画像より後ろに来る場合も考慮）
            block_start = img_matches[idx - 1][0] if idx > 0 else max(0, img_pos - 2000)
            block_end   = img_matches[idx + 1][0] if idx + 1 < len(img_matches) else img_pos + 2000
            block = html[block_start:block_end]

            # 店名 & 店舗URL（画像の前後両方を探す）
            store_m = None
            for sm in store_link_re.finditer(block):
                txt = sm.group(3).strip()
                # 全角スペース等を除去して店名らしいテキストのみ
                txt = re.sub(r'[\s　]+', '', txt)
                if len(txt) >= 2:
                    store_m = sm
                    store_name = txt
                    break
            if not store_m:
                continue

            store_url  = store_m.group(1)
            pref_slug  = store_m.group(2)

            # 日付: このカードの近傍（img_pos ±400文字）から探す
            near = html[max(0, img_pos - 400): img_pos + 800]
            date_m = date_re.search(near)
            if date_m:
                month, day = int(date_m.group(1)), int(date_m.group(2))
                # 明らかにおかしい値は今日
                if 1 <= month <= 12 and 1 <= day <= 31:
                    date_str = f"{month:02d}/{day:02d}"
                else:
                    date_str = f"{date.today().month:02d}/{date.today().day:02d}"
            else:
                date_str = f"{date.today().month:02d}/{date.today().day:02d}"

            # イベント種別 & キャスト名（img 後方500文字から抽出）
            after = html[img_pos: img_pos + 800]
            after_plain = strip_tags_re.sub(' ', after)

            ev_type = "取材"
            for kw, label in ev_type_kw:
                if kw in after_plain:
                    ev_type = label
                    break

            # キャスト名: タグ内テキストのうち最初の「意味のある」ものを採用
            cast = ""
            for tm in tag_text_re.finditer(after):
                txt = tm.group(1).strip()
                # 日付行・URLっぽいもの・短すぎるものは除外
                if (len(txt) < 4 or len(txt) > 60
                        or re.search(r'https?://', txt)
                        or re.match(r'^\d+/\d+', txt)):
                    continue
                # 「更新」「設置」など無意味な単語は除外
                if re.fullmatch(r'[更新設置情報台数]+', txt):
                    continue
                cast = txt
                break

            # pref/area
            pref_from_slug = _PWORLD_SLUG_TO_PREF.get(pref_slug, "")
            if pref_from_slug:
                pref = pref_from_slug
                area = PREF_AREA.get(pref, "全国")
            else:
                pref, area = store_pref_map.get(store_name, ("不明", "全国"))
                if pref == "不明":
                    pref, area = _guess_pref_area(store_name)

            ev_id = _make_id(store_name, date_str, img_url)
            if ev_id in seen_ids:
                continue
            seen_ids.add(ev_id)

            ev = {
                "id":        ev_id,
                "date":      date_str,
                "store":     store_name,
                "pref":      pref,
                "area":      area,
                "event":     ev_type,
                "detail":    cast,
                "cast":      cast[:40],
                "highlight": "",
                "image_url": img_url,
                "x_url":     "",
                "url":       store_url,
                "source":    "p-world",
            }
            results.append(ev)
            found += 1

        log(f"  page={page_no}: {found}件")
        if found == 0 and page_no > 1:
            break
        time.sleep(0.4)

    log(f"  P-World 取材来店情報 合計: {len(results)}件")
    return results


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
                    # 画像: src → data-src → data-lazy-src → data-original の順に試す
                    img = ""
                    for img_sel in ['img[src*="http"]', 'img[data-src]', 'img[data-lazy-src]', 'img[data-original]']:
                        img_el = card.query_selector(img_sel)
                        if img_el:
                            for attr in ("src", "data-src", "data-lazy-src", "data-original"):
                                val = img_el.get_attribute(attr) or ""
                                if val.startswith("http"):
                                    img = val
                                    break
                        if img:
                            break
                    ev = _make_event(text, href or url, img, source_name, store_names)
                    if ev:
                        results.append(ev)
                        log(f"      🌐 {ev['store'][:18]} [{ev['pref']}] ({source_name})")
                except Exception:
                    continue
            if results:
                break
    return results


# ---------------------------------------------------------------------------
# JOB E: YouTube スクレイピング（yt-dlp ベース）
# ---------------------------------------------------------------------------
def _yt_extract_from_text(text: str, url: str, img: str, source: str, store_names: set[str]) -> list[dict]:
    """YouTube テキスト（複数行）からイベント情報を抽出"""
    results: list[dict] = []
    blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]
    for block in blocks[:20]:
        ev = _make_event(block, url, img, source, store_names)
        if ev:
            results.append(ev)
    if not results and len(text) >= 15:
        ev = _make_event(text[:500], url, img, source, store_names)
        if ev:
            results.append(ev)
    return results


def _ytdlp(args: list[str], timeout: int = 40) -> str:
    """yt-dlp を呼び出して stdout を返す。失敗時は空文字列"""
    try:
        out = subprocess.check_output(
            ["yt-dlp"] + args,
            text=True, timeout=timeout,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return ""


def _yt_thumbnail(url: str) -> str:
    """YouTube URL からサムネイルURLを生成"""
    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
    if m:
        return f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg"
    return ""


def scrape_youtube_channel_ytdlp(ch_url: str, ch_name: str, store_names: set[str]) -> list[dict]:
    """yt-dlp でチャンネルの最新動画 + コミュニティ投稿をスクレイプ"""
    results: list[dict] = []

    # ── 最新動画タイトル ──────────────────────────────────────
    out = _ytdlp([
        "--flat-playlist", "--quiet", "--no-warnings",
        "--print", "%(title)s\t%(webpage_url)s",
        "--playlist-end", "30",
        f"{ch_url}/videos",
    ])
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        title, url = parts
        thumb = _yt_thumbnail(url)
        evs = _yt_extract_from_text(title, url, thumb, "youtube_video", store_names)
        for ev in evs:
            ev["cast"] = ev.get("cast") or ch_name
            results.append(ev)
            log(f"      🎥 {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({ch_name})")

    # ── コミュニティ投稿 ──────────────────────────────────────
    out = _ytdlp([
        "--flat-playlist", "--quiet", "--no-warnings",
        "--print", "%(title)s\t%(webpage_url)s",
        "--playlist-end", "30",
        f"{ch_url}/community",
    ])
    for line in out.splitlines():
        parts = line.split("\t", 1)
        text = parts[0]
        url = parts[1] if len(parts) > 1 else ch_url
        if len(text) < 10:
            continue
        thumb = _yt_thumbnail(url)
        evs = _yt_extract_from_text(text, url, thumb, "youtube_community", store_names)
        for ev in evs:
            ev["cast"] = ev.get("cast") or ch_name
            results.append(ev)
            log(f"      🎬 {ev['store'][:18]} [{ev['pref']}] {ev['date']} ({ch_name} community)")

    return results


def scrape_youtube_search_ytdlp(query: str, store_names: set[str]) -> list[dict]:
    """yt-dlp でYouTube検索（新着順）してホール撮影動画を収集"""
    results: list[dict] = []
    out = _ytdlp([
        "--flat-playlist", "--quiet", "--no-warnings",
        "--print", "%(channel)s\t%(title)s\t%(webpage_url)s",
        "--playlist-end", "30",
        f"ytsearch30:{query}",
    ])
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        ch, title, url = parts
        thumb = _yt_thumbnail(url)
        evs = _yt_extract_from_text(title, url, thumb, "youtube_search", store_names)
        for ev in evs:
            if ch and not ev.get("cast"):
                ev["cast"] = ch
            results.append(ev)
            log(f"      🔍 {ev['store'][:18]} [{ev['pref']}] {ev['date']} (YT search)")
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
    parser.add_argument("--job", choices=["accounts", "search", "google", "web", "youtube", "ptown", "all"], default="all")
    parser.add_argument("--ptown-pages", type=int, default=30, help="p-town schedulesの最大ページ数")
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

    # stores.jsonからイベント数上位の店舗名（X検索クエリ用）
    top_stores: list[str] = []
    if STORES_JSON.exists():
        with open(STORES_JSON, encoding="utf-8") as f:
            _all_stores = json.load(f)
        top_stores = [
            s["name"] for s in sorted(_all_stores, key=lambda x: x.get("event_count", 0), reverse=True)
            if s.get("event_count", 0) >= 3 and len(s.get("name", "")) >= 4
        ][:100]

    X_QUERIES = _build_queries(machine_names, top_stores)

    log("=" * 70)
    log(f"🚀 fetch_events  job={args.job}")
    log(f"   メディアアカウント:{len(MEDIA_ACCOUNTS)}  店舗アカウント:{len(STORE_ACCOUNTS)}")
    log(f"   検索クエリ:{len(X_QUERIES)}  Google:{len(GOOGLE_QUERIES)}  Yahoo:{len(YAHOO_RT_QUERIES)}")
    log(f"   Webソース:{len(WEB_SOURCES)}サイト  YouTubeチャンネル:{len(YOUTUBE_CHANNELS)}ch  YouTube検索:{len(YOUTUBE_SEARCH_QUERIES)}クエリ")

    # stores.jsonから店舗名セット・pref マップ（短すぎる名前は除外）
    store_names: set[str] = set()
    store_pref_map: dict[str, tuple[str, str]] = {}
    if STORES_JSON.exists():
        with open(STORES_JSON, encoding="utf-8") as f:
            for s in json.load(f):
                name = s.get("name", "")
                if name and len(name) >= 4:
                    store_names.add(name)
                    pref = s.get("pref", "不明")
                    area = PREF_AREA.get(pref, "全国")
                    store_pref_map[name] = (pref, area)
    log(f"📦 store_names: {len(store_names)}店舗")

    existing, original = load_events()
    log(f"📦 既存イベント: {len(existing)}件")

    all_new: list[dict] = []

    # ── JOB F: p-town /schedules + P-World 取材来店情報 HTTP スクレイプ（Playwright不要）──
    if args.job in ("ptown", "all"):
        ptown_res = scrape_pttown_schedules_http(store_pref_map, store_names, max_pages=args.ptown_pages)
        all_new.extend(ptown_res)
        pworld_res = scrape_pworld_interviews_http(store_pref_map, store_names, max_pages=50)
        all_new.extend(pworld_res)

    # ptown ジョブはHTTPのみ（playwright不要）
    if args.job == "ptown":
        seen_ids2: set[str] = set()
        deduped2 = [e for e in all_new if not (e["id"] in seen_ids2 or seen_ids2.add(e["id"]))]  # type: ignore
        merged2, added2 = merge_events(existing, deduped2)
        log(f"📊 p-town+p-world収集: {len(deduped2)}件 / 新規: {added2}件 / 累計: {len(merged2)}件")
        if added2 > 0:
            save_events(merged2, original)
        log("=" * 70)
        return

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
                        for ev in res:
                            ev["cast"] = ev.get("cast") or label
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
                        # store_hint=label: 店舗自身のアカウントなので店舗名を強制指定
                        # → ツイートに店舗名が書かれてなくても正しくマッチ + 画像も確実に収集
                        res = scrape_x_timeline(page, username, store_names, store_hint=label)
                        for ev in res:
                            ev["cast"] = ev.get("cast") or label
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

        # ── JOB E: YouTube（yt-dlp ベース・ボット検知回避）──
        if args.job in ("youtube", "all"):
            log(f"\n🎬 YouTube チャンネル ({len(YOUTUBE_CHANNELS)}ch) via yt-dlp")
            for i, ch in enumerate(YOUTUBE_CHANNELS, 1):
                log(f"  [{i}/{len(YOUTUBE_CHANNELS)}] {ch['url']} ({ch['name']})")
                try:
                    res = scrape_youtube_channel_ytdlp(ch["url"], ch["name"], store_names)
                    if res:
                        log(f"       → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(0.5)
                except Exception as e:
                    log(f"    ❌ {ch['name']}: {e}")

            log(f"\n🔍 YouTube 検索 ({len(YOUTUBE_SEARCH_QUERIES)}クエリ) via yt-dlp")
            for i, query in enumerate(YOUTUBE_SEARCH_QUERIES, 1):
                log(f"  [{i}] {query}")
                try:
                    res = scrape_youtube_search_ytdlp(query, store_names)
                    if res:
                        log(f"       → {len(res)}件")
                    all_new.extend(res)
                    time.sleep(1.0)
                except Exception as e:
                    log(f"    ❌ {e}")

        page.close()
        ctx.close()

    seen_ids: set[str] = set()
    deduped = [e for e in all_new if not (e["id"] in seen_ids or seen_ids.add(e["id"]))]  # type: ignore

    # store_pref_map で「不明」pref を補完（部分一致フォールバックあり）
    fixed_pref = 0
    for ev in deduped:
        if ev.get("pref") in ("不明", "", None) and ev.get("store"):
            store = ev["store"]
            pa = store_pref_map.get(store)
            if not pa:
                for sname, val in store_pref_map.items():
                    if store in sname or sname in store:
                        pa = val
                        break
            if pa and pa[0] not in ("不明", "", None):
                ev["pref"], ev["area"] = pa
                fixed_pref += 1
    if fixed_pref:
        log(f"🗺  pref補完: {fixed_pref}件")

    log(f"\n📊 収集: {len(deduped)}件（重複除去後）")

    merged, added = merge_events(existing, deduped)
    log(f"➕ 新規: {added}件 / 累計: {len(merged)}件")

    if added > 0:
        save_events(merged, original)

    log("=" * 70)


if __name__ == "__main__":
    main()
