-- =============================================================================
-- 004_events_performer_id.sql
-- events テーブルに performer_id カラムを追加
--
-- 制約:
--   - cast_names[] は削除しない（後方互換維持）
--   - 既存レコードの performer_id は NULL のまま（既存データ更新禁止）
--   - cast_names → normalized_name → cast_members.id の自動紐付けは将来実装
-- =============================================================================

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS performer_id INTEGER REFERENCES cast_members(id);

-- ── インデックス ──────────────────────────────────────────────────────────

-- performer_id 単体（演者別イベント一覧取得用）
CREATE INDEX IF NOT EXISTS idx_events_performer_id
    ON events (performer_id);

-- date 単体（日付絞り込みの既存クエリ補完）
CREATE INDEX IF NOT EXISTS idx_events_date
    ON events (date DESC);

-- performer_id + date 複合（演者×日付の絞り込み用）
CREATE INDEX IF NOT EXISTS idx_events_performer_id_date
    ON events (performer_id, date DESC);
