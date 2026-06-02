"""
店舗名マスタシステム — Python 版

スクレイピング取得した店舗名を stores テーブルの正式名称 (stores.id) に解決する。
DB保存前に必ずこのモジュールを通すこと（CLAUDE.md 参照）。

使用例:
    from store_resolver import StoreResolver
    resolver = StoreResolver(supabase_url, service_key)
    result = resolver.resolve("マルハン東宝")
    # → {"store_id": "...", "official_name": "マルハン東宝店", "pref": "東京都", ...}

注意:
- normalize_store_name() は機種名・演者名の正規化関数と混在禁止
- 閾値 0.88: 支店名が似ているケースで誤統合を防ぐため機種名(0.85)より厳格に
- store_aliases テーブルで表記揺れ・略称・チェーン別名を管理
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

# 店舗名末尾の「店・ホール・パーラー・PALACE」を正規化時に除去（照合精度向上）
_SUFFIX_RE = re.compile(
    r'(?:店|ホール|パーラー|PALACE|palace|パレス|センター)$',
    re.IGNORECASE,
)

# 店舗名照合の最低類似度（機種名 0.85 より厳格: 支店名の誤統合防止）
_MIN_CONFIDENCE = 0.88


def normalize_store_name(name: str) -> str:
    """
    店舗名を照合用に正規化する。register_stores.py の normalize_store_name と同一ロジック。
    - NFKC 正規化（全角英数→半角）
    - 空白除去
    - 小文字化
    - 末尾の 店/ホール/パーラー/PALACE を除去（マッチング精度向上のため）
    正式名称の保存には使わない（stores.name は元表記を保持）。
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name.strip())
    s = s.lower().replace(" ", "").replace("\u3000", "")
    s = _SUFFIX_RE.sub("", s)
    return s


class StoreResolver:
    """
    Supabase の stores + store_aliases をメモリにキャッシュして
    店舗名を解決する。スクリプト起動時に一度ロードし、以後はメモリ参照。
    """

    def __init__(self, supabase_url: str, service_key: str):
        self._url = supabase_url.rstrip("/")
        self._key = service_key
        self._stores: list[dict] = []
        # normalized_alias → {store_id, official_name, pref, area, confidence}
        self._alias_map: dict[str, dict] = {}
        self._loaded = False
        self._ssl_ctx = ssl._create_unverified_context()

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
        """stores と store_aliases を Supabase からメモリにロードする。"""
        try:
            self._stores = self._sb_get(
                "stores?select=id,name,normalized_name,pref,area"
                "&is_active=eq.true&order=name&limit=10000"
            )
        except Exception as e:
            print(f"⚠️  store_resolver: stores ロード失敗: {e}")
            self._stores = []

        try:
            aliases_raw = self._sb_get(
                "store_aliases?select=store_id,normalized_alias,confidence"
                ",stores(name,pref,area)"
            )
            self._alias_map = {}
            for a in aliases_raw:
                store_info = a.get("stores") or {}
                self._alias_map[a["normalized_alias"]] = {
                    "store_id":     a["store_id"],
                    "official_name": store_info.get("name", ""),
                    "pref":         store_info.get("pref", ""),
                    "area":         store_info.get("area", ""),
                    "confidence":   float(a.get("confidence", 1.0)),
                }
        except Exception as e:
            # store_aliases テーブルが未作成の場合は無視してグレースフルに動作
            print(f"⚠️  store_resolver: store_aliases ロード失敗（テーブル未作成の場合は無視可）: {e}")
            self._alias_map = {}

        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()

    # ── 公開 API ──────────────────────────────────────────────────────────

    def resolve(self, raw_name: str) -> Optional[dict]:
        """
        店舗名を解決して dict を返す。閾値未満は None（→ unknown_stores に保存）。

        Returns:
            {store_id, official_name, pref, area, confidence, match_type}
            または None
        match_type: "exact" | "alias" | "fuzzy"
        """
        if not raw_name or not raw_name.strip():
            return None

        self._ensure_loaded()
        norm = normalize_store_name(raw_name)
        if not norm:
            return None

        # 1. 完全一致（stores.normalized_name の末尾サフィックス除去後）
        for s in self._stores:
            stored_norm = s.get("normalized_name") or normalize_store_name(s["name"])
            if stored_norm == norm:
                return {
                    "store_id":     s["id"],
                    "official_name": s["name"],
                    "pref":         s.get("pref", ""),
                    "area":         s.get("area", ""),
                    "confidence":   1.0,
                    "match_type":   "exact",
                }

        # 2. エイリアス一致（store_aliases.normalized_alias）
        if norm in self._alias_map:
            a = self._alias_map[norm]
            return {
                "store_id":     a["store_id"],
                "official_name": a["official_name"],
                "pref":         a.get("pref", ""),
                "area":         a.get("area", ""),
                "confidence":   a["confidence"],
                "match_type":   "alias",
            }

        # 3. ファジーマッチ（SequenceMatcher ratio ≥ 0.88）
        # 店舗名は支店名が1文字違いで別店舗になるため機種名より厳格なしきい値を使用
        best_score = _MIN_CONFIDENCE - 0.001  # 0.879... (exclusive lower bound)
        best_match: Optional[dict] = None
        for s in self._stores:
            stored_norm = s.get("normalized_name") or normalize_store_name(s["name"])
            if not stored_norm:
                continue
            score = SequenceMatcher(None, norm, stored_norm).ratio()
            if score > best_score:
                best_score = score
                best_match = s

        if best_match:
            return {
                "store_id":     best_match["id"],
                "official_name": best_match["name"],
                "pref":         best_match.get("pref", ""),
                "area":         best_match.get("area", ""),
                "confidence":   round(best_score, 3),
                "match_type":   "fuzzy",
            }

        return None

    def save_unknown(self, raw_name: str, source_url: str = "") -> None:
        """
        解決できなかった店舗名を unknown_stores に保存（count++ で upsert）。
        保存失敗時はログを出力して継続（スクリプトを止めない）。
        """
        if not raw_name or not self._url or not self._key:
            return

        norm = normalize_store_name(raw_name)
        body = {
            "raw_name":       raw_name[:100],
            "normalized_name": norm[:100] if norm else None,
            "source_site":    "x.com",
            "source_url":     source_url[:500] if source_url else None,
        }
        try:
            status, resp = self._sb_post(
                "unknown_stores",
                body,
                prefer="resolution=merge-duplicates,return=minimal",
            )
            if status not in (200, 201):
                err = resp.decode(errors="replace")[:100] if resp else ""
                print(f"⚠️  store_resolver: unknown_stores 保存失敗 ({status}): {err}")
        except Exception as e:
            print(f"⚠️  store_resolver: unknown_stores 保存エラー: {e}")


# ── モジュールレベルのシングルトン ──────────────────────────────────────────

_resolver: Optional[StoreResolver] = None


def get_resolver() -> Optional[StoreResolver]:
    """
    環境変数からシングルトンの StoreResolver を返す。
    環境変数未設定の場合は None を返す。
    """
    global _resolver
    if _resolver is not None:
        return _resolver

    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None

    _resolver = StoreResolver(url, key)
    return _resolver
