# PROJECT STATUS

更新日時: 2026-06-04

---

## 完了した作業

### 機種名抽出バグ修正 (scripts/fetch_complete_info.py)
- **MACHINE_PATTERNS の `の|` バグ修正**: Pattern 4/6/7 の lookahead に `の|` が入っていたため、`スマスロ北斗の拳転生の章2` → `北斗の拳転生` と途中で切れていた → 除去済み
- **スマパチ prefix 除去**: Pattern 4 の対象から `スマパチ` を削除。`スマパチ 機種名` → `e機種名` へ変換する前処理を追加
- **カバネリ スペース区切り対応**: `甲鉄城のカバネリ 海門決戦` → `甲鉄城のカバネリ海門決戦` に前処理で結合
- **モンキーターン専用パターン追加**: `([LＬ]?モンキーターン[^\s...]{0,5})`
- **カバネリ フルネームパターン追加**: `甲鉄城のカバネリ海門決戦` の先行マッチ
- **e機種名+バージョン番号パターン追加**: `eカケグルイ219ver` 系の誤抽出防止

### MACHINE_NORMALIZE 追加 (update_ranking 内)
- `LモンキーターンV`, `Lモンキーターン`, `モンキーターンV` の正規化ルール追加

### データ修正
- `eカケグルイ219ver` → `eカケグルイ`, `machine_type: pachinko` (2件: complete_info.json + daily)
- `「モンスターハンターライズ」` → `スマスロ モンスターハンターライズ` (2件: complete_info.json + 5/26 daily)
- machines_master: `「モンスターハンターライズ」` (id=1eab6b8d) → `is_active=false` で無効化

### 全件監査 (complete_info.json 532件 + complete_ranking.json)
- 誤分類 0件
- official_name 不一致 0件
- 機種名短縮 0件

### ゴミデータ除去監査

| 対象 | ゴミ件数 | 修正件数 | 削除件数 | 残件数 |
|------|---------|---------|---------|------|
| Supabase | 59件(前回)+5件(今回) | 0 | 64件 | ※後述 |
| complete_info.json | 1件 | 1件 | 0件 | 532件 |
| daily JSON | 6件 | 2件 | 5件 | - |

今回削除 (Supabase):
- machine=NULL: 3件
- 番台番号混入: 1件 (牙狼から263番台)
- et_date混入: 1件 (et_date=2026-05-30)

### 同期ズレ解消 (2026-06-04)

| 種別 | バックフィル前 | バックフィル後 |
|------|------------|------------|
| JSON件数 | 532件 | 532件 |
| Supabase件数 | 264件 | 566件 |
| JSON only | 307件 | 0件 ✅ |
| Supabase only | 39件 | 34件 |
| 機種名不一致 | 27件 | 0件 ✅ (全件PATCH UPDATE) |

- **バックフィル**: 307件を Supabase に INSERT (ON CONFLICT DO NOTHING)
- **機種名修正**: 27件を直接 PATCH UPDATE

### machine_id NULL解消 (2026-06-04)

| 対象 | 解消件数 | 残件数 |
|------|---------|------|
| resolver解決 | 3件 (Ｌバイオ5, 吉宗, 東京喰種) | - |
| 手動マッピング | 7件 | - |
| ゴミ削除 | 7件 (NULL3+番台1+et_date1+前回追加分) | - |
| **残 machine_id=NULL** | - | **8件** |

残8件 (人手確認要):
- `e女神`: 3件
- `ヴヴヴ2`: 2件
- `牙狼1`: 1件
- `ミリオンゴット`: 1件
- `e戦乱カグラ`: 1件

---

## 未完了の作業

### 高優先
- [ ] Supabase-only 34件をJSONに追加 (現在JSONに未反映)
- [ ] `supabase_write_complete()` を `ON CONFLICT DO NOTHING` → `ON CONFLICT DO UPDATE` に変更 (機種名が修正されたときにSBも更新できるようにする)
- [ ] `patch_complete_data.py` を Supabase にも適用するステップを追加

### 中優先
- [ ] machine_id=NULL 8件の解決 (人手確認: e女神×3, ヴヴヴ2×2, 牙狼1, ミリオンゴット, e戦乱カグラ)
- [ ] 6/4 データ収集確認 (JST 15:00以降から自動収集)
- [ ] 6/3の件数減少調査 (5月平均30〜57件→6/3: 2件)

### 低優先
- [ ] unknown_machines 71件を精査・machines_master に登録
- [ ] machines_master: `「モンスターハンターライズ」` (id=1eab6b8d) の完全削除検討

---

## 次にやる作業 (推奨順)

