@AGENTS.md

## プロジェクト概要

**mesiuma-site** — パチスロ・パチンコの来店イベント・コンプリート実績を
X (Twitter) / Web から自動収集して配信する情報サイト。

| 項目 | 値 |
|------|-----|
| リポジトリ | `gretschsick-lgtm/mesiuma-site` |
| 本番 URL | https://mesiuma-site.vercel.app |
| フロント | Next.js 16 / React 19 / Tailwind v4 / TypeScript |
| バックエンド | Supabase (PostgreSQL) / Vercel |
| 収集基盤 | Python 3.12 + Playwright / GitHub Actions |

---

## よく使うコマンド

### フロントエンド

```bash
npm run dev          # 開発サーバー起動 → http://localhost:3000
npm run build        # 本番ビルド（Vercel と同一環境）
npm run lint         # ESLint チェック
```

### データ収集スクリプト（`scripts/` ）

```bash
# コンプリート情報収集（当日分）
python scripts/fetch_complete_info.py --date 2026-06-01

# コンプリート情報収集（GitHub Actions 用・ヘッドレス）
python scripts/fetch_complete_info.py --headless --date 2026-06-01

# 機種名・台番号の一括修正パッチ
python scripts/patch_complete_data.py

# ランキングのみ再生成（Python REPL）
python -c "import sys; sys.path.insert(0,'scripts'); from fetch_complete_info import update_ranking; update_ranking()"

# ブログ記事検証・自動修正・画像補完
python scripts/verify_blog.py --auto-fix --fetch-images

# X 投稿（当日集計）
python scripts/post_complete_x.py --date 2026-06-01
python scripts/post_complete_x.py --dry-run   # 投稿せず内容確認のみ
python scripts/post_complete_x.py --force     # 投稿済み日でも強制再投稿
```

---

## 機種名ルール

| ルール | 理由 |
|--------|------|
| AI 推測のみで機種名を確定しない | 誤った機種名がランキング・DB に永続する |
| DB 保存前に必ず `machine_resolver.py` の `resolve()` を通す | `supabase_write_complete()` 内で実施済み |
| `machines_master` の `official_name` を正式名称とする | `MACHINE_NORMALIZE` より優先 |
| 85% 未満の類似度は `unknown_machines` に保存し人手確認 | 誤統合防止 |
| P-WORLD へのリアルタイム問い合わせ禁止 | スクレイピング負荷・利用規約上の問題 |
| ジャグラー各機種は個別 `machines_master` 行として管理 | アイム・マイ・ファンキー等は別機種・誤統合禁止 |
| 機種マスタのライブ正本は **Supabase DB**（`machines_master` / `machines_aliases`）| resolver・collector は Supabase を SELECT する。CSV は正本ではない |
| 新機種追加・統合は **Supabase DB を直接更新**（対象 ID・件数検証・snapshot・回帰確認付き）| DB がライブ正本のため |
| `public/machines_master.csv` / `machines_aliases.csv` は **初期 bootstrap seed（legacy・現行 DB 全件を表さない）** | 過去 seed。現行 DB と乖離（例: master CSV 36 件 / DB 377 件）。**本番 DB へ再 import 禁止**・自動同期対象外 |

### 機種カタログの Source of Truth（重要）

- **唯一のライブ正本 = Supabase DB**（`machines_master` / `machines_aliases`）。resolver（`machine_resolver.py`）と collector は DB を SELECT する。
- `public/machines_master.csv` / `public/machines_aliases.csv` は**初期構築時の legacy seed**。現在の DB とは大きく乖離しており（過去 seed）、**本番 DB へ再 import してはいけない**。schedule workflow は CSV を import しない。
- `scripts/generate_machines_migration.py` / `scripts/generate_supplemental_machines.py` は legacy CSV を消費する**手動ツール**。stale seed からの誤 import を防ぐため `--allow-legacy-seed` 明示フラグ必須（フラグなしは停止）。生成 SQL を本番へ自動適用しない。
- DB からの読み取り専用バックアップは `scripts/export_machines_catalog.py`（SELECT のみ・出力先は明示指定・legacy CSV を自動上書きしない）。**export は backup であり Source of Truth ではない**。

