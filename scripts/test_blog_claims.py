#!/usr/bin/env python3
"""BLOG-CLAIM-LEDGER-FOUNDATION-1 テスト（ネットワーク非依存・記事/台帳を書き換えない）。"""
import copy
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import blog_claims as B  # noqa: E402

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


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


LIVE = B._load_posts()
LIVE_BY = {p["id"]: p for p in LIVE}
HASH_BLOG_BEFORE = sha_file(B.BLOG_PATH)
HASH_LEDGER_BEFORE = {n: sha_file(B.LEDGER_DIR / n) for n in B.LAYER_FILES.values()}


# ─────────── 合成記事・合成台帳 ───────────
def art(aid="2099-01-01-synth", content=None, title="【スペック完全解説】スマスロ テスト機｜基本スペック"):
    if content is None:
        content = (
            "「スマスロ テスト機」の解説です。\n\n"
            "## 基本スペック\n\n"
            "- **メーカー**：テスト社\n"
            "- **型式名**：LテストXX\n"
            "- **導入日**：2099年1月1日\n"
            "- **機種タイプ**：スマスロ（L機）\n"
            "- **純増**：約8.0枚/G\n\n"
            "**設定別 機械割 & AT初当り確率**\n\n"
            "| 設定 | AT初当り確率 | 機械割 |\n"
            "|------|------------|--------|\n"
            "| 設定1 | 1/370.7 | 97.9% |\n"
            "| 設定6 | 1/266.5 | 114.9% |\n\n"
            "## まとめ\n\n"
            "機械割は設定6で114.9%です。\n"
        )
    return {"id": aid, "title": title, "date": "2099-01-01", "author": "t", "tags": [], "summary": "", "image": "", "setting_images": [], "content": content}


def by_id(claims):
    return {c["claim_id"]: c for c in claims}


def mk_ledger(claim, fact_key, fact_value, *, tier="primary", method="human_read", ocr="NOT_OCR", reviewer="r1",
              conditions="設定別・通常時", locator="p.1 表1", verified_at="2026-10-08", model_status="CONFIRMED",
              model_numbers=("LテストXX",), semantics=("setting_probs",), rights=None, digest=False, machine_kind="slot",
              with_source=True, span_hash=None, context_hash=None, override=None):
    src = {"source_id": "S1", "source_name": "テスト社 公式PDF", "tier": tier, "doc_type": "press_pdf", "doc_title": "テスト機 製品情報",
           "url": "https://example.invalid/x.pdf", "field_semantics": list(semantics), "rights": rights or {}}
    mach = {"machine_key": "slot:LテストXX", "kind": machine_kind, "official_name": "スマスロ テスト機",
            "model_numbers": list(model_numbers), "model_number_status": model_status, "maker": {"brand": "テスト社"}}
    fact = {"fact_id": "F1", "machine_key": "slot:LテストXX", "fact_key": fact_key, "source_id": "S1", "locator": locator,
            "verified_at": verified_at, "verification_method": method, "ocr_review": ocr, "reviewer": reviewer,
            "conditions": conditions, "confidence": "high"}
    if digest:
        fact["value_digest"] = B.value_digest(fact_value)
    else:
        fact["normalized_value"] = fact_value
    bind = {"claim_id": claim["claim_id"], "article_id": claim["article_id"], "machine_key": "slot:LテストXX", "fact_id": "F1",
            "span_hash": span_hash or claim["span_hash"], "context_hash": context_hash or claim["context_hash"], "status_override": override}
    led = {"sources": [src] if with_source else [], "machines": [mach], "facts": [fact], "bindings": [bind]}
    return led


RATIO_266 = {"kind": "probability_ratio", "den": "266.5", "text": "1/266.5"}
PCT_1149 = {"kind": "percent", "value": "114.9"}
NET_80 = {"kind": "net_per_game", "value": "8.0", "unit": "枚/G"}


