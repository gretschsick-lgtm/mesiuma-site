#!/usr/bin/env python3
"""
ブログ記事の自動検証 + 自動修正 + 解析サイト画像取得スクリプト

使い方:
  python scripts/verify_blog.py                       # 全記事を検証（チェックのみ）
  python scripts/verify_blog.py --id 2026-05-10-x    # 特定記事のみ
  python scripts/verify_blog.py --auto-fix            # 検証 + 誤記を自動修正
  python scripts/verify_blog.py --fetch-images        # 解析サイトから画像を取得してJSONに反映
  python scripts/verify_blog.py --auto-fix --fetch-images  # 全部まとめて実行
"""
import json
import re
import sys
import urllib.request
import urllib.parse
import time
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
BLOG_PATH = ROOT / "public" / "blog_posts.json"

# ─── 既知の正誤マップ ───────────────────────────────────────────
# (誤り, 正しい表記, 対象機種または "all")
# ★ 新機種追加時はここに追記すること
KNOWN_ERRORS: list[tuple[str, str, str]] = [
    # メーカー誤記
    ("SANKYO",              "サミー",                      "カバネリ"),
    # AT・特化ゾーン名
    ("憑喰RUSH",            "東京喰種咬（かみつき）",        "東京喰種"),
    ("隻眼のRUSH",          "隻眼の梟（せきがんのふくろう）", "東京喰種"),
    ("喰種ハンター",        "レミニセンス",                  "東京喰種"),
    ("FINAL CIRCUS",        "超からくりサーカス",            "からくりサーカス"),
    ("神々の軌跡RUSH",      "GOD GAME（GG）",               "ミリオンゴッド"),
    ("ミリオンゴッド ZONE", "SUPER GOD GAME（SGG）",        "ミリオンゴッド"),
    ("波多野SG",            "SGラッシュ",                    "モンキーターン"),
    # 純増数
    ("純増約4.5枚/G",       "純増約4.0枚/G",                "北斗転生2"),
    ("純増約4.2枚/G",       "純増約7.6枚/G",                "からくりサーカス"),
]

# ─── 機種別ファクトチェック ──────────────────────────────────────
# ★ 新機種追加時はここにも追記すること
MACHINE_FACTS: dict[str, dict] = {
    "東京喰種": {
        "must_contain":     ["東京喰種咬", "BITES", "百足覚醒", "隻眼の梟", "裏AT"],
        "must_not_contain": ["憑喰RUSH", "隻眼のRUSH", "喰種ハンター（CZ）"],
        "maker": "フィールズ/スパイキー（CROSSALPHA）",
        "at_name": "東京喰種咬（かみつき）",
    },
    "からくりサーカス": {
        "must_contain":     ["超からくりサーカス", "純増約7.6枚/G"],
        "must_not_contain": ["FINAL CIRCUS（FC）", "純増約4.2枚"],
        "maker": "SANKYO",
        "at_name": "超からくりサーカス",
    },
    "ミリオンゴッド": {
        "must_contain":     ["GOD GAME", "SUPER GOD GAME"],
        "must_not_contain": ["神々の軌跡RUSH", "ミリオンゴッド ZONE"],
        "maker": "ミズホ",
        "at_name": "GOD GAME（GG）",
    },
    "モンキーターンV": {
        "must_contain":     ["SGラッシュ", "青島SG"],
        "must_not_contain": ["波多野SG", "SG RUSH（波多野"],
        "maker": "山佐（YAMASA）",
    },
    "カバネリ": {
        "must_contain":     ["サミー"],
        "must_not_contain": ["SANKYO"],
        "maker": "サミー",
    },
    "北斗転生2": {
        "must_contain":     ["闘神演舞"],
        "must_not_contain": ["純増約4.5枚/G"],
        "maker": "サミー",
    },
    "バイオハザードRE:3": {
        "must_contain":     ["スパイクチャンシー", "BINGO"],
        "must_not_contain": [],
        "maker": "エレコ",
    },
    "SAO": {
        "must_contain":     ["フルダイブ"],
        "must_not_contain": [],
        "maker": "バンナム",
    },
}

