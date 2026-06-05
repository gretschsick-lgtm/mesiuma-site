# PROJECT STATUS

更新日時: 2026-06-05 (実データ検証・machine_id=None修正・store_handles type修正・Supabase upsert改善・image_urlなし8件監査完了)

---

## 完了した作業

### image_urlなし8件 監査・image_status付与 (2026-06-05)

確認方法: cdn.syndication.twimg.com/tweet-result API

| # | date | store | machine | 判定 | 根拠 |
|---|------|-------|---------|------|------|
| 1 | 2026-05-28 | エクスアリーナ東京 | e牙狼12 | no_image | 投稿存在・media=空 |
| 2 | 2026-05-28 | エクスアリーナ東京 | L革命機ヴァルヴレイヴ2 | no_image | 投稿存在・media=空 |
| 3 | 2026-05-27 | ーク出水店 | スマスロ攻殻機動隊 | video_only | animated_gif mp4 / video_url確認済 |
| 4 | 2026-05-26 | メガフェイス1300淀川 | eシン・エヴァンゲリオン | video_only | amplify_video mp4 / video_url確認済 |
| 5 | 2026-05-25 | (なし) | L沖ドキDUO アンコール | video_only | amplify_video mp4 / video_url確認済 |
| 6 | 2026-05-24 | ダイナム佐世保店 | eフィーバーもののがたりF | video_only | ext_tw_video mp4 / video_url確認済 |
| 7 | 2026-05-22 | 楽園ハッピーロード大山店 | L沖ドキDUO アンコール | no_image | 投稿存在・media=空 |
| 8 | 2026-05-22 | メガガーデン所沢スロット館 | スマスロ北斗の拳転生の章2 | video_only | amplify_video mp4 / video_url確認済 |

**結果:**
- 補完成功(image_url追加): 0件 (取得可能な静止画なし)
- no_image (テキストのみ投稿): **3件** (image_status="no_image" 付与)
- video_only (動画のみ投稿): **5件** (image_status="video_only" 付与)
- 削除済み: **0件**
- 残件数(未処理): **0件 ✅**

**完了条件達成:** image_urlなし && image_statusなし = 0件 ✅

---

### 実データ検証・修正 (2026-06-05)

#### Priority 1: 誤分類監査 (対象9シリーズ)

| シリーズ | slot件数 | pachinko件数 | 誤分類 |
|---------|---------|-------------|-------|
| 東京喰種 | L東京喰種 27件 | e東京喰種/e東京喰種W | 0件 ✅ |
| リコリス | スマスロ リコリス・リコイル | eリコリス・リコイル | 0件 ✅ |
| 北斗 | パチスロ北斗/スマスロ北斗転生章2等 | e北斗の拳 暴凶星 | 0件 ✅ |
| 炎炎 | L炎炎ノ消防隊2/Lパチスロ炎炎ノ消防隊 | e炎炎ノ消防隊2 | 0件 ✅ |
| からくり | Lからくりサーカス/Lパチスロからくりサーカス2 | - | 0件 ✅ |
| 賭ケグルイ | スマスロ賭ケグルイ/カケグルイ219ver | eカケグルイ | 0件 ✅ |
| 牙狼 | - | e牙狼12/e牙狼12黄金騎士極限 | 0件 ✅ |
| シンフォギア | ランキング圏外 | - | 0件 ✅ |
| エヴァ | - | e新世紀エヴァンゲリオン等 | 0件 ✅ |

**確認結果: 誤分類 0件 ✅**
- complete_info.json 602件: e/P/PA/PF/スマパチがslot側 = 0件, L/スマスロ/パチスロがpachinko側 = 0件
- complete_ranking.json: slot_machines/pachinko_machines 両方で誤分類 0件

#### Priority 2: 画像反映漏れ監査

| 確認項目 | 実測値 |
|---------|-------|
| image_urlあり | 594件/602件 |
| image_urlなし | 8件 (ツイート削除またはimage未取得) |
| x_urlあり | 602件/602件 (全件) |
| 表示ロジック | image_url truethy → `<img>`表示 ✅ |
| 代替表示 | 「Xで見る」ボタン常時表示 ✅ |
| image_urlありなのに非表示 | 0件 ✅ |

**完了条件達成: 反映漏れ 0件 ✅**

#### Priority 3: store_handles監査