# ───────────────────────── [1] 全記事から抽出できる ─────────────────────────
print("[1] 全記事から抽出できる")
all_claims = []
fail_articles = []
for p in LIVE:
    try:
        cs = B.extract_claims(p)
    except Exception as e:  # noqa: BLE001
        fail_articles.append((p["id"], repr(e)))
        continue
    all_claims.extend(cs)
    if not cs:
        fail_articles.append((p["id"], "no claims"))
ok(not fail_articles, f"1a 全{len(LIVE)}記事で例外なく1件以上の主張を抽出（失敗={fail_articles[:2]}）")
types = {c["claim_type"] for c in all_claims}
ok({"date_intro", "model_number", "maker", "spec_bullet", "table_cell", "prose_numeric"} <= types, f"1b 箇条書き・表・本文・導入日・型式名を抽出（{sorted(types)}）")
ok(all(c.get(k) not in (None, "") for c in all_claims for k in ("article_id", "claim_id", "span_hash", "context_hash", "extraction_confidence", "field_path", "original_text")),
   "1c 全主張に article_id / claim_id / field_path / original_text / span_hash / extraction_confidence がある")
ok(all("normalized_value" in c for c in all_claims), "1d 全主張に normalized_value キーがある（曖昧なら null）")

# ───────────────────────── [2] 同じ入力で同じID ─────────────────────────
print("[2] 決定性")
a1 = [c["claim_id"] for c in B.extract_all(LIVE)]
a2 = [c["claim_id"] for c in B.extract_all(copy.deepcopy(LIVE))]
ok(a1 == a2, "2a 同じ記事データから同じclaim_id列")
shuf = LIVE[:]
random.Random(7).shuffle(shuf)
ok(sorted(c["claim_id"] for c in B.extract_all(shuf)) == sorted(a1), "2b 記事の並び順を変えても同じclaim_id集合")
rt = json.loads(json.dumps(LIVE, ensure_ascii=False))
ok([c["span_hash"] for c in B.extract_all(rt)] == [c["span_hash"] for c in B.extract_all(LIVE)], "2c JSON往復後も同じspan_hash")

# ───────────────────────── [3] claim_id重複なし ─────────────────────────
print("[3] claim_id の一意性")
ok(len(a1) == len(set(a1)), f"3a 全記事を通して claim_id が一意（{len(a1)}件）")
for p in LIVE:
    ids = [c["claim_id"] for c in B.extract_claims(p)]
    if len(ids) != len(set(ids)):
        ok(False, f"3b {p['id']} で重複")
        break
else:
    ok(True, "3b 各記事内でも一意")
dup = art(content="## まとめ\n\n機械割は114.9%です。機械割は114.9%です。\n")
dc = B.extract_claims(dup)
ok(len(dc) == 2 and len({c["claim_id"] for c in dc}) == 2 and all(c["disambiguated"] for c in dc), "3c 同一文の重複は連番で衝突を解消し disambiguated を立てる")

