#!/usr/bin/env python3
"""
機種名解決・種別判定の回帰テスト（DB非依存・オフライン実行可）。

合成 machines_master / machines_aliases を注入して、動的曖昧性ガードと
種別整合ガードを決定的に検証する。本番DBには一切アクセスしない。

実行:
    python scripts/test_machine_resolution.py
成功で exit 0 / 失敗で exit 1。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_complete_info as f
from machine_resolver import (
    MachineResolver, normalize_for_comparison, _series_stem, _has_type_prefix,
)


# ── 合成マスタ（曖昧・一意・両種別を網羅） ──────────────────────────────
_MASTERS = [
    # 牙狼: pachinko 2機種 → 裸「牙狼」は曖昧
    ("g1", "e牙狼12", "pachinko"),
    ("g2", "e牙狼12黄金騎士極限", "pachinko"),
    # 沖ドキ: slot+pachinko 複数 → 裸「沖ドキ」は曖昧（種別混在）
    ("o1", "L沖ドキ！DUOアンコール", "slot"),
    ("o2", "e沖ドキ！2", "pachinko"),
    ("o3", "沖ドキ！ゴージャス", "slot"),
    # 接頭辞なしの正式名「沖ドキ！DUO」（実DB同様 DUO2 は未登録＝誤解決防止の検証対象）
    ("o4", "沖ドキ！DUO", "slot"),
    # 世代違い検証用: 無印と2が両方存在（シリーズ名が名前の途中）→ 裸「ヴァルヴレイヴ」は曖昧
    ("v1", "L革命機ヴァルヴレイヴ2", "slot"),
    ("v2", "パチスロ 革命機ヴァルヴレイヴ", "slot"),
    # 甲鉄城/カバネリ: 複数 → 裸は曖昧、副題付きは一意
    ("k1", "L甲鉄城のカバネリ海門決戦", "slot"),
    ("k2", "スマスロ甲鉄城のカバネリ", "slot"),
    # 東京喰種: slot+pachinko → 裸は曖昧、prefix付きは一意
    ("t1", "L東京喰種", "slot"),
    ("t2", "e東京喰種", "pachinko"),
    # 北斗: 複数（slot+pachinko）
    ("h1", "スマスロ北斗の拳転生の章2", "slot"),
    ("h2", "スマスロ北斗の拳", "slot"),
    ("h3", "e北斗の拳暴凶星", "pachinko"),
    # 戦国乙女5: slot 1機種のみ（世代番号で一意）
    ("s1", "L戦国乙女5 業火を穿つ宿焔の双刃", "slot"),
    # 鉄拳: slot 1機種のみ（裸でも一意）
    ("z1", "L鉄拳4デビルVer.", "slot"),
    # 漢字副題で区別される派生機種（通常版 と 天膳BLACK EDITION版）
    ("b1", "バジリスク絆2", "slot"),
    ("b2", "スマスロバジリスク～甲賀忍法帖～絆2 天膳 BLACK EDITION", "slot"),
]


def make_resolver() -> MachineResolver:
    r = MachineResolver("http://test.local", "dummy")
    r._masters = [
        {"id": mid, "official_name": name,
         "normalized_name": normalize_for_comparison(name), "type": typ}
        for mid, name, typ in _MASTERS
    ]
    r._alias_map = {
        # 一意alias（世代番号あり）→ 正式名を返すべき
        normalize_for_comparison("戦国乙女5"): {
            "machine_id": "s1", "official_name": "L戦国乙女5 業火を穿つ宿焔の双刃",
            "machine_type": "slot", "confidence": 1.0},
        # 危険alias（裸シリーズを特定機種へ強制）→ ガードで拒否されるべき
        normalize_for_comparison("牙狼"): {
            "machine_id": "g1", "official_name": "e牙狼12",
            "machine_type": "pachinko", "confidence": 1.0},
        normalize_for_comparison("沖ドキ"): {
            "machine_id": "o1", "official_name": "L沖ドキ！DUOアンコール",
            "machine_type": "slot", "confidence": 1.0},
        # 一意シリーズの裸名 alias（マスタに鉄拳が1機種のみ）→ 解決してよい
        normalize_for_comparison("鉄拳"): {
            "machine_id": "z1", "official_name": "L鉄拳4デビルVer.",
            "machine_type": "slot", "confidence": 1.0},
    }
    r._master_stems = [(m["id"], _series_stem(m["official_name"])) for m in r._masters]
    r._prefixless_exact = {
        m["normalized_name"] for m in r._masters
        if not _has_type_prefix(m["official_name"])
    }
    r._loaded = True
    return r


PASS = 0
FAIL = 0


def _ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {label}")
    else:
        FAIL += 1
        print(f"  NG  {label}  {detail}")


def test_ambiguous_bare(r):
    print("[曖昧] 裸の複数候補シリーズ → 未解決(None)")
    for name in ["牙狼", "沖ドキ", "甲鉄城", "カバネリ", "東京喰種", "北斗"]:
        res = r.resolve(name)
        _ok(res is None, f"{name} → 未解決", f"got={res}")


def test_unique_resolve(r):
    print("[一意] prefix/世代/副題つき → 正式名で解決")
    cases = [
        ("e牙狼12黄金騎士極限", "e牙狼12黄金騎士極限", "pachinko"),
        ("L沖ドキ！DUOアンコール", "L沖ドキ！DUOアンコール", "slot"),
        ("スマスロ北斗の拳転生の章2", "スマスロ北斗の拳転生の章2", "slot"),
        ("甲鉄城のカバネリ海門決戦", "L甲鉄城のカバネリ海門決戦", "slot"),
        ("e東京喰種", "e東京喰種", "pachinko"),
        ("L戦国乙女5", "L戦国乙女5 業火を穿つ宿焔の双刃", "slot"),  # alias 経由
        # 接頭辞なしの完全な正式名は、続編の接頭辞であっても解決する（裸名扱いしない）
        ("沖ドキ！DUO", "沖ドキ！DUO", "slot"),
    ]
    for raw, official, typ in cases:
        res = r.resolve(raw)
        _ok(res is not None and res["official_name"] == official and res["machine_type"] == typ,
            f"{raw} → {official}[{typ}]", f"got={res}")


def test_generation_mismatch_rejected(r):
    print("[世代/数字違い] 別世代・別数字の機種へ fuzzy 解決しない")
    # 入力に数字あり、候補側に一致する数字が無い → 未解決
    _ok(r.resolve("L沖ドキDUO2") is None,
        "L沖ドキDUO2 → 未解決（DUO2 未登録・DUO/アンコールに寄せない）",
        f"got={r.resolve('L沖ドキDUO2')}")
    _ok(r.resolve("戦国乙女4") is None,
        "戦国乙女4 → 未解決（戦国乙女5に寄せない）", f"got={r.resolve('戦国乙女4')}")
    # 数字なし入力を数字付き候補（最新世代）へ寄せない（無印と2が両方存在＝曖昧）
    _ok(r.resolve("ヴァルヴレイヴ") is None,
        "ヴァルヴレイヴ → 未解決（無印/2 が両方存在し曖昧）",
        f"got={r.resolve('ヴァルヴレイヴ')}")
    # 一意シリーズ（マスタに1機種のみ）の裸名は alias で解決してよい
    tk = r.resolve("鉄拳")
    _ok(tk is not None and tk["official_name"] == "L鉄拳4デビルVer.",
        "鉄拳 → L鉄拳4デビルVer.（一意シリーズは解決）", f"got={tk}")


def test_subtitle_no_base_fallback(r):
    print("[副題誤解決防止] 漢字副題入力が通常版へ fallback しない")
    # 通常版「バジリスク絆2」へ誤解決してはいけない（未解決 or 天膳版のみ許容）
    for inp in ["バジリスク絆2 天膳", "バジ絆2 天膳", "バジリスク天膳"]:
        res = r.resolve(inp)
        bad = (res is not None and res["official_name"] == "バジリスク絆2")
        _ok(not bad, f"{inp} → 通常版バジリスク絆2にしない",
            f"got={res['official_name'] if res else '未解決'}")
    # Edition入力も通常版へ寄せない（未解決 or 天膳版のみ許容）
    for inp in ["絆2 BLACK EDITION", "バジリスク絆2 BLACK", "天膳 BLACK"]:
        res = r.resolve(inp)
        bad = (res is not None and res["official_name"] == "バジリスク絆2")
        _ok(not bad, f"{inp} → 通常版バジリスク絆2にしない",
            f"got={res['official_name'] if res else '未解決'}")


def test_identity_tokens():
    print("[identity] 型式・世代・副題トークンで別機種を区別")
    from machine_resolver import extract_identity_tokens as T
    pairs = [
        ("沖ドキ！DUO", "沖ドキ！DUO2"),      # DUO vs DUO2（数字）
        ("沖ドキ！GOLD", "沖ドキ！BLACK"),     # GOLD vs BLACK（型式語）
        ("沖ドキ！DUO", "沖ドキ！GOLD"),       # DUO vs GOLD
        ("戦国乙女4", "戦国乙女5"),            # 4 vs 5
        ("ヴァルヴレイヴ", "ヴァルヴレイヴ2"),    # 無印 vs 2
        ("北斗の拳", "北斗の拳 転生の章2"),      # 無印 vs 転生の章2
        ("通常機", "LT機"),                   # 通常 vs LT
        ("機種SPEC1", "機種SPEC2"),          # SPEC違い
        ("機種Ver.1", "機種Ver.2"),          # Ver.違い
    ]
    for a, b in pairs:
        _ok(T(a) != T(b), f"{a} ≠ {b}", f"{sorted(T(a))} vs {sorted(T(b))}")
    # ローマ数字と算用数字は同一視、全角半角も統一
    _ok(T("DUOⅡ") == T("DUO2") == T("ＤＵＯ２"),
        "DUOⅡ == DUO2 == ＤＵＯ２（表記統一）",
        f"{sorted(T('DUOⅡ'))}/{sorted(T('DUO2'))}/{sorted(T('ＤＵＯ２'))}")


def test_type_from_master(r):
    print("[種別] master.type を採用（本文単位に依存しない）")
    # resolve は本文を受け取らない = 単位で種別が変わらないことの証明
    slot = r.resolve("L戦国乙女5")
    pach = r.resolve("e東京喰種")
    _ok(slot and slot["machine_type"] == "slot", "slot機種は master の slot")
    _ok(pach and pach["machine_type"] == "pachinko", "pachinko機種は master の pachinko")


def test_cross_type_prefix_rejected(r):
    print("[種別整合] prefix種別と食い違う候補は不採用")
    # "P北斗の拳"(pachinko想定) を裸「北斗」相当に寄せない / slot北斗にも寄せない
    res = r.resolve("P北斗の拳")
    _ok(res is None or res["machine_type"] == "pachinko",
        "P北斗の拳 は slot機種へ確定しない", f"got={res}")


def test_alias_returns_official(r):
    print("[alias] 保存値は alias 文字列でなく正式マスタ名")
    res = r.resolve("戦国乙女5")
    _ok(res is not None and res["official_name"] == "L戦国乙女5 業火を穿つ宿焔の双刃",
        "戦国乙女5(alias) → 正式名", f"got={res}")


def test_dangerous_alias_rejected(r):
    print("[危険alias] 裸シリーズを強制する alias は採用しない")
    for name in ["牙狼", "沖ドキ"]:
        res = r.resolve(name)
        _ok(res is None, f"{name}(危険alias有) → 未解決", f"got={res}")


def test_noise_not_machine():
    print("[ノイズ] 数値/枚数/時刻/台番号 は機種名にしない")
    noise = ["本日47,500玉 コンプリート", "18571枚 コンプリート",
             "17:55頃 コンプリート機能発動", "1006番台 コンプリート"]
    for txt in noise:
        got = f.extract_machines(txt) or [f.extract_machine(txt)]
        got = [g for g in got if g]
        _ok(not got, f"{txt[:16]} → 機種名なし", f"got={got}")


def main():
    r = make_resolver()
    test_ambiguous_bare(r)
    test_unique_resolve(r)
    test_generation_mismatch_rejected(r)
    test_subtitle_no_base_fallback(r)
    test_identity_tokens()
    test_type_from_master(r)
    test_cross_type_prefix_rejected(r)
    test_alias_returns_official(r)
    test_dangerous_alias_rejected(r)
    test_noise_not_machine()
    print(f"\n=> PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
