# デプロイ・環境構築手順

---

## 前提条件

| ツール | バージョン | 用途 |
|-------|---------|------|
| Node.js | 18 以上 | フロントエンド |
| npm | 9 以上 | パッケージ管理 |
| Python | 3.12 以上 | スクレイピングスクリプト |
| pip | — | Python パッケージ管理 |
| Git | — | バージョン管理 |

アカウント:
- [Supabase](https://supabase.com) — データベース
- [Vercel](https://vercel.com) — ホスティング
- [GitHub](https://github.com) — リポジトリ・Actions
- X (Twitter) — スクレイピング用アカウント（`gretschsick-lgtm` または専用アカウント）

---

## 1. ローカル開発環境のセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/gretschsick-lgtm/mesiuma-site.git
cd mesiuma-site

# Node.js 依存パッケージをインストール
npm install

# Python 依存パッケージをインストール
pip install playwright playwright-stealth cryptography
playwright install chromium --with-deps
```

### 環境変数の設定

プロジェクトルートに `.env.local` を作成:

```bash
# Supabase（必須）
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...   # サーバーサイド専用・絶対に公開しない

# YouTube API（/api/youtube が必要な場合）
YOUTUBE_API_KEY=AIzaSy...               # 要確認: 使用有無
```

> **注意**: `SUPABASE_SERVICE_ROLE_KEY` は絶対にクライアントサイドのコードに渡してはいけない。

### 開発サーバー起動

```bash
npm run dev
# → http://localhost:3000
```

---

## 2. Supabase セットアップ

> **要確認**: 以下の SQL はコードから推定したものです。実際の Supabase ダッシュボードで確認・調整してください。

### テーブル作成 SQL

```sql
-- ① 店舗マスタ
CREATE TABLE stores (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    pref               TEXT,
    area               TEXT,
    address            TEXT,
    hp_url             TEXT,
    x_url              TEXT,
    dmm_id             TEXT,
    pworld_id          TEXT,
    ng_flag            BOOLEAN DEFAULT FALSE,
    meshiuma_score     INTEGER,
    event_count_30d    INTEGER DEFAULT 0,
    complete_count_30d INTEGER DEFAULT 0,
    cast_count_30d     INTEGER DEFAULT 0
);

-- ② キャストマスタ
CREATE TABLE cast_members (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE,
    x_url       TEXT,
    profile_url TEXT,
    ng_flag     BOOLEAN DEFAULT FALSE
);

-- ③ コンプリート報告
CREATE TABLE complete_reports (
    id           TEXT PRIMARY KEY,
    date         DATE NOT NULL,
    report_time  TIMESTAMPTZ,
    store_name   TEXT,
    store_id     TEXT REFERENCES stores(id),  -- 要確認
    machine      TEXT,
    slot_number  TEXT,
    machine_type TEXT CHECK (machine_type IN ('slot', 'pachinko')),
    x_url        TEXT NOT NULL,
    image_url    TEXT,
    text         TEXT,
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

-- ④ イベント
CREATE TABLE events (
    id         TEXT PRIMARY KEY,
    store_id   TEXT REFERENCES stores(id),    -- 要確認
    store_name TEXT NOT NULL,
    pref       TEXT,
    area       TEXT,
    date       DATE NOT NULL,
    event_name TEXT,
    detail     TEXT,
    cast_names TEXT[],
    x_url      TEXT,
    source_url TEXT,
    source     TEXT,
    highlight  BOOLEAN DEFAULT FALSE,
    ng_flag    BOOLEAN DEFAULT FALSE
);

-- ⑤ 収集ログ
CREATE TABLE fetch_logs (
    id              SERIAL PRIMARY KEY,
    job_name        TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    fetched_count   INTEGER DEFAULT 0,
    new_count       INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    error_detail    TEXT
);

-- ⑥ 収集状態
CREATE TABLE fetch_states (
    job_name        TEXT PRIMARY KEY,
    last_success_at TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### インデックス作成

```sql
CREATE INDEX idx_complete_reports_date     ON complete_reports (date DESC);
CREATE INDEX idx_complete_reports_machine  ON complete_reports (machine);
CREATE INDEX idx_complete_reports_store_id ON complete_reports (store_id);
CREATE INDEX idx_events_date  ON events (date DESC);
CREATE INDEX idx_events_pref  ON events (pref);
```

### RLS 設定（要確認）

```sql
-- complete_reports の読み取りを anon に許可（image_url は View で除外）
ALTER TABLE complete_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon read" ON complete_reports FOR SELECT TO anon USING (true);

-- events の読み取りを anon に許可（ng_flag=false のみ）
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon read" ON events FOR SELECT TO anon USING (ng_flag = false);

-- stores の読み取りを anon に許可
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon read" ON stores FOR SELECT TO anon USING (ng_flag = false);
```

---

## 3. Vercel セットアップ

### プロジェクトの作成

1. [Vercel ダッシュボード](https://vercel.com/dashboard) → **New Project**
2. GitHub リポジトリ `gretschsick-lgtm/mesiuma-site` をインポート
3. Framework Preset: **Next.js**（自動検出）
4. **Environment Variables** に以下を設定

| 変数名 | 環境 | 値 |
|--------|-----|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Production, Preview, Development | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Production, Preview, Development | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Production のみ | Supabase service role key |
| `YOUTUBE_API_KEY` | Production | YouTube Data API v3 キー（要確認） |

5. **Deploy** をクリック

---

## 4. GitHub Secrets の設定

リポジトリ Settings → Secrets and variables → Actions に以下を追加:

| シークレット名 | 説明 |
|--------------|------|
| `X_AUTH_TOKEN` | X の `auth_token` Cookie 値 |
| `X_CT0` | X の `ct0` Cookie 値 |
| `X_USERNAME` | X アカウントのユーザー名 |
| `X_PASSWORD` | X アカウントのパスワード |
| `COOKIE_ENCRYPT_KEY` | `.x_session.enc` の Fernet 暗号化キー（32 バイト base64）|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `YOUTUBE_API_KEY` | YouTube Data API v3 キー（要確認） |

> **注意**: `GITHUB_TOKEN` は GitHub が自動的に提供するため、手動設定不要。

### COOKIE_ENCRYPT_KEY の生成方法

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())  # このキーを COOKIE_ENCRYPT_KEY として設定
```

---

## 5. 初回データ投入

### 初期データファイルの確認

以下のファイルがリポジトリに含まれていることを確認:

```
public/
├── complete_info.json      必須（空配列 [] でも可）
├── complete_ranking.json   必須（空オブジェクト {} でも可）
├── events_public.json      必須（空配列 [] でも可）
├── stores.json             必須（店舗マスタ）
├── machines.json           必須（機種マスタ）
├── areas.json              必須（エリアデータ）
├── blog_posts.json         必須（空配列 [] でも可）
├── store_handles.json      必須（空オブジェクト {} でも可）
├── store_x_urls.json       必須（空オブジェクト {} でも可）
└── store_machines.json     必須（空オブジェクト {} でも可）
```

### 手動での初回収集

```bash
# コンプリート情報の初回収集（ローカルから）
python scripts/fetch_complete_info.py --date 2026-06-01

# イベント情報の初回収集（要確認: ローカルで実行可能か）
python scripts/fetch_events.py
```

---

## 6. GitHub Actions の有効化

リポジトリの **Actions** タブでワークフローが有効になっていることを確認。

初回は手動実行でテスト:
- `update_complete.yml` → **Run workflow** → 日付指定で実行
- `update_events.yml` → **Run workflow** で実行

---

## 運用手順

### X セッションの更新

X の Cookie が切れた場合（収集件数が 0 になったら疑う）:

1. `X_AUTH_TOKEN` と `X_CT0` を最新の値に更新（ブラウザの DevTools で取得）
2. GitHub Secrets を更新
3. `update_complete.yml` を手動実行して動作確認

### コンプリートデータの一括修正

```bash
python scripts/patch_complete_data.py
```

機種名正規化・全角台番号修正・ランキング再生成を一括実行。

### ブログ記事の追加・修正

1. `public/blog_posts.json` を編集
2. 以下を実行してから commit:

```bash
python scripts/verify_blog.py --auto-fix --fetch-images
```

### 本番デプロイ

GitHub `main` ブランチへの push で Vercel が自動デプロイ。

手動デプロイは Vercel ダッシュボードから実行。

---

## トラブルシューティング

### `public/*.json` が 404 になる

- ファイルが存在するか確認
- Vercel のデプロイが完了しているか確認

### GitHub Actions の収集件数が 0

1. X の Cookie 切れを疑う → X_AUTH_TOKEN / X_CT0 を更新
2. X 側のレート制限 → 数時間待ってから再実行

### Supabase への書き込みエラー

1. `SUPABASE_SERVICE_ROLE_KEY` が正しいか確認
2. テーブルが存在するか Supabase ダッシュボードで確認
3. RLS ポリシーで書き込みがブロックされていないか確認

### ローカルで `playwright install` が失敗する

```bash
# Linux の場合（GitHub Actions 環境）
playwright install chromium --with-deps

# macOS の場合（ローカル開発）
playwright install chromium
```