### 店舗の Source of Truth と store_id（重要）

- **complete データの canonical store_id 空間 = Supabase `stores` テーブル**（`id = sha256(店舗名)[:10]`）。
  `complete_reports.store_id` / JSON complete の `store_id` はすべてこの空間。
- `public/stores.json`（約6400件）は **別 id 方式のフロント表示用マスタ**であり、`stores` テーブルとは
  **id 空間が非重複**（同一実店舗でも id が異なる）。**stores.json の id を canonical store_id として扱わない。**
- 店舗名の正規化は `register_stores.py` の `normalize_store_name()`（NFKC+小文字+空白除去）を用いる。機種・演者の正規化と混在禁止。
- `store_handles.json` は「店舗名→X ハンドル」マップ（自動更新・マージ方式）。照合メタ（`store_id` /
  `verification_status` / `evidence_type` / `evidence_url` / `verified_at` / `is_active` / `rejection_reason` /
  `canonical_handle`）は **後方互換の任意フィールド**として付与。`scripts/resolve_store_handles.py` が
  DB `stores` を SELECT のみで参照し分類する（DB へは書き込まない）。collector の store_handles 自動更新は
  既存フィールドを保持するため、次回実行でメタは巻き戻らない。
- **公式 X の verified 判定は DB 公式 x_url 一致（canonical_x_url / Tier A）のみ**。X 表示名・名前一致だけでは
  verified にしない（candidate 保留）。manager 型は店舗公式 X の KPI から除外（従来用途で保持）。

### 正規化関数の所在と対象ドメイン

| ファイル | 関数名 | 用途 | 混在禁止 |
|---------|--------|------|---------|
| `scripts/machine_resolver.py` | `normalize_for_comparison()` | 機種名（Python / DB 保存）| ◀ 機種専用 |
| `lib/machines.ts` | `normalizeMachineName()` | 機種名（Next.js / フロントエンド）| ◀ 機種専用 |
| `scripts/register_cast.py` | `normalize_name()` | 演者名 | ◀ 演者専用 |
| `scripts/register_stores.py` | `normalize_store_name()` | 店舗名 | ◀ 店舗専用 |

**各正規化関数はドメイン専用。機種名正規化を演者名・店舗名に流用しない。**

---

## 重要な制約（やってはいけないこと）

| 禁止事項 | 理由 |
|---------|------|
| `public/*.json` を手動で大量削除 | フロントが静的 JSON を直接参照。削除するとサイト全体が壊れる |
| `image_url` をフロントに表示 | X 転載禁止ポリシー対応。DB に存在するが SELECT・表示を意図的に除外済み |
| `SUPABASE_SERVICE_ROLE_KEY` を client-side コードに渡す | セキュリティ上厳禁。`lib/supabase.ts` の `createAdminClient()` はサーバーサイド専用 |
| `scripts/.x_session.enc` を平文で保存・出力 | 暗号化済みの X セッション。`COOKIE_ENCRYPT_KEY` で復号する |
| `app/complete/page.tsx` の `e.machine !== "不明"` フィルタを削除 | 不正抽出エントリが露出する |
| `MACHINE_NORMALIZE` を片方だけ更新 | `fetch_complete_info.py` と `patch_complete_data.py` の **2ヶ所** に定義。必ず両方を同期更新 |
| GH Actions の `--no-verify` オプション | フックを迂回しない |
| `cast_members` / `stores` を DELETE で削除 | 削除禁止。`is_active=false` で運用。`register_cast.py` / `register_stores.py` はこれを遵守 |
| `store_machines` に機種名文字列を保存 | `machine_id` FK 必須。`register_stores.py` が `machines_master` で解決できない機種は `unknown_machines` に記録 |
| `machine_series` シリーズ名から `machine_id` を自動決定 | 分析用途のみ。`machine_resolver.py` のロジックに影響を与えない |
| 演者・店舗の正規化関数を機種名に流用 | 各正規化はドメイン専用。`normalize_for_comparison` は機種名専用 |

---

## ファイル役割早見表

