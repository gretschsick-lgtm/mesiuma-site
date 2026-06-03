-- =============================================================================
-- 010_cast_source_freelance.sql
-- cast_members.source の CHECK 制約に 'freelance' を追加
-- フリー演者対応: agency_id=NULL, source='freelance'
-- =============================================================================

ALTER TABLE cast_members
    DROP CONSTRAINT IF EXISTS cast_members_source_check;

ALTER TABLE cast_members
    ADD CONSTRAINT cast_members_source_check
        CHECK (source IN ('manual', 'auto', 'freelance'));