| 確認項目 | 修正前 | 修正後 |
|---------|-------|-------|
| 総件数 | 1491件 | 1491件 |
| store件数 | 1435件 | 1446件 (+11) |
| manager件数 | 45件 | 45件 |
| type=None | 11件 | **0件 ✅** |
| count=0件数 | 1171件 | 1171件 |
| count>0件数 | 320件 | 320件 |
| 重複x_url | 0件 | 0件 ✅ |
| 不正URL | 0件 | 0件 ✅ |

**修正内容:** type=None の11件(全て店舗アカウント確認済み) → type="store" に修正

#### Priority 4: manager_handles監査

| 確認項目 | 実測値 |
|---------|-------|
| 現在件数 | 45件 |
| count>0 | 24件 |
| count=0 | 21件 |
| 店舗公式をmanager扱い | 0件 ✅ |
| 演者/媒体をmanager扱い | 0件 ✅ |

**判定根拠:** ハンドル名/店舗名に「tencho」「店長」等の個人キーワード確認済み

#### Priority 5: Supabase upsert仕様修正

| 項目 | 修正前 | 修正後 |
|------|-------|-------|
| ON CONFLICT | DO NOTHING (ignore-duplicates) | **DO UPDATE (merge-duplicates)** |
| machine更新 | 不可 | 可 ✅ |
| machine_id更新 | 不可 | 可(NULL送信は除外) ✅ |
| store_name更新 | 不可 | 可(NULL除外) ✅ |
| store_id更新 | 不可 | 可(NULL除外) ✅ |
| NULL上書き防止 | 該当なし | payloadからNULL値を除外 ✅ |

**修正内容:**
- `prefer="resolution=merge-duplicates"` に変更
- NULL値フィールドはpayloadから除外 (machine_id未解決時はDB既存値を保持)
- 対象フィールド: machine, machine_id, store_name, store_id, slot_number

#### machine_id=None 修正 (patch_complete_data.py実行)

| 機種名 | 修正前 | 修正後 |
|-------|-------|-------|
| L革命機ヴァルヴレイヴ2 | 6件 NULL | 0件 ✅ |
| e女神のカフェテラス | 3件 NULL | 0件 ✅ |
| eエヴァ17はじまりR | 3件 NULL | 0件 ✅ |
| スマスロ北斗の拳転生の章2 | 2件 NULL | 0件 ✅ |
| e牙狼12 | 2件 NULL | 0件 ✅ |
| Lミリオンゴッド神々の軌跡 | 2件 NULL | 0件 ✅ |
| その他14機種 | 各1件 NULL | 0件 ✅ |
| **合計** | **33件 NULL** | **0件 ✅** |

**patch_complete_data.py 実行結果:** 修正前602件→修正後602件, 解決率 602/602 (100.0%)

---

### AMBIGUOUS_SERIES 全監査・炎炎/からくり誤分類バグ修正 (2026-06-04)

**監査対象 9シリーズの結果:**

| シリーズ | 判定 | 理由 |
|---------|------|------|
| 賭ケグルイ | ✅ 安全 | prefix付き alias のみ。prefix なし alias なし |
| 牙狼 | ✅ 安全 | pachinko のみ |
| 炎炎 | ❌ 修正済み | L炎炎(slot) + eフィーバー炎炎/e炎炎(pachinko) 両方存在 |
| シンフォギア | ✅ 安全 | slot のみ |
| エヴァ | ✅ 安全 | prefix付きで分離済み |
| ゴッドイーター | ✅ 安全 | slot のみ |
| からくり | ❌ 修正済み | Lからくりサーカス(slot) + Pフィーバーからくりサーカス(pachinko) 両方存在 |
| モンハン | ✅ 安全 | slot のみ |
| キン肉マン | ✅ 安全 | pachinko のみ |

**炎炎・からくりの修正内容:**

| 対象 | 修正内容 |
|------|---------|
| `machines_aliases` (Supabase) | 危険alias 7件削除: "炎炎2"/"炎炎の消防隊"/"炎炎ノ消防隊"/"炎炎の消防隊2"/"炎炎ノ消防隊2"/"からくり"/"からくりサーカス" → 148件→141件 |
| `machine_resolver.py` | AMBIGUOUS_SERIES に "炎炎ノ消防隊","炎炎の消防隊","炎炎ノ消防隊2","炎炎の消防隊2","炎炎2","からくり","からくりサーカス" 追加 |
| `fetch_complete_info.py _SLOT_KEYWORDS` | "炎炎ノ消防隊"/"からくりサーカス" 削除 |
| `fetch_complete_info.py MACHINE_NORMALIZE` | prefix なし炎炎5件・からくりサーカス1件を削除（prefix付き "Ｌ炎炎ノ消防隊２" は保持） |
| `complete_ranking.json` | 再生成 (slot/pachinko 完全分離確認 ✅ 誤分類0件) |

