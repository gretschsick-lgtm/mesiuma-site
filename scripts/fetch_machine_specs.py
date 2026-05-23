#!/usr/bin/env python3
"""
P-World (p-world.co.jp) パチスロ機種データベースから
スペック情報（機械割・確率・天井）を収集して public/machine_specs.json に保存する。

収集内容:
  - 機種名・メーカー・導入日
  - 設定別機械割・CZ/AT初当り確率
  - 天井情報（ゲーム数天井・スルー天井・AT間天井）
  - AT純増・コイン持ち

URL構造:
  機種詳細: https://www.p-world.co.jp/machine/database/{machine_id}
  新台カレンダー: https://www.p-world.co.jp/database/machine/introduce_calendar.cgi?year_month=YYYY-MM
  機種一覧: https://www.p-world.co.jp/_machine/t_machine.cgi?mode=s_spec&is_utf8=1&key={keyword}

Usage:
    python scripts/fetch_machine_specs.py
    python scripts/fetch_machine_specs.py --months 6   # 直近6ヶ月の新台を収集
    python scripts/fetch_machine_specs.py --limit 20   # 最大20機種（テスト用）
    python scripts/fetch_machine_specs.py --ids 9923,10207  # 特定機種のみ
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

MACHINE_SPECS_JSON = Path(__file__).parent.parent / "public/machine_specs.json"
BASE_URL = "https://www.p-world.co.jp"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.p-world.co.jp/",
}

# ──────────────────────────────────────────────
# 既知の人気スマスロ・パチスロ機種ID（P-World DB）
# ──────────────────────────────────────────────
KNOWN_MACHINE_IDS: list[int] = [
    # ─── P-World DB確認済みIDのみ（パチスロ機種）───
    9923,   # スマスロ モンキーターンV（山佐、2023年12月）
    10207,  # L 東京喰種（スパイキー、2025年2月）
    9843,   # Lからくりサーカス（SANKYO、2023年7月）
    10399,  # スマスロ 甲鉄城のカバネリ 海門決戦（サミー、2026年3月）
    10370,  # スマスロ 北斗の拳 転生の章2（サミー、2026年1月）
    # ─── 以下は月次カレンダーから自動取得（IDはweb確認後に追加）───
]


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_html(url: str, retries: int = 2) -> str:
    """URLからHTMLを取得（EUC-JPデコード対応）"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                raw = resp.read()
                # EUC-JP → UTF-8変換を試みる
                for enc in ("euc-jp", "utf-8", "shift_jis"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="replace")
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
                continue
            log(f"  ⚠️  {url}: {e}")
            return ""
    return ""


