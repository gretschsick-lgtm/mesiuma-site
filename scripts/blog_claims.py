#!/usr/bin/env python3
"""
ブログ記事の「主張単位の検証台帳」基盤（BLOG-CLAIM-LEDGER-FOUNDATION-1）

役割（このphaseの範囲）:
  - public/blog_posts.json から主張（claim）を機械的に抽出する（保存はしない）
  - 構造上の位置から安定した claim_id を作り、原文のハッシュ（span_hash）で編集を検出する
  - sources / machines / facts / bindings の4層の台帳を読み込み・検証する
  - 台帳と記事から、検証状態を「導出」する（保存しない）
  - 現在の全主張を legacy baseline として固定する（承認ではなく、変更検知のため）

やらないこと:
  - 記事・画像・公開JSONの変更、ネットワークアクセス、公式値の自動登録
  - verify_blog.py や workflow への連携（別phase）

使い方:
  python scripts/blog_claims.py report            # 抽出件数・状態の集計
  python scripts/blog_claims.py check             # 台帳の検証 + baselineとの差分
  python scripts/blog_claims.py baseline --write  # legacy_baseline.json を（未存在時のみ）生成
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXTRACTOR_VERSION = "1"
SCHEMA_VERSION = 1

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
BLOG_PATH = ROOT / "public" / "blog_posts.json"
LEDGER_DIR = SCRIPTS_DIR / "blog_claims"
BASELINE_PATH = LEDGER_DIR / "legacy_baseline.json"

STATUSES = ("PRIMARY_VERIFIED", "SECONDARY_CORROBORATED", "CONFLICTING", "UNVERIFIED", "STALE", "NOT_APPLICABLE")
OCR_REVIEW_STATES = ("NOT_OCR", "OCR_UNREVIEWED", "OCR_HUMAN_CONFIRMED")
VERIFICATION_METHODS = ("human_read", "text_layer", "ocr")
RIGHTS_VALUES = ("EXPLICITLY_ALLOWED", "CONTRACT_REQUIRED", "PERMISSION_REQUIRED", "PROHIBITED", "UNKNOWN")
RIGHTS_FIELDS = ("view", "auto_fetch", "store_values", "publish_numbers", "copy_table", "images", "redistribute")
MODEL_NUMBER_STATUSES = ("CONFIRMED", "NOT_PUBLISHED", "UNKNOWN", "CONFLICTING")
SOURCE_TIERS = ("primary", "secondary")
MACHINE_KINDS = ("slot", "pachinko")
DATE_FACT_KEYS = ("date.intro", "date.announce", "date.delivery")
# 記事の日付主張 → 検証できる fact_key（導入日は、発表日・納品日では検証できない）
DATE_CLAIM_FACT = {"date_intro": "date.intro"}


# ───────────────────────── 正規化・ハッシュ ─────────────────────────
def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def clean_text(s: str) -> str:
    """表示用: NFKC・Markdown強調除去・空白の圧縮。"""
    s = nfkc(s).replace("**", "")
    return re.sub(r"\s+", " ", s).strip()


def hash_text(s: str) -> str:
    """ハッシュ用: NFKC・Markdown強調除去・空白全削除。"""
    s = nfkc(s).replace("**", "")
    return re.sub(r"\s+", "", s)


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def span_hash_of(text: str) -> str:
    return sha16(hash_text(text))


def slug(s: str) -> str:
    s = nfkc(s).lower().replace("**", "")
    s = re.sub(r"[\s・･\-‐〜~～:：!！?？\.\,，、。「」『』()（）\[\]【】/／&＆'\"]", "", s)
    return s or "x"


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def value_digest(normalized: dict | None) -> str | None:
    return None if normalized is None else sha16(canonical_json(normalized))


# ───────────────────────── 値の正規化 ─────────────────────────
_TOKEN = re.compile(
    r"(?P<date>(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日)"
    r"|(?P<month>(?P<my>\d{4})年(?P<mm>\d{1,2})月(?!\d))"
    r"|(?P<ratio>1/(?P<den>\d+(?:\.\d+)?))"
    r"|(?P<net>(?P<netv>\d+(?:\.\d+)?)\s*枚/G)"
    r"|(?P<pct>(?P<pctv>\d+(?:\.\d+)?)\s*%)"
    r"|(?P<yen>(?P<yenv>\d+(?:\.\d+)?)\s*円)"
    r"|(?P<games>(?P<gv>\d+(?:\.\d+)?)\s*G)"
    r"|(?P<units>(?P<uv>\d+(?:\.\d+)?)\s*台)"
    r"|(?P<count>(?P<cv>\d+(?:\.\d+)?)\s*(?P<cu>枚|個|連|回|R|セット|分|pt|ポイント|倍))"
)


def _num(s: str) -> str:
    """数値文字列を正準化（桁区切り除去、末尾ゼロは保持して元表記を尊重）。"""
    return s.replace(",", "")


def tokenize(text: str) -> list[dict]:
    """数値トークンを抽出して種別ごとに正規化する（文脈は推測しない）。"""
    t = nfkc(text).replace(",", "")
    out: list[dict] = []
    for m in _TOKEN.finditer(t):
        approx = t[max(0, m.start() - 1):m.start()] == "約"
        raw = m.group(0)
        if m.group("date"):
            iso = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
            nv = {"kind": "date", "iso": iso}
        elif m.group("month"):
            nv = {"kind": "date_partial", "iso": f"{int(m.group('my')):04d}-{int(m.group('mm')):02d}"}
        elif m.group("ratio"):
            nv = {"kind": "probability_ratio", "den": _num(m.group("den")), "text": f"1/{_num(m.group('den'))}"}
        elif m.group("net"):
            nv = {"kind": "net_per_game", "value": _num(m.group("netv")), "unit": "枚/G"}
        elif m.group("pct"):
            nv = {"kind": "percent", "value": _num(m.group("pctv"))}
        elif m.group("yen"):
            nv = {"kind": "yen", "value": _num(m.group("yenv"))}
        elif m.group("games"):
            nv = {"kind": "games", "value": _num(m.group("gv")), "unit": "G"}
        elif m.group("units"):
            nv = {"kind": "units", "value": _num(m.group("uv")), "unit": "台"}
        else:
            nv = {"kind": "count", "value": _num(m.group("cv")), "unit": m.group("cu")}
        if approx:
            nv = dict(nv, approx=True)
        out.append({"raw": raw, "normalized": nv})
    return out


def values_equal(a: dict | None, b: dict | None) -> bool:
    """正規化値の等価判定。種別（単位）が違えば不一致。approx の有無は無視しない。"""
    if a is None or b is None:
        return False
    if a.get("kind") != b.get("kind") or a.get("unit") != b.get("unit"):
        return False
    if bool(a.get("approx")) != bool(b.get("approx")):
        return False
    for key in ("iso", "text", "value", "den"):
        if key in a or key in b:
            va, vb = a.get(key), b.get(key)
            if va is None or vb is None:
                return False
            if key in ("value", "den"):
                try:
                    if Decimal(str(va)) != Decimal(str(vb)):
                        return False
                except InvalidOperation:
                    return False
            elif va != vb:
                return False
    return True


# ───────────────────────── 語彙（列・ラベル） ─────────────────────────
_METRIC_RULES = [
    (r"^at(初当り|初当たり|当選)?(確率)?$", "at_prob"),
    (r"^cz(確率|初当り確率|初当たり確率)?$", "cz_prob"),
    (r"^(機械割|出玉率)$", "payout_pct"),
    (r"^reg(確率)?$", "reg_prob"),
    (r"^bb(確率)?$", "bb_prob"),
    (r"(大当り|大当たり)確率", "jackpot_prob"),
    (r"(ボーナス|合算).*確率", "bonus_prob"),
    (r"^純増", "net_per_game"),
    (r"^コイン単価", "coin_unit_price"),
    (r"^ベース", "base"),
    (r"天井", "ceiling"),
    (r"^(導入台数|販売台数)", "units_sold"),
    (r"^設定数", "setting_count"),
    (r"継続率", "continue_rate"),
    (r"突入率", "entry_rate"),
]


def metric_of(label: str) -> str | None:
    t = nfkc(label).lower().replace(" ", "")
    for pat, key in _METRIC_RULES:
        if re.search(pat, t):
            return key
    return None


def setting_of(cell: str, header0: str = "") -> str | None:
    """「設定1」「1」「設定3〜5」「設定4以上」→ setting1 / setting3-5 / setting4+。"""
    t = nfkc(cell).strip()
    t = re.sub(r"[（(].*?[)）]", "", t).strip()
    m = re.fullmatch(r"(?:設定)?\s*([1-6])\s*(?:[〜~\-～ー]\s*([1-6]))?\s*(以上|以下)?", t)
    if m and (t.startswith("設定") or "設定" in nfkc(header0) or m.group(2) or m.group(3)):
        a, b, sfx = m.group(1), m.group(2), m.group(3)
        if b:
            return f"setting{a}-{b}"
        if sfx == "以上":
            return f"setting{a}+"
        if sfx == "以下":
            return f"setting{a}-"
        return f"setting{a}"
    return None


LABEL_CLAIM_TYPE = {
    "導入日": "date_intro",
    "型式名": "model_number",
    "メーカー": "maker",
    "機種タイプ": "machine_type",
}


# ───────────────────────── 抽出 ─────────────────────────
_BULLET = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*\s*[：:]\s*(.*)$")
_PLAIN_LIST = re.compile(r"^\s*(?:-\s+|\d+\.\s+)(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s*(.*)$")


def _confidence_and_value(tokens: list[dict]) -> tuple[dict | None, str]:
    if len(tokens) == 1:
        return tokens[0]["normalized"], "HIGH"
    return None, "AMBIGUOUS"


def _extra_words(cell: str, toks: list[dict]) -> int:
    """セルから数値トークンと装飾（約・+α・括弧・記号）を除いた、残りの文字数。"""
    t = nfkc(cell).replace(",", "")
    for tk in toks:
        t = t.replace(tk["raw"], "", 1)
    t = re.sub(r"[約+＋αα〜~～（）()\[\]・\s/／\-—–以上以下未満]", "", t)
    return len(t)


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def extract_claims(article: dict) -> list[dict]:
    """1記事から主張を抽出する。決定的（同じ入力 → 同じ出力）。"""
    aid = article["id"]
    lines = article.get("content", "").split("\n")
    claims: list[dict] = []
    section = "top"
    last_nonempty = ""
    table_keys: collections.Counter = collections.Counter()
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        stripped = ln.strip()
        hm = _HEADING.match(stripped)
        if hm:
            section = clean_text(hm.group(2)) or "top"
            last_nonempty = ""
            i += 1
            continue
        # ── 表
        if stripped.startswith("|"):
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(_table_cells(lines[i]))
                i += 1
            is_title = bool(last_nonempty) and (
                (last_nonempty.startswith("**") and last_nonempty.endswith("**")) or last_nonempty.endswith(("：", ":"))
            )
            title_src = clean_text(last_nonempty) if is_title else ""
            base_key = slug(title_src)[:40] if title_src and len(title_src) <= 60 else ""
            if not base_key:
                base_key = f"t-{slug(section)[:20]}"
            table_keys[(section, base_key)] += 1
            tkey = base_key if table_keys[(section, base_key)] == 1 else f"{base_key}#{table_keys[(section, base_key)]}"
            claims.extend(_table_claims(aid, section, tkey, block))
            last_nonempty = ""
            continue
        if not stripped:
            i += 1
            continue
        last_nonempty = stripped
        # ── 基本スペック等の箇条書き（太字ラベル）
        bm = _BULLET.match(ln)
        if bm:
            claims.append(_bullet_claim(aid, section, clean_text(bm.group(1)), bm.group(2), stripped))
            i += 1
            continue
        # ── 本文・リスト
        body = stripped
        is_list = False
        lm = _PLAIN_LIST.match(ln)
        if lm:
            body = lm.group(1)
            is_list = True
        for seg in re.split(r"(?<=。)", body):
            seg = seg.strip()
            if not seg:
                continue
            toks = tokenize(seg)
            if not toks:
                continue
            nv, conf = _confidence_and_value(toks)
            if conf == "HIGH":
                conf = "MEDIUM"  # 文中の数値は文脈を推測しないため、最高信頼にしない
            sh = span_hash_of(seg)
            claims.append({
                "article_id": aid,
                "claim_id": f"{aid}::{'list' if is_list else 'prose'}::{slug(section)[:30]}::{sh[:8]}",
                "claim_type": "list_numeric" if is_list else "prose_numeric",
                "field_path": f"content > {section} > {'list' if is_list else 'prose'}",
                "original_text": clean_text(seg),
                "normalized_value": nv,
                "tokens": [t["raw"] for t in toks],
                "span_hash": sh,
                "context_hash": sha16(hash_text(section)),
                "extraction_confidence": conf,
                "section": section,
                "setting": None,
                "metric": None,
                "disambiguated": False,
            })
        i += 1
    _disambiguate(claims)
    return claims


def _bullet_claim(aid: str, section: str, label: str, value: str, whole_line: str) -> dict:
    ctype = LABEL_CLAIM_TYPE.get(label, "spec_bullet")
    toks = tokenize(value)
    metric = metric_of(label)
    if label == "導入日":
        dates = [t for t in toks if t["normalized"]["kind"] in ("date", "date_partial")]
        if len(dates) == 1:
            nv, conf = dates[0]["normalized"], "HIGH" if dates[0]["normalized"]["kind"] == "date" else "MEDIUM"
        else:
            nv, conf = None, "AMBIGUOUS"
    elif ctype in ("model_number", "maker", "machine_type"):
        text = clean_text(value)
        text = re.sub(r"[（(][^)）]*[)）]\s*$", "", text).strip() if ctype == "model_number" else text
        nv, conf = {"kind": ctype + "_text", "text": text}, "HIGH"
    elif toks:
        nv, conf = _confidence_and_value(toks)
    else:
        nv, conf = {"kind": "text", "text": clean_text(value)}, "HIGH"
    sh = span_hash_of(whole_line)
    return {
        "article_id": aid,
        "claim_id": f"{aid}::bullet::{slug(label)}",
        "claim_type": ctype,
        "field_path": f"content > {section} > bullet:{label}",
        "original_text": clean_text(whole_line.lstrip("- ").strip()),
        "normalized_value": nv,
        "tokens": [t["raw"] for t in toks],
        "span_hash": sh,
        "context_hash": sha16(hash_text(label)),
        "extraction_confidence": conf,
        "section": section,
        "setting": None,
        "metric": metric,
        "disambiguated": False,
        "_label": label,
    }


def _table_claims(aid: str, section: str, tkey: str, block: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    if not block:
        return out
    header = block[0]
    body = [r for r in block[1:] if not _is_sep(r)]
    hdr_sig = "|".join(clean_text(h) for h in header)
    for r in body:
        if not r:
            continue
        row_label = r[0]
        row_setting = setting_of(row_label, header[0] if header else "")
        row_key = row_setting or slug(row_label)[:30]
        for ci in range(1, min(len(r), len(header))):
            cell = r[ci]
            if not re.search(r"\d", cell):
                continue
            col_header = header[ci]
            col_setting = setting_of(col_header)
            col_metric = metric_of(col_header)
            col_key = col_setting or col_metric or f"col:{slug(col_header)[:24]}"
            setting = row_setting or col_setting
            metric = col_metric if row_setting else (metric_of(row_label) if col_setting else col_metric)
            toks = tokenize(cell)
            nv, conf = _confidence_and_value(toks)
            if not toks:  # 数字はあるが、単位付きトークンにならないもの（例: 「3段階」）は正規化しない
                nv, conf = None, "AMBIGUOUS"
            elif conf == "HIGH" and _extra_words(cell, toks) > 6:
                conf = "MEDIUM"  # セル内に数値以外の説明語が多い場合は、文脈を推測しない
            ctx = sha16(hash_text(f"{tkey}|{hdr_sig}|{row_label}|{col_header}"))
            out.append({
                "article_id": aid,
                "claim_id": f"{aid}::table::{tkey}::{row_key}::{col_key}",
                "claim_type": "table_cell",
                "field_path": f"content > {section} > table[{tkey}] row={row_key} col={col_key}",
                "original_text": clean_text(cell),
                "normalized_value": nv,
                "tokens": [t["raw"] for t in toks],
                "span_hash": span_hash_of(cell),
                "context_hash": ctx,
                "extraction_confidence": conf,
                "section": section,
                "setting": setting,
                "metric": metric,
                "disambiguated": False,
                "_row_label": clean_text(row_label),
                "_col_header": clean_text(col_header),
            })
    return out


def _disambiguate(claims: list[dict]) -> None:
    """同一記事内で claim_id が重複した場合、出現順の連番を付け、全員に印を付ける。"""
    cnt = collections.Counter(c["claim_id"] for c in claims)
    seen: collections.Counter = collections.Counter()
    for c in claims:
        base = c["claim_id"]
        if cnt[base] > 1:
            seen[base] += 1
            c["disambiguated"] = True
            if seen[base] > 1:
                c["claim_id"] = f"{base}#{seen[base]}"


def extract_all(posts: list[dict]) -> list[dict]:
    out: list[dict] = []
    for p in posts:
        out.extend(extract_claims(p))
    return out


def public_claim(c: dict) -> dict:
    """内部用キー（_で始まる）を除いた主張。"""
    return {k: v for k, v in c.items() if not k.startswith("_")}


# ───────────────────────── 機種の識別（自動統合しない） ─────────────────────────
def article_hints(article: dict) -> dict:
    """記事から機種のヒントを取り出す（machine_key の決定はしない）。"""
    c = article.get("content", "")
    lab = {clean_text(m.group(1)): clean_text(m.group(2)) for m in re.finditer(r"-\s*\*\*([^*]+)\*\*[：:]\s*([^\n]+)", c)}
    t = re.sub(r"^【[^】]*】", "", article.get("title", "")).split("｜")[0].strip()
    ty = lab.get("機種タイプ", "")
    if re.search(r"スマスロ|L機|パチスロ|AT機|ノーマル|ART", ty):
        kind = "slot"
    elif re.search(r"スマパチ|パチンコ|LT|甘デジ|ミドル|1種2種", ty):
        kind = "pachinko"
    else:
        kind = None
    return {"title_name": t, "kind_hint": kind, "model_number": lab.get("型式名"), "maker_text": lab.get("メーカー"), "machine_type": ty or None}


def machine_candidates(article: dict, machines: list[dict]) -> dict:
    """台帳の機種から、**完全一致**でだけ候補を探す。曖昧・不一致なら machine_key=None。"""
    h = article_hints(article)
    model = nfkc(h["model_number"]).replace(" ", "") if h["model_number"] else None
    name = slug(h["title_name"])
    hits = []
    for m in machines:
        mk_models = [nfkc(x).replace(" ", "") for x in m.get("model_numbers", [])]
        if model and model in mk_models and (h["kind_hint"] in (None, m.get("kind"))):
            hits.append((m["machine_key"], "model_number"))
        elif not model and name and slug(m.get("official_name", "")) == name and (h["kind_hint"] in (None, m.get("kind"))):
            hits.append((m["machine_key"], "official_name"))
    keys = sorted({k for k, _ in hits})
    if len(keys) == 1:
        return {"machine_key": keys[0], "method": hits[0][1], "reason": None}
    if len(keys) > 1:
        return {"machine_key": None, "method": None, "reason": "ambiguous_multiple_machines"}
    reason = "model_number_not_in_ledger" if model else "no_exact_match"
    return {"machine_key": None, "method": None, "reason": reason}


# ───────────────────────── 台帳の読み込み・検証 ─────────────────────────
LAYER_FILES = {"sources": "sources.json", "machines": "machines.json", "facts": "facts.json", "bindings": "bindings.json"}


def load_ledger(ledger_dir: Path = LEDGER_DIR) -> dict:
    led = {}
    for layer, fn in LAYER_FILES.items():
        p = ledger_dir / fn
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            led[layer] = data.get(layer, [])
        else:
            led[layer] = []
    return led


def validate_ledger(led: dict) -> list[str]:
    """台帳の構造・参照整合性・禁止状態を検査する。"""
    errs: list[str] = []
    sources = {s.get("source_id"): s for s in led.get("sources", [])}
    machines = {m.get("machine_key"): m for m in led.get("machines", [])}
    facts = {f.get("fact_id"): f for f in led.get("facts", [])}
    for layer, key in (("sources", "source_id"), ("machines", "machine_key"), ("facts", "fact_id")):
        ids = [x.get(key) for x in led.get(layer, [])]
        if any(not i for i in ids):
            errs.append(f"{layer}: {key} が空の項目がある")
        for dup in {i for i in ids if ids.count(i) > 1}:
            errs.append(f"{layer}: {key} が重複: {dup}")
    for s in led.get("sources", []):
        sid = s.get("source_id")
        if s.get("tier") not in SOURCE_TIERS:
            errs.append(f"source {sid}: tier が不正")
        rights = s.get("rights", {})
        for f in RIGHTS_FIELDS:
            v = rights.get(f, "UNKNOWN")
            if v not in RIGHTS_VALUES:
                errs.append(f"source {sid}: rights.{f} が不正: {v}")
    for m in led.get("machines", []):
        k = m.get("machine_key")
        if m.get("kind") not in MACHINE_KINDS:
            errs.append(f"machine {k}: kind が不正")
        if m.get("model_number_status", "UNKNOWN") not in MODEL_NUMBER_STATUSES:
            errs.append(f"machine {k}: model_number_status が不正")
    for f in led.get("facts", []):
        fid = f.get("fact_id")
        if f.get("source_id") not in sources:
            errs.append(f"fact {fid}: source_id が存在しない")
        if f.get("machine_key") not in machines:
            errs.append(f"fact {fid}: machine_key が存在しない")
        if f.get("verification_method") not in VERIFICATION_METHODS:
            errs.append(f"fact {fid}: verification_method が不正")
        if f.get("ocr_review", "NOT_OCR") not in OCR_REVIEW_STATES:
            errs.append(f"fact {fid}: ocr_review が不正")
        if f.get("verification_method") == "ocr" and f.get("ocr_review", "NOT_OCR") == "NOT_OCR":
            errs.append(f"fact {fid}: ocr なのに ocr_review=NOT_OCR")
        if f.get("normalized_value") is None and not f.get("value_digest"):
            errs.append(f"fact {fid}: normalized_value も value_digest も無い")
    for b in led.get("bindings", []):
        cid = b.get("claim_id")
        if not cid or not b.get("article_id"):
            errs.append("binding: claim_id / article_id が空")
        ov = b.get("status_override")
        if ov not in (None, "NOT_APPLICABLE"):
            errs.append(f"binding {cid}: status_override は NOT_APPLICABLE のみ許可（検証済みへの上書きは禁止）: {ov}")
        if ov is None:
            if b.get("fact_id") not in facts:
                errs.append(f"binding {cid}: fact_id が存在しない")
            elif facts[b["fact_id"]].get("machine_key") != b.get("machine_key"):
                errs.append(f"binding {cid}: machine_key が fact と一致しない")
            if not b.get("span_hash") or not b.get("context_hash"):
                errs.append(f"binding {cid}: span_hash / context_hash が必須")
    return errs


# ───────────────────────── 検証状態の導出（保存しない） ─────────────────────────
def _fact_key_parts(fact_key: str) -> tuple[str | None, str | None]:
    """'setting6.at_prob' → ('setting6','at_prob') / 'net_per_game' → (None,'net_per_game') / 'date.intro' → (None,'date.intro')"""
    if fact_key in DATE_FACT_KEYS:
        return None, fact_key
    if "." in fact_key:
        a, b = fact_key.split(".", 1)
        return a, b
    return None, fact_key


def fact_eligibility(fact: dict, source: dict | None, machine: dict | None) -> tuple[str | None, list[str]]:
    """この fact が 'primary' / 'secondary' の根拠として使えるか。使えない理由を返す。"""
    reasons: list[str] = []
    if source is None:
        return None, ["source_missing"]
    if machine is None:
        return None, ["machine_missing"]
    tier = source.get("tier")
    if not fact.get("locator"):
        reasons.append("locator_missing")
    if not fact.get("verified_at"):
        reasons.append("verified_at_missing")
    if not fact.get("reviewer"):
        reasons.append("reviewer_missing")
    if not fact.get("conditions"):
        reasons.append("conditions_missing")
    if not (source.get("doc_title") or source.get("source_name")):
        reasons.append("source_document_unnamed")
    if fact.get("verification_method") == "ocr" and fact.get("ocr_review") != "OCR_HUMAN_CONFIRMED":
        reasons.append("ocr_unreviewed")
    if fact.get("verification_method") not in VERIFICATION_METHODS:
        reasons.append("verification_method_invalid")
    # 型式: 確認済み、または「公開資料に型式の記載なし」と明示されている場合のみ
    st = machine.get("model_number_status", "UNKNOWN")
    if not ((st == "CONFIRMED" and machine.get("model_numbers")) or st == "NOT_PUBLISHED"):
        reasons.append("model_number_unconfirmed")
    if machine.get("kind") not in MACHINE_KINDS:
        reasons.append("machine_kind_invalid")
    if reasons:
        return None, reasons
    return ("primary" if tier == "primary" else "secondary"), []


def derive_status(claim: dict, led: dict) -> tuple[str, list[str]]:
    """主張1件の検証状態を、台帳と記事から導出する。"""
    cid = claim["claim_id"]
    bindings = [b for b in led.get("bindings", []) if b.get("claim_id") == cid]
    if not bindings:
        return "UNVERIFIED", ["no_binding"]
    sources = {s["source_id"]: s for s in led.get("sources", [])}
    machines = {m["machine_key"]: m for m in led.get("machines", [])}
    facts = {f["fact_id"]: f for f in led.get("facts", [])}
    results: list[tuple[str, list[str]]] = []
    for b in bindings:
        if b.get("status_override") == "NOT_APPLICABLE":
            results.append(("NOT_APPLICABLE", ["explicit_not_applicable"]))
            continue
        if b.get("span_hash") != claim["span_hash"]:
            results.append(("STALE", ["span_changed"]))
            continue
        if b.get("context_hash") != claim["context_hash"]:
            results.append(("STALE", ["context_changed"]))
            continue
        if claim.get("extraction_confidence") == "AMBIGUOUS" or claim.get("normalized_value") is None:
            results.append(("UNVERIFIED", ["ambiguous_claim_cannot_be_compared"]))
            continue
        fact = facts.get(b.get("fact_id"))
        if fact is None:
            results.append(("UNVERIFIED", ["fact_missing"]))
            continue
        if fact.get("machine_key") != b.get("machine_key"):
            results.append(("UNVERIFIED", ["machine_mismatch"]))
            continue
        # 位置（設定・項目）の一致: 設定1と6の取り違えを防ぐ
        f_setting, f_metric = _fact_key_parts(fact.get("fact_key", ""))
        if claim.get("setting") != f_setting:
            results.append(("UNVERIFIED", ["setting_mismatch"]))
            continue
        c_metric = claim.get("metric")
        if claim["claim_type"] in DATE_CLAIM_FACT:
            if fact.get("fact_key") != DATE_CLAIM_FACT[claim["claim_type"]]:
                results.append(("UNVERIFIED", ["date_semantics_mismatch"]))
                continue
        elif c_metric is None or c_metric != f_metric:
            results.append(("UNVERIFIED", ["metric_mismatch"]))
            continue
        tier, reasons = fact_eligibility(fact, sources.get(fact.get("source_id")), machines.get(fact.get("machine_key")))
        if claim["claim_type"] in DATE_CLAIM_FACT and tier:
            needed = DATE_CLAIM_FACT[claim["claim_type"]].split(".", 1)[1]  # 'date.intro' → 'intro'
            if needed not in (sources[fact["source_id"]].get("field_semantics") or []):
                tier, reasons = None, ["source_cannot_answer_date_kind"]
        # 値の比較
        if fact.get("normalized_value") is not None:
            same = values_equal(claim["normalized_value"], fact["normalized_value"])
        else:
            same = value_digest(claim["normalized_value"]) == fact.get("value_digest")
        if tier is None:
            # 根拠として未成熟（OCR未レビュー等）。食い違いも「候補」にとどめ、CONFLICTINGにはしない
            tag = "candidate_match" if same else "candidate_mismatch"
            results.append(("UNVERIFIED", reasons + [tag]))
        elif not same:
            results.append(("CONFLICTING", ["value_differs_from_" + tier]))
        else:
            results.append(("PRIMARY_VERIFIED" if tier == "primary" else "SECONDARY_CORROBORATED", ["matches_" + tier]))
    order = ["NOT_APPLICABLE", "STALE", "CONFLICTING", "PRIMARY_VERIFIED", "SECONDARY_CORROBORATED", "UNVERIFIED"]
    for st in order:
        for r in results:
            if r[0] == st:
                return r
    return "UNVERIFIED", ["no_result"]


def rights_summary(source: dict) -> dict:
    """出典資料の権利状態（精度とは独立）。"""
    r = source.get("rights", {})
    return {f: r.get(f, "UNKNOWN") for f in RIGHTS_FIELDS}


# ───────────────────────── baseline ─────────────────────────
BASELINE_NOTE = (
    "これは変更検知のためのスナップショットであり、記載内容の正確性の承認ではない。"
    "ここにあるclaimを検証済み扱いにしてはならず、将来の検証免除の恒久的根拠にもしない。"
    "claimの状態は台帳（facts/bindings）から導出する。"
)


def build_baseline(posts: list[dict]) -> dict:
    claims = extract_all(posts)
    raw = json.dumps(posts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "_note": BASELINE_NOTE,
        "extractor_version": EXTRACTOR_VERSION,
        "generated_from": {"blog_posts_sha256": hashlib.sha256(raw).hexdigest(), "articles": len(posts), "claims": len(claims)},
        "columns": ["claim_id", "span_hash", "context_hash"],
        "claims": [[c["claim_id"], c["span_hash"], c["context_hash"]] for c in claims],
    }


def dump_baseline(b: dict) -> str:
    """差分が見やすいよう、1主張1行で書き出す（有効なJSON）。"""
    head = {k: v for k, v in b.items() if k != "claims"}
    head_s = json.dumps(head, ensure_ascii=False, indent=2)[:-2]  # 末尾の "\n}" を外す
    rows = ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in b["claims"])
    return f'{head_s},\n  "claims": [\n{rows}\n  ]\n}}\n'


def load_baseline(path: Path = BASELINE_PATH) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def classify_against_baseline(claims: list[dict], baseline: dict | None) -> dict:
    """UNCHANGED / EDITED / NEW / REMOVED の件数。承認ではなく、変更検知のみ。"""
    if not baseline:
        return {"UNCHANGED": 0, "EDITED": 0, "NEW": len(claims), "REMOVED": 0, "baseline_present": False}
    base = {r[0]: (r[1], r[2]) for r in baseline.get("claims", [])}
    cur = {c["claim_id"]: c for c in claims}
    out = collections.Counter()
    for cid, c in cur.items():
        if cid not in base:
            out["NEW"] += 1
        elif base[cid] == (c["span_hash"], c["context_hash"]):
            out["UNCHANGED"] += 1
        else:
            out["EDITED"] += 1
    out["REMOVED"] = sum(1 for cid in base if cid not in cur)
    return {k: out.get(k, 0) for k in ("UNCHANGED", "EDITED", "NEW", "REMOVED")} | {"baseline_present": True}


# ───────────────────────── CLI ─────────────────────────
def _load_posts(path: Path = BLOG_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_report(args) -> int:
    posts = _load_posts()
    claims = extract_all(posts)
    led = load_ledger()
    ids = [c["claim_id"] for c in claims]
    st = collections.Counter(derive_status(c, led)[0] for c in claims)
    print(f"articles: {len(posts)}")
    print(f"claims extracted: {len(claims)}")
    print("by claim_type:", dict(collections.Counter(c["claim_type"] for c in claims)))
    print("by confidence:", dict(collections.Counter(c["extraction_confidence"] for c in claims)))
    print(f"claim_id duplicates (unresolved): {len(ids) - len(set(ids))}")
    print(f"disambiguated by ordinal (same text/position repeated): {sum(1 for c in claims if c['disambiguated'])}")
    print("verification status:", {s: st.get(s, 0) for s in STATUSES})
    print("baseline vs current:", classify_against_baseline(claims, load_baseline()))
    return 0


def cmd_check(args) -> int:
    led = load_ledger()
    errs = validate_ledger(led)
    for e in errs:
        print("LEDGER ERROR:", e)
    print(f"ledger: sources={len(led['sources'])} machines={len(led['machines'])} facts={len(led['facts'])} bindings={len(led['bindings'])}")
    bl = load_baseline()
    claims = extract_all(_load_posts())
    print("baseline vs current:", classify_against_baseline(claims, bl))
    return 1 if errs else 0


def cmd_baseline(args) -> int:
    if not args.write:
        b = build_baseline(_load_posts())
        print(f"baseline would contain {len(b['claims'])} claims from {b['generated_from']['articles']} articles (use --write to create)")
        return 0
    if BASELINE_PATH.exists() and not args.force:
        print(f"{BASELINE_PATH.name} は既に存在します。上書きするには --force が必要です（baselineは承認ではなく変更検知用）。")
        return 1
    b = build_baseline(_load_posts())
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(dump_baseline(b), encoding="utf-8")
    print(f"wrote {BASELINE_PATH} ({len(b['claims'])} claims)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ブログ記事の主張単位の検証台帳（基盤）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    sub.add_parser("check")
    pb = sub.add_parser("baseline")
    pb.add_argument("--write", action="store_true")
    pb.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return {"report": cmd_report, "check": cmd_check, "baseline": cmd_baseline}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
