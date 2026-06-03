-- =============================================================================
-- 011_stores_extend.sql
-- stores テーブル拡張
-- - normalized_name: 重複判定用正規化名
-- - is_active: 閉店フラグ（削除禁止・false で閉店扱い）
-- - parent_store_id: 移転元店舗 ID（旧→新を追跡）
-- - source_url: 情報収集元 URL
-- - address_history: 住所変更履歴 JSONB 配列 [{address, changed_at}]
-- すべて NULL 許可・既存データへの影響なし
-- =============================================================================

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS normalized_name  TEXT,
    ADD COLUMN IF NOT EXISTS is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS parent_store_id  TEXT        REFERENCES stores(id),
    ADD COLUMN IF NOT EXISTS source_url       TEXT,
    ADD COLUMN IF NOT EXISTS address_history  JSONB       NOT NULL DEFAULT '[]';

-- ── インデックス ──────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_stores_normalized_name
    ON stores (normalized_name);
CREATE INDEX IF NOT EXISTS idx_stores_is_active
    ON stores (is_active);
CREATE INDEX IF NOT EXISTS idx_stores_parent_store_id
    ON stores (parent_store_id);
CREATE INDEX IF NOT EXISTS idx_stores_pref
    ON stores (pref);