# ───────────────────────── [4] 原文編集でSTALE ─────────────────────────
print("[4] 原文が変わると STALE / 失効")
base = art()
cl = by_id(B.extract_claims(base))
cid6 = [k for k in cl if k.endswith("setting6::at_prob")][0]
led = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266)
ok(B.derive_status(cl[cid6], led)[0] == "PRIMARY_VERIFIED", "4a 条件を満たした公式factと一致 → PRIMARY_VERIFIED（導出）")
edited = art(content=base["content"].replace("1/266.5", "1/270.0"))
cl2 = by_id(B.extract_claims(edited))
ok(cid6 in cl2 and cl2[cid6]["span_hash"] != cl[cid6]["span_hash"], "4b セルの値を編集すると span_hash が変わる（claim_idは同じ）")
st = B.derive_status(cl2[cid6], led)
ok(st[0] == "STALE" and "span_changed" in st[1], f"4c 編集後は STALE（古い検証を再利用しない） {st}")
prose_base = by_id(B.extract_claims(base))
pid = [k for k in prose_base if "::prose::" in k][0]
ledp = mk_ledger(prose_base[pid], "net_per_game", NET_80)  # 本文は単一トークンでも MEDIUM
edited_prose = art(content=base["content"].replace("機械割は設定6で114.9%です。", "機械割は設定6で115.0%です。"))
cp2 = by_id(B.extract_claims(edited_prose))
ok(pid not in cp2, "4d 本文の文を編集するとclaim_idが変わり、旧bindingは当てはまらない（誤再利用なし）")
ctx = art(content=base["content"].replace("| 設定 | AT初当り確率 | 機械割 |", "| 設定 | CZ確率 | AT初当り確率 | 機械割 |").replace("| 設定1 | 1/370.7 | 97.9% |", "| 設定1 | 1/200 | 1/370.7 | 97.9% |").replace("| 設定6 | 1/266.5 | 114.9% |", "| 設定6 | 1/150 | 1/266.5 | 114.9% |").replace("|------|------------|--------|", "|------|------|------------|--------|"))
cc = by_id(B.extract_claims(ctx))
st2 = B.derive_status(cc[cid6], led)
ok(cid6 in cc and cc[cid6]["original_text"] == cl[cid6]["original_text"] and st2[0] == "STALE" and "context_changed" in st2[1],
   f"4e 表に列が挿入され、セル文字列が同じでも context_hash の変化で STALE（誤紐付けを検出） {st2}")

# ───────────────────────── [5] 設定1/6の区別 ─────────────────────────
print("[5] 設定1 と 設定6 を区別する")
ids5 = [k for k in cl if "::table::" in k]
ok(any("setting1::at_prob" in k for k in ids5) and any("setting6::at_prob" in k for k in ids5), "5a 設定1・設定6 で別のclaim_id")
ok(cl[[k for k in ids5 if k.endswith("setting1::at_prob")][0]]["setting"] == "setting1" and cl[cid6]["setting"] == "setting6", "5b setting 属性が行から導出される")
num_row = art(content="**設定別**\n\n| 設定 | AT初当り確率 |\n|---|---|\n| 1 | 1/370.7 |\n| 6 | 1/266.5 |\n")
nr = B.extract_claims(num_row)
ok({c["setting"] for c in nr} == {"setting1", "setting6"}, "5c 行ラベルが「1」「6」だけでも、見出し「設定」から setting1/6 を認識")
swap = mk_ledger(cl[cid6], "setting1.at_prob", RATIO_266)
ok(B.derive_status(cl[cid6], swap) == ("UNVERIFIED", ["setting_mismatch"]), "5d 設定6の主張を設定1のfactに紐付けても検証にならない")
swapped_val = mk_ledger(cl[cid6], "setting6.at_prob", {"kind": "probability_ratio", "den": "370.7", "text": "1/370.7"})
ok(B.derive_status(cl[cid6], swapped_val)[0] == "CONFLICTING", "5e 設定1の値を設定6の主張に当てると CONFLICTING")
col_orient = art(content="**項目別**\n\n| 項目 | 設定1 | 設定6 |\n|---|---|---|\n| 機械割 | 97.9% | 114.9% |\n")
co = {c["claim_id"].split("::")[-2:][0]: c for c in B.extract_claims(col_orient)}
ok({c["setting"] for c in B.extract_claims(col_orient)} == {"setting1", "setting6"} and all(c["metric"] == "payout_pct" for c in B.extract_claims(col_orient)), "5f 設定が列方向の表でも設定と項目を識別")
live_idx = LIVE_BY.get("2026-08-03-toaru-index2")
if live_idx:
    li = [c["claim_id"] for c in B.extract_claims(live_idx) if c["claim_type"] == "table_cell"]
    ok(any("::setting1::at_prob" in k for k in li) and any("::setting6::payout_pct" in k for k in li), "5g 実記事（禁書目録2 08-03）の表も setting1/setting6 で識別")