**修正後検証:**
- eプレフィックス機種が slot 側: 0件 ✅
- slot 機種が pachinko 側: 0件 ✅
- slot/pachinko 分布: slot=415, pachinko=170 (complete_info.json 585件)

---

### slot/pachinko 誤分類バグ修正 (2026-06-04)

**根本原因（3層）:**
1. `machine_resolver.py`: AMBIGUOUS_SERIES チェックが exact/alias match より後にあり迂回されていた
2. `machines_aliases` (Supabase): prefix なし "東京喰種"/"北斗"/"リコリコ" 等が slot 側に紐づき AMBIGUOUS_SERIES を迂回
3. `fetch_complete_info.py MACHINE_NORMALIZE`: "東京喰種" → "L東京喰種" の ambiguous mapping

**修正内容:**

| 対象 | 修正内容 |
|------|---------|
| `machine_resolver.py` | AMBIGUOUS_SERIES チェックを exact/alias match より前に移動 |
| `machine_resolver.py` | AMBIGUOUS_SERIES に "リコリス", "リコリコ", "リコリス・リコイル", "北斗の拳" 追加 |
| `machines_aliases` (Supabase) | 危険alias 6件削除: "東京喰種"/"東京グール"/"北斗"/"北斗の拳"/"リコリコ"/"リコリス・リコイル" |
| `fetch_complete_info.py _SLOT_KEYWORDS` | "東京喰種"/"リコリス"/"北斗" 削除（slot/pachinko 両存在シリーズ） |
| `fetch_complete_info.py MACHINE_NORMALIZE` | ("東京喰種","L東京喰種"), ("北斗の拳","スマスロ北斗の拳"), ("北斗","スマスロ北斗の拳") 削除 |
| `complete_ranking.json` | 再生成 (slot/pachinko 完全分離確認 ✅) |

**修正後検証:**
- eプレフィックス機種が slot 側: 0件 ✅
- slot 機種が pachinko 側: 0件 ✅
- slot/pachinko 分布: slot=409, pachinko=163 (complete_info.json)

---

### 機種名抽出バグ修正 (scripts/fetch_complete_info.py)
- MACHINE_PATTERNS の `の|` バグ修正（北斗転生問題）
- スマパチ prefix 除去
- カバネリ スペース区切り対応
- モンキーターン専用パターン追加
- eカケグルイ219ver 系誤抽出防止

### MACHINE_NORMALIZE 追加
- `LモンキーターンV`, `Lモンキーターン`, `モンキーターンV` の正規化ルール追加

### データ修正
- `eカケグルイ219ver` → `eカケグルイ` (2件)
- `「モンスターハンターライズ」` → `スマスロ モンスターハンターライズ` (2件)
- machines_master: `「モンスターハンターライズ」` → `is_active=false`

### 全件監査 (complete_info.json 565件)
- 誤分類 0件 ✅
- official_name 不一致 0件 ✅
- ゴミデータ 0件 ✅

### Supabase バックフィル (2026-06-04)
- 264件 → 571件 → 565件（ゴミ削除後）
- JSON only → 0件 ✅
- SB only → 0件 ✅（33件をJSONに反映）
- 機種名不一致 27件 → 0件 ✅ (直接PATCH UPDATE)

### machine_id=NULL 解消 (2026-06-04)

| 処理 | 件数 |
|------|------|
| resolver解決 | 3件 (Ｌバイオ5, 吉宗, 東京喰種) |
| 手動マッピング | 14件 |
| ゴミ削除 | 8件 (NULL3+番台1+et_date1+牙狼1他) |
| **残 machine_id=NULL** | **0件 ✅** |

新規machines_master登録:
- `e閃乱カグラ` (pachinko, 大一販売) ← 新規
- 解決に使ったmappig: e女神→e女神のカフェテラス, ヴヴヴ2→L革命機ヴァルヴレイヴ2, ミリオンゴット→スマスロ ミリオンゴッド-神々の軌跡-

