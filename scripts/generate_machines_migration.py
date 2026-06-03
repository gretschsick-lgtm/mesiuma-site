"""
機種マスタ拡張データ生成スクリプト
sources: machines.json + store_machines.json + complete_info.json + machines_master.csv
output:  005_machines_expand.sql + series_candidates.csv
"""
from __future__ import annotations
import csv, json, os, re, unicodedata, uuid, sys
from collections import defaultdict

# ── normalize_for_comparison: machine_resolver.py と完全同一 ───────────────
_PREFIX_RE = re.compile(r'^(スマスロ|L|Ｌ|パチスロ|スロット|SLOT)', re.IGNORECASE)

def normalize_for_comparison(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name.strip())
    prev = ""
    while n != prev:
        prev = n
        n = _PREFIX_RE.sub("", n).strip()
    return n.lower().replace(" ", "").replace("\u3000", "")

# ── ノイズフィルタ ─────────────────────────────────────────────────────────
_NOISE_START = re.compile(
    r'^(#|各台|ジャグラーコーナー|スロットコーナー|パチンコ|設置|是非|店舗|'
    r'お客様|機械管理|イベント|ジャンボ|スマパチ|スマスロコーナー|■|【|'
    r'最新|エリア最大|ぱちんこ依存|コーナー|▼|◆|☆|★|↓|◎|●)'
)
# 部分一致ノイズ
_NOISE_CONTAINS = re.compile(
    r'(依存問題|設置機種|導入機種|機種のご案内|好評稼働中|おすすめ機種|'
    r'ありがとう|地域最大|A\+AT機|【真打|ミリオンゴッド／|吉宗／|ジャグラー系／|'
    r'バイオ\/|ご来店ください|お客様応対|機械管理|&#[0-9a-zA-Z]+;|&[a-z]+;|'
    r'&nbsp;|\bst\.\s|のお店$|に色々|も目が|最新台を|最新機種|スマスロコーナー|'
    r'月\d+日|[①-⑳]st\.|nd\.\s|rd\.\s|th\.\s)'
)
# 末尾の … (U+2026) または .. / ... → truncated。単一 . は ver. 等の正規表記なので除外
_TRUNCATED = re.compile(r'(…|\.{2,})$')

def is_valid_name(name: str) -> bool:
    if not name or len(name) < 3:
        return False
    if _NOISE_START.search(name):
        return False
    if _NOISE_CONTAINS.search(name):
        return False
    if _TRUNCATED.search(name):
        return False
    # 数字のみや英字のみの短い文字列はスキップ
    if re.match(r'^[\d\s]+$', name):
        return False
    # HTML エンティティ
    if re.search(r'&[#a-zA-Z]', name):
        return False
    # ランク prefix（1st., 2nd., 13th. 等）
    if re.match(r'^\d+th\.|^\d+st\.|^\d+nd\.|^\d+rd\.', name):
        return False
    # 「のつく日」「3周年」等のキャンペーン文字列
    if re.search(r'のつく日|周年|3月|4月|5月|6月|7月|8月|9月|10月|11月|12月', name):
        return False
    # 日本語の文・センテンス（「が登場」「は閉店」「を導入」等の述語）
    if re.search(r'(が登場|が稼働|を導入|に導入|は閉店|が閉店|でした|します|してい|になり|ました|おります|います)', name):
        return False
    # 末尾が「】」「♪」「!」「！」等（破損・宣伝文）
    if re.search(r'[】♪！☆★]$', name):
        return False
    # 半角スラッシュ含み（複数機種併記 or URL）
    if '/' in name:
        return False
    # 「その他」「バイオシリーズ」「パチスロコーナー」等の説明語
    if re.match(r'^(その他|シリーズ|スマパチ|・スマパチ|バイオシリーズ|遊パチ|スマパチ)', name):
        return False
    return True

# ── 型判定 ─────────────────────────────────────────────────────────────────
def infer_type(name: str, hint: str = "") -> str:
    h = hint.lower()
    if h in ("slot", "パチスロ"):
        return "slot"
    if h in ("pachinko", "パチンコ"):
        return "pachinko"
    n = name
    # パチンコ prefix
    if re.match(r'^(e|E|P|p)[A-Z\u4e00-\u9fff\u30a0-\u30ff\u3040-\u309f]', n):
        return "pachinko"
    if re.match(r'^(デカスタ|PLT)', n):
        return "pachinko"
    return "slot"