1. **machine_id=NULL 8件 → machines_master登録 + SB UPDATE**
   - `e女神` → `e女神転生`系を確認
   - `ヴヴヴ2` → `蒼き鋼のアルペジオ`系を確認
   - `e戦乱カグラ` → `e戦乱カグラ2`系を確認
   - `牙狼1` → ツイート確認して判断
   - `ミリオンゴット` → ツイート確認して判断

2. **Supabase-only 34件をJSONに追加**

3. **supabase_write_complete() 修正**
   - `resolution=ignore-duplicates` → `resolution=merge-duplicates` に変更
   - または UPDATE 専用の `supabase_update_machines()` を追加

4. **6/3件数激減の調査**
   - GH Actionsのログを詳細確認
   - Xスクレイピングの状態確認

---

## GitHub Actions 状況

| workflow | 状況 | 最終成功 (UTC) | 備考 |
|---------|------|--------------|------|
| update_complete.yml | ✅ 正常 | 2026-06-03T15:25:03Z | complete全jobが成功 |
| update_events.yml | ⚠️ 部分失敗 | 2026-06-03T15:23:10Z | events_accounts/events_search の2件失敗 |

**6/3 UTC 15:22〜15:23 の失敗について:**
- 失敗ジョブ: events_accounts, events_search
- error_detail=None
- completeジョブには影響なし

**6/3 complete件数激減について:**
- GH Actions自体は全て成功 (6回実行)
- complete_2026-06-03.json: 2件
- 原因: 当日投稿ツイートが少ない or Xスクレイピングの部分劣化
- fetch_logs: runs=49, fetched=426, new=340

---

## Supabase 状況

| 項目 | 値 |
|------|-----|
| complete_reports 総件数 | 566件 (バックフィル後) |
| 日付範囲 | 2026-05-20 ～ 2026-06-03 |
| machine_id=NULL残数 | 8件 (人手確認要) |
| unknown_machines | 71件 (未処理) |
| fetch_logs 最終成功 | 2026-06-03T15:25:46Z |

**Supabase は 2026-05-20 以前のデータを持たない。** (JSONの2020-05-19以前のデータは未書き込み)

---

## 6/3収集状況

| データソース | 件数 | 状況 |
|------------|------|------|
| complete_2026-06-03.json | 2件 | 存在 ✅ |
| Supabase (date=2026-06-03) | 4件 | 存在 ✅ |

- 5月平均(30〜57件/日)から大幅減少
- GH Actions自体は正常実行 (fetch_logs: fetched=426, new=340)
- 当日投稿ツイートの実際の減少 or Xスクレイピング劣化の可能性

---

## 6/1 再収集状況

| データソース | 件数 | 状況 |
|------------|------|------|
| complete_2026-06-01.json | 16件 | 存在 ✅ |
| Supabase (date=2026-06-01) | 20件 | 存在 ✅ |

---

## manager 件数

| 種別 | 件数 |
|------|------|
| store (店舗公式) | 563件 |
| manager (店長系) | **45件** |
| **合計** | **608件** |

store_handles.json で管理。`fetch_manager_handles.py` で自動発掘済み。

---

## 現在の課題

### 課題 1: Supabase-only 34件 (JSONに未反映)

Supabaseにのみ存在する34件をJSONに追加する必要がある。

### 課題 2: machine_id=NULL 8件

| 機種名 | 件数 | 判断 |
|--------|------|------|
| e女神 | 3 | machines_masterに未登録 |
| ヴヴヴ2 | 2 | machines_masterに未登録 |
| 牙狼1 | 1 | ツイート確認要 |
| ミリオンゴット | 1 | 候補複数 |
| e戦乱カグラ | 1 | machines_masterに未登録 |

### 課題 3: 6/3件数激減

- GH Actionsは正常動作
- ツイート数減少 or Xセッション劣化の可能性
- 6/4以降で収集量を監視

### 課題 4: supabase_write_complete() の ON CONFLICT DO NOTHING

現在の実装では一度書き込まれた記録は永久に更新されない。
`patch_complete_data.py` や機種名修正がSupabaseに反映されない。
→ `ON CONFLICT DO UPDATE SET machine=excluded.machine, machine_id=excluded.machine_id` への変更を推奨

---

## データ品質指標 (2026-06-04時点)

| 指標 | 値 | 目標 |
|------|-----|------|
| complete_info.json 件数 | 532件 | - |
| 誤分類 (machine_type) | 0件 | 0件 ✅ |
| official_name 不一致 | 0件 | 0件 ✅ |
| JSON ゴミデータ | 0件 | 0件 ✅ |
| Supabase ゴミデータ | 0件 | 0件 ✅ |
| machine_id=NULL (SB) | 8件 | 0件 ❌ |
| unknown_machines | 71件 | 0件 ❌ |
| JSON↔SB 同期ズレ (JSON only) | 0件 | 0件 ✅ |
| JSON↔SB 同期ズレ (SB only) | 34件 | 0件 ❌ |
