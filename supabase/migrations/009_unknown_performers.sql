-- =============================================================================
-- 009_unknown_performers.sql
-- 未解決演者ログテーブル（unknown_machines と同構造）
--
-- 用途:
--   - register_cast.py が name+source_url だけでは解決できなかった演者を記録
--   - 人手確認後 status='approved' → cast_members に昇格
--   - status='rejected'/'ignored' は再登録しない
-- =============================================================================

CREATE TABLE IF NOT EXISTS unknown_performers (
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

CREATE INDEX IF NOT EXISTS idx_unknown_performers_normalized_name
    ON unknown_performers (normalized_name);
CREATE INDEX IF NOT EXISTS idx_unknown_performers_status
    ON unknown_performers (status);
CREATE INDEX IF NOT EXISTS idx_unknown_performers_raw_name
    ON unknown_performers (raw_name);

-- ── RLS ──────────────────────────────────────────────────────────────────

ALTER TABLE unknown_performers ENABLE ROW LEVEL SECURITY;

-- 管理用: service_role のみ全操作可
CREATE POLICY "service_all_unknown_performers"
    ON unknown_performers FOR ALL TO service_role
    USING (TRUE) WITH CHECK (TRUE);

-- anon は読み取り不可（内部管理データ）
