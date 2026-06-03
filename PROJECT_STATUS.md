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
- `「モンスターハンターライズ」` → `モンスターハンターライズ` (括弧除去、2件: complete_info.json + daily)

### 全件監査 (complete_info.json 528件 + complete_ranking.json)
- 誤分類 0件
- official_name 不一致 0件
- 機種名短縮 0件

### ゴミデータ除去監査

| 対象 | ゴミ件数 | 修正件数 | 削除件数 | 残件数 |
|------|---------|---------|---------|------|
| Supabase | 59件 | 0 | 59件 | 248件 |
| complete_info.json | 1件 | 1件 | 0件 | 528件 |
| daily JSON | 6件 | 1件 | 5件 | - |

削除内訳 (Supabase):
- machine=NULL: 33件
- 番台番号混入: 7件
- 既知ゴミフレーズ: 11件 (ＬＩＭＩＴＳＴＯＰ×2, にて×2, er, e機, L取材, コーナー, コンプおめ, ▶︎×1)
- コード/URL混入: 5件 (et_date=..., e.jp/..., ＋9000枚, 𝟡𝟝,𝟘𝟘𝟘玉, ＬＥＴＥ)
- 不正括弧/スラッシュ: 3件

### 同期ズレ監査
- JSON vs Supabase の同期ズレ: **370件** (詳細は「現在の課題」参照)
- 正データソース: **complete_info.json を正** と確定

---

## 未完了の作業

### 高優先
- [ ] Supabase ← complete_info.json バックフィル (312件 JSON-only を Supabase に upsert)
- [ ] `supabase_write_complete()` を `ON CONFLICT DO NOTHING` → `ON CONFLICT DO UPDATE` に変更 (機種名が修正されたときにSBも更新できるようにする)
- [ ] `patch_complete_data.py` を Supabase にも適用するステップを追加

### 中優先
- [ ] Supabase-only 32件をJSONに追加 (現在JSONに未反映)
- [ ] machine_id=NULL 30件の解決 (unknown_machinesに71件登録済み → machines_master への追加)
- [ ] 6/3〜6/4 のデータ収集再実行 (現在 complete_2026-06-03.json, complete_2026-06-04.json 存在しない)

### 低優先
- [ ] unknown_machines 71件を精査・machines_master に登録
- [ ] Supabase fetch_logs の 6/3 15:25 失敗原因調査 (error_detail=None)

---

## 次にやる作業 (推奨順)

1. **6/3〜6/4 手動再収集**
   ```bash
   gh workflow run update_complete.yml -f date=2026-06-03
   gh workflow run update_complete.yml -f date=2026-06-04
   ```

2. **Supabase バックフィル**
   - complete_info.json の全528件を Supabase に upsert
   - `machine_id` は `machine_resolver.py` で解決

3. **supabase_write_complete() 修正**
   - `resolution=ignore-duplicates` → `resolution=merge-duplicates` に変更
   - または UPDATE 専用の `supabase_update_machines()` を追加

4. **unknown_machines 71件 → machines_master 登録**

---

## GitHub Actions 状況

| workflow | 状況 | 最終成功 (UTC) | 最終失敗 (UTC) |
|---------|------|--------------|--------------|
| update_complete.yml | ⚠️ 部分失敗 | 2026-06-03 12:08 (JST 21:08) | 2026-06-03 15:25 (7件同時) |
| update_events.yml | 部分失敗 | 2026-06-03 15:23 (youtube/web) | 2026-06-03 15:23 (google/search/accounts) |

**6/3 15:25 の失敗について:**
- error_detail=None (ログなし)
- fetched=0, new=0 → X ログイン失敗の可能性
- 7件同時失敗 = matrix全モードが失敗
- **2026-06-03, 2026-06-04 のデータ未収集 (要手動再実行)**

---

## Supabase 状況

