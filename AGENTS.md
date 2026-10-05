<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- BEGIN:blog-rules -->
## ブログ記事を追加・修正したら必ず実行

`public/blog_posts.json` を編集した後は、**必ず以下のコマンドを実行**すること：

```bash
python scripts/verify_blog.py --auto-fix
```

これにより：
- 誤記・機種名ミスを自動修正（KNOWN_ERRORS に基づく）
- 画像が承認された出所か検証（未承認の出所が新規に入るとエラー終了）
- 修正があれば `blog_posts.json` を上書き保存

**画像について**: 第三者サイト（解析サイト等）から画像を自動取得・自動設定する処理は停止済み。
`--fetch-images` は無効（受け付けるが何もしない）。ブログ画像は「明示的に承認された出所のみ」許可し、
現在の承認済みは自社配信の `/blog-images/` 配下のみ（`APPROVED_IMAGE_PREFIXES`）。
既存記事に残る第三者画像は `scripts/blog_image_legacy_baseline.json`（置換待ち）に記録しており、新規追加の許可ではない。

実行後に変更がある場合はコミットに含めること。  
GitHub Actions (`verify_blog.yml`) でも push 時に自動実行される。

### 新機種を追加するときは
`scripts/verify_blog.py` 先頭の以下の辞書に追記すること：
- `KNOWN_ERRORS` — 誤記 → 正表記のマッピング
- `MACHINE_FACTS` — 必須表記・禁止表記・メーカー

画像の出所を新たに承認する場合は、権利・利用条件を確認した上で `APPROVED_IMAGE_PREFIXES` に明示的に追加すること。
`public/machine_specs.json`（P-WORLD由来）は削除済み。P-WORLD等の規約上自動取得できないサイトを再び取得元にしないこと。
<!-- END:blog-rules -->
