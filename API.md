# API 仕様

---

## API Routes (Next.js / Vercel Functions)

### `GET /api/complete`

Supabase の `complete_reports` テーブルからコンプリート情報を取得する。

**クエリパラメータ**:

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|---------|------|
| `date` | `string` | — | `YYYY-MM-DD` 形式の日付でフィルタ |
| `machine` | `string` | — | 機種名（部分一致）でフィルタ（要確認） |
| `limit` | `number` | 100 | 取得件数上限（要確認） |

**レスポンス** (`200 OK`):

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "date": "2026-06-01",
    "report_time": "2026-06-01T18:30:00+09:00",
    "store_name": "ABC パーラー渋谷店",
    "store_id": "store_001",
    "machine": "L革命機ヴァルヴレイヴ2",
    "slot_number": "123",
    "machine_type": "slot",
    "x_url": "https://x.com/store_handle/status/1234567890",
    "collected_at": "2026-06-01T18:35:00Z"
  }
]
```

**注意**: `image_url` は意図的にレスポンスから除外（X 転載禁止ポリシー）。

---

### `GET /api/events`

Supabase の `events` テーブルからイベント情報を取得する。

**クエリパラメータ**:

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|---------|------|
| `date` | `string` | — | `YYYY-MM-DD` 形式の日付でフィルタ |
| `pref` | `string` | — | 都道府県でフィルタ |
| `limit` | `number` | 100 | 取得件数上限（要確認） |

**レスポンス** (`200 OK`):

```json
[
  {
    "id": "evt_001",
    "store_id": "store_001",
    "store_name": "ABC パーラー渋谷店",
    "pref": "東京都",
    "area": "渋谷",
    "date": "2026-06-05",
    "event_name": "来店イベント",
    "detail": "XX ライター来店予定",
    "cast_names": ["ライター田中"],
    "x_url": "https://x.com/store_handle/status/9876543210",
    "source_url": "https://example.com/event/001",
    "source": "イベント収集ソース名",
    "highlight": false,
    "ng_flag": false
  }
]
```

---

### `GET /api/youtube`

YouTube RSS から最新動画を取得する。30 分間キャッシュ。

**クエリパラメータ**: なし（要確認: チャンネル ID 指定の有無）

**レスポンス** (`200 OK`):

```json
{
  "items": [
    {
      "title": "動画タイトル",
      "link": "https://www.youtube.com/watch?v=xxxxx",
      "published": "2026-06-01T12:00:00Z",
      "thumbnail": "https://img.youtube.com/vi/xxxxx/hqdefault.jpg"
    }
  ]
}
```

---

## 静的 JSON ファイル

Vercel CDN から配信される静的ファイル。GitHub Actions で定期更新。

### `public/complete_info.json`

全コンプリート報告（最大 3000 件・直近 30 日分）。

**更新頻度**: 30 分ごと (JST 15:00〜翌2:00) + JST 08:00, 10:00, 13:00

**フィールド**:

```typescript
interface CompleteInfoEntry {
  id: string;            // MD5(x_url)[:12]
  date: string;          // "YYYY-MM-DD"
  report_time?: string;  // ISO8601
  store_name?: string;
  store_id?: string;
  machine: string;       // 正規化済み機種名 or "不明"
  slot_number?: string;  // 台番号（文字列）
  machine_type: string;  // "slot" | "pachinko"
  x_url: string;
  text?: string;         // ツイート本文
  collected_at?: string;
  // image_url は含まない（X 転載禁止ポリシー）
}
```

---

### `public/complete_ranking.json`

月別・総合コンプリートランキング。

**更新頻度**: `complete_info.json` と同タイミング

**フィールド**:

```typescript
interface CompleteRanking {
  updated_at: string;     // ISO8601
  total: {
    machines: Array<{ name: string; count: number }>;
    stores:   Array<{ name: string; count: number; x_url?: string }>;
  };
  monthly: {
    [month: string]: {    // "YYYY-MM"
      machines: Array<{ name: string; count: number }>;
      stores:   Array<{ name: string; count: number; x_url?: string }>;
    };
  };
}
```

---

### `public/complete_YYYY-MM-DD.json`

日付別コンプリート情報（`complete_info.json` と同形式）。

**更新頻度**: 当日分のみ更新

---

### `public/events_public.json`

来店・取材イベント情報（最大 15,000 件）。

**更新頻度**: 毎時（5 並列 Job）

**フィールド**: `events` テーブルと同構造（`ng_flag=false` のみ含む）

---

### `public/blog_posts.json`

ブログ記事一覧（手動管理 + `verify_blog.py` で補完）。

**更新頻度**: 手動更新（push 時に `verify_blog.yml` で自動検証・修正）

**フィールド**:

```typescript
interface BlogPost {
  id: string;
  title: string;
  slug: string;
  published_at: string;  // "YYYY-MM-DD"
  content?: string;
  image?: string;        // アイキャッチ画像 URL
  machine?: string;      // 関連機種名
  setting_images?: string[];  // 設定示唆画像 URL リスト
  tags?: string[];
}
```

---

### `public/stores.json`

全国店舗マスタ。

**フィールド**: `stores` テーブルと同構造

---

### `public/machines.json`

スロット機種マスタ。

**フィールド** (要確認):

```typescript
interface Machine {
  name: string;          // 正式名称（MACHINE_NORMALIZE の正規化後名）
  type: string;          // "slot" | "pachinko"
  maker?: string;        // メーカー名
  // その他のフィールドは要確認
}
```

---

### `public/areas.json`

エリア別店舗リスト（都道府県 × 地域）。

**フィールド** (要確認):

```typescript
interface AreasData {
  [pref: string]: {
    [area: string]: Store[];
  };
}
```

---

### `public/store_handles.json`

店舗名 → X アカウントハンドル マッピング（収集時に自動更新）。

```json
{
  "ABC パーラー渋谷店": "abc_parlor_shibuya",
  ...
}
```

---

### `public/store_x_urls.json`

店舗名 → X 公式アカウント URL マッピング。

```json
{
  "ABC パーラー渋谷店": "https://x.com/abc_parlor_shibuya",
  ...
}
```

---

### `public/store_machines.json`

店舗別機種・貸玉率データ。

**更新頻度**: 手動または `fetch_store_info.py` 実行時（自動ワークフロー要確認）

**フィールド** (要確認):

```typescript
interface StoreMachines {
  [storeId: string]: {
    machines: string[];      // 設置機種リスト
    ball_rate?: number;      // 貸玉率
    updated_at?: string;
  };
}
```

---

## エラーレスポンス

API Routes の共通エラー形式:

```json
{
  "error": "エラーメッセージ"
}
```

| ステータス | 状況 |
|-----------|------|
| `400` | 不正なクエリパラメータ |
| `500` | Supabase 接続エラー・内部エラー |
