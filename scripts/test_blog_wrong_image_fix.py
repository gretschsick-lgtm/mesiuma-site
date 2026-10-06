#!/usr/bin/env python3
"""BLOG-WRONG-IMAGE-FIX-1 テスト（ネットワーク非依存）。

機種が明確に異なる画像が表示されていた9記事から、誤画像を撤去した状態を固定する。
正しい画像の追加は許諾取得後の別phase。ここでは「誤画像が無い」「新しい外部画像を足していない」
「画像なしでも描画できる」ことだけを検証する（承認済み /blog-images/ を後から足しても通る）。
"""
import json
import sys
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


posts = json.loads((ROOT / "public" / "blog_posts.json").read_text(encoding="utf-8"))
by = {p["id"]: p for p in posts}

NP = "https://image.nana-press.com/kaiseki/machine/"
CB = "https://chonborista.com/wp-content/uploads/"
# 記事ID: この記事に表示されていた「機種違い」の画像URL（main）
WRONG_MAIN = {
    "2026-07-13-aobuta": CB + "2026/03/l_karakuri2_90.jpg",                                  # からくりサーカス2
    "2026-08-03-bancho-otokonoritadaki-99": CB + "2026/05/ps_yjkm_kyotai.png",               # スマスロ やじきた道中記
    "2026-06-29-mushoku-tensei-pachinko": CB + "2026/04/l_darkhibi_90.jpg",                  # ダークハイビ
    "2026-06-08-birdie-wing": CB + "2026/03/l_otome5_90.jpg",                                # 戦国乙女5
    "2026-06-15-koukaku-kidotai-sac": CB + "repair/2017/07/koukakusamne.jpg",                # 2017年のパチンコ機
    "2026-07-27-sumasuro-lycoris-recoil": NP + "1129/35063/20260325133440_69c365e036a82.jpeg",  # パチンコ版リコリコ
    "2026-07-27-e-sao-alicization-yozora": NP + "490/20230413093834_machine_panel.png",      # スロット版SAO
    "2026-06-22-kabaneri2": NP + "437/20220901123403_machine_panel.png",                     # ルパン三世
    "2026-06-11-e-tokyoghoul-choudekaichougeki": NP + "889/25694/20260317150711_69b8ef8f45b68.jpeg",  # スロット版東京喰種
}
WRONG_SETTING = {
    "2026-07-27-e-sao-alicization-yozora": [  # スロット版SAOの設定画像
        NP + "490/20230507161326.jpeg",
        NP + "490/20230714194430.jpeg",
        NP + "490/20230507172613.jpeg",
        NP + "490/report/20230519191142_report.jpeg",
    ],
    "2026-06-11-e-tokyoghoul-choudekaichougeki": [NP + "889/20260312143135.jpeg"],  # スロット版東京喰種の獲得示唆
}
DEAD_RELATIVE = "/component/img/settei_suisoku.jpg"  # 本番で404（chonboristaサイト相対パス）

print("[T1] 9記事が存在する")
for pid in WRONG_MAIN:
    ok(pid in by, f"T1 {pid} が存在")

print("[T2] 9記事に既知の誤main imageが無い")
for pid, url in WRONG_MAIN.items():
    ok(by[pid]["image"] != url, f"T2 {pid} の main が誤画像でない")

print("[T3] eSAO: 誤setting imagesが無い（スロット版SAOの5枚）")
e = by["2026-07-27-e-sao-alicization-yozora"]
urls = [s["url"] for s in e["setting_images"]]
ok(all(u not in urls for u in WRONG_SETTING[e["id"]]), "T3a スロット版SAOの設定画像4枚が無い")
ok(DEAD_RELATIVE not in urls, "T3b 表示できない相対パス設定画像が無い")
ok(e["setting_images"] == [], "T3c eSAO の setting_images が空")

print("[T4] e東京喰種: 誤setting imageが無い")
t = by["2026-06-11-e-tokyoghoul-choudekaichougeki"]
turls = [s["url"] for s in t["setting_images"]]
ok(WRONG_SETTING[t["id"]][0] not in turls, "T4a スロット版東京喰種の獲得示唆画像が無い")
ok(all(not u.startswith("/component/") for u in turls), "T4b 表示できない相対パス設定画像が無い")

