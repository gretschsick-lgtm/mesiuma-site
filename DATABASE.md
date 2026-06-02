# データベース設計

Supabase (PostgreSQL) の確定済みテーブル定義。
`supabase/migrations/` の各 SQL が正本。`lib/supabase.ts` の型定義と同期済み。

---

## テーブル一覧

| テーブル名 | 概要 | 追加 Migration |
|-----------|------|--------------|
| `complete_reports` | コンプリート達成報告 | `001` |
| `events` | 来店・取材イベント | `004` |
| `stores` | 全国店舗マスタ | `011` |
| `store_machines` | 店舗×機種 設置情報 | `012` |
| `cast_members` | キャスト情報 | `003` |
| `agencies` | 所属事務所 | `002` |
| `machines_master` | 機種マスタ（375件） | `001`,`005`,`006` |
| `machines_aliases` | 機種エイリアス（43件） | `001` |
| `machine_series` | 機種シリーズ（分析用）| `007` |
| `machine_series_members` | シリーズ×機種対応 | `007` |
| `unknown_machines` | 未解決機種ログ | `001` |
| `unknown_performers` | 未解決演者ログ | `009` |
| `store_aliases` | 店舗名エイリアス（表記揺れ・略称） | `014` |
| `unknown_stores` | 未解決店舗ログ | `013` |
| `fetch_logs` | 収集ジョブ実行ログ | — |
| `fetch_state` | 収集ジョブ最終状態 | — |

---

## `complete_reports`

X (Twitter) からスクレイピングされたコンプリート達成報告。