# ───────────────────────── [6] 単位の区別 ─────────────────────────
print("[6] 確率・機械割・純増などの単位を区別")
kinds = {t["raw"]: t["normalized"]["kind"] for t in B.tokenize("1/398.8 97.9% 約8.0枚/G 4.1円 800G 3,100枚 20,000台 2026年8月3日 約2倍")}
ok(kinds == {"1/398.8": "probability_ratio", "97.9%": "percent", "8.0枚/G": "net_per_game", "4.1円": "yen", "800G": "games",
             "3100枚": "count", "20000台": "units", "2026年8月3日": "date", "2倍": "count"}, f"6a 種別ごとに正規化 {kinds}")
ok(not B.values_equal({"kind": "percent", "value": "50"}, {"kind": "count", "value": "50", "unit": "枚"}), "6b 同じ数字でも種別（%/枚）が違えば不一致")
ok(not B.values_equal({"kind": "net_per_game", "value": "8.0", "unit": "枚/G"}, {"kind": "count", "value": "8.0", "unit": "枚"}), "6c 純増(枚/G)と枚数は別")
ok(B.values_equal({"kind": "percent", "value": "114.9"}, {"kind": "percent", "value": "114.90"}), "6d 同じ数値は小数の書式が違っても一致")
ok(not B.values_equal({"kind": "percent", "value": "114.9"}, {"kind": "percent", "value": "114.9", "approx": True}), "6e 「約」の有無も区別")
ok(B.metric_of("AT確率") == B.metric_of("AT初当り確率") == "at_prob" and B.metric_of("機械割") == B.metric_of("出玉率") == "payout_pct", "6f 語彙の揺れ（AT確率/AT初当り確率、機械割/出玉率）を正規化")
met = mk_ledger(cl[cid6], "payout_pct", RATIO_266)  # 項目（metric）違いのfact
ok(B.derive_status(cl[cid6], mk_ledger(cl[cid6], "setting6.payout_pct", PCT_1149))[1] == ["metric_mismatch"], "6g 項目（at_prob と payout_pct）違いのfactには紐付かない")

# ───────────────────────── [7] 型式違いを自動統合しない ─────────────────────────
print("[7] 型式違い・同名別機種を自動統合しない")
M_A = {"machine_key": "slot:LA", "kind": "slot", "official_name": "スマスロ テスト機", "model_numbers": ["LテストAA"]}
M_B = {"machine_key": "slot:LB", "kind": "slot", "official_name": "スマスロ テスト機", "model_numbers": ["LテストBB"]}
M_P = {"machine_key": "pachinko:PA", "kind": "pachinko", "official_name": "スマスロ テスト機", "model_numbers": ["eテストPP"]}
a_aa = art(content=art()["content"].replace("LテストXX", "LテストAA"))
ok(B.machine_candidates(a_aa, [M_A, M_B])["machine_key"] == "slot:LA", "7a 型式が完全一致する機種だけを候補にする")
a_none = art(content=art()["content"].replace("- **型式名**：LテストXX\n", ""))
r7 = B.machine_candidates(a_none, [M_A, M_B])
ok(r7["machine_key"] is None and r7["reason"] == "ambiguous_multiple_machines", f"7b 型式の記載が無く、同名の機種が複数ある場合は決めない {r7}")
r7c = B.machine_candidates(art(), [M_A, M_B])
ok(r7c["machine_key"] is None and r7c["reason"] == "model_number_not_in_ledger", f"7c 台帳に無い型式（LテストXX）は、名前が同じ機種に自動統合しない {r7c}")
ok(B.machine_candidates(a_none, [M_P, M_A])["machine_key"] == "slot:LA", "7d パチンコ/スロットが違う同名機種には当てはめない（種別でも区別）")
live_pair = [LIVE_BY[i] for i in ("2026-06-22-toaru-index2", "2026-08-03-toaru-index2") if i in LIVE_BY]
if len(live_pair) == 2:
    mods = [B.article_hints(p)["model_number"] for p in live_pair]
    ok(len(set(mods)) == 2 and all(B.machine_candidates(p, [])["machine_key"] is None for p in live_pair), f"7e 実記事: 同名で型式表記が異なる2記事を、台帳なしで統合しない {mods}")

