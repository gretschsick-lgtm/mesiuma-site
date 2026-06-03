# システムアーキテクチャ

## 概要

mesiuma-site は以下の 3 レイヤーで構成される。

```
[X (Twitter)] ──Playwright──▶ [Python スクリプト] ──▶ [public/*.json]
                                       │                        │
                               [Supabase DB]          [Vercel CDN]
                                                               │
                                                      [Next.js フロント]
                                                               │
                                                        [ブラウザ]
```

---

## 技術スタック

| レイヤー | 技術 | バージョン |
|---------|------|-----------|
| フロントエンド | Next.js (App Router) | 16 |
| UI フレームワーク | React | 19 |
| スタイリング | Tailwind CSS | v4 |
| 言語 | TypeScript | 5.x |
| データベース | Supabase (PostgreSQL) | — |
| ホスティング | Vercel | — |
| スクレイピング | Python + Playwright | 3.12 |
| ブラウザ自動化 | playwright-stealth | — |
| 暗号化 | cryptography (Fernet) | — |
| CI/CD | GitHub Actions | — |

---

## データフロー

### コンプリート情報収集

```
GitHub Actions (cron 30分)
        │
        ▼
fetch_complete_info.py
  1. .x_session.enc を COOKIE_ENCRYPT_KEY で復号
  2. Playwright + stealth で X.com を開く
  3. COMPLETE_QUERIES (40+クエリ) で検索
  4. is_store_tweet() でフィルタ
  5. extract_machine() / extract_slot_number() で解析
  6. MACHINE_NORMALIZE で機種名正規化
  7. get_machine_type() で slot/pachinko 判定
  8. MD5[:12] で重複排除
        │
        ├──▶ public/complete_info.json     (最大3000件・30日分)
        ├──▶ public/complete_YYYY-MM-DD.json (日付別)
        ├──▶ public/complete_ranking.json  (月別ランキング)
        ├──▶ public/store_handles.json     (store名→X handle)
        └──▶ Supabase complete_reports テーブル
```

### イベント情報収集

```
GitHub Actions (cron 毎時・5並列 Job)
        │
        ▼
fetch_events.py
  5つのソースから並列収集
        │
        └──▶ public/events_public.json (最大15,000件)
             └──▶ Supabase events テーブル
```

### フロントエンドのデータ取得

```
ブラウザ
  ├── 静的 JSON (Vercel CDN)
  │     public/complete_info.json    → /complete ページ
  │     public/events_public.json   → /raiten, /torisai
  │     public/blog_posts.json      → /blog
  │     public/stores.json          → /stores
  │
  └── API Routes (Vercel Functions)
        /api/complete → Supabase complete_reports
        /api/events   → Supabase events
        /api/youtube  → YouTube RSS (30分キャッシュ)
```

---

## GitHub Actions スケジュール

| ワークフロー | トリガー | 役割 |
|------------|---------|------|
| `update_complete.yml` | 毎30分 (JST 15:00〜翌2:00) + JST 08:00, 10:00, 13:00 | コンプリート情報収集 |
| `fetch_complete_images.yml` | 収集の15分・45分後 | ツイートから画像URL補完 |
| `update_events.yml` | 毎時・5並列 Job | 来店・取材イベント収集 |
| `post_complete_x.yml` | 毎日 JST 21:00 | 日次集計を X に投稿 |
| `verify_blog.yml` | blog_posts.json push 時 | ブログ記事検証・自動修正 |

**並列実行制御**: `update_complete.yml` は `concurrency: cancel-in-progress: false` により直列化。前の実行が完了するまでキューで待機し、JSON の同時書き換えを防止。

---

## キャッシュ戦略

| データ | キャッシュ場所 | TTL |
|--------|-------------|-----|
| 静的 JSON | Vercel Edge CDN | deploy ごとに更新 |
| YouTube RSS | Vercel Functions メモリ | 30分 |
| Supabase | なし（毎回クエリ） | — |

---

## 設計上の決定事項

### なぜ静的 JSON をメインデータソースにするのか
- Supabase の無料枠には API 呼び出し制限がある
- ページロードごとに DB クエリを発行すると高トラフィック時にコストが急増する
- GitHub Actions で定期生成した JSON を Vercel CDN に乗せることでほぼゼロコストを維持

### なぜ Supabase にも書き込むのか
- 静的 JSON は最大 3000 件・30 日分しか保持しない
- 長期データ分析・管理 UI での高度なクエリに使用
- 将来的な機能拡張（ユーザー認証、リアルタイム通知等）に備えた基盤

### image_url を表示しない理由
- X の転載禁止ポリシーへの対応
- DB には保存するが SELECT・表示を意図的に除外している

### MACHINE_NORMALIZE が 2 ヶ所に存在する理由
- `fetch_complete_info.py` の `update_ranking()` 内に定義（スクレイピング → ランキング生成の流れで使用）
- `patch_complete_data.py` にも定義（既存 JSON の一括修正に使用）
- 両方を常に同期させること（CLAUDE.md の禁止事項を参照）

---

## セキュリティ境界

| コード | アクセスレベル |
|--------|-------------|
| `lib/supabase.ts` の `getBrowserClient()` | anon key・RLS 適用・公開データのみ |
| `lib/supabase.ts` の `createAdminClient()` | service role key・サーバーサイド専用 |
| `scripts/*.py` | service role key・GitHub Secrets から取得 |
| `scripts/.x_session.enc` | Fernet 暗号化・`COOKIE_ENCRYPT_KEY` で復号 |
