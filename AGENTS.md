<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- BEGIN:blog-rules -->
## ブログ記事を追加・修正したら必ず実行

`public/blog_posts.json` を編集した後は、**必ず以下のコマンドを実行**すること：

```bash
python scripts/verify_blog.py --auto-fix --fetch-images
```

これにより：
- 誤記・機種名ミスを自動修正（KNOWN_ERRORS に基づく）
- 解析サイト（nana-press）から機種画像を取得して `image` / `setting_images` を補完
- 修正があれば `blog_posts.json` を上書き保存

実行後に変更がある場合はコミットに含めること。  
GitHub Actions (`verify_blog.yml`) でも push 時に自動実行される。

### 新機種を追加するときは
`scripts/verify_blog.py` 先頭の以下の辞書に追記すること：
- `KNOWN_ERRORS` — 誤記 → 正表記のマッピング
- `MACHINE_FACTS` — 必須表記・禁止表記・メーカー
- `ANALYSIS_PAGES` — nana-press の機種ページURL
<!-- END:blog-rules -->
