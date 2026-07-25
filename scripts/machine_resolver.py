"""
機種名マスタシステム — Python 版

スクレイピング取得した機種名を machines_master テーブルの正式名称に解決する。
DB保存前に必ずこのモジュールを通すこと（CLAUDE.md 参照）。

使用例:
    from machine_resolver import MachineResolver
    resolver = MachineResolver(supabase_url, service_key)
    result = resolver.resolve("ヴァルヴレイヴ")
    # → {"machine_id": "...", "official_name": "L革命機ヴァルヴレイヴ2", ...}
"""
from __future__ import annotations

import json
import os
import re
import ssl
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Optional

# 接頭辞除去パターン（正式名称の保存時は元表記を維持。照合時のみ除去）
_PREFIX_RE = re.compile(r'^(スマスロ|L|パチスロ|スロット|SLOT)', re.IGNORECASE)

# シリーズ名のみでの機種確定を禁止するリスト（raw入力の strip() と比較）
# 例: "吉宗" は L吉宗 / L真打吉宗 の両方があり曖昧 → unknown_machines に記録
# 重要: このチェックは exact match / alias match よりも前に実施すること（resolve() 参照）
_AMBIGUOUS_SERIES = {
    "北斗", "北斗の拳",          # スマスロ北斗の拳(slot) と eフィーバー北斗(pachinko) 両方存在
    "ジャグラー", "番長",
    "エヴァ", "ガンダム",
    "東京喰種",                  # L東京喰種(slot) と e東京喰種(pachinko) 両方存在
    "モンキー", "吉宗", "バジリスク", "カバネリ",
    "リコリス", "リコリコ", "リコリス・リコイル",  # スマスロ(slot) と eリコリス(pachinko) 両方存在
    "炎炎ノ消防隊", "炎炎の消防隊", "炎炎ノ消防隊2", "炎炎の消防隊2", "炎炎2",  # L炎炎(slot) と eフィーバー炎炎/e炎炎(pachinko) 両方存在
    "からくり", "からくりサーカス",  # Lからくりサーカス(slot) と Pフィーバーからくりサーカス(pachinko) 両方存在
}


def normalize_for_comparison(name: str) -> str:
    """
    機種名を照合用に正規化する。
    - NFKC 正規化（全角英数→半角・ローマ数字展開等）
    - 接頭辞除去: スマスロ / L / Ｌ / パチスロ / スロット / SLOT（繰り返し適用）
    - 小文字化
    - 空白（全角・半角）除去
    正式名称の保存には使わない（official_name は元表記を保持）。
    """
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name.strip())
    prev = ""
    while n != prev:
        prev = n
        n = _PREFIX_RE.sub("", n).strip()
    return n.lower().replace(" ", "").replace("\u3000", "")


# \u2500\u2500 \u30b7\u30ea\u30fc\u30ba\u66d6\u6627\u6027\u5224\u5b9a\u201c\u5c02\u7528\u201d\u306e\u524d\u51e6\u7406 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# \u76ee\u7684: \u300c\u88f8\u306e\u30b7\u30ea\u30fc\u30ba\u540d\uff08\u578b\u30d7\u30ec\u30d5\u30a3\u30c3\u30af\u30b9\u30fb\u4e16\u4ee3\u756a\u53f7\u30fb\u526f\u984c\u306a\u3057\uff09\u300d\u304c machines_master
#       \u4e0a\u3067\u8907\u6570\u6a5f\u7a2e\u306b\u8a72\u5f53\u3059\u308b\u304b\u3092\u5224\u5b9a\u3059\u308b\u305f\u3081\u3060\u3051\u306b\u4f7f\u3046\u3002
# \u91cd\u8981: \u6b63\u5f0f\u540d\u79f0\u306e\u4fdd\u5b58\u3084\u901a\u5e38\u306e exact/alias \u5224\u5b9a\u306b\u306f\u4f7f\u308f\u306a\u3044\u3002
#       \u6570\u5b57\u30fb\u30ed\u30fc\u30de\u6570\u5b57\u30fb\u4e16\u4ee3\u756a\u53f7\u30fb\u526f\u984c\u30fbSPEC/LT \u7b49\u306e\u201c\u8b58\u5225\u60c5\u5831\u201d\u306f\u524a\u9664\u3057\u306a\u3044\u3002
#       \u3053\u3053\u3067\u9664\u53bb\u3059\u308b\u306e\u306f\u300c\u7a2e\u5225\u30d7\u30ec\u30d5\u30a3\u30c3\u30af\u30b9\u300d\u3068\u300c\u62ec\u5f27\u30fb\u8a18\u53f7\u30fb\u7a7a\u767d\u300d\u3060\u3051\u3002