新規machines_aliases登録 (5件):
- e女神, ミリオンゴット, ヴヴヴ2, e戦乱カグラ, e閃乱カグラ

### machines_aliases 強化 (2026-06-04)
- 70件 → **154件** (+84件)
- 追加対象機種: L革命機ヴァルヴレイヴ2/パチスロ革命機/東京喰種4種/北斗の拳/モンキーターン/カバネリ/牙狼/からくりサーカス/炎炎ノ消防隊/ミリオンゴッド/かぐや様/モンハンライズ/ゴジラ/戦国乙女/シンフォギア/ゴッドイーター/ダンベル/ToLOVEる/ジャグラー/吉宗/一騎当千/リコリコ/バイオ/エヴァ/チバリヨ/攻殻/鬼武者/バジリスク/リゼロ/転スラ/閃乱カグラ他
- 重複防止: normalized_alias unique制約を尊重し、prefix除去衝突は先着優先でスキップ

### unknown_machines 整理 (2026-06-04)
- 72件 → pending **3件**, rejected 36件, ignored 33件
- rejected (ゴミ): 番台番号混入・URL断片・et_date・コーナー・取材・LIMITSTOP等 36件
- ignored (alias登録済み): 東京喰種・カバネリ・革命機・牙狼・モンハンライズ・エヴァ等 33件
- pending残3件 (要調査): L鋼鉄城・キン肉マン・ライザのアトリエ

### Phase 1: コンプリート画像調査 (2026-06-04)

| 確認項目 | 実測値 |
|---------|-------|
| complete_info.json image_url あり | 524件/565件 |
| Supabase image_url | 全件 NULL（設計通り：転載禁止対応） |
| pbs.twimg.com 外部アクセス | HTTP 200 OK / CORS: access-control-allow-origin: * |
| CSP ブロック | なし (vercel.json 未設定) |
| フロント表示コード | app/complete/page.tsx に `<img src={entry.image_url}>` あり |

**原因**: 画像 URL は取得・保存済み・CDN アクセス可能。表示コードも存在するが、サムネイルが X 投稿にリンクしていなかった (X転載禁止対応との整合性問題)

**修正**: 画像を `<a href={entry.x_url}>` でラップし、クリックで元 X 投稿へ遷移するサムネイル UI を実装。`referrerPolicy="no-referrer"` を追加。

### Phase 5: COMPLETE_QUERIES 拡張 (2026-06-04)
- 96件 → **107件** (+11件)
- 追加: ヴヴヴ2/e女神のカフェテラス/e閃乱カグラ/東京喰種W/牧狼12黄金騎士極限/スマスロミリオンゴッド/モンハンライズ/リコリス・リコイル/炎炎ノ消防隊/ダンベル/L革命機ヴァルヴレイヴ

### Phase 6: unknown_machines 完全解消 (2026-06-04)
- pending: 5件 → **0件 ✅**
- 牧狼141番台 → rejected (番台番号混入)
- eエヴァ17はじまりの記憶 → alias追加→ignored
- L鋼鉄城 → alias追加 (甲鉄城カバネリ, confidence=0.75) → ignored
- キン肉マン → ignored (機種曖昧)
- ライザのアトリエ → machines_master 新規登録 (パチスロ ライザのアトリエ/エレコ) + alias追加 → ignored
- machines_aliases: 150件 → **154件**
- machines_master: 376件 → **377件** (パチスロ ライザのアトリエ追加)

### SB-only 33件 → JSON反映 (2026-06-04)
- complete_info.json: 532 → 565件
- 11個のdaily JSON更新
- ランキング再生成

---

## 現在の実測値 (2026-06-05 更新)

| 指標 | 値 | 目標 |
|------|-----|------|
| complete_info.json 件数 | 602件 | - |
| machine_id=NULL (JSON) | **0件 ✅** | 0件 ✅ |
| 誤分類 (machine_type) | 0件 | 0件 ✅ |
| image_urlあり | 594件/602件 | - |
| image_urlありなのに非表示 | 0件 | 0件 ✅ |
| store_handles 総件数 | 1491件 | 3000件 △ |
| store_handles type=None | **0件 ✅** | 0件 ✅ |
| manager_handles | 45件 | 500件 ❌ |
| store_handles重複URL | 0件 ✅ | 0件 ✅ |
| Supabase upsert仕様 | **DO UPDATE ✅** | DO UPDATE |
| machines_aliases 総件数 | 141件 | - |
| COMPLETE_QUERIES | 116件 | - |
| ゴミデータ (JSON) | 0件 | 0件 ✅ |

