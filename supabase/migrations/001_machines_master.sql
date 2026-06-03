-- =============================================================================
-- 001_machines_master.sql
-- 機種名マスタシステム
-- =============================================================================

-- ── テーブル作成 ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS machines_master (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    official_name   TEXT        NOT NULL UNIQUE,
    manufacturer    TEXT,
    brand           TEXT,
    type            TEXT        NOT NULL DEFAULT 'slot'
                                CHECK (type IN ('slot', 'pachinko')),
    normalized_name TEXT        NOT NULL,  -- 照合用正規化済み名（接頭辞除去・小文字・空白なし）
    release_date    DATE,
    source_url      TEXT,                  -- メーカー公式ページ等の参照元URL
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS machines_aliases (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id       UUID        NOT NULL REFERENCES machines_master(id) ON DELETE CASCADE,
    alias_name       TEXT        NOT NULL,        -- 元表記（例: ヴァルヴレイヴ）
    normalized_alias TEXT        NOT NULL UNIQUE, -- 照合用正規化済み（接頭辞除去・小文字・空白なし）
    confidence       NUMERIC(4,3) NOT NULL DEFAULT 1.000
                                 CHECK (confidence >= 0 AND confidence <= 1),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unknown_machines (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name            TEXT        NOT NULL UNIQUE, -- 重複登録防止
    normalized_raw_name TEXT,
    source_site         TEXT,
    source_url          TEXT,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count               INTEGER     NOT NULL DEFAULT 1,
    status              TEXT        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'approved', 'rejected', 'ignored'))
);

-- complete_reports に機種マスタ外部キーを追加（後から追加・既存行は NULL で互換維持）
ALTER TABLE complete_reports
    ADD COLUMN IF NOT EXISTS machine_id UUID REFERENCES machines_master(id);

-- ── インデックス ───────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_machines_master_normalized
    ON machines_master (normalized_name);
