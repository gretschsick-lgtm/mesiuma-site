#!/usr/bin/env python3
"""
ブログ記事の自動検証 + 誤記の自動修正スクリプト

使い方:
  python scripts/verify_blog.py                       # 全記事を検証（チェックのみ）
  python scripts/verify_blog.py --id 2026-05-10-x    # 特定記事のみ
  python scripts/verify_blog.py --auto-fix            # 検証 + 誤記を自動修正

画像について（BLOG-DATA-SOURCE-SAFETY-FIX-1）:
  第三者サイト（解析サイト等）から画像URLを自動取得・自動採用する処理は停止している。
  `--fetch-images` は後方互換のため受け付けるが何もしない（無効）。
  ブログ画像は「明示的に承認された出所のみ」許可する（下記 IMAGE_POLICY 参照）。
"""
import json
import re
import sys
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
    ("FINAL CIRCUS",        "超からくりサーカス",            "からくりサーカス(?!2)"),
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
    "からくりサーカス(?!2)": {
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
    "化物語": {
        "must_contain":     ["血闘ノ刻", "特別ノ刻"],
        "must_not_contain": [],
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
    "超デカ超一撃": {
        "must_contain":     ["HYPER喰種RUSH", "喰MAXループ"],
        "must_not_contain": [],
        "maker": "ビスティ",
    },
    "ダークハイビ": {
        "must_contain":     ["ダークハイビモード", "BIG BONUS"],
        "must_not_contain": [],
        "maker": "パイオニア（ピーセカンド）",
    },
    "からくりサーカス2": {
        "must_contain":     ["超からくりサーカス", "機械仕掛けの女神"],
        "must_not_contain": [],
        "maker": "SANKYO",
        "at_name": "超からくりサーカス",
    },
    "戦国コレクション6": {
        "must_contain":     ["時幻城RUSH", "夢幻回廊"],
        "must_not_contain": [],
        "maker": "コナミアミューズメント",
    },
    "一方通行.*最狂": {
        "must_contain":     ["アクセラレータOVER RUSH", "最狂ジャッジメント"],
        "must_not_contain": [],
        "maker": "オレンジ",
    },
    "リコリス・リコイル": {
        "must_contain":     ["SPECIAL LycoReco RUSH", "ULTIMATE DRIVE"],
        "must_not_contain": [],
        "maker": "ニューギン",
    },
    "見える子ちゃん": {
        "must_contain":     ["神判ノ刻", "祈願チャレンジ", "見える子カウンター"],
        "must_not_contain": [],
        "maker": "パイオニア",
    },
    "七つの大罪3": {
        "must_contain":     ["SEVEN RUSH", "PERFECT BONUS"],
        "must_not_contain": [],
        "maker": "サミー",
    },
}

# ─── 画像ポリシー（明示的に承認された出所のみ）──────────────────
# ブログ記事の画像（`image` / `setting_images[].url`）として許可するのは、
# 自社サイトが配信する次のパス配下のみ。第三者サイトのURLを自動で採用しない。
# ★ 新しい出所を承認する場合は、権利・利用条件を確認した上でここに明示的に追加すること。
APPROVED_IMAGE_PREFIXES: tuple[str, ...] = (
    "/blog-images/",
)

# 既存記事に残っている「承認されていない出所」の画像URL（置換待ちの既存分）。
# このphaseでは移行・削除しない。置換が完了したらここから削除していくこと。
# このリストに無い未承認URLが新たに入った場合は検証エラーとする。
LEGACY_IMAGE_BASELINE_PATH = Path(__file__).parent / "blog_image_legacy_baseline.json"


def load_legacy_image_baseline(path: Path = LEGACY_IMAGE_BASELINE_PATH) -> set[str]:
    """置換待ちの既存画像URL集合を返す。ファイルが無い/壊れている場合は空集合（=全て未承認扱い）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("urls", []))
    except Exception:
        return set()


def is_approved_image_url(url: str) -> bool:
    """承認済み出所（自社配信の許可パス）か。"""
    if not isinstance(url, str) or not url.startswith(APPROVED_IMAGE_PREFIXES):
        return False
    # パストラバーサル・別ホスト指定・クエリ経由の迂回を許さない
    return ".." not in url and "://" not in url and "\\" not in url


def collect_post_image_urls(post: dict) -> list[str]:
    """記事が参照している画像URL（空文字は除く）。"""
    urls = [post.get("image", "")]
    urls += [(si or {}).get("url", "") for si in (post.get("setting_images") or [])]
    return [u for u in urls if u]


def check_image_policy(post: dict, legacy: set[str] | None = None) -> list[str]:
    """承認されておらず、かつ既存分(baseline)にも無い画像URLを違反として返す。"""
    if legacy is None:
        legacy = load_legacy_image_baseline()
    out = []
    for u in collect_post_image_urls(post):
        if is_approved_image_url(u) or u in legacy:
            continue
        out.append(f"🚫 未承認の画像出所: {u[:80]}")
    return out


def auto_fix_content(content: str, title: str, pid: str) -> tuple[str, list[str]]:
    """KNOWN_ERRORSに基づき本文を自動修正。変更したログも返す。"""
    fixes = []
    for wrong, correct, machine in KNOWN_ERRORS:
        if machine != "all":
            try:
                machine_matched = (
                    re.search(machine, title, re.IGNORECASE) is not None
                    or re.search(machine, pid, re.IGNORECASE) is not None
                )
            except re.error:
                machine_matched = (machine.lower() in title.lower() or machine.lower() in pid.lower())
            if not machine_matched:
                continue
        if wrong in content:
            content = content.replace(wrong, correct)
            fixes.append(f"  ✏️  修正: '{wrong}' → '{correct}'")
    return content, fixes


def verify_post(post: dict) -> list[str]:
    """記事を検証し、エラーリストを返す（修正は行わない）。"""
    errors = []
    content = post.get("content", "")
    title   = post.get("title", "")
    pid     = post.get("id", "")

    for wrong, correct, machine in KNOWN_ERRORS:
        if machine != "all":
            try:
                machine_matched = (
                    re.search(machine, title, re.IGNORECASE) is not None
                    or re.search(machine, pid, re.IGNORECASE) is not None
                )
            except re.error:
                machine_matched = (machine.lower() in title.lower() or machine.lower() in pid.lower())
            if not machine_matched:
                continue
        if wrong in content:
            errors.append(f"❌ 誤記: '{wrong}' → 正しくは '{correct}'")

    for machine_key, facts in MACHINE_FACTS.items():
        try:
            key_matched = (
                re.search(machine_key, title, re.IGNORECASE) is not None
                or re.search(machine_key, pid, re.IGNORECASE) is not None
            )
        except re.error:
            key_matched = (machine_key.lower() in title.lower() or machine_key.lower() in pid.lower())
        if not key_matched:
            continue
        for must in facts.get("must_contain", []):
            if must not in content:
                errors.append(f"⚠️  [{machine_key}] 必須表記なし: '{must}'")
        for must_not in facts.get("must_not_contain", []):
            if must_not in content:
                errors.append(f"❌  [{machine_key}] 誤記あり: '{must_not}'")

    return errors


def main():
    parser = argparse.ArgumentParser(description="ブログ記事の自動検証・誤記修正")
    parser.add_argument("--id",           help="対象記事ID（省略で全記事）")
    parser.add_argument("--auto-fix",     action="store_true", help="誤記を自動修正してJSONを上書き")
    parser.add_argument("--fetch-images", action="store_true",
                        help="【無効】後方互換のため受け付けるが何もしない（第三者画像の自動取得は停止）")
    args = parser.parse_args()

    if args.fetch_images:
        print("ℹ️  --fetch-images は無効です（第三者サイトからの画像自動取得は停止しました）。")

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
    policy_violations = 0
    legacy = load_legacy_image_baseline()

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

        # ── 画像ポリシー（承認出所のみ。画像の自動取得・自動書き換えはしない）──
        violations = check_image_policy(post, legacy)
        if violations:
            policy_violations += len(violations)
            for v in violations:
                print(f"  {v}")

    # ── 保存 ──
    if changed:
        BLOG_PATH.write_text(
            json.dumps(posts, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n✅ blog_posts.json を更新しました")

    print(f"\n{'='*60}")
    print(f"検証完了: {len(targets)}記事, 残存エラー {total_err}件, 画像ポリシー違反 {policy_violations}件")
    if policy_violations > 0:
        # --auto-fix でも許容しない（未承認の出所が新規に入った＝要確認）
        sys.exit(2)
    if total_err > 0 and not args.auto_fix:
        sys.exit(1)


if __name__ == "__main__":
    main()