---

## 6/3件数激減調査 (実測のみ)

### 実測値
| 項目 | 6/2 | 6/3 | 5月平均 |
|------|-----|-----|---------|
| daily件数 | 10件 | 4件 | 39件 |
| runs (fetch_logs) | 58 | 49 | - |
| fetched_count | 619 | 426 | - |
| new_count (SB) | 506 | 340 | - |

### 最新run (26894847945) の7モード別収集件数

| モード | 収集件数 | SB新規 | SB重複 |
|--------|---------|--------|--------|
| keyword_a (50クエリ) | 9件 | 1件 | 8件 |
| keyword_b (45クエリ) | 3件 | 1件 | 2件 |
| handle_a (50クエリ) | 16件 | 5件 | 11件 |
| handle_b (50クエリ) | 4件 | 2件 | 2件 |
| handle_c (50クエリ) | 11件 | 5件 | 6件 |
| handle_d (50クエリ) | 1件 | 1件 | 0件 |
| manager (45クエリ) | 7件 | 1件 | 6件 |
| **合計** | **51件** | **16件** | **35件** |

### 結論
- GH Actions: 全340クエリ完走、全モードsuccess
- 6/4合計0件（JST深夜run → 当日ツイートなし）
- **5月のfetch_logsデータなし（6/2から記録開始）のため5月との比較不可**
- 断定的原因特定は不可（要継続監視）

---

## Priority1-5 調査・実施結果 (2026-06-04)

### Priority 1: コンプリート画像反映漏れ調査

| 確認項目 | 実測値 |
|---------|-------|
| image_url件数 (truthy) | 530件/571件 |
| 実表示件数 (slot tab) | 381件 |
| 実表示件数 (all tab) | 530件 |
| 反映漏れ件数 (slot visible・画像なし) | 26件 (null/empty string) |
| HTTPステータス (全530件) | 200 OK |
| Vercel反映状況 | Phase 1 fix デプロイ済み ✅ (referrerPolicy:"no-referrer" 確認) |
| Next.js表示状況 | 条件分岐正常 / image_url=""はJS falsy→非表示 |
| CSS非表示 | なし |
| 条件分岐 | slot tab でpachinko 163件非表示（設計通り） |
| CSP ブロック | なし (vercel.json 未設定) |

**原因**:
- A) 26件のスロットエントリでimage_urlが未取得またはnull → fetch_complete_images.py待ち/ツイート削除
- B) image_url="" の2件 → JSONのバグ（nullに修正済み ✅）
- 「image_urlありなのに表示されない」バグ: 0件（全530件正常）

**修正**:
- `image_url=""` の2件を null に修正（complete_info.json）
- パチンコ149件の slot tab 非表示は設計通り

---

### Priority 5: COMPLETE_QUERIES 更新 (107→116件)

- 重複クエリ削除: 「炎炎ノ消防隊 コンプリート 番台」が2件→1件 (-1)
- 実績確認済み新規追加 (+10件):
  - ひきこまり / 東京リベンジャーズ / 無職転生 / ビッグドリーム / ゾンビランドサガ
  - タクトオーパス / 鉄拳 / 超電磁砲 / 一騎当千 / 番長

---

## Phase 2-4 調査結果 (2026-06-04実測)

### Priority 2: Store Expansion 実施結果

| 追加元 | 新規件数 | 追加後総計 |
|--------|---------|----------|
| events_public.json (店舗系フィルタ) | +873件 | 1491件 |
| stores.json / store_x_urls.json | 0件(既登録済み) | - |

- フィルタ基準: ユニーク出現店舗 ≤ 3 かつ メディアキーワードなし
- メディア系94件は除外 (複数店舗に言及するアグリゲーター)
- 618件 → **1491件** (+873件)

チェーン別追加結果:
| チェーン | 追加前 | 追加後 | 状況 |
|---------|-------|-------|------|
| アミューズ | 3 | 8 | △ |
| ガイア | 10 | 20 | △ |
| MJ | 4 | 5 | △ |
| ニッコー | 0 | 0 | ✗ イベントデータに出現なし |
| コスモス | 0 | 0 | ✗ イベントデータに出現なし |
| 共楽 | 0 | 0 | ✗ イベントデータに出現なし |
| VEAM | 1 | 1 | ✗ count=0のまま |