```sql
CREATE TABLE complete_reports (
    id           TEXT        PRIMARY KEY,       -- MD5(x_url)[:12]
    date         DATE,
    report_time  TIMESTAMPTZ,
    store_name   TEXT,
    store_id     TEXT        REFERENCES stores(id),
    machine      TEXT,                          -- 機種名（正規化後）
    machine_id   UUID        REFERENCES machines_master(id),  -- 解決済みのみ設定
    slot_number  TEXT,
    x_url        TEXT        NOT NULL,
    image_url    TEXT,                          -- SELECT・表示禁止（X転載禁止）
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**注意事項**:
- `image_url` は DB に存在するが、全 SELECT から意図的に除外している
- `machine_id` は `machine_resolver.py` が解決済みの場合のみ設定（85% 未満は NULL）

---

## `events`

来店・取材イベント情報（5 ソースから収集）。

```sql
CREATE TABLE events (
    id           TEXT        PRIMARY KEY,
    store_id     TEXT        REFERENCES stores(id),
    store_name   TEXT,
    pref         TEXT,
    area         TEXT,
    date         DATE,
    event_name   TEXT,
    detail       TEXT,
    cast_names   TEXT[],                        -- 後方互換維持・削除禁止
    performer_id INTEGER     REFERENCES cast_members(id),  -- Step3追加
    x_url        TEXT,
    source_url   TEXT,
    source       TEXT,
    highlight    BOOLEAN     NOT NULL DEFAULT FALSE,
    ng_flag      BOOLEAN     NOT NULL DEFAULT FALSE,
    image_url    TEXT,                          -- SELECT・表示禁止
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**インデックス**:
```sql
CREATE INDEX idx_events_performer_id       ON events (performer_id);
CREATE INDEX idx_events_date               ON events (date DESC);
CREATE INDEX idx_events_performer_id_date  ON events (performer_id, date DESC);
```

---

## `stores`

全国のパチスロ・パチンコ店舗マスタ。

```sql
CREATE TABLE stores (
    id                  TEXT        PRIMARY KEY,   -- 10桁16進 (SHA256[:10])
    name                TEXT        NOT NULL,
    pref                TEXT,
    area                TEXT,
    address             TEXT,
    hp_url              TEXT,
    x_url               TEXT,
    dmm_id              TEXT,
    pworld_id           TEXT,
    ng_flag             BOOLEAN     NOT NULL DEFAULT FALSE,
    ng_reason           TEXT,
    meshiuma_score      INTEGER     NOT NULL DEFAULT 0,
    event_count_30d     INTEGER     NOT NULL DEFAULT 0,
    complete_count_30d  INTEGER     NOT NULL DEFAULT 0,
    cast_count_30d      INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Step7 追加 (011_stores_extend.sql)
    normalized_name     TEXT,                      -- 重複判定用正規化名
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,  -- 閉店: FALSE
    parent_store_id     TEXT        REFERENCES stores(id),  -- 移転元店舗 ID
    source_url          TEXT,
    address_history     JSONB       NOT NULL DEFAULT '[]'   -- [{address, changed_at}]
);
```

**閉店・移転ルール**:
- 閉店: `is_active=false`（削除禁止）
- 移転: 新店舗に `parent_store_id=旧店舗ID` を設定
- 住所変更: `address_history` JSONB に `{address, changed_at}` を追記

---

## `store_machines`

店舗に設置されている機種（機種名文字列は保存しない）。

```sql
CREATE TABLE store_machines (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     TEXT        NOT NULL REFERENCES stores(id)          ON DELETE CASCADE,
    machine_id   UUID        NOT NULL REFERENCES machines_master(id) ON DELETE RESTRICT,
    rate         TEXT,        -- 貸玉率 例: '4円', '1円'
    count        INTEGER,     -- 設置台数
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, machine_id)
);
```

**制約**:
- `machine_id` は `machines_master.id` FK 必須（機種名文字列保存禁止）
- 撤去: `is_active=false`（削除禁止）

---

## `cast_members`

キャスト（ライター・イベント出演者）情報。

```sql
CREATE TABLE cast_members (
    -- 既存カラム
    id               SERIAL      PRIMARY KEY,
    name             TEXT        NOT NULL,
    slug             TEXT        UNIQUE,
    x_url            TEXT,
    profile_url      TEXT,
    ng_flag          BOOLEAN     NOT NULL DEFAULT FALSE,
    ng_reason        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Step2 拡張 (003_cast_members_extend.sql)
    agency_id        UUID        REFERENCES agencies(id),
    display_name     TEXT,
    normalized_name  TEXT,                  -- 重複判定用
    birthday         DATE,
    description      TEXT,
    profile_image_url TEXT,
    instagram_url    TEXT,
    youtube_url      TEXT,
    area             TEXT,
    gender           TEXT        CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    is_active        BOOLEAN     DEFAULT TRUE,
    source           TEXT        DEFAULT 'manual'
                                 CHECK (source IN ('manual', 'auto', 'freelance')),
    first_detected_at TIMESTAMPTZ
);
```

**重複判定**: `normalized_name` で exact match のみ（fuzzy 不使用）  
**削除禁止**: `is_active=false` で運用  
**フリー演者**: `agency_id=NULL`, `source='freelance'`

---

## `agencies`

キャストの所属事務所。

```sql
CREATE TABLE agencies (
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
```

---

## `machines_master`

パチスロ・パチンコ機種マスタ（375件・2026-06時点）。

```sql
CREATE TABLE machines_master (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    official_name   TEXT    NOT NULL UNIQUE,
    manufacturer    TEXT,               -- NULL = メーカー未確認
    brand           TEXT,
    type            TEXT    NOT NULL DEFAULT 'slot'
                            CHECK (type IN ('slot', 'pachinko')),
    normalized_name TEXT    NOT NULL,   -- normalize_for_comparison() 結果
    release_date    DATE,
    source_url      TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (official_name)
);
```

**正規化関数**: `scripts/machine_resolver.py` の `normalize_for_comparison()` と
`lib/machines.ts` の `normalizeMachineName()` が同一ロジック。  
**メーカー NULL**: 375件中248件が NULL（DMM sources は maker フィールドが空）。  
**追加禁止**: AI 推測のみで機種名を確定しない。ソースデータに存在するもののみ登録。

---

## `machines_aliases`

機種名の別表記・略称（43件）。

```sql
CREATE TABLE machines_aliases (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id      UUID    NOT NULL REFERENCES machines_master(id) ON DELETE CASCADE,
    alias_name      TEXT    NOT NULL,
    normalized_alias TEXT   NOT NULL,
    confidence      REAL    NOT NULL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## `machine_series`

機種シリーズグループ（分析用途のみ）。

```sql
CREATE TABLE machine_series (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT    NOT NULL UNIQUE,   -- シリーズ名
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**重要制約**: シリーズ名から `machine_id` を自動決定する機能を実装しない。  
`machine_resolver.py` のロジックに影響を与えない。

---

## `machine_series_members`

シリーズ×機種の多対多テーブル（確認済み machine_id のみ登録）。

```sql
CREATE TABLE machine_series_members (
    series_id   UUID NOT NULL REFERENCES machine_series(id)  ON DELETE CASCADE,
    machine_id  UUID NOT NULL REFERENCES machines_master(id) ON DELETE CASCADE,
    PRIMARY KEY (series_id, machine_id)
);
```

現状: 29 シリーズ × 84 機種。

---

## `unknown_machines`

未解決機種ログ。`machine_resolver.py` が類似度 85% 未満で解決できなかった機種。

```sql
CREATE TABLE unknown_machines (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name            TEXT        NOT NULL,
    normalized_raw_name TEXT,
    source_site         TEXT,
    source_url          TEXT,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count               INTEGER     NOT NULL DEFAULT 1,
    status              TEXT        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','approved','rejected','ignored'))
);
```

---

## `unknown_performers`

未解決演者ログ。`register_cast.py` が `source_url`/`profile_url` なしで登録できなかった演者。

```sql
CREATE TABLE unknown_performers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name        TEXT        NOT NULL,
    normalized_name TEXT,
    source_site     TEXT,
    source_url      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count           INTEGER     NOT NULL DEFAULT 1,
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','approved','rejected','ignored'))
);
```

---

## `unknown_stores`

未解決店舗ログ。`register_stores.py` が解決できなかった店舗名。

```sql
CREATE TABLE unknown_stores (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_name        TEXT        NOT NULL,
    normalized_name TEXT,
    source_site     TEXT,
    source_url      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count           INTEGER     NOT NULL DEFAULT 1,
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','approved','rejected','ignored'))
);
```

---

## `store_aliases`

店舗名のエイリアス（表記揺れ・略称・チェーン別名）。`store_resolver.py` が参照。

```sql
CREATE TABLE store_aliases (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id         TEXT        NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    alias            TEXT        NOT NULL,
    normalized_alias TEXT        NOT NULL,  -- normalize_store_name() 適用済み
    confidence       FLOAT       NOT NULL DEFAULT 1.0,
    source           TEXT        NOT NULL DEFAULT 'manual'
                                 CHECK (source IN ('manual', 'auto')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (normalized_alias)
);
```

**用途例**:
- `マルハン東宝` / `マルハン新宿東宝` / `マルハン東宝店` → 同一 `store_id`
- normalize_store_name() 後に exact match で検索するため末尾の「店」は除去済みで登録

---

## `fetch_logs`

GitHub Actions の各収集ジョブの実行ログ。

```sql
CREATE TABLE fetch_logs (
    id              SERIAL      PRIMARY KEY,
    job_name        TEXT        NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    status          TEXT        CHECK (status IN ('success', 'partial', 'failed')),
    fetched_count   INTEGER     NOT NULL DEFAULT 0,
    new_count       INTEGER     NOT NULL DEFAULT 0,
    duplicate_count INTEGER     NOT NULL DEFAULT 0,
    error_count     INTEGER     NOT NULL DEFAULT 0,
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## `fetch_state`

各収集ジョブの最終実行状態（最新 1 件のみ保持）。

```sql
CREATE TABLE fetch_state (
    job_name        TEXT        PRIMARY KEY,
    last_success_at TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## RLS ポリシー一覧

| テーブル | anon SELECT | service_role |
|---------|------------|--------------|
| `complete_reports` | ✅ (image_url 除外) | ✅ |
| `events` | ✅ (ng_flag=false) | ✅ |
| `stores` | ✅ | ✅ |
| `store_machines` | ✅ (is_active=true) | ✅ |
| `cast_members` | ✅ (ng_flag=false) | ✅ |
| `agencies` | ✅ (is_active=true) | ✅ |
| `machines_master` | ✅ | ✅ |
| `machines_aliases` | ✅ | ✅ |
| `machine_series` | ✅ | ✅ |
| `machine_series_members` | ✅ | ✅ |
| `unknown_machines` | ❌ | ✅ |
| `unknown_performers` | ❌ | ✅ |
| `unknown_stores` | ❌ | ✅ |
| `fetch_logs` | ✅ (anon SELECT) | ✅ |

---

## Migration 履歴

| ファイル | 内容 |
|--------|------|
| `001_machines_master.sql` | `machines_master` / `machines_aliases` / `unknown_machines` 作成・`complete_reports.machine_id` 追加 |
| `002_agencies.sql` | `agencies` 作成・RLS・`updated_at` トリガー |
| `003_cast_members_extend.sql` | `cast_members` に 13 カラム追加 |
| `004_events_performer_id.sql` | `events.performer_id` 追加・インデックス 3本 |
| `005_machines_expand.sql` | `machines_master` に 286 機種追加（ソース確認済み）|
| `006_machines_expand2.sql` | `machines_master` に 90 機種追加（supplemental・ソース確認済み）|
| `007_machine_series.sql` | `machine_series` / `machine_series_members` 作成・29シリーズ 84機種登録 |
| `008_manufacturer_fill.sql` | `machines_master.manufacturer` 補完（19件）|
| `009_unknown_performers.sql` | `unknown_performers` 作成 |
| `010_cast_source_freelance.sql` | `cast_members.source` CHECK に `'freelance'` 追加 |
| `011_stores_extend.sql` | `stores` に 5 カラム追加（normalized_name / is_active / parent_store_id / source_url / address_history）|
| `012_store_machines_table.sql` | `store_machines` 作成・RLS・トリガー |
| `013_unknown_stores.sql` | `unknown_stores` 作成 |

---

## 正規化関数の所在

| 対象 | ファイル | 関数名 |
|-----|---------|--------|
| 機種名 | `scripts/machine_resolver.py` | `normalize_for_comparison()` |
| 機種名 (TS) | `lib/machines.ts` | `normalizeMachineName()` |
| 演者名 | `scripts/register_cast.py` | `normalize_name()` |
| 店舗名 | `scripts/register_stores.py` | `normalize_store_name()` |

**混在禁止**: 各正規化関数は対象ドメイン専用。機種名正規化を演者名や店舗名に流用しない。

---

## unknown テーブルの status フロー

```
pending → approved  : 人手確認後、対応テーブルに昇格
pending → rejected  : 誤登録・ノイズ
pending → ignored   : 対応不要（再登録しない）
```

`rejected` / `ignored` に設定された raw_name は以降スキップされる。
