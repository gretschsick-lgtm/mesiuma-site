-- =============================================================================
-- 007_machine_series.sql
-- 機種シリーズ管理テーブル（分析用途のみ）
--
-- 重要制約:
--   - シリーズ名から machine_id を自動決定する機能は実装しない
--   - machine_resolver.py のロジックに影響を与えない
--   - members テーブルは確認済みの machine_id のみを登録する
-- =============================================================================

CREATE TABLE IF NOT EXISTS machine_series (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS machine_series_members (
    series_id   UUID NOT NULL REFERENCES machine_series(id)  ON DELETE CASCADE,
    machine_id  UUID NOT NULL REFERENCES machines_master(id) ON DELETE CASCADE,
    PRIMARY KEY (series_id, machine_id)
);

CREATE INDEX IF NOT EXISTS idx_series_members_machine_id
    ON machine_series_members (machine_id);

ALTER TABLE machine_series         ENABLE ROW LEVEL SECURITY;
ALTER TABLE machine_series_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_select_machine_series"
    ON machine_series FOR SELECT TO anon USING (TRUE);
CREATE POLICY "service_all_machine_series"
    ON machine_series FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "anon_select_machine_series_members"
    ON machine_series_members FOR SELECT TO anon USING (TRUE);
CREATE POLICY "service_all_machine_series_members"
    ON machine_series_members FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- ── シリーズマスタ登録 ──────────────────────────────────────────────────
INSERT INTO machine_series (name) VALUES
    ('からくりサーカス'),
    ('まどか☆マギカ'),
    ('もののがたり'),
    ('アズールレーン'),
    ('エヴァンゲリオン'),
    ('カバネリ'),
    ('キン肉マン'),
    ('ゴッドイーター'),
    ('ジャグラー'),
    ('バイオハザード'),
    ('バジリスク'),
    ('ブルーロック'),
    ('ミリオンゴッド'),
    ('リコリス・リコイル'),
    ('リゼロ'),
    ('ルパン三世'),
    ('ヴァルヴレイヴ'),
    ('化物語'),
    ('北斗の拳'),
    ('吉宗'),
    ('大海物語'),
    ('戦国乙女'),
    ('東京喰種'),
    ('機動戦士ガンダム'),
    ('沖ドキ'),
    ('炎炎ノ消防隊'),
    ('牙狼'),
    ('転スラ'),
    ('鉄拳')
ON CONFLICT (name) DO NOTHING;

-- ── シリーズメンバー登録 ─────────────────────────────────────────────────
INSERT INTO machine_series_members (series_id, machine_id)
VALUES
    ((SELECT id FROM machine_series WHERE name = 'からくりサーカス'), '11111111-1111-1111-1111-000000000021'),
    ((SELECT id FROM machine_series WHERE name = 'からくりサーカス'), '50a8867c-f0f0-4e60-9274-06d1435ebf1a'),
    ((SELECT id FROM machine_series WHERE name = 'からくりサーカス'), '2e1ae276-ecbb-44e9-bcb6-5fcea1a3a54c'),
    ((SELECT id FROM machine_series WHERE name = 'まどか☆マギカ'), '5bea9ac7-e2a9-407a-8f06-22ad163d12ad'),
    ((SELECT id FROM machine_series WHERE name = 'もののがたり'), '11111111-1111-1111-1111-000000000032'),
    ((SELECT id FROM machine_series WHERE name = 'もののがたり'), '11111111-1111-1111-1111-000000000033'),
    ((SELECT id FROM machine_series WHERE name = 'アズールレーン'), 'd2224ff3-9cfd-4a98-b26d-611938255007'),
    ((SELECT id FROM machine_series WHERE name = 'アズールレーン'), '72c0ff95-f4d1-4075-a45f-d9952b2cde3c'),
    ((SELECT id FROM machine_series WHERE name = 'アズールレーン'), 'cc397c5c-3872-4d97-a65c-b99e27374223'),
    ((SELECT id FROM machine_series WHERE name = 'エヴァンゲリオン'), 'dbd5361a-dfb5-4d95-a9cb-109bf3f4a3c0'),
    ((SELECT id FROM machine_series WHERE name = 'エヴァンゲリオン'), '380c9bf1-ca03-4b79-8caf-5e4547ca3820'),
    ((SELECT id FROM machine_series WHERE name = 'エヴァンゲリオン'), '70ae27fb-534d-4d33-b58f-418daaf8501b'),
    ((SELECT id FROM machine_series WHERE name = 'エヴァンゲリオン'), '2af9db8c-399e-4941-9136-6d612754ebc8'),
    ((SELECT id FROM machine_series WHERE name = 'カバネリ'), '11111111-1111-1111-1111-000000000005'),
    ((SELECT id FROM machine_series WHERE name = 'カバネリ'), 'f8445f36-4c03-42da-b080-d2cd466f3ea6'),
    ((SELECT id FROM machine_series WHERE name = 'カバネリ'), 'aaa688fc-0489-4c0d-bae6-5538e536a168'),
    ((SELECT id FROM machine_series WHERE name = 'キン肉マン'), '11111111-1111-1111-1111-000000000031'),
    ((SELECT id FROM machine_series WHERE name = 'ゴッドイーター'), '11111111-1111-1111-1111-000000000012'),
    ((SELECT id FROM machine_series WHERE name = 'ゴッドイーター'), 'a28db5a8-6e36-4f30-95b5-52b2b21d1425'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '11111111-1111-1111-1111-000000000023'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '11111111-1111-1111-1111-000000000024'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '11111111-1111-1111-1111-000000000025'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '11111111-1111-1111-1111-000000000026'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '11111111-1111-1111-1111-000000000027'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '0c78ecb3-64e2-4772-8059-ae292b61d9bf'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), 'f99a8fbf-3da9-4374-876e-5e40777347f1'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), 'eb7718f4-daac-4d64-9e3c-222079458751'),
    ((SELECT id FROM machine_series WHERE name = 'ジャグラー'), '2ea12eec-558a-4120-beec-34d4cd2e8db6'),
    ((SELECT id FROM machine_series WHERE name = 'バイオハザード'), '11111111-1111-1111-1111-000000000018'),
    ((SELECT id FROM machine_series WHERE name = 'バイオハザード'), '11111111-1111-1111-1111-000000000030'),
    ((SELECT id FROM machine_series WHERE name = 'バイオハザード'), '2c7e680c-04bd-48dc-ae71-ee98ba9133cb'),
    ((SELECT id FROM machine_series WHERE name = 'バイオハザード'), '595de8f1-8f72-4600-b1cd-a645fa6182eb'),
    ((SELECT id FROM machine_series WHERE name = 'バイオハザード'), 'b8ecc10a-87d9-469a-80e5-f803096039ff'),
    ((SELECT id FROM machine_series WHERE name = 'バジリスク'), '11111111-1111-1111-1111-000000000009'),
    ((SELECT id FROM machine_series WHERE name = 'バジリスク'), 'a4556aec-6b75-4c39-aa81-0f6b39c12fad'),
    ((SELECT id FROM machine_series WHERE name = 'ブルーロック'), '43c709fa-b6c8-4b23-8676-834ec693a48c'),
    ((SELECT id FROM machine_series WHERE name = 'ブルーロック'), '8242d72f-0825-4c89-820a-c5f4b5c96a0b'),
    ((SELECT id FROM machine_series WHERE name = 'ミリオンゴッド'), '11111111-1111-1111-1111-000000000004'),
    ((SELECT id FROM machine_series WHERE name = 'ミリオンゴッド'), '8e439e6c-c3b7-4a2a-a3e5-bb5f7de1cbac'),
    ((SELECT id FROM machine_series WHERE name = 'リコリス・リコイル'), 'd5ec225f-a289-4577-9d2d-56ea7305f3d9'),
    ((SELECT id FROM machine_series WHERE name = 'リコリス・リコイル'), '9ac47d6a-d02f-48fc-82d0-993a00c03f35'),
    ((SELECT id FROM machine_series WHERE name = 'リゼロ'), '11111111-1111-1111-1111-000000000019'),
    ((SELECT id FROM machine_series WHERE name = 'リゼロ'), 'c81a452d-0df0-4a0b-ba9a-ed4e406dfab7'),
    ((SELECT id FROM machine_series WHERE name = 'ルパン三世'), 'dfb29be8-a636-4a54-b9e2-107a194a43d1'),
    ((SELECT id FROM machine_series WHERE name = 'ヴァルヴレイヴ'), '11111111-1111-1111-1111-000000000002'),
    ((SELECT id FROM machine_series WHERE name = 'ヴァルヴレイヴ'), '3612602b-f7fe-4dac-b103-fd0fe06ede94'),
    ((SELECT id FROM machine_series WHERE name = '化物語'), '92105b27-3261-4af0-b2ed-24f63c5cd477'),
    ((SELECT id FROM machine_series WHERE name = '化物語'), '95d007b8-95ea-4a1d-8880-0f76eda50d03'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '11111111-1111-1111-1111-000000000001'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '11111111-1111-1111-1111-000000000007'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '7ec80d33-c1f2-4ca4-8705-cd468f736d4d'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '531c3170-97eb-4ba1-89fc-0ee33a8bf426'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '4b7631e5-c602-47c2-a90b-c2c68609e371'),
    ((SELECT id FROM machine_series WHERE name = '北斗の拳'), '90030ef0-24cc-4cb6-8c96-289653a686af'),
    ((SELECT id FROM machine_series WHERE name = '吉宗'), '11111111-1111-1111-1111-000000000010'),
    ((SELECT id FROM machine_series WHERE name = '吉宗'), '11111111-1111-1111-1111-000000000011'),
    ((SELECT id FROM machine_series WHERE name = '吉宗'), 'ca3b52ba-f566-4b93-94a6-dbd6555848e3'),
    ((SELECT id FROM machine_series WHERE name = '吉宗'), 'f5217a60-0976-45e7-bfe6-d5e94c244e21'),
    ((SELECT id FROM machine_series WHERE name = '大海物語'), 'aa34cc91-d58a-4323-bcad-d80197919a9d'),
    ((SELECT id FROM machine_series WHERE name = '大海物語'), 'bf93ac46-0255-4b4b-8bc1-7737db6faa6d'),
    ((SELECT id FROM machine_series WHERE name = '大海物語'), 'ea1f5ef2-9fe3-4046-b1c0-77a9d3d05e09'),
    ((SELECT id FROM machine_series WHERE name = '大海物語'), '381b3918-9a19-4c67-8a45-c0ebd75a5410'),
    ((SELECT id FROM machine_series WHERE name = '戦国乙女'), '68dc490e-6079-4538-919d-7156151e6d7c'),
    ((SELECT id FROM machine_series WHERE name = '戦国乙女'), 'b95d7d14-c053-4306-b910-3a2e695cd512'),
    ((SELECT id FROM machine_series WHERE name = '戦国乙女'), 'bb41345e-6661-4274-84c7-58b0d8035681'),
    ((SELECT id FROM machine_series WHERE name = '東京喰種'), '11111111-1111-1111-1111-000000000006'),
    ((SELECT id FROM machine_series WHERE name = '東京喰種'), 'b82cd024-1b5f-43cb-b717-b51184135f21'),
    ((SELECT id FROM machine_series WHERE name = '東京喰種'), 'c6514d9a-0dfc-4b7c-93d4-521a82c505c9'),
    ((SELECT id FROM machine_series WHERE name = '機動戦士ガンダム'), 'bd08a897-3292-4be7-8eb3-b6e076c5f029'),
    ((SELECT id FROM machine_series WHERE name = '機動戦士ガンダム'), '703a0726-9703-49da-98d5-972845db0942'),
    ((SELECT id FROM machine_series WHERE name = '沖ドキ'), '11111111-1111-1111-1111-000000000013'),
    ((SELECT id FROM machine_series WHERE name = '沖ドキ'), '905472b8-6aac-42bb-a58c-8d0036f953eb'),
    ((SELECT id FROM machine_series WHERE name = '沖ドキ'), 'f4f45af3-13f6-4638-8f45-18fc5968fa0a'),
    ((SELECT id FROM machine_series WHERE name = '沖ドキ'), '0cc2acb2-d44a-4dfb-947e-a1df44f5f130'),
    ((SELECT id FROM machine_series WHERE name = '沖ドキ'), 'a06e2595-6437-4adf-9ccb-235f4bbe242a'),
    ((SELECT id FROM machine_series WHERE name = '炎炎ノ消防隊'), '11111111-1111-1111-1111-000000000003'),
    ((SELECT id FROM machine_series WHERE name = '炎炎ノ消防隊'), '916d0fc0-7fc9-4226-9cfb-c1eb1580d2d2'),
    ((SELECT id FROM machine_series WHERE name = '炎炎ノ消防隊'), '161fbfe7-c12e-4ccb-89c3-84d3fa06977c'),
    ((SELECT id FROM machine_series WHERE name = '炎炎ノ消防隊'), '8dca107c-3255-4ce9-ba00-2c606f35fada'),
    ((SELECT id FROM machine_series WHERE name = '炎炎ノ消防隊'), 'b80d3db4-6b73-4009-a63f-61ee5c302dd3'),
    ((SELECT id FROM machine_series WHERE name = '牙狼'), '11111111-1111-1111-1111-000000000028'),
    ((SELECT id FROM machine_series WHERE name = '牙狼'), '11111111-1111-1111-1111-000000000029'),
    ((SELECT id FROM machine_series WHERE name = '転スラ'), '11111111-1111-1111-1111-000000000036'),
    ((SELECT id FROM machine_series WHERE name = '鉄拳'), '11111111-1111-1111-1111-000000000022')
ON CONFLICT DO NOTHING;
