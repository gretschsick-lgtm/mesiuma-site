-- =============================================================================
-- 014_store_aliases.sql
-- 店舗名エイリアステーブル（表記揺れ・略称・チェーン別名対応）
--
-- 用途:
--   - store_resolver.py がエイリアスから stores.id を解決する
--   - マルハン東宝/マルハン新宿東宝/マルハン東宝店 → 同一 store_id
--   - normalize_store_name() 適用済みの文字列を normalized_alias に保存
--
-- 注意:
--   - normalized_alias は normalize_store_name() 適用後（末尾の店/ホール除去済み）
--   - confidence: 1.0=確実な別名, 0.95=ほぼ確実, 0.90=推定
-- =============================================================================

CREATE TABLE IF NOT EXISTS store_aliases (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id         TEXT        NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    alias            TEXT        NOT NULL,
    normalized_alias TEXT        NOT NULL,
    confidence       FLOAT       NOT NULL DEFAULT 1.0
                                 CHECK (confidence BETWEEN 0.0 AND 1.0),
    source           TEXT        NOT NULL DEFAULT 'manual'
                                 CHECK (source IN ('manual', 'auto')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_store_aliases_store_id
    ON store_aliases (store_id);

CREATE INDEX IF NOT EXISTS idx_store_aliases_alias
    ON store_aliases (normalized_alias);

COMMENT ON TABLE store_aliases IS
    '店舗名のエイリアス（略称・表記揺れ・チェーン別名対応）。store_resolver.py が参照。';
COMMENT ON COLUMN store_aliases.normalized_alias IS
    'normalize_store_name() 適用済み（末尾の店/ホール除去・小文字化）';

-- ── 初期データ: 主要チェーン店の別名 ───────────────────────────────────────
-- INSERT は stores テーブルに該当レコードが登録されてから実行すること。
-- 以下はコメントアウト例として記載する。
--
-- マルハン新宿東宝店の例:
-- INSERT INTO store_aliases (store_id, alias, normalized_alias, confidence, source)
-- VALUES
--   ('<store_id>', 'マルハン東宝',     'マルハン東宝',     1.0, 'manual'),
--   ('<store_id>', 'マルハン新宿東宝', 'マルハン新宿東宝', 1.0, 'manual'),
--   ('<store_id>', 'マルハン東宝店',   'マルハン東宝',     1.0, 'manual');