# ─── P-WORLD 機種ID（メイン画像取得に使用）─────────────────────
# ★ 新機種追加時はここにも追記すること
# 画像URL: https://idn.p-world.co.jp/machines/{id}/image/thumb_1.jpg
PWORLD_IDS: dict[str, int] = {
    "SAO2":              10483,
    "ソードアートオンラインII": 10483,
    "花の慶次":          10490,
    "バイオハザードRE:3": 10434,
    "東京喰種":          10040,
    "ミリオンゴッド":    10156,
    "モンキーターンV":   10021,
    "カバネリ":           9760,
    "北斗転生2":         10227,
    "からくりサーカス":  10316,
    "賭ケグルイ":        10460,
}

PWORLD_IMAGE_URL = "https://idn.p-world.co.jp/machines/{id}/image/thumb_1.jpg"
PWORLD_SEARCH    = "https://www.p-world.co.jp/machine/database/search.php?keyword={query}&category=all"

# ─── 解析サイト画像ページ（設定示唆画像用 / nana-press）─────────────
# ★ 新機種追加時にURLも追記すること
ANALYSIS_PAGES: dict[str, list[str]] = {
    "東京喰種":        ["https://nana-press.com/kaiseki/machine/889/"],
    "からくりサーカス": ["https://nana-press.com/kaiseki/machine/571/"],
    "ミリオンゴッド":  ["https://nana-press.com/kaiseki/machine/1116/"],
    "モンキーターンV": ["https://nana-press.com/kaiseki/machine/644/"],
    "カバネリ":        ["https://nana-press.com/kaiseki/machine/437/"],
    "北斗転生2":       ["https://nana-press.com/kaiseki/machine/1059/"],
    "バイオハザードRE:3": ["https://nana-press.com/kaiseki/machine/1140/"],
    "SAO":             ["https://nana-press.com/kaiseki/machine/1161/"],
}

# ─── nana-press 機種一覧ページ（設定示唆画像検索） ───────────────
NANAPRESS_SEARCH = "https://nana-press.com/kaiseki/machine/?keyword={query}"


