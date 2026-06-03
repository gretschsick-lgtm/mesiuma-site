-- =============================================================================
-- 003_cast_members_extend.sql
-- cast_members テーブル拡張
-- すべて NULL 許可・既存行への影響なし
-- =============================================================================

ALTER TABLE cast_members
    ADD COLUMN IF NOT EXISTS agency_id         UUID        REFERENCES agencies(id),
    ADD COLUMN IF NOT EXISTS display_name      TEXT,
    ADD COLUMN IF NOT EXISTS normalized_name   TEXT,
    ADD COLUMN IF NOT EXISTS birthday          DATE,
    ADD COLUMN IF NOT EXISTS description       TEXT,
    ADD COLUMN IF NOT EXISTS profile_image_url TEXT,
    ADD COLUMN IF NOT EXISTS instagram_url     TEXT,
    ADD COLUMN IF NOT EXISTS youtube_url       TEXT,
    ADD COLUMN IF NOT EXISTS area              TEXT,
    ADD COLUMN IF NOT EXISTS gender            TEXT
        CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    ADD COLUMN IF NOT EXISTS is_active         BOOLEAN     DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS source            TEXT        DEFAULT 'manual'
        CHECK (source IN ('manual', 'auto')),
    ADD COLUMN IF NOT EXISTS first_detected_at TIMESTAMPTZ;

-- ── インデックス ──────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_cast_members_agency_id
    ON cast_members (agency_id);
CREATE INDEX IF NOT EXISTS idx_cast_members_normalized_name
    ON cast_members (normalized_name);
CREATE INDEX IF NOT EXISTS idx_cast_members_is_active
    ON cast_members (is_active);