def _clean(text: str) -> str:
    """HTMLタグ・余分な空白を除去"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_machine_page(html: str, machine_id: int) -> dict | None:
    """P-World機種詳細ページからスペックを抽出"""
    if not html or len(html) < 500:
        return None

    spec: dict = {
        "id": machine_id,
        "pworld_url": f"https://www.p-world.co.jp/machine/database/{machine_id}",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # ──────────────────────────────────────────────
    # 機種名
    # ──────────────────────────────────────────────
    m = re.search(r'<h1[^>]*>([^<]{3,60})</h1>', html)
    if m:
        spec["name"] = _clean(m.group(1))
    else:
        # titleタグから取得
        m = re.search(r'<title>([^|<]+)', html)
        if m:
            spec["name"] = _clean(m.group(1)).replace("| P-WORLD", "").strip()

    if not spec.get("name"):
        return None

    # ──────────────────────────────────────────────
    # メーカー・導入日（#spec セクション or dl要素）
    # ──────────────────────────────────────────────
    maker_m = re.search(r'メーカー[^\w]*</[^>]+>\s*<[^>]+>([^<]{2,30})</[^>]+>', html)
    if maker_m:
        spec["maker"] = _clean(maker_m.group(1))

    date_m = re.search(r'(?:導入日|稼動開始)[^\w]*</[^>]+>\s*<[^>]+>([0-9年月日\s]+)</[^>]+>', html)
    if date_m:
        spec["release_date"] = _clean(date_m.group(1))

    # ──────────────────────────────────────────────
    # 設定別機械割テーブル（#spec 内のtableを解析）
    # ──────────────────────────────────────────────
    # spec セクション抽出
    spec_sec_m = re.search(r'id=["\']spec["\'][^>]*>(.*?)(?:id=["\'](?:how_to|action|analysis|peak)["\'])', html, re.DOTALL)
    spec_html = spec_sec_m.group(1) if spec_sec_m else html

    # table要素抽出
    tables = re.findall(r'<table[^>]*>(.*?)</table>', spec_html, re.DOTALL)

    settings_data: list[dict] = []
    for table_html in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if len(rows) < 3:
            continue

        # ヘッダー行を取得
        headers_raw = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', rows[0], re.DOTALL)
        headers = [_clean(h).replace('\n', '').strip() for h in headers_raw]

        if not headers or '設定' not in headers[0] and '設定' not in ' '.join(headers[:3]):
            continue

        # データ行をパース
        for row in rows[1:]:
            cells_raw = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
            cells = [_clean(c) for c in cells_raw]
            if not cells:
                continue

            # 設定番号を特定
            setting_num = None
            for c in cells[:2]:
                if re.match(r'^[1-6L]$', c):
                    setting_num = c
                    break
            if not setting_num:
                continue

            row_data: dict = {"setting": setting_num}

            # 各列をヘッダーに対応させる
            for i, (h, v) in enumerate(zip(headers, cells)):
                if i == 0:
                    continue  # 設定列スキップ
                if v and v != "-":
                    # 機械割（出玉率）
                    if any(kw in h for kw in ["出玉率", "機械割", "払出率"]):
                        row_data["payout"] = v
                    # AT初当り
                    elif any(kw in h for kw in ["AT", "ART"]):
                        row_data["at_prob"] = v
                    # CZ確率
                    elif "CZ" in h:
                        row_data["cz_prob"] = v
                    # ボーナス確率
                    elif any(kw in h for kw in ["ボーナス", "BB", "RB"]):
                        row_data[f"bonus_{i}"] = v
                    else:
                        row_data[f"col_{h[:10]}"] = v

            if len(row_data) >= 2:
                settings_data.append(row_data)

        if settings_data:
            break  # 最初の有効なテーブルのみ使用

    if settings_data:
        spec["settings"] = settings_data

        # 設定1・6の要約を separate フィールドとして追加（ブログ参照用）
        s1 = next((s for s in settings_data if s.get("setting") == "1"), None)
        s6 = next((s for s in settings_data if s.get("setting") == "6"), None)
        if s1:
            spec["setting1_payout"] = s1.get("payout", "")
            spec["setting1_at"] = s1.get("at_prob", "")
        if s6:
            spec["setting6_payout"] = s6.get("payout", "")
            spec["setting6_at"] = s6.get("at_prob", "")

    # ──────────────────────────────────────────────
    # 天井情報（#peak セクション）
    # ──────────────────────────────────────────────
    peak_sec_m = re.search(r'id=["\']peak["\'][^>]*>(.*?)(?:id=["\'](?:surmise|at_art|bbs)["\'])', html, re.DOTALL)
    if peak_sec_m:
        peak_html = peak_sec_m.group(1)
        peak_text = _clean(peak_html)

        # dl/dtパターンで天井情報を抽出
        dt_dd_pairs = re.findall(r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', peak_html, re.DOTALL)
        ceilings: dict = {}
        for dt, dd in dt_dd_pairs:
            key = _clean(dt)
            val = _clean(dd)
            if key and val and len(key) < 50:
                ceilings[key] = val

        if ceilings:
            spec["ceilings"] = ceilings

        # 天井G数を直接抽出（数値パターン）
        g_nums = re.findall(r'(\d{3,4})\s*G', peak_text)
        if g_nums:
            spec["ceiling_values"] = sorted(set(int(g) for g in g_nums if 50 <= int(g) <= 5000))

    # ──────────────────────────────────────────────
    # AT/ART情報（#at_art セクション）
    # ──────────────────────────────────────────────
    at_sec_m = re.search(r'id=["\']at_art["\'][^>]*>(.*?)(?:id=["\']bbs["\']|</div>)', html, re.DOTALL)
    if at_sec_m:
        at_text = _clean(at_sec_m.group(1))
        # 純増枚数
        pure_m = re.search(r'純増[：:]\s*約?\s*([\d.]+)\s*枚', at_text)
        if pure_m:
            spec["at_pure_increase"] = pure_m.group(1) + "枚/G"
        # コイン持ち
        coin_m = re.search(r'コイン持ち[^0-9]*([\d]+)\s*G', at_text)
        if coin_m:
            spec["coin_持ち"] = coin_m.group(1) + "G/50枚"

    return spec


def get_machine_ids_from_calendar(months: int = 3) -> list[int]:
    """月次新台カレンダーから機種IDを収集"""
    ids: set[int] = set()
    now = datetime.now(timezone.utc)

    for i in range(months):
        target = now - timedelta(days=30 * i)
        year_month = target.strftime("%Y-%m")
        url = f"{BASE_URL}/database/machine/introduce_calendar.cgi?year_month={year_month}"
        log(f"  📅 カレンダー取得: {year_month}")
        html = fetch_html(url)
        if not html:
            continue

        # パチスロのみ（スロット機種のリンク）
        found = re.findall(r'/machine/database/(\d+)', html)
        for mid in found:
            ids.add(int(mid))

        time.sleep(1)

    log(f"  📋 カレンダーから {len(ids)} 機種IDを取得")
    return list(ids)


def get_machine_ids_by_keyword(keyword: str) -> list[int]:
    """キーワード検索で機種IDを収集"""
    ids: set[int] = set()
    start = 0
    while True:
        url = (
            f"{BASE_URL}/_machine/t_machine.cgi"
            f"?mode=s_spec&is_utf8=1"
            f"&key={urllib.parse.quote(keyword)}"
            f"&aflag=1&start={start}"
        )
        html = fetch_html(url)
        if not html:
            break
        found = re.findall(r'/machine/database/(\d+)', html)
        if not found:
            break
        ids.update(int(m) for m in found)
        if len(found) < 50:
            break
        start += 50
        time.sleep(1)
    return list(ids)


def main():
    import urllib.parse

    parser = argparse.ArgumentParser(description="P-World機種スペック収集")
    parser.add_argument("--months", type=int, default=3, help="直近N ヶ月の新台を収集")
    parser.add_argument("--limit",  type=int, default=0,  help="最大取得機種数（0=無制限）")
    parser.add_argument("--ids",    type=str, default="", help="カンマ区切りの機種ID（個別指定）")
    parser.add_argument("--known-only", action="store_true", help="既知機種リストのみ（カレンダー取得しない）")
    args = parser.parse_args()

    # ──────────────────────────────────────────────
    # 収集対象IDを決定
    # ──────────────────────────────────────────────
    target_ids: set[int] = set(KNOWN_MACHINE_IDS)

    if args.ids:
        for raw in args.ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                target_ids.add(int(raw))

    if not args.known_only:
        calendar_ids = get_machine_ids_from_calendar(args.months)
        target_ids.update(calendar_ids)

    id_list = sorted(target_ids)
    if args.limit and args.limit > 0:
        id_list = id_list[:args.limit]

    log(f"🎰 収集対象: {len(id_list)} 機種")

    # ──────────────────────────────────────────────
    # 既存データをロード
    # ──────────────────────────────────────────────
    existing: dict[int, dict] = {}
    if MACHINE_SPECS_JSON.exists():
        with open(MACHINE_SPECS_JSON, encoding="utf-8") as f:
            try:
                for item in json.load(f):
                    existing[item["id"]] = item
            except (json.JSONDecodeError, KeyError):
                pass

    log(f"📂 既存データ: {len(existing)} 機種")

    # ──────────────────────────────────────────────
    # スクレイピング
    # ──────────────────────────────────────────────
    results: list[dict] = []
    new_count = 0
    update_count = 0

    for i, mid in enumerate(id_list, 1):
        url = f"{BASE_URL}/machine/database/{mid}"
        log(f"  [{i}/{len(id_list)}] ID={mid} {url}")
        html = fetch_html(url)
        spec = parse_machine_page(html, mid)

        if spec:
            name = spec.get("name", "不明")
            payout1 = spec.get("setting1_payout", "-")
            payout6 = spec.get("setting6_payout", "-")
            ceilings = spec.get("ceiling_values", [])
            log(f"    ✅ {name} | 設定1:{payout1} 設定6:{payout6} | 天井G:{ceilings}")

            if mid in existing:
                update_count += 1
            else:
                new_count += 1
            results.append(spec)
        else:
            log(f"    ⚠️  スペック取得失敗（ID={mid}）")
            # 既存データがあれば保持
            if mid in existing:
                results.append(existing[mid])

        time.sleep(1.5)

    # ──────────────────────────────────────────────
    # 保存（パチスロのみフィルタリング可能）
    # ──────────────────────────────────────────────
    results.sort(key=lambda x: x.get("release_date", ""), reverse=True)

    MACHINE_SPECS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(MACHINE_SPECS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log(f"\n✅ 完了: {len(results)} 機種保存")
    log(f"   新規: {new_count}件 / 更新: {update_count}件")
    log(f"   保存先: {MACHINE_SPECS_JSON}")


if __name__ == "__main__":
    main()