### Priority 3: Manager Expansion 状況
- 現在: **45件** (count>0: 24件)
- イベントデータからmanager判定不可 → 手動X検索が必要
- 次のアクション: 各チェーンの店長アカウントを fetch_store_x_urls.py で探索

### Priority 4: count=0店舗 理由調査
- count=0合計: 1171件（うち旧618件分の298件含む）
- PIA: 7件 count=0 → コンプリートのツイート形式が検索クエリにマッチしない可能性
- アミューズ: 8件 count=0 → 同上
- VEAM: 1件 count=0 → veam_web は公式アカウントだがコンプリート投稿なし
- **根本原因**: X APIによるリアルタイム確認が必要。GH Actions次回実行後にcount変化を監視する

### Phase 2: Store Expansion 状況

| チェーン | 登録数 | 実績あり | 実績率 | 課題 |
|---------|-------|---------|-------|------|
| マルハン | 77 | 21 | 27% | manager増強 |
| ダイナム | 53 | 32 | 60% | ◯ |
| ワンダーランド | 38 | 5 | 13% | ツイート確認要 |
| キコーナ | 20 | 8 | 40% | ◯ |
| D'STATION | 13 | 9 | 69% | ◯ |
| パラダイス | 12 | 1 | 8% | 実績低 |
| キング観光 | 11 | 3 | 27% | - |
| 楽園 | 10 | 10 | 100% | ◯ |
| キャッスル | 10 | 7 | 70% | ◯ |
| やすだ | 10 | 3 | 30% | - |
| メガフェイス | 9 | 9 | 100% | ◯ |
| ビックマーチ | 9 | 3 | 33% | - |
| ABC | 8 | 5 | 63% | ◯ |
| ガイア | 7 | 2 | 29% | - |
| PIA | 5 | 0 | 0% | ✗実績なし |
| アミューズ | 3 | 0 | 0% | ✗実績なし |
| コスモス | 3 | 0 | 0% | ✗実績なし |
| ニッコー | 3 | 0 | 0% | ✗実績なし |
| VEAM | 1 | 0 | 0% | ✗実績なし |

- count=0（未実績）: **298件/618件 (48%)**
- **次のアクション**: PIA/アミューズ/コスモス/ニッコー/VEAM のアカウントがツイートしているか確認。count=0 のアカウントは非活動の可能性。

### Phase 3: Manager Expansion 状況
- 現在: **45件** (目標: 500件)
- 実績あり (count>=1): 約30件
- 追加方法: 各チェーン店の店長・副店長アカウントを手動または fetch_store_x_urls.py で探索

### Phase 4: Coverage Audit (5月→6月)
- 5月出現: 297店舗 / 6月出現: 40店舗 (6/1-6/3, 3日分のみ)
- 5月2件以上+6月未出現: **87店舗** (6月データ少ないため正常範囲内)
- 重点4店舗の確認:

| 店舗名 | handle | 最終収集日 | 状況 |
|--------|--------|----------|------|
| SuperD'station東金 | sd_tougane | 2026-05-31 | 登録済み・実績5件 |
| ARROW浪速 | arrow_naniwa | 2026-05-30 | 登録済み・実績6件 |
| キクヤ春日井 | 315kasugai | 2026-05-29 | 登録済み・実績7件 |
| メガフェイス1300淀川 | megaface_1300 | 2026-05-31 | 登録済み・実績5件 |

→ 全4店舗登録済み。6月未出現は収集期間が短いため（3日のみ）、継続監視が必要。

---

## チェーン別 store_handles カバー率 (2026-06-04実測)

### 全体 (2026-06-04 更新後)
- 総件数: 1491件 (store=1435, manager=45, unknown=11)
- count=0（未実績）: 1171件
- count>=1（実績あり）: 320件

### チェーン別