# ── シリーズ抽出キーワード ─────────────────────────────────────────────────
SERIES_KEYWORDS = [
    ("北斗の拳",       ["北斗"]),
    ("ジャグラー",      ["ジャグラー"]),
    ("バイオハザード",   ["バイオハザード", "バイオ"]),
    ("牙狼",           ["牙狼"]),
    ("エヴァンゲリオン", ["エヴァ", "エヴァンゲリオン"]),
    ("まどか☆マギカ",  ["まどか", "マギカ"]),
    ("ゴッドイーター",  ["ゴッドイーター"]),
    ("ミリオンゴッド",  ["ミリオンゴッド"]),
    ("ヴァルヴレイヴ",  ["ヴァルヴレイヴ"]),
    ("バジリスク",      ["バジリスク"]),
    ("炎炎ノ消防隊",    ["炎炎"]),
    ("東京喰種",        ["東京喰種", "東京グール"]),
    ("吉宗",            ["吉宗"]),
    ("リゼロ",          ["リゼロ", "Re:ゼロ"]),
    ("カバネリ",        ["カバネリ"]),
    ("沖ドキ",          ["沖ドキ"]),
    ("牙狼",            ["牙狼"]),
    ("機動戦士ガンダム", ["ガンダム"]),
    ("ルパン三世",      ["ルパン"]),
    ("からくりサーカス", ["からくりサーカス"]),
    ("鉄拳",            ["鉄拳"]),
    ("キン肉マン",      ["キン肉マン"]),
    ("リコリス・リコイル", ["リコリス"]),
    ("化物語",          ["化物語"]),
    ("戦国乙女",        ["戦国乙女"]),
    ("大海物語",        ["大海物語", "海物語"]),
    ("転スラ",          ["転生したらスライム", "転スラ"]),
    ("もののがたり",    ["もののがたり"]),
    ("ブルーロック",    ["ブルーロック"]),
    ("アズールレーン",  ["アズールレーン"]),
]

def extract_series(name: str) -> str | None:
    for series, kws in SERIES_KEYWORDS:
        for kw in kws:
            if kw in name:
                return series
    return None

# ── データ収集 ─────────────────────────────────────────────────────────────

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_machines_json() -> list[dict]:
    path = os.path.join(BASE, "public", "machines.json")
    with open(path) as f:
        d = json.load(f)
    rows = []
    for m in d.get("machines", []):
        name = m.get("name", "").strip()
        mtype_raw = m.get("type", "")
        maker = m.get("maker", "") or None
        src_url = m.get("url", "") or None
        if not is_valid_name(name):
            continue
        mtype = "slot" if "スロ" in mtype_raw else "pachinko" if "パチンコ" in mtype_raw else "slot"
        rows.append({"name": name, "type": mtype, "maker": maker, "source_url": src_url})
    return rows

# 正規の機種名プレフィックスパターン（store_machines エントリの品質検証用）
_MACHINE_PREFIX = re.compile(
    r'^(スマスロ|L|Ｌ|LB|LBパチスロ|パチスロ|Lパチスロ|SLOT|'
    r'e|E|P(?!LT激デジ ジューシーハニー極嬢|愛の不時着|結城友奈|えとたま|ハネモノ|ラブ嬢|化物語|大海|野生|花満開)|PA|PLT|デカスタ|'
    r'スーパーリオ|HEY！|バジリスク|Re:|アイム|マイジャグ|ファンキー|ゴーゴー|ハッピー|押忍|'
    r'A-SLOT\+)',
    re.IGNORECASE,
)
# store_machines で許可するプレフィックス（よりシンプル）
_VALID_MACHINE_PREFIX = re.compile(
    r'^(スマスロ[\s　]|L[\s　\w\u30a0-\u30ff\u3040-\u309f\u4e00-\u9fff]|Ｌ|LB|'
    r'パチスロ[\s　]|Lパチスロ|'
    r'e[\u30a0-\u30ff\u3040-\u309f\u4e00-\u9fff\sA-Z86]|'
    r'E[\u30a0-\u30ff\u3040-\u309f\u4e00-\u9fff]|'
    r'P[\u30a0-\u30ff\u3040-\u309f\u4e00-\u9fff]|'
    r'PA[\u30a0-\u30ff\u3040-\u309f\u4e00-\u9fff]|PLT|'
    r'デカスタP|HEY！|Re:|A-SLOT\+|'
    r'(アイムジャグラー|マイジャグラー|ファンキージャグラー|ゴーゴージャグラー|ハッピージャグラー|'
    r'ミスタージャグラー|ウルトラミラクルジャグラー|クレアの秘宝伝|押忍！番長|バジリスク|'
    r'スーパーリオエース|HEY！エリートサラリーマン鏡))',
    re.IGNORECASE,
)