_STEM_LEADING_BRACKETS = re.compile(r'^[\s\u3000\u300e\u300c\u3010\u3014\[(\uff08\u300a\u3008\u00ab\u276e\u226a]+')
# \u66d6\u6627\u6027\u7167\u5408\u306e\u30ce\u30a4\u30ba\u306b\u306a\u308b\u8a18\u53f7\u30fb\u7a7a\u767d\u306e\u307f\u9664\u53bb\uff08\u82f1\u6570\u5b57\u30fb\u304b\u306a\u30fb\u6f22\u5b57\u30fb\u30fc\u306f\u6b8b\u3059\uff09
_STEM_JUNK = re.compile(r'[\s\u3000\uff01!\uff1f?\u30fb:\uff1a\u300c\u300d\u300e\u300f\u3010\u3011\u3014\u3015\[\]\uff08\uff09()\u300a\u300b\u3008\u3009\u00ab\u00bb\u276e\u276f\u226a\u226b\u3001\u3002,\uff0e\.~\u301c"\u201d\u201c\'`\uff40]+')
# \u7a2e\u5225\u30d7\u30ec\u30d5\u30a3\u30c3\u30af\u30b9\uff08\u7167\u5408\u5c02\u7528\u306b\u9664\u53bb\u3002\u9577\u3044\u3082\u306e\u3092\u5148\u306b\uff09
# \u6ce8: "lt" \u306f\u578b\u5f0f\u8b58\u5225\u5b50\uff08LT\u7248\uff09\u3068\u3057\u3066\u6b8b\u3059\uff1d\u30d7\u30ec\u30d5\u30a3\u30c3\u30af\u30b9\u9664\u53bb\u306b\u542b\u3081\u306a\u3044
_STEM_PREFIX_MULTI = ["\u30b9\u30de\u30b9\u30ed", "\u30b9\u30de\u30d1\u30c1", "p\u30d5\u30a3\u30fc\u30d0\u30fc", "\u30d5\u30a3\u30fc\u30d0\u30fc", "\u30d1\u30c1\u30b9\u30ed",
                      "\u30b9\u30ed\u30c3\u30c8", "slot", "cr", "pa"]
_STEM_PREFIX_SINGLE = ["l", "e", "p", "s"]  # \u76f4\u5f8c\u304c\u975eASCII\uff08\u65e5\u672c\u8a9e\uff09\u306e\u5834\u5408\u306e\u307f\u9664\u53bb


def _series_stem(name: str) -> str:
    """\u66d6\u6627\u6027\u78ba\u8a8d\u5c02\u7528\u306e\u30b7\u30ea\u30fc\u30ba stem \u3092\u8fd4\u3059\uff08\u8b58\u5225\u60c5\u5831=\u6570\u5b57/\u4e16\u4ee3/\u526f\u984c\u306f\u4fdd\u6301\uff09\u3002"""
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name.strip())
    n = _STEM_LEADING_BRACKETS.sub("", n).lower()
    changed = True
    while changed:
        changed = False
        for p in _STEM_PREFIX_MULTI:
            if n.startswith(p) and len(n) > len(p):
                n = n[len(p):]; changed = True; break
        if changed:
            continue
        for p in _STEM_PREFIX_SINGLE:
            # \u5358\u4e00\u30e9\u30c6\u30f3\u63a5\u982d\u8f9e\u306f\u300c\u76f4\u5f8c\u304c\u65e5\u672c\u8a9e\uff08\u975eASCII\uff09\u300d\u306e\u3068\u304d\u3060\u3051\u9664\u53bb
            # \u4f8b: e\u7259\u72fc / L\u6c96\u30c9\u30ad / P\u5317\u6597 \u2192 \u9664\u53bb\u3001Re:\u30bc\u30ed \u7b49\u306f\u8aa4\u9664\u53bb\u3057\u306a\u3044
            if n.startswith(p) and len(n) > len(p) and not n[len(p)].isascii():
                n = n[len(p):]; changed = True; break
    return _STEM_JUNK.sub("", n)


