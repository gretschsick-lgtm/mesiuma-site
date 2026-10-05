#!/usr/bin/env python3
"""BLOG-DATA-SOURCE-SAFETY-FIX-1 テスト（ネットワーク非依存・DB非依存）。

- P-WORLD由来の公開データ/取得処理が復活していない
- verify_blog.py が第三者サイトから画像を取得・採用しない
- 画像ポリシー（承認された出所のみ）が機能する
- 既存の安全な検証機能は維持され、既存ブログデータは変更されていない
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import verify_blog as V  # noqa: E402

PASS = 0
FAIL = 0


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1
        print(f"  OK  {m}")
    else:
        FAIL += 1
        print(f"  ❌ FAIL  {m}")


def read(p):
    return Path(p).read_text(encoding="utf-8")


def run_main(argv, blog_path):
    """verify_blog.main() を一時データで実行し (exit_code, 保存後posts) を返す。ネットワークは遮断。"""
    import urllib.request
    import socket
    old_blog, old_argv = V.BLOG_PATH, sys.argv
    old_urlopen, old_conn = urllib.request.urlopen, socket.create_connection
    calls = []

    def _boom(*a, **k):
        calls.append(a)
        raise AssertionError("network access attempted")

    urllib.request.urlopen = _boom
    socket.create_connection = _boom
    V.BLOG_PATH = Path(blog_path)
    sys.argv = ["verify_blog.py"] + argv
    code = 0
    try:
        try:
            V.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        V.BLOG_PATH, sys.argv = old_blog, old_argv
        urllib.request.urlopen, socket.create_connection = old_urlopen, old_conn
    return code, calls


def tmp_blog(posts):
    d = Path(tempfile.mkdtemp())
    p = d / "blog_posts.json"
    p.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    return p


def post(pid, title, image="", setting=None, content="本文"):
    return {"id": pid, "title": title, "date": "2026-01-01", "author": "t", "tags": [],
            "summary": "", "image": image, "setting_images": setting or [], "content": content}


# ───────── 1. P-WORLD 由来データ/取得処理 ─────────
print("[1] P-WORLD 由来データ・取得処理")
ok(not (ROOT / "public" / "machine_specs.json").exists(), "1a public/machine_specs.json が公開物に存在しない")
ok(not (ROOT / "scripts" / "fetch_machine_specs.py").exists(), "1b fetch_machine_specs.py が復活していない")
ok(not (ROOT / ".github" / "workflows" / "update_machine_specs.yml").exists(), "1c update_machine_specs.yml が復活していない")
refs = []
for base in ("app", "lib", "scripts", ".github"):
    for f in (ROOT / base).rglob("*"):
        if f.is_file() and f.suffix in {".py", ".ts", ".tsx", ".js", ".mjs", ".yml", ".yaml", ".json"} \
                and f.name != "test_blog_source_safety.py" and "node_modules" not in f.parts:
            try:
                t = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if "machine_specs" in t:
                refs.append(str(f.relative_to(ROOT)))
ok(refs == [], f"1d machine_specs への参照がrepoに無い（runtimeを壊さない） refs={refs}")
nc = read(ROOT / "next.config.ts")
ok("p-world" not in nc, "1e next.config に p-world の画像許可が無い")
wf = "".join(read(f) for f in (ROOT / ".github" / "workflows").glob("*.yml"))
ok("p-world.co.jp/machine/database" not in wf, "1f どのworkflowもP-WORLD機種DBを取得しない")

# ───────── 2. verify_blog.py に外部画像取得が無い ─────────
print("[2] verify_blog.py: 第三者画像の自動取得が存在しない")
src = read(HERE / "verify_blog.py")
for name in ("fetch_and_patch_images", "fetch_html", "extract_og_image", "extract_nanapress_images",
             "search_nanapress_id", "ANALYSIS_PAGES", "NANAPRESS_SEARCH", "CHONBORISTA_SEARCH"):
    ok(not hasattr(V, name), f"2a 関数/定数 {name} が存在しない")
for needle in ("urllib", "nana-press.com", "chonborista.com", "pachiseven", "p-world", "og:image", "requests"):
    ok(needle not in src, f"2b verify_blog.py に '{needle}' が無い")
ok("--fetch-images" not in read(ROOT / ".github" / "workflows" / "verify_blog.yml"),
   "2c verify_blog.yml が --fetch-images を渡さない")

# ───────── 3. 画像を自動設定しない（ネット遮断で実行） ─────────
print("[3] 画像が空の記事に対して画像を自動設定しない／ネット接続しない")
titles = [
    "【スペック完全解説】L青春ブタ野郎はバニーガール先輩の夢を見ない｜基本スペック",   # 未登録機種（検索フォールバック対象だった）
    "【スペック完全解説】スマスロ 東京喰種｜基本スペック",                                # ANALYSIS_PAGES 登録済みだった
    "【スペック完全解説】Lからくりサーカス2｜基本スペック",                              # 同上
]
p = tmp_blog([post(f"t{i}", t) for i, t in enumerate(titles)])
before = read(p)
code, calls = run_main(["--auto-fix", "--fetch-images"], p)
after = json.loads(read(p))
ok(calls == [], "3a --fetch-images を付けてもネットワークアクセスが発生しない")
ok(code == 0, f"3b 画像の空な記事は正常終了する (exit={code})")
ok(all(x["image"] == "" and x["setting_images"] == [] for x in after), "3c image / setting_images が自動設定されない（検索先頭リンク採用なし）")
ok(read(p) == before, "3d 画像取得で blog_posts.json が書き換わらない")
code, calls = run_main([], p)
ok(calls == [] and code in (0, 1), f"3e --fetch-images 無しでもネットワークに触れない（exit 1 は既存仕様の必須表記エラー、画像ポリシー違反の2ではない） exit={code}")

# ───────── 4. 画像ポリシー ─────────
print("[4] 画像ポリシー（明示的に承認された出所のみ）")
legacy = {"https://chonborista.com/wp-content/uploads/2026/03/l_legacy_90.jpg"}
cases = [
    ("https://nana-press.com/x.jpg", False, "nana-press"),
    ("https://image.nana-press.com/kaiseki/machine/1/a.jpeg", False, "image.nana-press"),
    ("https://chonborista.com/wp-content/uploads/a.webp", False, "chonborista"),
    ("https://contents.pachiseven.jp/imgs/a.webp", False, "pachiseven"),
    ("https://www.p-world.co.jp/a.jpg", False, "p-world"),
    ("https://example.com/anything.png", False, "未知の外部ドメイン（ブラックリスト外でも拒否）"),
    ("/component/img/settei_suisoku.jpg", False, "相対パス（承認パス外）"),
    ("/blog-images.evil/a.png", False, "承認パスに似た別パス"),
    ("/blog-images/../secret.png", False, "パストラバーサル"),
    ("/blog-images/https://evil.example/a.png", False, "承認パス配下に埋め込んだ外部URL"),
    ("/blog-images/aobuta.webp", True, "承認済み自社配信パス"),
]
for url, expect, label in cases:
    ok(V.is_approved_image_url(url) is expect, f"4a 承認判定 {label}: {url[:50]} → {expect}")
pl = post("p", "t", image="https://nana-press.com/new.jpg")
ok(len(V.check_image_policy(pl, legacy)) == 1, "4b 新規の第三者画像URLは違反になる")
pl = post("p", "t", image="https://chonborista.com/wp-content/uploads/2026/03/l_legacy_90.jpg")
ok(V.check_image_policy(pl, legacy) == [], "4c 既存(基準)の画像URLは今回は違反にしない（移行しない）")
pl = post("p", "t", image="/blog-images/ok.webp", setting=[{"url": "https://image.nana-press.com/n.jpeg", "caption": "c"}])
ok(len(V.check_image_policy(pl, legacy)) == 1, "4d setting_images の新規第三者URLも違反になる")
ok(V.check_image_policy(post("p", "t", image="", setting=[{"url": "", "caption": "c"}]), legacy) == [], "4e 空URLは違反にしない")
ok(V.check_image_policy(post("p", "t", image="https://x.example/a.png"), set()) != [], "4f 基準が空なら全て未承認扱い")
ok(V.load_legacy_image_baseline(Path("/nonexistent/baseline.json")) == set(), "4g 基準ファイル欠落時は空集合（fail-closed）")
p = tmp_blog([post("n1", "新記事", image="https://image.nana-press.com/kaiseki/machine/9/new.jpeg")])
code, calls = run_main(["--auto-fix"], p)
ok(code == 2 and calls == [], f"4h 新規の第三者画像が入ると --auto-fix でもexit 2（commitに進めない） exit={code}")
p = tmp_blog([post("n2", "新記事", image="/blog-images/new.webp")])
code, _ = run_main(["--auto-fix"], p)
ok(code == 0, f"4i 承認済み画像は通る exit={code}")

# ───────── 5. 既存の安全な検証機能が維持されている ─────────
print("[5] 既存の誤記検証・自動修正が維持されている")
bad = post("kabaneri2", "e甲鉄城のカバネリ2 咲かせや燦然", content="メーカー：SANKYO")
ok(any("SANKYO" in e for e in V.verify_post(bad)), "5a KNOWN_ERRORS（カバネリ×SANKYO）を検出")
fixed, logs = V.auto_fix_content("メーカー：SANKYO", bad["title"], bad["id"])
ok("サミー" in fixed and logs != [], "5b auto_fix_content が誤記を修正")
ok(any("必須表記なし" in e for e in V.verify_post(post("x", "スマスロ 東京喰種", content="空"))), "5c MACHINE_FACTS の必須表記チェックが機能")
p = tmp_blog([bad])
code, _ = run_main(["--auto-fix"], p)
ok("サミー" in json.loads(read(p))[0]["content"], "5d main() --auto-fix が本文の誤記を修正して保存")

# ───────── 6. 既存ブログデータ／レンダリング ─────────
print("[6] 既存ブログデータは変更されず、描画に必要な形のまま")
live = ROOT / "public" / "blog_posts.json"
posts = json.loads(read(live))
need = {"id", "title", "date", "author", "tags", "summary", "image", "setting_images", "content"}
ok(len(posts) > 0 and all(need <= set(x) for x in posts), f"6a blog_posts.json の全{len(posts)}件が描画に必要なキーを持つ")
head = subprocess.run(["git", "show", "HEAD:public/blog_posts.json"], cwd=ROOT, capture_output=True)
ok(head.returncode == 0 and head.stdout.decode("utf-8") == read(live), "6b blog_posts.json は HEAD から未変更（既存画像を削除/書換えしていない）")
imgs = [u for x in posts for u in V.collect_post_image_urls(x)]
base = V.load_legacy_image_baseline()
ok(len(imgs) > 0 and all(V.is_approved_image_url(u) or u in base for u in imgs), "6c 現行データの全画像URLが『承認済み or 置換待ち基準』に含まれる（既存データで検証が通る）")
ok(all(u in imgs for u in base), "6d 基準ファイルは現行データに存在するURLだけを含む（余計な許可を持たない）")
# 実データには触れず、一時コピーに対して実行する（--auto-fix が本文を書き換える可能性があるため）
cp = tmp_blog(posts)
code, calls = run_main(["--auto-fix"], cp)
ok(code == 0 and calls == [], f"6e 現行データ(一時コピー)に verify_blog --auto-fix を実行しても exit 0・ネット不使用・画像ポリシー違反なし (exit={code})")
ok(json.loads(read(cp)) is not None and all(a_["image"] == b_["image"] and a_["setting_images"] == b_["setting_images"]
                                           for a_, b_ in zip(posts, json.loads(read(cp)))),
   "6f その実行で image / setting_images は一切変更されない")
ok(read(live) == head.stdout.decode("utf-8"), "6g 実データ blog_posts.json はテスト実行後も HEAD と同一")

print(f"\n{'=' * 50}\nPASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
