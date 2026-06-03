# TODO / 技術的負債

優先度: **最優先** → **高** → **中** → **低**

---

## バグ・不具合

### 最優先

- [ ] **`e` + 全角スペース + 機種名 の抽出漏れ**
  - 例: `ｅ　東京喰種` のように全角スペースが挟まるパターンを `extract_machine()` が拾えない
  - 対応: `extract_machine()` の前処理に `re.sub(r'^[eｅ][　\s]+', lambda m: m.group(0)[0], text)` 相当を追加

- [ ] **`MACHINE_NORMALIZE` の 2 ヶ所管理**
  - `fetch_complete_info.py:update_ranking()` 内と `patch_complete_data.py` に同一定義が重複している
  - 片方を更新するともう一方と乖離しバグの温床になる
  - 対応: `scripts/machine_normalize.py` に切り出して両方からインポートする形にリファクタリング

### 高

- [ ] **`store_machines.json` の陳腐化**
  - `fetch_store_info.py` でスクレイピングして生成するが、自動更新ワークフローが存在しない
  - 対応: `update_machines.yml` ワークフローを確認・有効化（要確認）

- [ ] **`extract_machine()` の正規表現パターン重複**
  - `MACHINE_PATTERNS` に類似パターンが多数あり、最初にマッチしたものが採用される
  - 意図しない誤抽出の原因になりうる
  - 対応: パターンをグループ分けし優先順位を明確化

- [ ] **X セッション自動更新の失敗検出が不十分**
  - `scripts/.x_session.enc` の Cookie が切れても GitHub Actions はエラーにならず収集件数 0 で終了することがある
  - 対応: 収集件数が 0 の場合に Slack/メール通知を追加（または Actions の `if: steps.fetch.outcome == 'success'` で判定）

### 中

- [ ] **`complete_info.json` のエントリに `store_id` が入らない場合がある**
  - `extract_store()` が店舗名を正確に抽出できない場合、`store_id` が空になりランキングのリンクが壊れる
  - 対応: `store_handles.json` との突合精度を上げる

- [ ] **`events_public.json` の重複エントリ**
  - 5 ソース並列収集で同一イベントが複数ソースから取れた場合、重複排除が不完全
  - 対応: `fetch_events.py` の重複排除ロジックを強化

---

## テスト

### 高

- [ ] **自動テストが存在しない**
  - `extract_machine()`, `extract_slot_number()`, `normalize_machine()` 等のコアロジックに対するユニットテストを追加
  - 対応: `scripts/tests/test_extract.py` を作成し、既知の入力→期待出力のペアをテストケースとして網羅

- [ ] **E2E テストが存在しない**
  - フロントエンドのページ（特に `/complete`・`/raiten`）の表示確認は手動のみ
  - 対応: Playwright Test または Cypress を追加

---

## TypeScript / コード品質

### 中

- [ ] **TypeScript の strict モードが無効**
  - `tsconfig.json` で `strict: true` が設定されていない可能性がある（要確認）
  - 有効にすると `null` チェック漏れ等が顕在化する

- [ ] **`any` 型の使用**
  - `app/admin/page.tsx` 等で `any` 型が使われている箇所あり
  - 対応: `lib/supabase.ts` の型定義を活用して置き換え

- [ ] **`app/complete/page.tsx` の `e.machine !== "不明"` フィルタ**
  - 削除すると不正抽出エントリが UI に露出する（CLAUDE.md の禁止事項参照）
  - 中長期的には DB 側でフィルタして JSON に含めないよう改善したい

---

## インフラ・自動化

### 中

- [ ] **GitHub Actions のシークレット管理ドキュメント不足**
  - `DEPLOY.md` に記載はあるが、シークレットのローテーション手順が未整備
  - 対応: `DEPLOY.md` に「シークレット更新手順」セクションを追加

- [ ] **Vercel プレビューデプロイで Supabase が本番 DB を参照している**
  - PR のプレビュー URL が本番 DB を参照するため、テストデータが混入するリスクがある
  - 対応: Supabase の Branch Database 機能を利用してプレビュー用 DB を分離（要確認）

### 低

- [ ] **`README.md` が create-next-app のボイラープレートのまま**
  - 新規参加者が最初に見るファイルとしての役割を果たしていない
  - 対応: プロジェクト概要・開発環境構築手順を記載したものに置き換え

- [ ] **`fetch_store_x_urls.py` の実行頻度が不明**
  - 自動実行ワークフローが見当たらない（要確認）
  - 対応: 定期実行ワークフローの有無を確認し、なければ追加

---

## 機能追加

### 中

- [ ] **機種名の読み方（フリガナ）追加**
  - 現状、機種名は日本語のみで検索・ソートがしにくい
  - `machines.json` に `kana` フィールドを追加

- [ ] **コンプリート情報の店舗ページへの導線**
  - `/stores/[id]` ページに「この店舗のコンプリート実績」を表示するセクションがない

### 低

- [ ] **管理ダッシュボードの認証**
  - `app/admin/page.tsx` は現在認証なし（内部利用前提）
  - 公開 URL でアクセス可能な状態なので、将来的には Basic 認証か Supabase Auth を追加

- [ ] **`post_complete_x.py` のドライランの自動テスト**
  - `--dry-run` の出力内容が正しいかを CI で検証できていない