CREATE INDEX IF NOT EXISTS idx_machines_master_type
    ON machines_master (type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_machines_aliases_norm
    ON machines_aliases (normalized_alias);
CREATE INDEX IF NOT EXISTS idx_machines_aliases_machine
    ON machines_aliases (machine_id);
CREATE INDEX IF NOT EXISTS idx_unknown_machines_status
    ON unknown_machines (status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_unknown_machines_count
    ON unknown_machines (count DESC);
CREATE INDEX IF NOT EXISTS idx_complete_reports_machine_id
    ON complete_reports (machine_id);

-- ── RLS ───────────────────────────────────────────────────────────────────

ALTER TABLE machines_master  ENABLE ROW LEVEL SECURITY;
ALTER TABLE machines_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE unknown_machines ENABLE ROW LEVEL SECURITY;

-- machines_master: anon は is_active=TRUE のみ参照可
CREATE POLICY "anon_select_machines" ON machines_master
    FOR SELECT TO anon USING (is_active = TRUE);
CREATE POLICY "service_all_machines" ON machines_master
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- machines_aliases: anon は参照のみ
CREATE POLICY "anon_select_aliases" ON machines_aliases
    FOR SELECT TO anon USING (TRUE);
CREATE POLICY "service_all_aliases" ON machines_aliases
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- unknown_machines: anon は INSERT/SELECT 可（スクリプトからの保存用）
CREATE POLICY "anon_select_unknown" ON unknown_machines
    FOR SELECT TO anon USING (TRUE);
CREATE POLICY "anon_insert_unknown" ON unknown_machines
    FOR INSERT TO anon WITH CHECK (TRUE);
CREATE POLICY "service_all_unknown" ON unknown_machines
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- ── 更新日時トリガー ─────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_machines_master_updated_at ON machines_master;
CREATE TRIGGER trg_machines_master_updated_at
    BEFORE UPDATE ON machines_master
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- サンプルデータ（現行 MACHINE_NORMALIZE から抽出）
-- normalized_name: 接頭辞(スマスロ/L/パチスロ/スロット/SLOT)除去 + NFKC + 小文字 + 空白除去
-- =============================================================================

INSERT INTO machines_master
    (id, official_name, manufacturer, brand, type, normalized_name, is_active)
VALUES
-- スロット機種
('11111111-1111-1111-1111-000000000001', 'スマスロ北斗の拳転生の章2',    'サミー',                   NULL,   'slot',     '北斗の拳転生の章2',        TRUE),
('11111111-1111-1111-1111-000000000002', 'L革命機ヴァルヴレイヴ2',       'サミー',                   NULL,   'slot',     '革命機ヴァルヴレイヴ2',    TRUE),
('11111111-1111-1111-1111-000000000003', 'L炎炎ノ消防隊2',               'ユニバーサルエンターテインメント', NULL, 'slot', '炎炎ノ消防隊2',            TRUE),
('11111111-1111-1111-1111-000000000004', 'Lミリオンゴッド神々の軌跡',    'ユニバーサルエンターテインメント', NULL, 'slot', 'ミリオンゴッド神々の軌跡', TRUE),
('11111111-1111-1111-1111-000000000005', 'L甲鉄城のカバネリ海門決戦',    'ビスティ',                 NULL,   'slot',     '甲鉄城のカバネリ海門決戦', TRUE),
('11111111-1111-1111-1111-000000000006', 'L東京喰種',                    'コナミアミューズメント',   NULL,   'slot',     '東京喰種',                 TRUE),
('11111111-1111-1111-1111-000000000007', 'スマスロ北斗の拳',              'サミー',                   NULL,   'slot',     '北斗の拳',                 TRUE),
('11111111-1111-1111-1111-000000000008', 'スマスロ攻殻機動隊',            'エレコ',                   NULL,   'slot',     '攻殻機動隊',               TRUE),
('11111111-1111-1111-1111-000000000009', 'バジリスク絆2',                 'ユニバーサルエンターテインメント', NULL, 'slot', 'バジリスク絆2',            TRUE),
('11111111-1111-1111-1111-000000000010', 'L真打吉宗',                    '大都技研',                 NULL,   'slot',     '真打吉宗',                 TRUE),
('11111111-1111-1111-1111-000000000011', 'L吉宗',                        '大都技研',                 NULL,   'slot',     '吉宗',                     TRUE),
('11111111-1111-1111-1111-000000000012', 'スマスロゴッドイーター',        NULL,                       NULL,   'slot',     'ゴッドイーター',            TRUE),  -- 要確認: メーカー
('11111111-1111-1111-1111-000000000013', 'L沖ドキDUO アンコール',        'ユニバーサルエンターテインメント', NULL, 'slot', '沖ドキduoアンコール',      TRUE),
('11111111-1111-1111-1111-000000000014', 'Lチバリヨ2ZB',                 'ユニバーサルエンターテインメント', NULL, 'slot', 'チバリヨ2zb',              TRUE),
('11111111-1111-1111-1111-000000000015', 'Lシャーマンキング',             'KPE',                      NULL,   'slot',     'シャーマンキング',          TRUE),
('11111111-1111-1111-1111-000000000016', 'L新鬼武者3',                   'コナミアミューズメント',   NULL,   'slot',     '新鬼武者3',                TRUE),
('11111111-1111-1111-1111-000000000017', 'Lかぐや様は告らせたい',         'KPE',                      NULL,   'slot',     'かぐや様は告らせたい',     TRUE),
('11111111-1111-1111-1111-000000000018', 'スマスロバイオハザードRE:3',    'エレコ',                   NULL,   'slot',     'バイオハザードre:3',       TRUE),
('11111111-1111-1111-1111-000000000019', 'Re:ゼロから始める異世界生活',  'ビスティ',                 NULL,   'slot',     're:ゼロから始める異世界生活', TRUE),
('11111111-1111-1111-1111-000000000020', 'Lゴジラ',                      NULL,                       NULL,   'slot',     'ゴジラ',                   TRUE),  -- 要確認: メーカー
('11111111-1111-1111-1111-000000000021', 'Lからくりサーカス',             'パオン・ディーピー',       NULL,   'slot',     'からくりサーカス',          TRUE),
('11111111-1111-1111-1111-000000000022', 'L鉄拳6',                       'コナミアミューズメント',   NULL,   'slot',     '鉄拳6',                    TRUE),
-- ジャグラーシリーズ（誤統合防止のため個別登録）
('11111111-1111-1111-1111-000000000023', 'アイムジャグラーEX',            'ユニバーサルブロス',       'ジャグラー', 'slot', 'アイムジャグラーex',       TRUE),
('11111111-1111-1111-1111-000000000024', 'マイジャグラー5',               'ユニバーサルブロス',       'ジャグラー', 'slot', 'マイジャグラー5',           TRUE),
('11111111-1111-1111-1111-000000000025', 'ファンキージャグラー2',          'ユニバーサルブロス',       'ジャグラー', 'slot', 'ファンキージャグラー2',     TRUE),
('11111111-1111-1111-1111-000000000026', 'ゴーゴージャグラー3',            'ユニバーサルブロス',       'ジャグラー', 'slot', 'ゴーゴージャグラー3',       TRUE),
('11111111-1111-1111-1111-000000000027', 'ハッピージャグラーVⅢ',          'ユニバーサルブロス',       'ジャグラー', 'slot', 'ハッピージャグラーviii',    TRUE),
-- パチンコ機種
('11111111-1111-1111-1111-000000000028', 'e牙狼12黄金騎士極限',           '三洋物産',                 NULL,   'pachinko', 'e牙狼12黄金騎士極限',      TRUE),
('11111111-1111-1111-1111-000000000029', 'e牙狼12',                       '三洋物産',                 NULL,   'pachinko', 'e牙狼12',                  TRUE),
('11111111-1111-1111-1111-000000000030', 'eバイオハザード6',               '平和',                     NULL,   'pachinko', 'eバイオハザード6',          TRUE),
('11111111-1111-1111-1111-000000000031', 'eフィーバーキン肉マン',          'SANKYO',                   NULL,   'pachinko', 'eフィーバーキン肉マン',     TRUE),
('11111111-1111-1111-1111-000000000032', 'eフィーバーもののがたりF',        'SANKYO',                   NULL,   'pachinko', 'eフィーバーもののがたりf',  TRUE),
('11111111-1111-1111-1111-000000000033', 'eフィーバーもののがたり',         'SANKYO',                   NULL,   'pachinko', 'eフィーバーもののがたり',   TRUE),
('11111111-1111-1111-1111-000000000034', 'eひきこまり吸血姫の悶々',        NULL,                       NULL,   'pachinko', 'eひきこまり吸血姫の悶々',  TRUE),  -- 要確認: メーカー
('11111111-1111-1111-1111-000000000035', 'eカケグルイ',                   '藤商事',                   NULL,   'pachinko', 'eカケグルイ',               TRUE),
('11111111-1111-1111-1111-000000000036', 'e転生したらスライムだった件2',   NULL,                       NULL,   'pachinko', 'e転生したらスライムだった件2', TRUE)  -- 要確認: メーカー
ON CONFLICT (official_name) DO NOTHING;

-- ── エイリアスデータ ──────────────────────────────────────────────────────
-- normalized_alias: normalize_for_comparison(alias_name) の値
-- 機種の normalized_name と同値になるエイリアスは省略（exact matchで解決するため）

INSERT INTO machines_aliases
    (machine_id, alias_name, normalized_alias, confidence)
VALUES
-- スマスロ北斗の拳転生の章2
('11111111-1111-1111-1111-000000000001', '転生の章2',             '転生の章2',             1.0),
('11111111-1111-1111-1111-000000000001', '転生の章Ⅱ',            '転生の章ii',            1.0),
('11111111-1111-1111-1111-000000000001', '転生2',                 '転生2',                 1.0),
('11111111-1111-1111-1111-000000000001', '転生の章',              '転生の章',              1.0),
('11111111-1111-1111-1111-000000000001', '北斗の拳転生',          '北斗の拳転生',          1.0),
('11111111-1111-1111-1111-000000000001', '北斗転生',              '北斗転生',              1.0),
-- L革命機ヴァルヴレイヴ2
('11111111-1111-1111-1111-000000000002', 'ヴァルヴレイヴ2',       'ヴァルヴレイヴ2',       1.0),
('11111111-1111-1111-1111-000000000002', 'ヴァルヴレイヴ',        'ヴァルヴレイヴ',        1.0),
-- L炎炎ノ消防隊2
('11111111-1111-1111-1111-000000000003', '炎炎ノ消防隊',          '炎炎ノ消防隊',          1.0),
('11111111-1111-1111-1111-000000000003', '炎炎の消防隊',          '炎炎の消防隊',          1.0),
-- Lミリオンゴッド神々の軌跡
('11111111-1111-1111-1111-000000000004', 'ミリオンゴッド',        'ミリオンゴッド',        1.0),
-- L甲鉄城のカバネリ海門決戦
('11111111-1111-1111-1111-000000000005', '甲鉄城のカバネリ',      '甲鉄城のカバネリ',      1.0),
('11111111-1111-1111-1111-000000000005', 'カバネリ海門決戦',      'カバネリ海門決戦',      1.0),
('11111111-1111-1111-1111-000000000005', 'カバネリ',              'カバネリ',              1.0),
('11111111-1111-1111-1111-000000000005', '甲鉄城',                '甲鉄城',                1.0),
-- L東京喰種（テストケース: 東京グール）
('11111111-1111-1111-1111-000000000006', '東京グール',            '東京グール',            0.950),
-- スマスロ北斗の拳（テストケース: スマスロ北斗 → 北斗の拳）
('11111111-1111-1111-1111-000000000007', '北斗',                  '北斗',                  1.0),
-- バジリスク絆2
('11111111-1111-1111-1111-000000000009', 'バジリスク絆',          'バジリスク絆',          1.0),
('11111111-1111-1111-1111-000000000009', 'バジリスク',            'バジリスク',            1.0),
-- L沖ドキDUO アンコール
('11111111-1111-1111-1111-000000000013', '沖ドキDUO',             '沖ドキduo',             1.0),
('11111111-1111-1111-1111-000000000013', '沖ドキ',                '沖ドキ',                1.0),
-- Lチバリヨ2ZB
('11111111-1111-1111-1111-000000000014', 'チバリヨ2',             'チバリヨ2',             1.0),
('11111111-1111-1111-1111-000000000014', 'チバリヨ',              'チバリヨ',              1.0),
-- L新鬼武者3
('11111111-1111-1111-1111-000000000016', '鬼武者3',               '鬼武者3',               1.0),
-- Lかぐや様は告らせたい
('11111111-1111-1111-1111-000000000017', 'かぐや様',              'かぐや様',              1.0),
-- スマスロバイオハザードRE:3
('11111111-1111-1111-1111-000000000018', 'バイオハザードRe',      'バイオハザードre',      1.0),
-- Re:ゼロから始める異世界生活（テストケース）
('11111111-1111-1111-1111-000000000019', 'Re:ゼロ',               're:ゼロ',               1.0),
('11111111-1111-1111-1111-000000000019', 'リゼロ',                'リゼロ',                1.0),
-- Lからくりサーカス（テストケース: からくり）
('11111111-1111-1111-1111-000000000021', 'からくり',              'からくり',              1.0),
-- L鉄拳6
('11111111-1111-1111-1111-000000000022', '鉄拳',                  '鉄拳',                  1.0),
-- ジャグラーエイリアス
('11111111-1111-1111-1111-000000000023', 'アイムジャグラー',      'アイムジャグラー',      1.0),
('11111111-1111-1111-1111-000000000024', 'マイジャグ',            'マイジャグ',            1.0),
-- e牙狼12（牙狼 は e牙狼12 に統一。e牙狼12黄金騎士極限 は別機種で保護）
('11111111-1111-1111-1111-000000000029', '牙狼',                  '牙狼',                  1.0),
-- eバイオハザード6
('11111111-1111-1111-1111-000000000030', 'eバイオ',               'eバイオ',               1.0),
-- eフィーバーキン肉マン
('11111111-1111-1111-1111-000000000031', 'eFEVERキン肉マン',      'efeverキン肉マン',      1.0),
('11111111-1111-1111-1111-000000000031', 'eFキン肉マン',          'efキン肉マン',          1.0),
('11111111-1111-1111-1111-000000000031', 'eキン肉マン',           'eキン肉マン',           1.0),
-- eフィーバーもののがたり
('11111111-1111-1111-1111-000000000033', 'eFEVERもののがたり',    'efeverもののがたり',    1.0),
('11111111-1111-1111-1111-000000000033', 'eもののがたり',         'eもののがたり',         1.0),
-- eひきこまり吸血姫の悶々
('11111111-1111-1111-1111-000000000034', 'eひきこまり吸血鬼の悶々', 'eひきこまり吸血鬼の悶々', 0.950),
('11111111-1111-1111-1111-000000000034', 'eひきこまり',           'eひきこまり',           1.0),
-- e転生したらスライムだった件2（テストケース: 転スラ）
('11111111-1111-1111-1111-000000000036', '転生したらスライムだった件', '転生したらスライムだった件', 1.0),
('11111111-1111-1111-1111-000000000036', '転スラ',                '転スラ',                1.0)
ON CONFLICT (normalized_alias) DO NOTHING;