print("[T5] 9記事に新規の外部画像URLが無い（空 or 承認済みパスのみ）")
for pid in WRONG_MAIN:
    p = by[pid]
    allu = V.collect_post_image_urls(p)
    ok(all(V.is_approved_image_url(u) for u in allu), f"T5 {pid}: 画像は空または承認済みのみ（{len(allu)}件）")
    ok(p["image"] == "" or V.is_approved_image_url(p["image"]), f"T5 {pid}: main は空または承認済み")

print("[T6] frontend が画像なしを安全に扱う（描画条件の静的確認）")
lst = (ROOT / "app" / "blog" / "blog-client.tsx").read_text(encoding="utf-8")
det = (ROOT / "app" / "blog" / "[slug]" / "page.tsx").read_text(encoding="utf-8")
ok("post.image && (" in lst, "T6a 一覧: image が空ならサムネイルを描画しない")
ok("post.image && (" in det, "T6b 詳細: image が空ならメイン画像を描画しない")
ok("post.setting_images && post.setting_images.length > 0" in det, "T6c 詳細: setting_images が空なら設定画像セクションを描画しない")
meta_files = [ROOT / "app" / "blog" / "page.tsx", ROOT / "app" / "sitemap.ts"]
ok(all("post.image" not in f.read_text(encoding="utf-8") and ".image" not in f.read_text(encoding="utf-8") for f in meta_files),
   "T6d メタデータ/sitemapが記事画像URLを生成しない")
ok(isinstance(by["2026-07-16-sumasuro-juuou"]["image"], str) and by["2026-07-16-sumasuro-juuou"]["image"] == "",
   "T6e 既存の画像なし記事(獣王)と同じ表現 image='' を使っている")
for pid in WRONG_MAIN:
    ok(isinstance(by[pid]["image"], str) and isinstance(by[pid]["setting_images"], list), f"T6f {pid}: image は文字列、setting_images は配列のまま")

print("[T7] legacy baseline が現在のusageと整合")
base = V.load_legacy_image_baseline()
used_unapproved = {u for p in posts for u in V.collect_post_image_urls(p) if not V.is_approved_image_url(u)}
ok(base == used_unapproved, f"T7a baseline == 現行データの未承認URL集合（distinct {len(base)}）")
bj = json.loads((HERE / "blog_image_legacy_baseline.json").read_text(encoding="utf-8"))
ok(bj["count"] == len(bj["urls"]) == len(base), "T7b baseline の count と URL 数が一致")
for pid, url in WRONG_MAIN.items():
    still = any(url in V.collect_post_image_urls(q) for q in posts)
    ok((url in base) == still, f"T7c {pid} の旧URLは、他記事で使用中なら保持／未使用なら削除（使用中={still}）")
ok(DEAD_RELATIVE in base and any(DEAD_RELATIVE in V.collect_post_image_urls(q) for q in posts), "T7d 他記事で使用中の相対URLは baseline に保持")

print("[T8] 外部画像の自動取得が復活していない")
src = (HERE / "verify_blog.py").read_text(encoding="utf-8")
ok(all(not hasattr(V, n) for n in ("fetch_and_patch_images", "fetch_html", "extract_og_image", "ANALYSIS_PAGES", "search_nanapress_id")),
   "T8a 画像取得関数/定数が無い")
ok("urllib" not in src and "nana-press.com" not in src and "chonborista.com" not in src, "T8b verify_blog.py が外部サイトを参照しない")

print("[T9] P-WORLD関連データが復活していない")
ok(not (ROOT / "public" / ("machine" + "_specs.json")).exists(), "T9a P-WORLD由来の機種スペックJSONが公開物に無い")
ok(not (ROOT / "scripts" / ("fetch_machine" + "_specs.py")).exists(), "T9b P-WORLD取得スクリプトが無い")
ok(all("pworld_url" not in json.dumps(p, ensure_ascii=False) for p in posts), "T9c blog_posts.json に pworld_url が無い")

print("[T10] 記事の他項目が空画像化の影響を受けていない（構造）")
need = {"id", "title", "date", "author", "tags", "summary", "image", "setting_images", "content"}
ok(len(posts) == 62 and all(need <= set(p) for p in posts), f"T10a 全{len(posts)}記事が必要キーを保持")
for pid in WRONG_MAIN:
    ok(len(by[pid]["content"]) > 500 and "基本スペック" in by[pid]["content"], f"T10b {pid}: 本文が保持されている")

print(f"\n{'=' * 50}\nPASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