def _has_type_prefix(name: str) -> bool:
    """\u578b\u30d7\u30ec\u30d5\u30a3\u30c3\u30af\u30b9\uff08L/S/e/P/PA/CR/\u30b9\u30de\u30b9\u30ed \u7b49\uff09\u3092\u6301\u3064\u304b\u3002\u6301\u3066\u3070\u88f8\u540d\u3067\u306f\u306a\u3044\u3002"""
    if not name:
        return False
    n = unicodedata.normalize("NFKC", name.strip())
    n = _STEM_LEADING_BRACKETS.sub("", n).lower()
    for p in _STEM_PREFIX_MULTI:
        if n.startswith(p) and len(n) > len(p):
            return True
    for p in _STEM_PREFIX_SINGLE:
        if n.startswith(p) and len(n) > len(p) and not n[len(p)].isascii():
            return True
    return False


_ROMAN_MAP = {
    "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5", "Ⅵ": "6",
    "Ⅶ": "7", "Ⅷ": "8", "Ⅸ": "9", "Ⅹ": "10", "Ⅺ": "11", "Ⅻ": "12",
    "ⅰ": "1", "ⅱ": "2", "ⅲ": "3", "ⅳ": "4", "ⅴ": "5", "ⅵ": "6",
}
_DIGIT_RUN = re.compile(r"\d+")
_LATIN_RUN = re.compile(r"[a-z]{2,}")  # DUO / GOLD / BLACK / LT / SPEC / VER / EX / RUSH 等


def extract_identity_tokens(name: str) -> frozenset:
    """機種を一意に識別する“識別トークン集合”を返す（世代・型式・別機種の区別用）。

    捕捉するもの（データから抽出。特定機種名のハードコードはしない）:
      - 数字列（Unicode ローマ数字 Ⅱ→2 に変換してから抽出。全角→半角は NFKC で統一）
      - 2 文字以上のラテン語トークン（DUO / GOLD / BLACK / LT / SPEC / VER / EX / RUSH …）

    重要:
      - series_stem 経由で抽出するため、型プレフィックス（L/e/P/CR/PA/スマスロ 等）は
        識別トークンに混入しない（例: CR牙狼 → {} / L沖ドキDUO2 → {"duo","2"}）。
      - 数字・型式語は削除しない。副題のかな/漢字（アンコール・海門決戦 等）は
        トークン化しないが、それらは exact / alias / fuzzy スコアで区別される。

    用途は fuzzy 候補の“世代・数字・型式違い”排除に限定する。exact/alias 判定には使わない。
    例: 沖ドキ！DUO2 → {"duo","2"} / 沖ドキ！DUO → {"duo"} / 沖ドキ！GOLD → {"gold"}
        / 沖ドキ！BLACK → {"black"} / 戦国乙女5 → {"5"} / ヴァルヴレイヴ → 空集合
    """
    if not name:
        return frozenset()
    n = name
    for r, a in _ROMAN_MAP.items():
        n = n.replace(r, a)
    s = _series_stem(n)  # 型プレフィックス除去 + NFKC + lower + 記号除去
    return frozenset(_DIGIT_RUN.findall(s)) | frozenset(_LATIN_RUN.findall(s))


def _prefix_implied_type(name: str) -> Optional[str]:
    """型プレフィックスから種別を推定（slot/pachinko）。判定不能は None。

    信頼できる接頭辞のみ。曖昧な S 単独等は None（推定しない）。
    slot   : L / Ｌ / スマスロ / パチスロ / スロット / SLOT
    pachinko: e / ｅ / P / Ｐ / CR / PA / スマパチ / (P)フィーバー
    """
    if not name:
        return None
    n = unicodedata.normalize("NFKC", name.strip())
    n = _STEM_LEADING_BRACKETS.sub("", n).lower()
    if n.startswith(("スマスロ", "パチスロ", "スロット", "slot")):
        return "slot"
    if n.startswith(("スマパチ", "pフィーバー", "フィーバー", "cr", "pa")):
        return "pachinko"
    # 単一ラテン接頭辞（直後が日本語のときのみ有効）
    if len(n) > 1 and not n[1].isascii():
        if n[0] == "l":
            return "slot"
        if n[0] in ("e", "p"):
            return "pachinko"
    return None