# ───────────────────────── [8] OCR未レビューは検証済みにならない ─────────────────────────
print("[8] OCR未レビューは PRIMARY_VERIFIED にならない")
o1 = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, method="ocr", ocr="OCR_UNREVIEWED")
s8 = B.derive_status(cl[cid6], o1)
ok(s8[0] == "UNVERIFIED" and "ocr_unreviewed" in s8[1] and "candidate_match" in s8[1], f"8a 値が一致しても OCR未レビューは UNVERIFIED {s8}")
o2 = mk_ledger(cl[cid6], "setting6.at_prob", {"kind": "probability_ratio", "den": "999", "text": "1/999"}, method="ocr", ocr="OCR_UNREVIEWED")
ok(B.derive_status(cl[cid6], o2)[0] == "UNVERIFIED", "8b OCR未レビューの食い違いは CONFLICTING にもしない（候補止まり）")
o3 = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, method="ocr", ocr="OCR_HUMAN_CONFIRMED")
ok(B.derive_status(cl[cid6], o3)[0] == "PRIMARY_VERIFIED", "8c 人が原本と目視照合した（OCR_HUMAN_CONFIRMED）場合のみ PRIMARY_VERIFIED")
ok(any("ocr なのに ocr_review=NOT_OCR" in e for e in B.validate_ledger(mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, method="ocr", ocr="NOT_OCR"))), "8d OCRなのに NOT_OCR と書く台帳は検証でエラー")

# ───────────────────────── [9] 出典なし・要件不足は検証済みにならない ─────────────────────────
print("[9] 出典・型式・条件・確認者の要件")
def status_with(**kw):
    return B.derive_status(cl[cid6], mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, **kw))
ok(B.derive_status(cl[cid6], {"sources": [], "machines": [], "facts": [], "bindings": []}) == ("UNVERIFIED", ["no_binding"]), "9a 台帳が空 → UNVERIFIED（記事に数値があるだけでは検証済みにならない）")
ok(status_with(with_source=False)[0] == "UNVERIFIED", "9b 出典（source）が無い → UNVERIFIED")
ok(status_with(reviewer="")[0] == "UNVERIFIED" and "reviewer_missing" in status_with(reviewer="")[1], "9c 確認者なし → UNVERIFIED")
ok("locator_missing" in status_with(locator="")[1], "9d 該当箇所（locator）なし → UNVERIFIED")
ok("conditions_missing" in status_with(conditions="")[1], "9e 条件なし → UNVERIFIED")
ok("verified_at_missing" in status_with(verified_at="")[1], "9f 確認日なし → UNVERIFIED")
ok("model_number_unconfirmed" in status_with(model_status="UNKNOWN", model_numbers=())[1] and status_with(model_status="UNKNOWN", model_numbers=())[0] == "UNVERIFIED", "9g 型式が未確認 → UNVERIFIED")
ok(status_with(model_status="NOT_PUBLISHED", model_numbers=())[0] == "PRIMARY_VERIFIED", "9h 型式が『公開資料に記載なし』と明示されていれば許容（NOT_PUBLISHED）")
ok(status_with(tier="secondary")[0] == "SECONDARY_CORROBORATED", "9i 二次資料は SECONDARY_CORROBORATED（PRIMARYにならない）")
ok(B.derive_status(cl[cid6], mk_ledger(cl[cid6], "setting6.at_prob", {"kind": "probability_ratio", "den": "999", "text": "1/999"}))[0] == "CONFLICTING", "9j 要件を満たした公式値と違えば CONFLICTING")
dg = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, digest=True)
ok(B.derive_status(cl[cid6], dg)[0] == "PRIMARY_VERIFIED" and "normalized_value" not in dg["facts"][0], "9k 値そのものを保存せず value_digest だけでも照合できる（権利配慮）")

