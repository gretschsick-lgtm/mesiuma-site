-- =============================================================================
-- 008_manufacturer_fill.sql
-- machines_master.manufacturer 補完
-- ソース: SUPPLEMENTAL_MACHINES (確認済みエントリ) + machines_master.csv
-- 推測補完なし・exact/normalized 一致のみ・要確認エントリ除外済み
-- =============================================================================

UPDATE machines_master SET manufacturer = '山佐' WHERE id = '716572a7-b35e-447c-bb67-a7d69faea6ed' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'ユニバーサルエンターテインメント' WHERE id = 'a06e2595-6437-4adf-9ccb-235f4bbe242a' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'オリンピア' WHERE id = 'a690ff40-a765-4b27-8654-fb8bb3fab866' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '大都技研' WHERE id = '4cffc2ae-41eb-47b1-91a0-b8c6e19574e0' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '大都技研' WHERE id = 'ca3b52ba-f566-4b93-94a6-dbd6555848e3' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '大都技研' WHERE id = '3a537f37-65a7-45ae-ab78-fd065fa039ce' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'パオン・ディーピー' WHERE id = '50a8867c-f0f0-4e60-9274-06d1435ebf1a' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'タイヨーエレック' WHERE id = 'fcec3359-8161-48a4-b288-0752b8a02297' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '大都技研' WHERE id = '4a8abedb-1c83-4af5-a5ff-0798dce8ab34' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'ユニバーサルエンターテインメント' WHERE id = '92105b27-3261-4af0-b2ed-24f63c5cd477' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'KPE' WHERE id = '703a0726-9703-49da-98d5-972845db0942' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'サミー' WHERE id = 'dbd5361a-dfb5-4d95-a9cb-109bf3f4a3c0' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '平和' WHERE id = 'dfb29be8-a636-4a54-b9e2-107a194a43d1' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'ビスティ' WHERE id = 'c81a452d-0df0-4a0b-ba9a-ed4e406dfab7' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '山佐' WHERE id = 'ca3fe012-b288-4dc3-9535-a16d2ed06f81' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = '藤商事' WHERE id = '380c9bf1-ca03-4b79-8caf-5e4547ca3820' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'エレコ' WHERE id = '595de8f1-8f72-4600-b1cd-a645fa6182eb' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'ビスティ' WHERE id = 'aaa688fc-0489-4c0d-bae6-5538e536a168' AND manufacturer IS NULL;
UPDATE machines_master SET manufacturer = 'エレコ' WHERE id = 'b8ecc10a-87d9-469a-80e5-f803096039ff' AND manufacturer IS NULL;
