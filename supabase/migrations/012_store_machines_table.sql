-- =============================================================================
-- 012_store_machines_table.sql
-- store_machines テーブル新規作成
--
-- 制約:
--   - machine_id は machines_master.id FK（機種名文字列保存禁止）
--   - (store_id, machine_id) は UNIQUE（同一店舗×同一機種は1レコード）
--   - 機種撤去は is_active=false（削除禁止）
-- =============================================================================

CREATE TABLE IF NOT EXISTS store_machines (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     TEXT        NOT NULL REFERENCES stores(id)          ON DELETE CASCADE,
    machine_id   UUID        NOT NULL REFERENCES machines_master(id) ON DELETE RESTRICT,
    rate         TEXT,          -- 貸玉率 例: '4円', '1円', '2円'
    count        INTEGER,       -- 設置台数
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, machine_id)
);

-- ── インデックス ──────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_store_machines_store_id
    ON store_machines (store_id);
CREATE INDEX IF NOT EXISTS idx_store_machines_machine_id
    ON store_machines (machine_id);
CREATE INDEX IF NOT EXISTS idx_store_machines_is_active
    ON store_machines (is_active);

-- ── updated_at 自動更新トリガー ───────────────────────────────────────────

CREATE TRIGGER trg_store_machines_updated_at
    BEFORE UPDATE ON store_machines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── RLS ──────────────────────────────────────────────────────────────────

ALTER TABLE store_machines ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_select_store_machines"
    ON store_machines FOR SELECT TO anon USING (is_active = TRUE);
CREATE POLICY "service_all_store_machines"
    ON store_machines FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
