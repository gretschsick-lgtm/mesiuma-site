# スクレイピングルール

X (Twitter) からコンプリート情報を収集する際のルール・設計方針をまとめる。

---

## 認証フロー

`scripts/fetch_complete_info.py` は以下の優先順位で X にログインする。

```
1. scripts/.x_session.enc  (Fernet 暗号化済みの Cookie)
   └─ COOKIE_ENCRYPT_KEY 環境変数で復号
   └─ 有効な auth_token / ct0 を含む Cookie を Playwright に注入

2. 環境変数 X_AUTH_TOKEN + X_CT0
   └─ GitHub Secrets から直接注入

3. X_USERNAME + X_PASSWORD によるフォームログイン
   └─ Cookie 切れ検出時のフォールバック
   └─ 2FA / 追加確認画面が出た場合は username で突破を試みる
```

セッションは実行のたびに最新 Cookie を `.x_session.enc` に保存（Fernet 暗号化）。

---

## 検索クエリ

`COMPLETE_QUERIES` リストに 40+ のクエリが定義されている。
クエリは以下のカテゴリに分類される。

| カテゴリ | 例 |
|---------|---|
| 台番号 × 機能発動 | `"コンプリート機能発動 番台"` |
| ハッシュタグ | `"#コンプリート機能発動"` |
| スマスロ特化 | `"スマスロ コンプリート機能 発動"` |
| 機種名 × コンプリート | `"ヴァルヴレイヴ コンプリート 番台"` |

---

## 店舗投稿フィルタ

`is_store_tweet(text)` が `True` を返すツイートのみ処理対象とする。

**除外パターン (`EXCLUDE_PATTERNS`)**: 個人ユーザーの実戦報告・攻略情報・広告と判断されるパターン。

**店舗投稿パターン (`STORE_TWEET_PATTERNS`)**: 以下のパターンのいずれかにマッチするもの。
- `○○番台` + コンプリート関連語句
- `コンプリート機能発動/作動`
- `おめでとうございます` + コンプリート
- 店舗の定型挨拶フレーズ

---

## 機種名抽出: `extract_machine(text)`

### 前処理

```python
# 全角スペースを含む「北斗の拳 転生」を結合
text = re.sub(r'(北斗の拳)[　\s]+(転生)', r'\1\2', text)

# 炎炎消防隊のひらがな・半角カタカナを統一
text = re.sub(r'炎炎[のﾉ]消防隊', '炎炎ノ消防隊', text)
```

### MACHINE_PATTERNS による抽出

`MACHINE_PATTERNS` は `re.compile` オブジェクトのリスト。
**リストの順番が優先順位**になる（先にマッチしたパターンが採用される）。

主なパターングループ（抜粋）:
1. スマスロ・スマパチ系プレフィックス (`スマスロ○○`, `L○○`, `e○○`)
2. 機種名直接マッチ（ヴァルヴレイヴ、炎炎ノ消防隊、ミリオンゴッドなど）
3. 台番号前後の文脈マッチ (`番台.*?機種名`, `機種名.*?番台`)
4. コンプリート周辺の文脈マッチ

### 後処理（共通クリーニング）

抽出後に以下の除去処理を適用:

```python
# 先頭・末尾の括弧除去
name = re.sub(r'^[『「【（(]+', '', name).strip()
name = re.sub(r'[』」】）)]+$', '', name).strip()

# 末尾の助詞・接続詞除去
name = re.sub(r'(から|にて|より|での|への|として|まで|っ|て|が|は|で|に|を|も|と|の)+$', '', name)

# 「から一撃」「から速報」等の余分テキスト除去
name = re.sub(r'から[一-龠ぁ-んァ-ン]{1,4}$', '', name)

# ポイント・枚数の混入除去
name = re.sub(r'[/／]\s*[\d,]+(?:Pt\.|pt\.|枚|点|玉).*$', '', name)

# バージョン番号除去（例: eカケグルイ7500ver → eカケグルイ）
name = re.sub(r'\d{3,6}[Vv][Ee][Rr]$', '', name)

# コンプリート文言の混入除去
name = re.sub(r'コンプリート.*$', '', name)
```

最大 35 文字に切り詰めて返す。一致しない場合は空文字列を返す。

---

## 機種名正規化: MACHINE_NORMALIZE

`MACHINE_NORMALIZE` は `(パターン, 正規化後の名前)` のタプルリスト。
**リストの順番が優先順位**になる（長いパターンを先に書くこと）。

### 重要ルール

1. 長いパターンを短いパターンより先に書く
   - 例: `"転生の章2"` → `"転生の章"` → `"転生"` の順
