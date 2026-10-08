#!/usr/bin/env python3
"""BLOG-FACT-SAFETY-FIX-1 テスト（ネットワーク非依存）。

- スロット記事 ワールドダイスター から、パチンコ版の画像（種別違い）を撤去した状態を固定する。
- 本番で404になる相対パスの設定画像が、どの記事にも残っていないことを固定する。
- 正常に表示される画像・記事本文・他フィールドを巻き込んでいないことを検証する。
"""
import json
import re
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
WD = "2026-07-09-worlddaistar"
PACHINKO_WD_IMAGE = "https://chonborista.com/wp-content/uploads/2026/05/e_worlddiceter_90.webp"  # eワールドダイスター（パチンコ）
DEAD = ["/component/img/settei_suisoku.jpg", "/component/img/settei_suisoku_kanni.jpg"]
# 相対パスの設定画像を撤去した記事 → 撤去後も残るべき（正常表示される）設定画像の件数
KEEP_SETTING = {
    "2026-07-23-mierukochan": 1,
    "2026-07-23-e-nanatsunotaizai3": 0,
    "2026-06-25-nangoku-sodachi-special": 0,
    "2026-06-25-e-tokyorevengers-seiya": 0,
    "2026-06-15-e-lycoris-recoil": 0,
    "2026-06-08-e-bakemonogatari-99": 0,
    "2026-05-21-biohazard-re3": 3,
    "2026-05-14-million-god": 0,
}

print("[F1] ワールドダイスター: スロット記事にパチンコ版画像が無い")
w = by[WD]
ok(re.search(r"スマスロ|L機", " ".join(re.findall(r"機種タイプ\*\*[：:]\s*([^\n]+)", w["content"]))) is not None, "F1a 記事の機種タイプはスロット（スマスロ/L機）")
ok(w["image"] != PACHINKO_WD_IMAGE, "F1b main がパチンコ版画像でない")
ok(w["image"] == "" or V.is_approved_image_url(w["image"]), "F1c main は空または承認済みパスのみ")
ok(all(PACHINKO_WD_IMAGE not in V.collect_post_image_urls(p) for p in posts), "F1d パチンコ版画像がどの記事にも使われていない")
ok(w["setting_images"] == [], "F1e setting_images は空配列のまま")

print("[F2] 本番404の相対パス画像が残っていない")
allu = [u for p in posts for u in V.collect_post_image_urls(p)]
ok(not any(u.startswith("/") and not V.is_approved_image_url(u) for u in allu), "F2a 承認パス以外の相対パスが無い")
ok(not any(d in allu for d in DEAD), "F2b 設定推測ツールの相対パス画像が無い")
base = V.load_legacy_image_baseline()
ok(not any(d in base for d in DEAD), "F2c baseline にも無い")

print("[F3] 正常な画像は巻き込んでいない")
for pid, n in KEEP_SETTING.items():
    p = by[pid]
    ok(len(p["setting_images"]) == n, f"F3a {pid}: 設定画像は {n} 件（正常な画像のみ残る）")
    ok(all(s["url"].startswith("https://") and s.get("caption") for s in p["setting_images"]), f"F3b {pid}: 残る設定画像は絶対URL・キャプションあり")
ok(by["2026-05-21-biohazard-re3"]["image"].startswith("https://"), "F3c バイオRE:3 の main は維持")
ok(by["2026-07-23-mierukochan"]["image"].startswith("https://"), "F3d 見える子ちゃん の main は維持")

print("[F4] 整合性")
need = {"id", "title", "date", "author", "tags", "summary", "image", "setting_images", "content"}
ok(len(posts) == 62 and all(need <= set(p) for p in posts), "F4a 62記事・必要キーを保持")
ok(all(isinstance(p["setting_images"], list) and isinstance(p["image"], str) for p in posts), "F4b image は文字列、setting_images は配列")
used_unapproved = {u for u in allu if not V.is_approved_image_url(u)}
ok(base == used_unapproved, f"F4c baseline == 現行データの未承認URL集合（distinct {len(base)}）")
ok(all(u.startswith("https://") for u in base), "F4d baseline は絶対URLのみ")
ok(len(w["content"]) > 500 and "基本スペック" in w["content"], "F4e ワールドダイスターの本文が保持されている")

print(f"\n{'=' * 50}\nPASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
