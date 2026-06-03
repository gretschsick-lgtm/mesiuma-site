-- =============================================================================
-- 002_agencies.sql
-- 事務所・プロダクション管理
-- =============================================================================

CREATE TABLE IF NOT EXISTS agencies (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL UNIQUE,
    slug        TEXT        UNIQUE,
    hp_url      TEXT,
    x_url       TEXT,
    description TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agencies_slug ON agencies (slug);

ALTER TABLE agencies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_select_agencies" ON agencies
    FOR SELECT TO anon USING (is_active = TRUE);
CREATE POLICY "service_all_agencies" ON agencies
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- update_updated_at_column() は 001_machines_master.sql で定義済み
DROP TRIGGER IF EXISTS trg_agencies_updated_at ON agencies;
CREATE TRIGGER trg_agencies_updated_at
    BEFORE UPDATE ON agencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