| チェーン | store | manager | count合計 | 状態 |
|---------|-------|---------|----------|------|
| マルハン | 88 | 14 | 72 | ◯ |
| ダイナム | 50 | 3 | 41 | ◯ |
| ワンダーランド | 37 | 0 | 5 | △実績低 |
| キコーナ | 22 | 0 | 19 | ◯ |
| ビックマーチ | 15 | 2 | 17 | ◯ |
| ガイア | 10 | 0 | 4 | △実績低 |
| 楽園 | 9 | 0 | 29 | ◯ |
| やすだ | 9 | 0 | 4 | △実績低 |
| メガフェイス | 8 | 0 | 28 | ◯ |
| キング観光 | 8 | 2 | 11 | ◯ |
| キャッスル | 7 | 0 | 35 | ◯ |
| D'STATION | 6 | 1 | 14 | △登録少 |
| ABC | 6 | 1 | 5 | △実績低 |
| PIA | 5 | 0 | 0 | ✗実績なし |
| コンコルド | 4 | 0 | 3 | △実績低 |
| 123 | 3 | 1 | 1 | △実績低 |
| MGM | 3 | 0 | 2 | △実績低 |
| アミューズ | 3 | 0 | 0 | ✗実績なし |
| MJ | 3 | 0 | 5 | △実績低 |
| ニッコー | 0 | 0 | 0 | ✗未登録 |
| VEAM | 0 | 0 | 0 | ✗未登録 |
| コスモス | 0 | 0 | 0 | ✗未登録 |
| 共楽 | 0 | 0 | 0 | ✗未登録 |

---

## 未完了の作業

### 高優先
- [ ] store_handles 1491件 → 3000件 (残り +1509件)
  - ニッコー, コスモス, 共楽: イベントデータに出現なし → 手動X検索必要
  - fetch_store_x_urls.py を定期実行して自動発掘
- [ ] manager_handles 拡大 (現45件 → 目標500件)
  - 手動X検索 or fetch_store_x_urls.py で探索
- [x] unknown_machines pending → **0件 ✅**
- [x] supabase_write_complete() を ON CONFLICT DO UPDATE に変更 **✅ 2026-06-05完了**
  - merge-duplicates に変更, NULL値はpayloadから除外してNULL上書き防止
- [x] image_urlなし8件 監査完了 **✅ 2026-06-05**
  - no_image: 3件 (テキストのみ投稿), video_only: 5件 (mp4動画)
  - 削除済み: 0件, 補完可能: 0件
  - image_status フィールドをcomplete_info.jsonに付与

### 中優先
- [ ] 6/4 以降のdaily件数継続監視
- [ ] patch_complete_data.py を Supabase にも適用するステップ追加

---

## GitHub Actions 状況

| workflow | 状況 | 最終実行 (UTC) |
|---------|------|--------------|
| update_complete.yml | ✅ 正常 | 2026-06-03T15:25:03Z |
| update_events.yml | ⚠️ 部分失敗 | events_accounts/events_search 2件失敗 |

- 失敗ジョブ: events_accounts, events_search（complete とは無関係）
- complete 収集: 全340クエリ正常完走

---

## Supabase 状況

| 項目 | 値 |
|------|-----|
| complete_reports 総件数 | 565件 |
| 日付範囲 | 2026-05-19 ～ 2026-06-03 |
| machine_id=NULL | 0件 ✅ |
| unknown_machines | 71件 |
| machines_master 総件数 | 376件（e閃乱カグラ追加後）|
| machines_aliases 総件数 | 150件（+80件追加後）|
| unknown_machines pending | 3件（L鋼鉄城・キン肉マン・ライザのアトリエ）|

---

## 次のボトルネックと改善計画

### ボトルネック 1: store_handles 618件 → 3000件
- **現状**: 618件中320件が実績あり（51.8%）
- **計画**:
  1. `fetch_store_x_urls.py` で未登録チェーン店を自動発掘
  2. ニッコー・VEAM・コスモス・共楽 のXアカウント一覧をWeb検索で取得
  3. `fetch_manager_handles.py` でmanager 500件を目標に拡大

### ボトルネック 2: 6月件数低下
- **実測**: 5月平均39件/日 → 6月平均11件/日
- **計画**:
  1. 6/4〜6/10の件数を継続監視
  2. COMPLETE_QUERIESに新機種（ヴヴヴ2、e女神のカフェテラス、e閃乱カグラ）を追加
  3. 収集対象store_handlesを3000件に拡大することで網羅率向上

### ボトルネック 3: unknown_machines pending 3件
- 72件中69件整理済み (rejected 36件 + ignored 33件)
- 残3件: L鋼鉄城（甲鉄城誤字の可能性）、キン肉マン（機種曖昧）、ライザのアトリエ（machines_master未登録）
- ライザのアトリエはmachines_master登録検討