2. パチンコ機種 (`e`/`ｅ` プレフィックス) をスマスロ名 (`L`/`スマスロ`) に誤変換しない
   - 例: `e北斗` は `スマスロ北斗の拳` に正規化しない
3. 同じ機種でも別機種と区別が必要なものは保護パターンを先に書く
   - 例: `"eフィーバーもののがたりF"` (甘デジ) を `"eフィーバーもののがたり"` より先に書く

### ファイルの所在

`MACHINE_NORMALIZE` は以下の **2 ヶ所** に定義されている（必ず両方を同期更新すること）:

- `scripts/fetch_complete_info.py` — `update_ranking()` 関数内（約 1437 行目）
- `scripts/patch_complete_data.py` — モジュールレベル（約 20 行目）

---

## 機種名 NG リスト: MACHINE_NAME_NG

ランキング集計から除外すべき非機種名文字列のセット。
`scripts/fetch_complete_info.py:update_ranking()` 内と `scripts/patch_complete_data.py` に定義。

含まれる例:
- `"不明"` — 機種名が特定できなかったエントリ
- `"コンプリート"`, `"達成"`, `"発動"` — 動詞・ツイート文の断片
- `"お客様より"`, `"閉店間際になんと"` — ツイート文の断片
- `"コーナー"`, `"オススメ機種"` — 誤抽出パターン

---

## 機種タイプ判定: `get_machine_type(machine)`

優先順位:

| 優先度 | 条件 | 結果 |
|--------|------|------|
| 1 | `L` / `Ｌ` プレフィックス | `"slot"` (スマスロ) |
| 2 | `e` / `ｅ` プレフィックス | `"pachinko"` (スマパチ) |
| 3 | `CR` プレフィックス | `"pachinko"` |
| 4 | `_PACHINKO_KEYWORDS` に含まれる | `"pachinko"` |
| 5 | `_SLOT_KEYWORDS` に含まれる | `"slot"` |
| 6 | デフォルト | `"slot"` |

---

## 新機種の追加手順

1. **`MACHINE_PATTERNS` に正規表現を追加**（`scripts/fetch_complete_info.py`）
   - 機種名が抽出されやすい位置（コンプリート前後）のパターンを追加
   - 既存パターンとの優先順位に注意
   - 例: `re.compile(r'(新機種名[^\s　\n#「」【】、。！!]{0,10})')`

2. **`MACHINE_NORMALIZE` に表記ゆれを追加**（2 ヶ所）
   - 長いパターンを先に書く
   - パチンコ機種の場合は `is_pachinko_prefix` ガードが正しく動作することを確認

3. **`_SLOT_KEYWORDS` または `_PACHINKO_KEYWORDS` に追加**
   - プレフィックス (`L`/`e`) なしで判定が必要な場合のみ

4. **`patch_complete_data.py` の `_DIRECT_KEYWORDS` に追加**（オプション）
   - `extract_machine()` が失敗する難しいケースのキーワードフォールバック用

5. **`scripts/verify_blog.py` の `MACHINE_FACTS` に追加**
   - ブログ記事での正式表記・禁止表記・メーカーを登録

6. **動作確認**
   ```bash
   python scripts/patch_complete_data.py   # 既存データを再パッチ
   python -c "from scripts.fetch_complete_info import extract_machine; print(extract_machine('新機種名 コンプリート機能発動 123番台'))"
   ```

---

## デバッグガイド

### 機種名が `不明` のまま残る場合

1. 対象ツイートの `text` を確認
2. `extract_machine(text)` で生の抽出結果を確認
3. `MACHINE_PATTERNS` のどのパターンにマッチしているか確認
4. `MACHINE_NORMALIZE` での正規化結果を確認
5. `MACHINE_NAME_NG` に意図せず登録されていないか確認

```python
import sys
sys.path.insert(0, 'scripts')
from fetch_complete_info import extract_machine, get_machine_type

text = "ここにツイートのテキスト"
raw = extract_machine(text)
print(f"raw: {raw!r}")
print(f"type: {get_machine_type(raw)}")
```

### `extract_machine()` が誤抽出する場合

1. どのパターンがマッチしているかをデバッグ
2. 誤抽出パターンを `MACHINE_PATTERNS` の後方に移動 or 除外条件を追加
3. `_MACHINE_EXTRACT_NG` または `_MACHINE_NG_PATTERNS` に除外対象を追加

---

## 重複排除

各ツイートの ID は `MD5(x_url)[:12]` をエントリ ID として使用。
同一 URL のツイートは Supabase への挿入時に `ON CONFLICT DO NOTHING` で排除。
`complete_info.json` は Python 側で ID によるセット管理で重複を排除。