# ───────────────────────── [10] baselineは承認ではない ─────────────────────────
print("[10] legacy baseline は承認ではない")
bl = B.build_baseline([base])
ok("承認ではない" in bl["_note"] and "検証済み扱いにしてはならず" in bl["_note"], "10a baseline に『承認ではない』旨が明記されている")
ok(all(B.derive_status(c, {"sources": [], "machines": [], "facts": [], "bindings": []})[0] == "UNVERIFIED" for c in B.extract_claims(base)), "10b baseline に載っている主張も UNVERIFIED のまま")
cur = B.extract_claims(base)
ok(B.classify_against_baseline(cur, bl)["UNCHANGED"] == len(cur), "10c 変更なしなら全て UNCHANGED")
cur2 = B.extract_claims(edited)
cl_ = B.classify_against_baseline(cur2, bl)
ok(cl_["EDITED"] == 1 and cl_["UNCHANGED"] == len(cur2) - 1, f"10d 1セルの編集は EDITED として検出 {cl_}")
extra = art(content=base["content"] + "\n追加の説明で稼働は2倍になります。\n")
ok(B.classify_against_baseline(B.extract_claims(extra), bl)["NEW"] >= 1, "10e 追加された主張は NEW")
ok(B.classify_against_baseline(B.extract_claims(art(content="## x\n\n本文のみ\n")), bl)["REMOVED"] > 0, "10f 削除された主張は REMOVED")
shipped = B.load_baseline()
ok(shipped is not None and shipped["schema_version"] == B.SCHEMA_VERSION and "承認ではない" in shipped["_note"], "10g 同梱の legacy_baseline.json が存在し、承認ではない旨を含む")
if shipped:
    sid = [r[0] for r in shipped["claims"]]
    ok(len(sid) == len(set(sid)) == shipped["generated_from"]["claims"], f"10h 同梱baselineの件数・一意性が整合（{len(sid)}件）")
    ok(all(len(r) == 3 for r in shipped["claims"]) and shipped["columns"] == ["claim_id", "span_hash", "context_hash"], "10i 同梱baselineの形式が正しい")
    ok(shipped["extractor_version"] == B.EXTRACTOR_VERSION, "10j baseline の抽出器バージョンが現行と一致（抽出器を変えたら再生成が必要）")
    st_all = {B.derive_status(c, B.load_ledger())[0] for c in all_claims}
    ok(st_all == {"UNVERIFIED"}, f"10k baseline があっても、実記事の全主張は UNVERIFIED（検証済みは0件）{st_all}")

# ───────────────────────── [11] 台帳の構造・権利の独立 ─────────────────────────
print("[11] 台帳の初期状態・検証・権利の独立性")
led0 = B.load_ledger()
ok(all(led0[k] == [] for k in ("sources", "machines", "facts", "bindings")), "11a 初期状態の台帳は4層とも空（公式値を自動登録していない）")
ok(B.validate_ledger(led0) == [], "11b 空の台帳は検証を通る")
bad = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, override="PRIMARY_VERIFIED")
ok(any("status_override" in e for e in B.validate_ledger(bad)), "11c 検証済みへの status_override は禁止（NOT_APPLICABLE のみ）")
na = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, override="NOT_APPLICABLE")
ok(B.validate_ledger(na) == [] or all("status_override" not in e for e in B.validate_ledger(na)), "11d NOT_APPLICABLE の明示は許可")
ok(B.derive_status(cl[cid6], na)[0] == "NOT_APPLICABLE", "11e 明示された NOT_APPLICABLE が導出される")
r_allow = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, rights={f: "EXPLICITLY_ALLOWED" for f in B.RIGHTS_FIELDS})
r_deny = mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, rights={f: "PROHIBITED" for f in B.RIGHTS_FIELDS})
ok(B.derive_status(cl[cid6], r_allow) == B.derive_status(cl[cid6], r_deny), "11f 権利状態は精度の判定に影響しない（独立）")
ok(B.rights_summary(r_deny["sources"][0])["copy_table"] == "PROHIBITED" and B.rights_summary({})["view"] == "UNKNOWN", "11g 権利状態は別に取得でき、未記載は UNKNOWN")
ok(any("rights" in e for e in B.validate_ledger(mk_ledger(cl[cid6], "setting6.at_prob", RATIO_266, rights={"view": "MAYBE"}))), "11h 権利の値が不正なら検証エラー")
dsem = mk_ledger(cl["2099-01-01-synth::bullet::導入日"], "date.announce", {"kind": "date", "iso": "2099-01-01"}, semantics=("announce",))
ok(B.derive_status(cl["2099-01-01-synth::bullet::導入日"], dsem)[1] == ["date_semantics_mismatch"], "11i 導入日の主張は、発表日・納品日のfactでは検証できない")
dsem2 = mk_ledger(cl["2099-01-01-synth::bullet::導入日"], "date.intro", {"kind": "date", "iso": "2099-01-01"}, semantics=("announce",))
ok("source_cannot_answer_date_kind" in B.derive_status(cl["2099-01-01-synth::bullet::導入日"], dsem2)[1], "11j 資料が『導入日』を答えられない種類（発表日のみ）なら date.intro としても検証できない")
dsem3 = mk_ledger(cl["2099-01-01-synth::bullet::導入日"], "date.intro", {"kind": "date", "iso": "2099-01-01"}, semantics=("intro",))
ok(B.derive_status(cl["2099-01-01-synth::bullet::導入日"], dsem3)[0] == "PRIMARY_VERIFIED", "11k 導入日を答えられる一次資料のfactなら検証できる")

