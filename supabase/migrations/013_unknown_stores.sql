-- =============================================================================
-- 013_unknown_stores.sql
-- 未解決店舗ログテーブル（unknown_machines / unknown_performers と同構造）
--
-- 用途:
--   - register_stores.py が名前解決できなかった店舗を記録
--   - 人手確認後 status='approved' → stores に昇格
-- =============================================================================

CREATE TABLE IF NOT EXISTS unknown_stores (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name        TEXT        NOT NULL,
    normalized_name TEXT,
    source_site     TEXT,
    source_url      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count           INTEGER     NOT NULL DEFAULT 1,
    status          TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'ignored'))
);

-- ── インデックス ──────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_unknown_stores_normalized_name
    ON unknown_stores (normalized_name);
CREATE INDEX IF NOT EXISTS idx_unknown_stores_status
    ON unknown_stores (status);

-- ── RLS ──────────────────────────────────────────────────────────────────

ALTER TABLE unknown_stores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_all_unknown_stores"
    ON unknown_stores FOR ALL TO service_role
    USING (TRUE) WITH CHECK (TRUE);