def load_store_machines_json(mj_fullnames: dict[str, dict] | None = None) -> list[dict]:
    """
    store_machines.json の new_machines を収集。
    - explicit type (slot/pachinko) を持つエントリのみ採用
    - 正規プレフィックスで機種名バリデーション
    - truncated 名は mj_fullnames で復元を試みる
    """
    path = os.path.join(BASE, "public", "store_machines.json")
    with open(path) as f:
        d = json.load(f)
    seen = set()
    rows = []
    for info in d.values():
        for m in info.get("new_machines", []):
            name = m.get("name", "").strip()
            mtype_hint = m.get("type", "")

            # type 未設定エントリはスキップ（ノイズが多い）
            if mtype_hint not in ("slot", "pachinko"):
                continue

            # truncated → machines.json で復元
            if _TRUNCATED.search(name) and mj_fullnames:
                prefix = name.rstrip("…. ").strip()
                matches = [
                    full for full in mj_fullnames
                    if unicodedata.normalize("NFKC", full).startswith(
                        unicodedata.normalize("NFKC", prefix)
                    )
                ]
                if matches:
                    name = matches[0]
                else:
                    continue

            if not is_valid_name(name):
                continue
            # 正規機種名プレフィックスチェック
            if not _VALID_MACHINE_PREFIX.match(name):
                continue
            key = normalize_for_comparison(name)
            if key in seen:
                continue
            seen.add(key)
            mtype = infer_type(name, mtype_hint)
            rows.append({"name": name, "type": mtype, "maker": None, "source_url": None})
    return rows

def load_complete_info_json() -> list[dict]:
    path = os.path.join(BASE, "public", "complete_info.json")
    with open(path) as f:
        data = json.load(f)
    seen = set()
    rows = []
    for e in data:
        name = e.get("machine", "").strip()
        if not name or name == "不明":
            continue
        if not is_valid_name(name):
            continue
        key = normalize_for_comparison(name)
        if key in seen:
            continue
        seen.add(key)
        mtype = e.get("machine_type", "") or infer_type(name)
        rows.append({"name": name, "type": mtype, "maker": None, "source_url": None})
    return rows

def load_csv() -> list[dict]:
    path = os.path.join(BASE, "public", "machines_master.csv")
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("official_name", "").strip()
            if not name:
                continue
            maker = row.get("manufacturer", "") or None
            if maker == "要確認":
                maker = None
            brand = row.get("brand", "") or None
            mtype = row.get("type", "slot")
            rows.append({"name": name, "type": mtype, "maker": maker, "brand": brand, "source_url": None})
    return rows

# ── 統合・重複除去 ─────────────────────────────────────────────────────────