```
app/                          Next.js ページ・API Routes
├── page.tsx + home-client.tsx   ホームページ（イベント・コンプリート・YouTube）
├── complete/page.tsx            コンプリート実績・ランキング
├── blog/                        ブログ一覧・詳細
├── cast/                        キャスト一覧・来店スケジュール
├── stores/                      店舗一覧・詳細
├── raiten/page.tsx              来店イベント一覧
├── torisai/                     取材イベント情報
├── meshimazu/                   メシマズ認定店舗一覧
├── admin/page.tsx               管理ダッシュボード（認証なし・内部用）
└── api/
    ├── complete/route.ts        GET /api/complete → Supabase
    ├── events/route.ts          GET /api/events   → Supabase
    └── youtube/route.ts         GET /api/youtube  → YouTube RSS（30分キャッシュ）

lib/
└── supabase.ts                  Supabase クライアント・型定義・クエリヘルパー

public/                          静的ファイル（Vercel CDN 配信）
├── complete_info.json           全コンプリート報告（自動生成・30日分・最大3000件）
├── complete_ranking.json        月別・総合ランキング（自動生成）
├── complete_YYYY-MM-DD.json     日付別コンプリート（自動生成）
├── events_public.json           来店・取材イベント（最大15,000件・自動生成）
├── blog_posts.json              ブログ記事（手動管理 + verify_blog.py で補完）
├── stores.json                  全国店舗マスタ
├── machines.json                スロット機種マスタ
├── areas.json                   エリア別店舗リスト（都道府県×地域）
├── store_handles.json           店舗名 → X ハンドル マッピング（自動更新）
├── store_x_urls.json            店舗名 → X 公式 URL マッピング
└── store_machines.json          店舗別機種・貸玉率データ

scripts/
├── fetch_complete_info.py       X からコンプリート情報収集（メイン・2055行）
├── fetch_events.py              来店・取材イベント収集（5ソース並列・1994行）
├── patch_complete_data.py       機種名正規化・データ一括修正ユーティリティ
├── verify_blog.py               ブログ記事検証・自動修正・画像補完
├── post_complete_x.py           日次集計を X に投稿
├── fetch_complete_images.py     ツイートページから画像/動画 URL 補完
├── fetch_store_x_urls.py        店舗公式 X アカウント検索
├── fetch_store_info.py          店舗 HP から住所・台数スクレイプ
├── machine_resolver.py          機種名解決・正規化（normalize_for_comparison）
├── register_cast.py             演者マスタ自動登録（agencies / cast_members）
├── register_stores.py           店舗マスタ自動登録（stores / store_machines）
└── .x_session.enc               暗号化 X セッション（要 COOKIE_ENCRYPT_KEY）

.github/workflows/
├── update_complete.yml          コンプリート収集（30分ごと・JST 15:00〜翌2:00 + 夜間補完3本 + 朝3回）
├── update_events.yml            イベント収集（毎時・5並列 Job）
├── fetch_complete_images.yml    コンプリート画像 URL 補完（上記の15/45分後）
├── post_complete_x.yml          X 投稿（毎日 21:00 JST）
├── verify_blog.yml              ブログ検証（blog_posts.json 変更時に自動起動）
└── verify_complete.yml          パイプライン検証（毎朝 JST 08:00・Actions Summary 出力）
```

---

## データ更新タイミング

| データ | 更新頻度 | 担当 workflow |
|--------|---------|--------------|
| `complete_info.json` / ランキング | 30分ごと（JST 15:00〜翌2:00）+ 夜間補完3本 + 朝3回 | `update_complete.yml` |
| コンプリート画像 URL | 上記の15分・45分後 | `fetch_complete_images.yml` |
| `events_public.json` | 毎時（5並列 Job） | `update_events.yml` |
| X 投稿 | 毎日 21:00 JST | `post_complete_x.yml` |
| `blog_posts.json` 検証 | `blog_posts.json` push 時 | `verify_blog.yml` |
| パイプライン検証 | 毎朝 JST 08:00 | `verify_complete.yml` |

### update_complete.yml cron 一覧

