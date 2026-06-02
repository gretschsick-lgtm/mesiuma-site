-- store_aliases 初期データ（表記揺れ対応）
-- 前提: 014_store_aliases.sql マイグレーション実行済みであること
-- 生成: 2026-06-02 patch_complete_data 未解決エントリ分析より

INSERT INTO store_aliases (store_id, alias, normalized_alias, confidence, source) VALUES
  ('cbc9c2710d', 'キャッスル春日井',             'キャッスル春日井',              1.0, 'manual'),
  ('771f030669', '栄若宮大通店',                  '栄若宮大通',                    1.0, 'manual'),
  ('ac9e0c0f5d', 'メガフェイス菊陽',              'メガフェイス菊陽',               1.0, 'manual'),
  ('036ad33f3f', 'メガフェイス1120豊崎本館',       'メガフェイス1120豊崎本',         1.0, 'manual'),
  ('ef707cf8fe', '楽園池袋',                      '楽園池袋',                      1.0, 'manual'),
  ('30980119a2', 'スーパーD''ステーション３９女神店', 'スーパーd''ステーション39女神', 1.0, 'manual')
ON CONFLICT (normalized_alias) DO NOTHING;