# ───────────────────────── [12] 曖昧な主張は勝手に正規化しない ─────────────────────────
print("[12] 曖昧な主張")
amb = art(content="## まとめ\n\n機械割は97.8%〜114.9%（設定1〜6）です。\n")
ac = B.extract_claims(amb)[0]
ok(ac["extraction_confidence"] == "AMBIGUOUS" and ac["normalized_value"] is None and len(ac["tokens"]) == 2, f"12a 数値が複数ある文は AMBIGUOUS・正規化しない {ac['tokens']}")
ledamb = mk_ledger(ac, "payout_pct", {"kind": "percent", "value": "114.9"})
ok(B.derive_status(ac, ledamb)[1] == ["ambiguous_claim_cannot_be_compared"], "12b 曖昧な主張は、台帳に紐付けても検証にならない")
ok(all(c["extraction_confidence"] in ("HIGH", "MEDIUM", "AMBIGUOUS") for c in all_claims), "12c 確度は HIGH / MEDIUM / AMBIGUOUS のいずれか")
ok(all((c["normalized_value"] is None) == (c["extraction_confidence"] == "AMBIGUOUS") for c in all_claims), "12d AMBIGUOUS の主張は全て normalized_value=null（勝手に正規化していない）")

# ───────────────────────── [13] 副作用なし ─────────────────────────
print("[13] 副作用がない（ネットワーク・書き込み）")
src = (HERE / "blog_claims.py").read_text(encoding="utf-8")
ok(not any(w in src for w in ("import urllib", "import requests", "import socket", "import http", "urlopen", "subprocess")), "13a モジュールにネットワーク・外部プロセスのimportが無い")
B.extract_all(LIVE)
ok(sha_file(B.BLOG_PATH) == HASH_BLOG_BEFORE, "13b 抽出を実行しても public/blog_posts.json は変更されない")
ok({n: sha_file(B.LEDGER_DIR / n) for n in B.LAYER_FILES.values()} == HASH_LEDGER_BEFORE, "13c 台帳ファイルも変更されない（テスト中に書き込まない）")
ok(not (B.LEDGER_DIR.parent.parent / "public" / "blog_claims").exists() and not any("blog_claims" in str(p) for p in (ROOT / "public").rglob("*") if p.is_file()), "13d 台帳は public/ に置かれていない（公開されない）")
ok(B.BASELINE_PATH.parent == B.LEDGER_DIR and B.LEDGER_DIR.parent == HERE, "13e 台帳は scripts/blog_claims/ にある")

print(f"\n{'=' * 50}\nPASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