| cron | UTC | JST | 目的 |
|------|-----|-----|------|
| `*/30 6-17 * * *` | 06:00〜17:30 毎30分 | 15:00〜翌02:30 | メイン収集 |
| `0 18 * * *` | 18:00 | 翌03:00 | 夜間補完①（メイン終了直後） |
| `0 20 * * *` | 20:00 | 翌05:00 | 夜間補完② |
| `0 22 * * *` | 22:00 | 翌07:00 | 夜間補完③（verify 直前） |
| `0 23 * * *` | 23:00 | 翌08:00 | 朝の追加ラン① |
| `0 1 * * *`  | 01:00 | 10:00 | 朝の追加ラン② |
| `0 4 * * *`  | 04:00 | 13:00 | 朝の追加ラン③ |

---

## コンプリート情報の確認・異常対応

### 反映確認コマンド（手動）

```bash
# 前日データを確認（JST 基準）
python scripts/verify_complete_pipeline.py

# 特定日を指定
python scripts/verify_complete_pipeline.py --date 2026-06-01

# 成功 → exit 0 / 異常 → exit 1 + 内容を stdout に出力
```

### verify_complete.yml の見方

毎朝 JST 08:00 に自動実行。
GitHub → Actions → `Verify Complete Pipeline` → 最新 run の **Summary** タブに判定結果が表示される。

- **✅ OK** — 前日データが正常に収集・反映されている
- **❌ NG** — Summary に異常内容と修正候補が記載される

### 異常時の対応

| 異常 | 原因候補 | 対応 |
|------|---------|------|
| 対象日 0件 | GH Actions 停止 / X セッション切れ | `update_complete.yml` を手動実行 |
| 前日比 70%以上減少 | X API 制限 / 収集クエリ変更 | `fetch_logs` テーブルで error_detail を確認 |
| GH Actions 停止疑い | GitHub スケジューラー障害 | Actions タブで `workflow_dispatch` |
| JSON 未更新（サイレント失敗） | X スクレイピング失敗（ログイン切れ等） | `fetch_logs` の最新エラーを確認 |

### 手動再実行コマンド

```bash
# 特定日のコンプリート情報を再収集
gh workflow run update_complete.yml -f date=2026-06-01

# 検証のみ手動実行
gh workflow run verify_complete.yml -f date=2026-06-01
```

### 必要な GitHub Actions Secrets

| Secret | 用途 |
|--------|------|
| `GITHUB_TOKEN` | 自動提供。verify スクリプトの GitHub API 呼び出しに使用 |
| `X_AUTH_TOKEN` / `X_CT0` | X (Twitter) 認証 Cookie |
| `X_USERNAME` / `X_PASSWORD` | X 再ログイン用認証情報 |
| `COOKIE_ENCRYPT_KEY` | `.x_session.enc` の暗号化キー |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase 接続 URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role キー |

Telegram 関連の Secret は不要。

---

## 開発上の注意点

- **Next.js バージョン**: v16 (App Router)。学習データの Next.js と異なる API が存在する。コードを書く前に `node_modules/next/dist/docs/` を確認すること（→ AGENTS.md 参照）
- **Tailwind v4**: `@apply` や設定ファイルの記法が v3 と異なる。`globals.css` の既存記法に合わせること
- **Supabase クライアント使い分け**:
  - ブラウザ: `getBrowserClient()` (anon key、RLS 適用)
  - サーバー / スクリプト: `createAdminClient()` (service role key、RLS バイパス)
- **Python スクリプトの依存**: `playwright`, `playwright-stealth`, `cryptography` が必要。`pip install playwright playwright-stealth cryptography && playwright install chromium --with-deps`

---

## ドキュメント参照先

| 内容 | ドキュメント |
|------|------------|
| システム全体構成・データフロー図 | `ARCHITECTURE.md` |
| Supabase スキーマ・テーブル定義 | `DATABASE.md` |
| X スクレイピング・機種名抽出ルール | `SCRAPING_RULES.md` |
| API エンドポイント仕様・レスポンス型 | `API.md` |
| デプロイ・初回環境構築手順 | `DEPLOY.md` |
| 技術的負債・既知バグ・予定機能 | `TODO.md` |
| ブログ記事追加・機種マスタ更新 | `AGENTS.md` |
