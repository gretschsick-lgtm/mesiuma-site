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

        # 1. 完全一致（machines_master.normalized_name）
        for m in self._masters:
            if m["normalized_name"] == norm:
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
        best_score = 0.849  # 0.85 未満は unknown 扱い
        best_match: Optional[dict] = None
        for m in self._masters:
            score = SequenceMatcher(None, norm, m["normalized_name"]).ratio()
            if score > best_score:
                best_score = score
                best_match = m

        if best_match:
            return {
                "machine_id":    best_match["id"],
                "official_name": best_match["official_name"],
                "machine_type":  best_match.get("type", "slot"),
                "normalized_name": best_match["normalized_name"],
                "confidence":    round(best_score, 3),
                "match_type":    "fuzzy",
            }

        return None

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