class MachineResolver:
    """
    Supabase の machines_master + machines_aliases をメモリにキャッシュして
    機種名を解決する。スクリプト起動時に一度ロードし、以後はメモリ参照。
    """

    def __init__(self, supabase_url: str, service_key: str):
        self._url = supabase_url.rstrip("/")
        self._key = service_key
        self._masters: list[dict] = []
        # normalized_alias → {machine_id, official_name, confidence}
        self._alias_map: dict[str, dict] = {}
        # 曖昧性判定用: (machine_id, series_stem) のリスト（_load でメモリに構築）
        self._master_stems: list[tuple[str, str]] = []
        # 型プレフィックスを持たない正式名の normalized_name 集合（_load で構築）
        self._prefixless_exact: set[str] = set()
        self._loaded = False
        self._ssl_ctx = ssl._create_unverified_context()  # macOS + GH Actions 対応

    # ── 内部ユーティリティ ────────────────────────────────────────────────

    def _sb_get(self, path: str) -> list[dict]:
        req = urllib.request.Request(
            f"{self._url}/rest/v1/{path}",
            headers={
                "apikey":        self._key,
                "Authorization": f"Bearer {self._key}",
                "Content-Type":  "application/json",
            },
        )
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=15) as r:
            return json.loads(r.read())

    def _sb_post(self, path: str, body: dict, prefer: str = "") -> tuple[int, bytes]:
        data = json.dumps(body).encode()
        headers = {
            "apikey":        self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type":  "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        req = urllib.request.Request(
            f"{self._url}/rest/v1/{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # ── キャッシュロード ──────────────────────────────────────────────────

    def _load(self) -> None:
        """machines_master と machines_aliases を Supabase からメモリにロードする。"""
        try:
            self._masters = self._sb_get(
                "machines_master?select=id,official_name,normalized_name,type"
                "&is_active=eq.true&order=official_name"
            )
        except Exception as e:
            print(f"⚠️  machine_resolver: machines_master ロード失敗: {e}")
            self._masters = []

        # 曖昧性判定用の series_stem をメモリに構築（収集開始時に一括・以後DB問い合わせ不要）
        self._master_stems = [
            (m["id"], _series_stem(m.get("official_name", "")))
            for m in self._masters
            if _series_stem(m.get("official_name", ""))
        ]
        # 「型プレフィックスを持たない正式名」の normalized_name 集合。
        # 入力がこれに完全一致する場合は“接頭辞なしの完全な正式名そのもの”なので
        # 裸シリーズ扱いしない（例: 沖ドキ！DUO / 沖ドキ！ゴージャス）。
        # 一方 ゴジラ→Lゴジラ のように official 側に接頭辞がある名前は含まれないため、
        # 裸名 ゴジラ は従来どおり曖昧としてブロックされる。
        self._prefixless_exact = {
            m["normalized_name"]
            for m in self._masters
            if m.get("normalized_name") and not _has_type_prefix(m.get("official_name", ""))
        }

        try:
            aliases_raw = self._sb_get(
                "machines_aliases?select=machine_id,normalized_alias,confidence"
                ",machines_master(official_name,type)"
            )
            self._alias_map = {}
            for a in aliases_raw:
                master_info = a.get("machines_master") or {}
                self._alias_map[a["normalized_alias"]] = {
                    "machine_id":    a["machine_id"],
                    "official_name": master_info.get("official_name", ""),
                    "machine_type":  master_info.get("type", "slot"),
                    "confidence":    float(a.get("confidence", 1.0)),
                }
        except Exception as e:
            print(f"⚠️  machine_resolver: machines_aliases ロード失敗: {e}")
            self._alias_map = {}

        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()

    # ── 公開 API ──────────────────────────────────────────────────────────

    def _is_ambiguous_bare(self, raw_name: str) -> bool:
        """
        「裸のシリーズ名」がマスタ上で複数機種に該当するかを動的に判定する。

        True の条件（すべて満たす）:
          1. 型プレフィックス（L/S/e/P/PA/CR/スマスロ 等）を持たない
          2. series_stem が 2 文字以上
          3. その stem に一致（完全一致 or stem を接頭辞に持つ）する
             有効な machines_master が 2 機種以上存在する

        型プレフィックス付き（例: e牙狼12黄金騎士極限, L沖ドキDUOアンコール）や、
        世代番号・副題で stem 自体が一意に絞れる名前（例: 甲鉄城のカバネリ海門決戦,
        L戦国乙女5）は False（＝通常の exact/alias 解決に進む）。
        """
        if _has_type_prefix(raw_name):
            return False
        # 接頭辞なしの完全な正式名そのものに一致する場合は曖昧としない
        # （例: 沖ドキ！DUO は master に接頭辞なし正式名として存在する具体機種）
        if normalize_for_comparison(raw_name) in self._prefixless_exact:
            return False
        s = _series_stem(raw_name)
        if len(s) < 2:
            return False
        # (a) stem が接頭辞として複数機種に一致（例: 沖ドキ / 甲鉄城 / 北斗）
        members = [
            (mid, mstem) for mid, mstem in self._master_stems
            if mstem == s or mstem.startswith(s)
        ]
        distinct_ids = {mid for mid, _ in members}
        if len(distinct_ids) >= 2:
            member_stems = {mstem for _, mstem in members}
            # 例外: 全メンバーが「入力 stem と完全一致の単一 stem」= 型プレフィックス違いの
            # 重複登録（同一機種を L版/スマスロ版 等で二重登録）とみなし、曖昧としない。
            # 例: 沖ドキ！DUOアンコール（L沖ドキDUOアンコール と スマスロ沖ドキ！DUOアンコール）
            # 一方 ヴァルヴレイヴ（無印 と 2）や 沖ドキ（多数の別副題）は stem が複数種類 → 曖昧。
            if not (len(member_stems) == 1 and s in member_stems):
                return True
        # (b) 数字を含まない裸名で、stem がシリーズ名として複数機種に“含まれる”場合も曖昧。
        #     シリーズ名が正式名の途中に現れる機種（例: L革命機ヴァルヴレイヴ / …2）を捕捉。
        #     数字付き入力（戦国乙女5 等）はこの分岐に入らない＝世代指定は一意解決を許す。
        if not extract_identity_tokens(raw_name):
            sub_members = {mid for mid, mstem in self._master_stems if s in mstem}
            if len(sub_members) >= 2:
                return True
        return False

    def resolve(self, raw_name: str) -> Optional[dict]:
        """
        機種名を解決して dict を返す。85% 未満は None（→ unknown_machines に保存）。

        Returns:
            {machine_id, official_name, normalized_name, confidence, match_type}
            または None
        match_type: "exact" | "alias" | "fuzzy"
        """
        if not raw_name or not raw_name.strip():
            return None

        # 0. シリーズ名のみでの機種確定を禁止（exact/alias matchより先に確認）
        # slot/pachinko 両方が存在するシリーズは prefix なし入力を unknown に送る
        # 例: "東京喰種" → L東京喰種(slot) と e東京喰種(pachinko) が曖昧
        # 例外: "L東京喰種" や "e東京喰種" など prefix 付きはこのチェックをパス
        if raw_name.strip() in _AMBIGUOUS_SERIES:
            return None

        self._ensure_loaded()
        norm = normalize_for_comparison(raw_name)
        if not norm:
            return None

        # 0.5 動的な曖昧性ガード（machines_master 実データ基準）
        # 型プレフィックス・世代・副題のない「裸のシリーズ名」が、マスタ上で
        # 複数機種に該当する場合は、exact/alias 一致があっても特定機種へ確定しない。
        # 例: 牙狼 / 沖ドキ / 甲鉄城 / かぐや / ゴジラ / 革命機（複数世代・複数機種）
        # → 誤った正式名称を保存するより未解決（unknown_machines）を優先する。
        if self._is_ambiguous_bare(raw_name):
            return None

        # 入力プレフィックスが示す種別（slot/pachinko）。候補の種別がこれと食い違う
        # 場合は採用しない（例: "P北斗の拳"(pachinko) が fuzzy で スマスロ北斗(slot) に
        # 誤マッチするのを防ぐ）。master 種別を正とする原則の裏返し。
        implied = _prefix_implied_type(raw_name)

        def _type_ok(mtype: str) -> bool:
            return implied is None or (mtype or "slot") == implied

        # 1. 完全一致（machines_master.normalized_name）
        for m in self._masters:
            if m["normalized_name"] == norm and _type_ok(m.get("type", "slot")):
                return {
                    "machine_id":    m["id"],
                    "official_name": m["official_name"],
                    "machine_type":  m.get("type", "slot"),
                    "normalized_name": m["normalized_name"],
                    "confidence":    1.0,
                    "match_type":    "exact",
                }

        # 2. エイリアス一致（machines_aliases.normalized_alias）
        if norm in self._alias_map:
            a = self._alias_map[norm]
            if _type_ok(a.get("machine_type", "slot")):
                return {
                    "machine_id":    a["machine_id"],
                    "official_name": a["official_name"],
                    "machine_type":  a.get("machine_type", "slot"),
                    "normalized_name": norm,
                    "confidence":    a["confidence"],
                    "match_type":    "alias",
                }

        # 3. ファジーマッチ用の追加 AMBIGUOUS_SERIES チェック（到達しないはずだが念のため）
        # normalized 後に曖昧性が生じるケースを防ぐ
        if raw_name.strip() in _AMBIGUOUS_SERIES:
            return None

        # 4. ファジーマッチ（SequenceMatcher ratio ≥ 0.85）
        # 類似度が同点の場合は official_name 辞書順（ロード時にソート済み）で最初のものを採用
        # 制約:
        #  (a) プレフィックス種別と食い違う候補は除外（誤った種別の確定を防ぐ）
        #  (b) 入力と候補の“数字集合”が一致しない候補は除外
        #      → 世代・数字違いの別機種へ寄せない（例: 沖ドキDUO2 を 沖ドキ！DUO に寄せない）
        #      数字なし入力を数字付き候補（最新世代等）へ寄せることも防ぐ
        input_ids = extract_identity_tokens(raw_name)
        candidates: list[tuple[float, dict]] = []
        for m in self._masters:
            if not _type_ok(m.get("type", "slot")):
                continue
            if extract_identity_tokens(m.get("official_name", "")) != input_ids:
                continue
            score = SequenceMatcher(None, norm, m["normalized_name"]).ratio()
            if score > 0.849:  # 0.85 未満は unknown 扱い
                candidates.append((score, m))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (-x[0], x[1]["official_name"]))
        best_score, best_match = candidates[0]
        # 一意性: 別機種が同点（僅差）で競合する場合は確定しない（誤確定より未解決）
        if any(m["id"] != best_match["id"] and s >= best_score - 1e-9
               for s, m in candidates):
            return None

        return {
            "machine_id":    best_match["id"],
            "official_name": best_match["official_name"],
            "machine_type":  best_match.get("type", "slot"),
            "normalized_name": best_match["normalized_name"],
            "confidence":    round(best_score, 3),
            "match_type":    "fuzzy",
        }

    def save_unknown(self, raw_name: str, source_url: str = "") -> None:
        """
        解決できなかった機種名を unknown_machines に保存（count++ で upsert）。
        保存失敗時はログを出力して継続（スクリプトを止めない）。
        """
        if not raw_name or not self._url or not self._key:
            return

        norm = normalize_for_comparison(raw_name)
        body = {
            "raw_name":            raw_name[:100],
            "normalized_raw_name": norm[:100] if norm else None,
            "source_site":         "x.com",
            "source_url":          source_url[:500] if source_url else None,
        }
        try:
            status, resp = self._sb_post(
                "unknown_machines",
                body,
                prefer="resolution=merge-duplicates,return=minimal",
            )
            if status not in (200, 201):
                err = resp.decode(errors="replace")[:100] if resp else ""
                print(f"⚠️  machine_resolver: unknown_machines 保存失敗 ({status}): {err}")
        except Exception as e:
            print(f"⚠️  machine_resolver: unknown_machines 保存エラー: {e}")


# ── モジュールレベルのシングルトン（fetch_complete_info.py から使用）─────────

_resolver: Optional[MachineResolver] = None


def get_resolver() -> Optional[MachineResolver]:
    """
    環境変数からシングルトンの MachineResolver を返す。
    環境変数未設定の場合は None を返す（ローカル実行等で Supabase 不要なケース）。
    """
    global _resolver
    if _resolver is not None:
        return _resolver

    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None

    _resolver = MachineResolver(url, key)
    return _resolver