def merge_all() -> tuple[list[dict], dict]:
    """
    Returns:
      machines: list of {official_name, type, maker, brand, normalized_name, source_url, series_candidate}
      norm_to_official: normalized → official_name (重複検出用)
    """
    # machines.json フルネーム辞書（truncated復元用）
    mj_path = os.path.join(BASE, "public", "machines.json")
    with open(mj_path) as f:
        mj_fullnames = {m["name"].strip(): m for m in json.load(f).get("machines", []) if m.get("name","").strip()}

    sources = [
        ("csv",            load_csv()),
        ("machines_json",  load_machines_json()),
        ("complete_info",  load_complete_info_json()),
        ("store_machines", load_store_machines_json(mj_fullnames)),
    ]

    seen_norm: dict[str, str] = {}     # normalized → official_name
    seen_official: dict[str, str] = {} # lower(official_name) → official_name
    machines: list[dict] = []
    dup_count = 0
    source_counts = {}

    for src_name, rows in sources:
        added = 0
        duped = 0
        for r in rows:
            name = r["name"]
            norm = normalize_for_comparison(name)
            off_lower = name.lower().replace(" ", "")

            # 正規化名の重複チェック
            if norm in seen_norm:
                duped += 1
                dup_count += 1
                continue
            # official_name 大文字小文字無視重複チェック
            if off_lower in seen_official:
                duped += 1
                dup_count += 1
                continue

            seen_norm[norm] = name
            seen_official[off_lower] = name

            series = extract_series(name)
            machines.append({
                "official_name":    name,
                "type":             r.get("type", "slot"),
                "manufacturer":     r.get("maker"),
                "brand":            r.get("brand"),
                "normalized_name":  norm,
                "source_url":       r.get("source_url"),
                "series_candidate": series,
            })
            added += 1

        source_counts[src_name] = {"added": added, "duped": duped}

    return machines, source_counts, dup_count

# ── SQL 生成 ────────────────────────────────────────────────────────────────

def escape_sql(s):
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"

def generate_sql(machines: list[dict]) -> str:
    lines = [
        "-- =============================================================================",
        "-- 005_machines_expand.sql",
        "-- machines_master 拡張（500機種以上）",
        "--",
        "-- sources: machines.json + store_machines.json + complete_info.json + machines_master.csv",
        "-- ON CONFLICT (official_name) DO NOTHING で冪等",
        "-- normalize_for_comparison() は machine_resolver.py と同一ロジックで生成",
        "-- =============================================================================",
        "",
        "INSERT INTO machines_master",
        "    (official_name, manufacturer, brand, type, normalized_name, source_url, is_active)",
        "VALUES",
    ]

    rows_sql = []
    for m in machines:
        rows_sql.append(
            f"    ({escape_sql(m['official_name'])}, "
            f"{escape_sql(m['manufacturer'])}, "
            f"{escape_sql(m['brand'])}, "
            f"'{m['type']}', "
            f"{escape_sql(m['normalized_name'])}, "
            f"{escape_sql(m['source_url'])}, "
            f"TRUE)"
        )

    lines.append(",\n".join(rows_sql))
    lines.append("ON CONFLICT (official_name) DO NOTHING;")
    return "\n".join(lines)

# ── シリーズ候補 CSV ────────────────────────────────────────────────────────

def generate_series_csv(machines: list[dict]) -> str:
    series_map: dict[str, list[str]] = defaultdict(list)
    for m in machines:
        s = m["series_candidate"]
        if s:
            series_map[s].append(m["official_name"])

    lines = ["series_name,official_names"]
    for series, names in sorted(series_map.items()):
        quoted = "|".join(names)
        lines.append(f'"{series}","{quoted}"')
    return "\n".join(lines)

# ── main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    machines, source_counts, dup_count = merge_all()

    # SQL 出力
    sql_path = os.path.join(BASE, "supabase", "migrations", "005_machines_expand.sql")
    with open(sql_path, "w") as f:
        f.write(generate_sql(machines))

    # シリーズ候補 CSV
    csv_path = os.path.join(BASE, "public", "series_candidates.csv")
    with open(csv_path, "w") as f:
        f.write(generate_series_csv(machines))

    # 統計出力
    print(f"=== 統計 ===")
    print(f"総機種数 (INSERT対象): {len(machines)}")
    print()
    for src, counts in source_counts.items():
        print(f"  [{src}] 追加={counts['added']} 重複除外={counts['duped']}")
    print()
    print(f"重複除外合計: {dup_count}")
    print()

    slot_count = sum(1 for m in machines if m["type"] == "slot")
    pachinko_count = sum(1 for m in machines if m["type"] == "pachinko")
    print(f"  スロット: {slot_count}")
    print(f"  パチンコ: {pachinko_count}")
    print()

    series_map = defaultdict(list)
    for m in machines:
        if m["series_candidate"]:
            series_map[m["series_candidate"]].append(m["official_name"])
    print(f"シリーズ候補数: {len(series_map)}")
    for s, names in sorted(series_map.items()):
        print(f"  {s}: {len(names)}機種")
    print()
    print(f"SQL: {sql_path}")
    print(f"CSV: {csv_path}")