def fetch_html(url: str, timeout: int = 12) -> str:
    """URLからHTMLを取得。失敗時は空文字列を返す。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} ({e})")
        return ""


def extract_og_image(html: str) -> str | None:
    """OGP画像URLを取得。"""
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
    return m.group(1) if m else None


def extract_nanapress_images(html: str) -> list[dict]:
    """nana-pressの解析ページから設定示唆・プレミア画像URLを抽出。"""
    imgs = []
    # <figure> 内の <img> + <figcaption>
    for m in re.finditer(
        r'<figure[^>]*>.*?<img[^>]+src=["\']([^"\']+)["\'][^>]*>.*?<figcaption[^>]*>(.*?)</figcaption>.*?</figure>',
        html, re.DOTALL
    ):
        url = m.group(1)
        caption = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if url.startswith("http") and caption:
            imgs.append({"url": url, "caption": caption})
    # <img> with alt containing "設定" or "プレミア" etc.
    if not imgs:
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]+alt=["\']([^"\']*(?:設定|プレミア|示唆|確定)[^"\']*)["\']', html):
            imgs.append({"url": m.group(1), "caption": m.group(2)})
    return imgs[:8]  # 最大8枚


def search_nanapress_id(machine_keyword: str) -> str | None:
    """nana-pressでキーワード検索して機種ページURLを返す。"""
    query = urllib.parse.quote(machine_keyword)
    url = NANAPRESS_SEARCH.format(query=query)
    html = fetch_html(url)
    if not html:
        return None
    m = re.search(r'href=["\'](https://nana-press\.com/kaiseki/machine/\d+/)["\']', html)
    return m.group(1) if m else None


def auto_fix_content(content: str, title: str, pid: str) -> tuple[str, list[str]]:
    """KNOWN_ERRORSに基づき本文を自動修正。変更したログも返す。"""
    fixes = []
    for wrong, correct, machine in KNOWN_ERRORS:
        if machine != "all":
            if machine.lower() not in title.lower() and machine.lower() not in pid.lower():
                continue
        if wrong in content:
            # からくりサーカスのSANKYOは正しいので修正しない
            if wrong == "SANKYO" and machine == "からくりサーカス":
                continue
            content = content.replace(wrong, correct)
            fixes.append(f"  ✏️  修正: '{wrong}' → '{correct}'")
    return content, fixes


def fetch_pworld_image(title: str, pid: str) -> str | None:
    """
    P-WORLD から機種のメイン画像URLを取得。
    1) PWORLD_IDS の既知IDを使用
    2) 見つからなければ P-WORLD で検索してIDを取得
    DMMは使用しない。
    """
    # 既知IDから検索
    for key, mid in PWORLD_IDS.items():
        if key.lower() in title.lower() or key.lower() in pid.lower():
            img_url = PWORLD_IMAGE_URL.format(id=mid)
            print(f"  🌐 P-WORLD 画像: {img_url}")
            # 実在確認
            try:
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status == 200:
                        return img_url
            except Exception:
                pass

    # P-WORLD 検索
    machine_guess = re.sub(
        r'(スマスロ|パチスロ|スペック|解説|完全|まとめ|基本|天井|AT性能|RUSH|パチスロ|スロット|パチンコ|PA|【|】|｜.*)',
        '', title
    ).strip()
    if machine_guess and len(machine_guess) > 3:
        query = urllib.parse.quote(machine_guess)
        search_url = PWORLD_SEARCH.format(query=query)
        html = fetch_html(search_url)
        # P-WORLDの機種IDを抽出
        m = re.search(r'/machine/database/(\d+)', html)
        if m:
            mid = int(m.group(1))
            img_url = PWORLD_IMAGE_URL.format(id=mid)
            print(f"  🔍 P-WORLD 検索発見 (id={mid}): {img_url}")
            try:
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status == 200:
                        return img_url
            except Exception:
                pass

    return None


def fetch_and_patch_images(post: dict) -> tuple[str | None, list[dict]]:
    """
    P-WORLD からメイン画像、nana-press から設定示唆画像を取得。
    DMMは使用しない。
    戻り値: (main_image_url, setting_images_list)
    """
    title = post.get("title", "")
    pid   = post.get("id", "")

    # ── メイン画像は P-WORLD 優先
    og_image = fetch_pworld_image(title, pid)

    # ── 設定示唆画像は nana-press から
    setting_imgs: list[dict] = []
    for machine_key, urls in ANALYSIS_PAGES.items():
        if machine_key.lower() not in title.lower() and machine_key.lower() not in pid.lower():
            continue
        for url in urls:
            print(f"  📷 設定示唆画像: {url}")
            html = fetch_html(url)
            if not html:
                continue
            setting_imgs = extract_nanapress_images(html)
            # メイン画像がまだない場合のみ nana-press の OG 画像を使用
            if not og_image:
                og_image = extract_og_image(html)
            time.sleep(0.5)
            break
        if setting_imgs:
            break

    # nana-press の ANALYSIS_PAGES にない機種は検索
    if not setting_imgs:
        machine_guess = re.sub(
            r'(スマスロ|パチスロ|スペック|解説|完全|まとめ|基本|天井|AT性能|RUSH|パチスロ|スロット|パチンコ|PA|【|】|｜.*)',
            '', title
        ).strip()
        if machine_guess and len(machine_guess) > 3:
            found_url = search_nanapress_id(machine_guess)
            if found_url:
                print(f"  🔍 nana-press発見: {found_url}")
                html = fetch_html(found_url)
                setting_imgs = extract_nanapress_images(html)
                if not og_image:
                    og_image = extract_og_image(html)
                time.sleep(0.5)

    return og_image, setting_imgs


def verify_post(post: dict) -> list[str]:
    """記事を検証し、エラーリストを返す（修正は行わない）。"""
    errors = []
    content = post.get("content", "")
    title   = post.get("title", "")
    pid     = post.get("id", "")

    for wrong, correct, machine in KNOWN_ERRORS:
        if machine != "all":
            if machine.lower() not in title.lower() and machine.lower() not in pid.lower():
                continue
        if wrong == "SANKYO" and machine == "からくりサーカス":
            continue
        if wrong in content:
            errors.append(f"❌ 誤記: '{wrong}' → 正しくは '{correct}'")

    for machine_key, facts in MACHINE_FACTS.items():
        if machine_key.lower() not in title.lower() and machine_key.lower() not in pid.lower():
            continue
        for must in facts.get("must_contain", []):
            if must not in content:
                errors.append(f"⚠️  [{machine_key}] 必須表記なし: '{must}'")
        for must_not in facts.get("must_not_contain", []):
            if must_not in content:
                errors.append(f"❌  [{machine_key}] 誤記あり: '{must_not}'")

    return errors


def main():
    parser = argparse.ArgumentParser(description="ブログ記事の自動検証・修正・画像取得")
    parser.add_argument("--id",           help="対象記事ID（省略で全記事）")
    parser.add_argument("--auto-fix",     action="store_true", help="誤記を自動修正してJSONを上書き")
    parser.add_argument("--fetch-images", action="store_true", help="解析サイトから画像を取得してJSONに反映")
    args = parser.parse_args()

    posts: list[dict] = json.loads(BLOG_PATH.read_text(encoding="utf-8"))

    if args.id:
        targets = [p for p in posts if p.get("id") == args.id]
        if not targets:
            print(f"記事が見つかりません: {args.id}")
            sys.exit(1)
    else:
        targets = posts

    changed   = False
    total_err = 0

    for post in targets:
        pid   = post.get("id", "")
        title = post.get("title", "")
        print(f"\n[{pid}] {title[:60]}")

        # ── 自動修正 ──
        if args.auto_fix:
            new_content, fixes = auto_fix_content(post.get("content", ""), title, pid)
            if fixes:
                post["content"] = new_content
                changed = True
                for f in fixes:
                    print(f)
            else:
                print("  ✅ 修正対象なし")

        # ── 検証 ──
        errors = verify_post(post)
        if errors:
            total_err += len(errors)
            for e in errors:
                print(f"  {e}")
        else:
            print("  ✅ 検証OK")

        # ── 画像取得 ──
        if args.fetch_images:
            has_image     = bool(post.get("image"))
            has_si        = bool(post.get("setting_images"))
            if not has_image or not has_si:
                og, imgs = fetch_and_patch_images(post)
                if og and not has_image:
                    post["image"] = og
                    changed = True
                    print(f"  🖼  メイン画像セット: {og[:80]}")
                if imgs and not has_si:
                    post["setting_images"] = imgs
                    changed = True
                    print(f"  🖼  設定示唆画像: {len(imgs)}枚追加")
                if not og and not imgs:
                    print("  ⚠️  画像取得できず（解析ページを確認してください）")
            else:
                print("  📷 画像は既に設定済み")

    # ── 保存 ──
    if changed:
        BLOG_PATH.write_text(
            json.dumps(posts, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n✅ blog_posts.json を更新しました")

    print(f"\n{'='*60}")
    print(f"検証完了: {len(targets)}記事, 残存エラー {total_err}件")
    if total_err > 0 and not args.auto_fix:
        sys.exit(1)


if __name__ == "__main__":
    main()