| 項目 | 値 |
|------|-----|
| complete_reports 総件数 | 248件 |
| 日付範囲 | 2026-05-24 ～ 2026-06-02 |
| machine_id=NULL残数 | 30件 |
| unknown_machines | 71件 |
| fetch_logs 最終成功 | 2026-06-03 12:08 UTC |

**Supabase は 2026-05-24 以前のデータを持たない。** (JSON側に196件が存在するが未書き込み)

---

## 6/1 再収集状況

| データソース | 件数 | 状況 |
|------------|------|------|
| complete_2026-06-01.json | 15件 | 存在 ✅ |
| Supabase (date=2026-06-01) | 17件 | 存在 ✅ |

- 15件 (JSON) vs 17件 (SB) の差異: 2件はSupabaseのみ存在
- 6/1は正常収集済み

---

## manager 件数

| 種別 | 件数 |
|------|------|
| store (店舗公式) | 563件 |
| manager (店長系) | **45件** |
| **合計** | **608件** |

store_handles.json で管理。`fetch_manager_handles.py` で自動発掘済み。

---

## store 件数

| ファイル | 件数 |
|---------|------|
| store_handles.json | 608件 (store+manager合計) |
| daily JSON (直近) | complete_2026-06-01.json = 15件 |
| public/stores.json | 全国店舗マスタ（件数は別途確認） |

---

## 現在の課題

### 課題 1: JSON ↔ Supabase 同期ズレ (370件)

| 種別 | 件数 | 原因 |
|------|------|------|
| JSON のみ存在 | 312件 | 196件は Supabase 実装前 (pre-5/24)、116件は書き込み漏れ |
| Supabase のみ存在 | 32件 | JSON に未反映 (partial モード統合ミス等) |
| 同一 x_url で機種名不一致 | 26件 | patch_complete_data.py が JSON のみ更新 |
| **合計** | **370件** | |

**正データソース: complete_info.json**
サイト表示・ランキング生成ともに complete_info.json を参照。Supabase は二次保存。

### 課題 2: machine_id=NULL 30件

Supabase の machine_id が解決できていない機種名:
```
e女神×3, 東京喰種×3, ミリオンゴット神々×2, エヴァ17, 革命機
ライザのアトリエ, 牙狼1, ヴヴヴ2, eとある科学, e牙狼×1
Lミリオンゴッド～神々, Lミリオンゴット, 吉宗, モンハンライズ, ミリオンゴット
e新世紀エヴァンゲリオン17シリーズ×2, 真・一騎当千～軍神覚醒～, eカケグルイ〜生か死か〜LTT-KR
無職転生×2, Ｌバイオ5
```
→ machines_master への追加・aliases 登録が必要

### 課題 3: GH Actions 部分失敗

- 2026-06-03 15:25 UTC: 7件同時失敗 (complete全モード)
- 6/3, 6/4 のデータが存在しない
- error_detail=None のため原因不明 → X セッション切れの可能性が高い

### 課題 4: supabase_write_complete() の ON CONFLICT DO NOTHING

現在の実装では一度書き込まれた記録は永久に更新されない。
`patch_complete_data.py` や機種名修正がSupabaseに反映されない。
→ `ON CONFLICT DO UPDATE SET machine=excluded.machine, machine_id=excluded.machine_id` への変更を推奨

---

## データ品質指標 (2026-06-04時点)

| 指標 | 値 | 目標 |
|------|-----|------|
| complete_info.json 件数 | 528件 | - |
| 誤分類 (machine_type) | 0件 | 0件 ✅ |
| official_name 不一致 | 0件 | 0件 ✅ |
| JSON ゴミデータ | 0件 | 0件 ✅ |
| Supabase ゴミデータ | 0件 (59件削除済) | 0件 ✅ |
| machine_id=NULL (SB) | 30件 | 0件 ❌ |
| unknown_machines | 71件 | 0件 ❌ |
| JSON↔SB 同期ズレ | 370件 | 0件 ❌ |
