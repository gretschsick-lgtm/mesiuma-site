#!/usr/bin/env python3
"""
CC-QUALITY-2M — Quality Funnel telemetry (metadata-only) のユニットテスト。

production DB / network には一切依存しない（fixture純粋関数のみ）。
最重要: raw tweet 本文・画像・生ハンドルがカウンタ/出力ファイルに一切
含まれないことを確認する（このテストスイート自体が privacy boundary の回帰検知）。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_complete_info as F

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


# ══════════════════════════════════════════════════════════════════════════
# A. is_store_tweet: パターン単位テレメトリ（判定ロジック自体は変更していないことも確認）
# ══════════════════════════════════════════════════════════════════════════

F.reset_quality_counters()
result = F.is_store_tweet("youtube.comで生配信中！コンプリート達成しました")
c = F.get_quality_counters()
ok(result is False, "A1 EXCLUDE_PATTERNS一致テキストは is_store_tweet=False（判定不変）")
ok(c.get("EXCLUDED_PATTERN") == 1, "A2 EXCLUDED_PATTERN が1加算される")
ok(c.get("exclude_pattern_0") == 1, "A3 exclude_pattern_0（youtube.com）が加算される")
ok("STORE_PATTERN_MATCHED" not in c, "A4 EXCLUDE一致時はSTORE_PATTERN_MATCHEDが加算されない")

F.reset_quality_counters()
result = F.is_store_tweet("今日はいい天気ですね")
c = F.get_quality_counters()
ok(result is False, "A5 無関係テキストは is_store_tweet=False（判定不変）")
ok(c.get("NO_STORE_PATTERN") == 1, "A6 NO_STORE_PATTERN が1加算される")
ok("EXCLUDED_PATTERN" not in c, "A7 EXCLUDE非一致時はEXCLUDED_PATTERNが加算されない")

F.reset_quality_counters()
result = F.is_store_tweet("マルハンテスト店にてコンプリート達成おめでとうございます")
c = F.get_quality_counters()
ok(result is True, "A8 STORE_TWEET_PATTERNS一致テキストは is_store_tweet=True（判定不変）")
ok(c.get("STORE_PATTERN_MATCHED") == 1, "A9 STORE_PATTERN_MATCHED が1加算される")
ok(any(k.startswith("store_pattern_") for k in c), "A10 store_pattern_<idx> が加算される")

# ══════════════════════════════════════════════════════════════════════════
# B. parse_tweet: drop reason（既存の drop 条件そのものは一切変更していない）
# ══════════════════════════════════════════════════════════════════════════

F.reset_quality_counters()
entries = F.parse_tweet(
    "本日コンプリートしました", "https://x.com/unknown_random_user_xyz/status/1",
    "2026-09-07", "2026-09-07", "12:00",
)
c = F.get_quality_counters()
ok(entries == [], "B1 未知ハンドル×店舗名抽出失敗は従来通り [] を返す（判定不変）")
ok(c.get("STORE_EXTRACTION_FAILED") == 1, "B2 STORE_EXTRACTION_FAILED が1加算される")
ok("PARSED_OK" not in c, "B3 dropされた場合PARSED_OKは加算されない")

F.reset_quality_counters()
entries = F.parse_tweet(
    "マルハンテスト店にてコンプリート達成おめでとうございます",
    "https://x.com/unknown_random_user_xyz/status/2",
    "2026-09-07", "2026-09-07", "12:00",
)
c = F.get_quality_counters()
ok(len(entries) == 1, "B4 店舗名抽出成功時は従来通りentryが1件返る（判定不変）")
# extract_store()の既存挙動（本テストの変更対象外）: 先頭のチェーン名は
# 「役職・ニックネーム除去」正規表現の対象になり "テスト店" として抽出される。
# ここではその既存挙動自体ではなく、store抽出が成功しfalsyにならないことのみ確認する。
ok(bool(entries[0]["store"]), "B5 store抽出結果が空でない（既存extract_store挙動は不変・対象外）")
ok(c.get("MACHINE_EXTRACTION_FAILED") == 1, "B6 機種名なしはMACHINE_EXTRACTION_FAILEDが加算される")
ok(c.get("SLOT_NOT_FOUND") == 1, "B7 台番号なしはSLOT_NOT_FOUNDが加算される")
ok(c.get("PARSED_OK") == 1, "B8 PARSED_OK が加算される")

# ══════════════════════════════════════════════════════════════════════════
# C. Multi-machine / slot mismatch（extract_machines/extract_slot_numberを
#    monkeypatch し、正規表現の詳細に依存せず分岐そのものを確定的に検証する）
# ══════════════════════════════════════════════════════════════════════════

_orig_extract_machines = F.extract_machines
_orig_extract_slot = F.extract_slot_number
try:
    F.extract_machines = lambda text: ["e機種A", "スロット機種B"]
    F.extract_slot_number = lambda text: "123"
    F.reset_quality_counters()
    entries = F.parse_tweet(
        "マルハンテスト店にてコンプリート達成おめでとうございます",
        "https://x.com/unknown_random_user_xyz/status/3",
        "2026-09-07", "2026-09-07", "12:00",
    )
    c = F.get_quality_counters()
    ok(len(entries) == 2, "C1 複数機種は従来通り複数entryを生成する（判定不変）")
    ok(entries[0]["slot_number"] == "123" and entries[1]["slot_number"] == "",
       "C2 台番号は1機種目のみ付与される既知の設計（判定不変、CC-QUALITY-1確認済み）")
    ok(c.get("MULTI_MACHINE") == 1, "C3 MULTI_MACHINE が加算される")
    ok(c.get("SLOT_MACHINE_MISMATCH") == 1, "C4 SLOT_MACHINE_MISMATCH が加算される")
    ok(c.get("PARSED_OK") == 2, "C5 PARSED_OK は生成entry数(2件)ぶん加算される")
finally:
    F.extract_machines = _orig_extract_machines
    F.extract_slot_number = _orig_extract_slot

# ══════════════════════════════════════════════════════════════════════════
# D. Privacy boundary: raw text/画像/生ハンドルがカウンタに一切含まれない
# ══════════════════════════════════════════════════════════════════════════

F.reset_quality_counters()
SECRET_TEXT = "この文字列は絶対にカウンタへ混入してはいけないraw本文サンプルxyz12345"
F.parse_tweet(
    f"マルハンテスト店にてコンプリート達成おめでとうございます {SECRET_TEXT}",
    "https://x.com/some_handle_abc/status/4",
    "2026-09-07", "2026-09-07", "12:00",
)
c = F.get_quality_counters()
serialized = json.dumps(c, ensure_ascii=False)
ok(SECRET_TEXT not in serialized, "D1 raw tweet本文の断片がカウンタ(JSON化後含む)に含まれない")
ok("some_handle_abc" not in serialized, "D2 生ハンドルがカウンタに含まれない")
ok(all(isinstance(v, int) for v in c.values()), "D3 カウンタの値は全て整数のみ（textや配列を含まない）")

# ══════════════════════════════════════════════════════════════════════════
# E. write_quality_summary: fail-open（書き込み失敗しても例外を外に伝播しない）
# ══════════════════════════════════════════════════════════════════════════

F.reset_quality_counters()
F._qcount("COLLECTED", 3)
bad_path = "/nonexistent_dir_xyz_abc/should_fail/quality.json"
try:
    result = F.write_quality_summary(bad_path)
    ok(result is False, "E1 書き込み不可能なパスでも例外を投げずFalseを返す(fail-open)")
except Exception as e:
    ok(False, f"E1 書き込み不可能なパスで例外が伝播した(fail-openに違反): {e}")

with tempfile.TemporaryDirectory() as td:
    good_path = Path(td) / "complete_quality_test.json"
    result = F.write_quality_summary(str(good_path))
    ok(result is True, "E2 正常パスへの書き込みはTrueを返す")
    payload = json.loads(good_path.read_text(encoding="utf-8"))
    ok(payload.get("counts", {}).get("COLLECTED") == 3, "E3 書き出したJSONのcountsが正しい")
    ok("meta" in payload and "run_number" in payload["meta"] and "git_sha" in payload["meta"],
       "E4 meta(run_number/git_sha)が含まれる（新しいversion管理テーブルは作らない設計）")
    serialized_file = good_path.read_text(encoding="utf-8")
    ok(SECRET_TEXT not in serialized_file, "E5 出力ファイルにもraw本文が含まれない")

# ══════════════════════════════════════════════════════════════════════════
# F. merge_complete_data._merge_quality_summaries: 複数matrix jobの集計
# ══════════════════════════════════════════════════════════════════════════

import merge_complete_data as M

with tempfile.TemporaryDirectory() as td:
    orig_root = M.ROOT
    try:
        fake_root = Path(td)
        (fake_root / "public").mkdir()
        M.ROOT = fake_root

        (fake_root / "public" / "complete_quality_handle_a.json").write_text(
            json.dumps({"counts": {"COLLECTED": 10, "PARSED_OK": 3}, "meta": {}}), encoding="utf-8"
        )
        (fake_root / "public" / "complete_quality_handle_b.json").write_text(
            json.dumps({"counts": {"COLLECTED": 5, "PARSED_OK": 1}, "meta": {}}), encoding="utf-8"
        )
        # 7 matrix jobs 相当のうち1つが異常/空でも集計全体を壊さないことを確認
        (fake_root / "public" / "complete_quality_manager.json").write_text("not valid json", encoding="utf-8")

        totals = M._merge_quality_summaries(keep=True)
        ok(totals.get("COLLECTED") == 15, "F1 複数matrix jobのCOLLECTEDが正しく合算される")
        ok(totals.get("PARSED_OK") == 4, "F2 複数matrix jobのPARSED_OKが正しく合算される")
        ok((fake_root / "public" / "complete_quality_handle_a.json").exists(),
           "F3 keep=Trueなら quality ファイルは削除されない")

        totals2 = M._merge_quality_summaries(keep=False)
        ok(not (fake_root / "public" / "complete_quality_handle_a.json").exists(),
           "F4 keep=Falseなら quality ファイルは削除される（partial fileと同じ運用）")
    finally:
        M.ROOT = orig_root

# ══════════════════════════════════════════════════════════════════════════
# G. CC-QUALITY-2M-T2 — main() の Behavior Matrix（Case A/B/C/D）
#    zero-partial(complete追加0件)の natural run でも quality funnel が
#    集計・出力されることを確認する（今回のroot fix本体）。
# ══════════════════════════════════════════════════════════════════════════

import contextlib
import io


def _run_main_with_fixture(fake_root: Path, argv_extra: list[str] | None = None):
    """merge_complete_data.main() を fake_root 上で実行し、
    (stdout文字列, save_complete呼び出し回数, update_ranking呼び出し回数) を返す。
    save_complete/update_ranking は実際のファイル書き込み・ネットワークを一切行わないstubに差し替える。
    """
    orig_root = M.ROOT
    orig_save_complete = M.save_complete
    orig_update_ranking = M.update_ranking
    orig_argv = sys.argv

    calls = {"save_complete": 0, "update_ranking": 0}

    def _stub_save_complete(entries, date):
        calls["save_complete"] += 1
        return len(entries)

    def _stub_update_ranking():
        calls["update_ranking"] += 1

    try:
        M.ROOT = fake_root
        M.save_complete = _stub_save_complete
        M.update_ranking = _stub_update_ranking
        sys.argv = ["merge_complete_data.py", "--date", "2026-09-09"] + (argv_extra or [])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            M.main()
        return buf.getvalue(), calls["save_complete"], calls["update_ranking"]
    finally:
        M.ROOT = orig_root
        M.save_complete = orig_save_complete
        M.update_ranking = orig_update_ranking
        sys.argv = orig_argv


# --- Case B(今回の主対象): partial=0 / quality>0 ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"COLLECTED": 5, "NO_STORE_PATTERN": 5}, "meta": {"run_number": "999"}}),
        encoding="utf-8",
    )
    out, n_save, n_rank = _run_main_with_fixture(fake_root)
    ok(n_save == 0, "G-B1 partial=0の場合 save_complete は呼ばれない")
    ok(n_rank == 0, "G-B2 partial=0の場合 update_ranking は呼ばれない")
    ok("📊 Quality Funnel" in out, "G-B3 partial=0でもQuality Funnelがstdoutに出力される(root fix本体)")
    ok("collected: 5" in out, "G-B4 quality shardの実カウントが反映される")
    ok("部分ファイルが見つかりません" in out, "G-B5 既存の情報メッセージも維持される")

# --- Case D: partial=0 / quality=0 ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    out, n_save, n_rank = _run_main_with_fixture(fake_root)
    ok(n_save == 0, "G-D1 partial=0/quality=0でもsave_complete呼ばれない")
    ok(n_rank == 0, "G-D2 partial=0/quality=0でもupdate_ranking呼ばれない")
    ok("📊 Quality Funnel" not in out, "G-D3 quality shardが無ければFunnelは出力されない(元の設計を維持)")
    ok("部分ファイルが見つかりません" in out, "G-D4 既存の情報メッセージは出る")

# --- Case A(既存本番動作の回帰確認): partial>0 / quality>0 ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_partial_handle_a.json").write_text(
        json.dumps([{"id": "abc123", "x_url": "https://x.com/foo/status/1", "store": "テスト店",
                     "machine": "", "slot_number": "", "date": "2026-09-09", "time": "12:00",
                     "store_handle": "foo", "store_x_url": "", "manager_x_url": "",
                     "source_account_type": "unknown", "collected_at": "2026-09-09T00:00:00Z"}]),
        encoding="utf-8",
    )
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"COLLECTED": 3, "SAVED_SUPABASE": 1}, "meta": {}}), encoding="utf-8"
    )
    out, n_save, n_rank = _run_main_with_fixture(fake_root)
    ok(n_save == 1, "G-A1 partial>0なら従来通りsave_completeが呼ばれる(回帰なし)")
    ok(n_rank == 1, "G-A2 partial>0なら従来通りupdate_rankingが呼ばれる(回帰なし)")
    ok("📊 Quality Funnel" in out, "G-A3 partial>0/quality>0でも従来通りFunnelが出力される")
    ok("saved_json: 1" in out, "G-A4 実際のadded件数(1)がFunnelのsaved_jsonに反映される(added=0で固定されていない)")

# --- Case C: partial>0 / quality=0 (fail-open維持の回帰確認) ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_partial_handle_a.json").write_text(
        json.dumps([{"id": "abc456", "x_url": "https://x.com/foo/status/2", "store": "テスト店2",
                     "machine": "", "slot_number": "", "date": "2026-09-09", "time": "12:00",
                     "store_handle": "foo", "store_x_url": "", "manager_x_url": "",
                     "source_account_type": "unknown", "collected_at": "2026-09-09T00:00:00Z"}]),
        encoding="utf-8",
    )
    out, n_save, n_rank = _run_main_with_fixture(fake_root)
    ok(n_save == 1, "G-C1 quality shard欠落でもsave_completeは正常に呼ばれる(fail-open)")
    ok(n_rank == 1, "G-C2 quality shard欠落でもupdate_rankingは正常に呼ばれる(fail-open)")

# ══════════════════════════════════════════════════════════════════════════
# H. CC-QUALITY-3E3 — Machine extraction pattern telemetry(metadata-only)
#    #5(l_generic)/#7(e_generic)/シリーズアンカーのbucket分類とresolver結果の
#    正しい紐付けを検証する。raw candidate文字列はカウンタに一切含まれない。
# ══════════════════════════════════════════════════════════════════════════

# --- H1. pattern数とslug数の一致(3D/3Eで「28」「17/18」と揺れていた数を実コードで固定) ---
ok(len(F.MACHINE_PATTERNS) == len(F.MACHINE_PATTERN_SLUGS),
   f"H1 MACHINE_PATTERNSとMACHINE_PATTERN_SLUGSの件数が一致({len(F.MACHINE_PATTERNS)}件)")
ok(F.MACHINE_PATTERN_SLUGS[F._L_GENERIC_PATTERN_IDX] == "l_generic",
   f"H2 l_genericのindexが実コードと一致(#{F._L_GENERIC_PATTERN_IDX})")
ok(F.MACHINE_PATTERN_SLUGS[F._E_GENERIC_PATTERN_IDX] == "e_generic",
   f"H3 e_genericのindexが実コードと一致(#{F._E_GENERIC_PATTERN_IDX})")
ok(len(F._SERIES_ANCHOR_INDICES) == 21,
   f"H4 シリーズアンカー件数は実コード上21件(3D/3Eの「17/18」表記は誤りだったことを固定)"
   f" got={len(F._SERIES_ANCHOR_INDICES)}")
for _idx in F._SERIES_ANCHOR_INDICES:
    ok(_idx in F._SERIES_ANCHOR_TEXT, f"H5 series index #{_idx} に対応するアンカー文字列が定義されている")

# --- H6. L_GENERIC bucket分類 ---
ok(F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, "L沖ドキ")["bucket"] == "0_1",
   "H6 L直後が日本語(run=0) → bucket 0_1")
ok(F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, "LINEからチェック")["bucket"] == "2plus",
   "H7 L直後にASCII2文字以上(LINE型) → bucket 2plus")

# --- H8. E_GENERIC bucket分類(3Eで確認した閾値: 0-2/3-5/6+) ---
ok(F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "e86ｰエイティシックス")["bucket"] == "0_2",
   "H8 e86型(run=2, production実在パターン) → bucket 0_2")
ok(F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "efeverキン肉マン")["bucket"] == "3_5",
   "H9 efever型(run=5, production実在alias) → bucket 3_5(rejectされないbucket)")
ok(F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "eabcdefキン肉マン")["bucket"] == "6plus",
   "H10 ASCII6文字以上連続 → bucket 6plus")

# --- H11. series anchor: 括弧内のparticleはboundaryにならない(3Eのカバネリ例外を再現) ---
_kabaneri_idx = F.MACHINE_PATTERN_SLUGS.index("kabaneri_anchor")
kabaneri_case = "甲鉄城のカバネリ 海門（うなと）決戦"
meta_kabaneri = F._classify_pattern_bucket(_kabaneri_idx, kabaneri_case)
ok(meta_kabaneri["boundary"] is False, f"H11 括弧内(うなと)の「と」はboundaryとして検出しない(3Eのfalse-drop回避を再現) (got={meta_kabaneri})")

_garo_idx = F.MACHINE_PATTERN_SLUGS.index("garo_anchor")
meta_garo_none = F._classify_pattern_bucket(_garo_idx, "牙狼12黄金騎士極限")
ok(meta_garo_none["boundary"] is False, "H12 会話的続きがない場合 boundary=False")

meta_garo_present = F._classify_pattern_bucket(_garo_idx, "牙狼はひりつく感じ")
ok(meta_garo_present["boundary"] is True, "H13 「牙狼は...」→ boundary=True(会話文混入を検出)")

_shinuchi_idx = F.MACHINE_PATTERN_SLUGS.index("shinuchi_yoshimune_anchor")
meta_shinuchi = F._classify_pattern_bucket(_shinuchi_idx, "真打吉宗まで…")
ok(meta_shinuchi["boundary"] is True, "H14 「真打吉宗まで」→ boundary=True(「まで」を検出)")

# --- H15. Correlation: 同一candidate単位でresolver結果が正しく紐付く(single) ---
F.reset_quality_counters()
fake_entry_a = {"id": "a", "machine": "LINEからチェック"}
F._MACHINE_EXTRACTION_META[id(fake_entry_a)] = F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, "LINEからチェック")
F._record_extraction_telemetry(F._MACHINE_EXTRACTION_META.pop(id(fake_entry_a), None), resolved=False)
c = F.get_quality_counters()
ok(c.get("EXTRACT_L_GENERIC_RUN_2PLUS_UNRESOLVED") == 1, f"H15 L_GENERIC(2plus)+unresolvedが正しいkeyへ加算される (got={c})")
ok(id(fake_entry_a) not in F._MACHINE_EXTRACTION_META, "H16 消費後は対応表から除去される(メモリリーク防止)")

# --- H17. Single/Multi Correlation: 2candidateが別pattern・別resolver結果でも混線しない ---
F.reset_quality_counters()
entry_l = {"id": "l1", "machine": "LINEからチェック"}      # l_generic, run>=2
entry_e = {"id": "e1", "machine": "efeverキン肉マン"}       # e_generic, run=5(3_5)
F._MACHINE_EXTRACTION_META[id(entry_l)] = F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, entry_l["machine"])
F._MACHINE_EXTRACTION_META[id(entry_e)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, entry_e["machine"])
# entry_l は unresolved、entry_e は resolved という異なる結果をシミュレート
F._record_extraction_telemetry(F._MACHINE_EXTRACTION_META.pop(id(entry_l), None), resolved=False)
F._record_extraction_telemetry(F._MACHINE_EXTRACTION_META.pop(id(entry_e), None), resolved=True)
c = F.get_quality_counters()
ok(c.get("EXTRACT_L_GENERIC_RUN_2PLUS_UNRESOLVED") == 1, f"H17 candidate Aのunresolvedが正しく加算(混線なし) (got={c})")
ok(c.get("EXTRACT_E_GENERIC_RUN_3_5_RESOLVED") == 1, f"H18 candidate Bのresolvedが正しく加算(混線なし) (got={c})")
ok(c.get("EXTRACT_L_GENERIC_RUN_2PLUS_RESOLVED") is None, "H19 candidate Aがresolved側へ誤加算されていない")
ok(c.get("EXTRACT_E_GENERIC_RUN_3_5_UNRESOLVED") is None, "H20 candidate Bがunresolved側へ誤加算されていない")

# --- H21. Behavior Preservation: telemetry追加前後で抽出結果(文字列)が不変であること ---
_behavior_cases = [
    ("LINEからチェックしてね📈🔎", ["LINEからチェックしてね📈🔎"]),
    ("本日47,500玉 コンプリート", []),
]
for _txt, _expected in _behavior_cases:
    _got = F.extract_machines(_txt)
    ok(_got == _expected, f"H21 抽出結果が既存仕様のまま不変: {_txt!r} (got={_got} expected={_expected})")

# --- H22. Privacy: quality summary出力にraw candidate文字列が含まれない ---
F.reset_quality_counters()
_SECRET_MACHINE = "この文字列は絶対にカウンタへ混入してはいけないraw機種名xyz999"
entry_secret = {"id": "s1", "machine": _SECRET_MACHINE}
F._MACHINE_EXTRACTION_META[id(entry_secret)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, _SECRET_MACHINE)
F._record_extraction_telemetry(F._MACHINE_EXTRACTION_META.pop(id(entry_secret), None), resolved=False)
with tempfile.TemporaryDirectory() as td:
    _p = Path(td) / "complete_quality_test.json"
    F.write_quality_summary(str(_p))
    _serialized = _p.read_text(encoding="utf-8")
    ok(_SECRET_MACHINE not in _serialized, "H22 raw機種名文字列がquality summaryファイルに含まれない")
    ok(all(isinstance(v, int) for v in json.loads(_serialized)["counts"].values()),
       "H23 countsの値は全て整数のみ(H22と合わせてprivacy境界を確認)")

# --- H24. Cardinality: 新規keyの理論上限を確認(bounded) ---
_max_l = 2 * 2       # 2 bucket x 2 result
_max_e = 3 * 2       # 3 bucket x 2 result
_max_series = len(F._SERIES_ANCHOR_INDICES) * 2 * 2  # anchor x boundary(2) x result(2)
_max_path = 2
_max_total = _max_l + _max_e + _max_series + _max_path
ok(_max_total < 200, f"H24 新規telemetry keyの理論上限は候補内容に依存せず固定({_max_total}件)")

# ══════════════════════════════════════════════════════════════════════════
# I. CC-QUALITY-3E3A — _MACHINE_EXTRACTION_META cleanup(残留防止)
#    CC-QUALITY-3E4のREAD-ONLY監査で確定した2つの漏れ経路
#    (dedup除外・Supabase early return)、およびresolver例外時の
#    cleanupを直接検証する。
# ══════════════════════════════════════════════════════════════════════════

import machine_resolver as MR


class _FakeResolver:
    """テスト用のmachine resolverスタブ(実DB/ネットワーク非依存)。"""
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise_exc = raise_exc
        self.calls = 0

    def resolve(self, raw_name):
        self.calls += 1
        if self._raise_exc:
            raise self._raise_exc
        return self._result

    def save_unknown(self, raw_name, source_url=""):
        pass


def _with_sb_env_and_request(fn):
    """_sb_env()を有効化し、_sb_request()を実ネットワークなしのfakeに差し替えて実行する。"""
    orig_env = F._sb_env
    orig_req = F._sb_request
    try:
        F._sb_env = lambda: ("https://fake.supabase.local", "fake-key")
        F._sb_request = lambda method, path, body=None, prefer=None: (
            200, json.dumps(body if isinstance(body, list) else [body]).encode()
        )
        return fn()
    finally:
        F._sb_env = orig_env
        F._sb_request = orig_req


# --- I1. Dedup cleanup: dropされたentryのmetadataだけ消え、keptは残る ---
F._MACHINE_EXTRACTION_META.clear()
entry_kept = {"id": "dupid", "machine": "LINEからチェック"}
entry_dropped = {"id": "dupid", "machine": "efeverキン肉マン"}  # 同じid→dedupでdropされる想定
F._MACHINE_EXTRACTION_META[id(entry_kept)] = F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, entry_kept["machine"])
F._MACHINE_EXTRACTION_META[id(entry_dropped)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, entry_dropped["machine"])
deduped = F._dedupe_entries_with_telemetry_cleanup([entry_kept, entry_dropped])
ok(len(deduped) == 1 and deduped[0] is entry_kept, "I1 dedup結果自体は既存仕様のまま不変(先勝ち)")
ok(id(entry_kept) in F._MACHINE_EXTRACTION_META, "I2 keptされたentryのmetadataは残る")
ok(id(entry_dropped) not in F._MACHINE_EXTRACTION_META, "I3 dropされたentryのmetadataはcleanupされる(3E4で発見した漏れの修正)")
F._MACHINE_EXTRACTION_META.clear()

# --- I4. Supabase early return: _sb_env()がFalseでもmetadataがcleanupされる ---
F._MACHINE_EXTRACTION_META.clear()
orig_env = F._sb_env
try:
    F._sb_env = lambda: None
    e_early = {"id": "early1", "x_url": "https://x.com/foo/status/1", "machine": "efeverキン肉マン"}
    F._MACHINE_EXTRACTION_META[id(e_early)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, e_early["machine"])
    result = F.supabase_write_complete([e_early])
    ok(result == (0, 0), "I5 _sb_env()falseの戻り値は既存仕様のまま(0, 0)")
    ok(id(e_early) not in F._MACHINE_EXTRACTION_META, "I6 _sb_env()false early returnでもmetadataがcleanupされる(3E4で発見した漏れの修正)")
finally:
    F._sb_env = orig_env
F._MACHINE_EXTRACTION_META.clear()

# --- I7. x_url欠落entry: batch内でcontinueする経路でもcleanupされる ---
def _test_x_url_missing():
    F._MACHINE_EXTRACTION_META.clear()
    e_noxurl = {"id": "noxurl1", "x_url": "", "machine": "efeverキン肉マン"}
    F._MACHINE_EXTRACTION_META[id(e_noxurl)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, e_noxurl["machine"])
    orig_resolver_mod = MR.get_resolver
    try:
        MR.get_resolver = lambda: None  # resolverは未使用でよい(x_url欠落で早期continueするため)
        F.supabase_write_complete([e_noxurl])
    finally:
        MR.get_resolver = orig_resolver_mod
    ok(id(e_noxurl) not in F._MACHINE_EXTRACTION_META, "I7 x_url欠落entryでもcleanupされる")

_with_sb_env_and_request(_test_x_url_missing)
F._MACHINE_EXTRACTION_META.clear()

# --- I8. Resolver例外: 例外はそのまま伝播するが、metadataはfinallyでcleanupされる ---
def _test_resolver_exception():
    F._MACHINE_EXTRACTION_META.clear()
    e_exc = {"id": "exc1", "x_url": "https://x.com/foo/status/2", "machine": "efeverキン肉マン"}
    F._MACHINE_EXTRACTION_META[id(e_exc)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, e_exc["machine"])
    fake_resolver = _FakeResolver(raise_exc=RuntimeError("simulated resolver failure"))
    orig_resolver_mod = MR.get_resolver
    raised = False
    try:
        MR.get_resolver = lambda: fake_resolver
        F.supabase_write_complete([e_exc])
    except RuntimeError:
        raised = True
    finally:
        MR.get_resolver = orig_resolver_mod
    ok(raised, "I9 resolver例外は既存仕様通りそのまま伝播する(exception policy不変)")
    ok(id(e_exc) not in F._MACHINE_EXTRACTION_META, "I10 例外発生後もmetadataはfinallyでcleanupされる(残留なし)")

_with_sb_env_and_request(_test_resolver_exception)
F._MACHINE_EXTRACTION_META.clear()

# --- I11. Sequential candidate isolation: Aのmetadataがcleanupされた後、Bには影響しない ---
def _test_sequential_isolation():
    F._MACHINE_EXTRACTION_META.clear()
    e_a = {"id": "seqA", "x_url": "https://x.com/foo/status/3", "machine": "efeverキン肉マン"}
    F._MACHINE_EXTRACTION_META[id(e_a)] = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, e_a["machine"])
    MR.get_resolver_orig = MR.get_resolver
    fake_resolved = _FakeResolver(result={"official_name": "eFキン肉マン", "machine_id": "mid1"})
    try:
        MR.get_resolver = lambda: fake_resolved
        F.supabase_write_complete([e_a])
    finally:
        MR.get_resolver = MR.get_resolver_orig
    ok(id(e_a) not in F._MACHINE_EXTRACTION_META, "I11 candidate A処理後、metadataは残らない")

    # 新しいcandidate Bを作成(id()再利用が起きてもstale keyが存在しないことが保証されていればOK)
    e_b = {"id": "seqB", "x_url": "https://x.com/foo/status/4", "machine": "LINEからチェック"}
    ok(id(e_b) not in F._MACHINE_EXTRACTION_META,
       "I12 新規candidate BはAのstale metadataを取得しない(cross-run isolation)")

_with_sb_env_and_request(_test_sequential_isolation)
F._MACHINE_EXTRACTION_META.clear()

# --- I13. _LAST_EXTRACT_META: 前回callのmetadataが次callへ持ち越されない ---
F.extract_machine("e牙狼12がコンプリート達成")
ok(len(F._LAST_EXTRACT_META) >= 1, "I13a match ありのcallではmetadataが記録される")
F.extract_machine("本日47,500玉 コンプリート")  # 今回はno match
ok(F._LAST_EXTRACT_META == [], "I13b no-match callでは前回のmetadataが残らない(callごとにclear済み)")

F.extract_machines("e牙狼12とL革命機ヴァルヴレイヴ2が同時にコンプリート")
ok(len(F._LAST_EXTRACT_META) >= 1, "I14a multi matchでmetadataが記録される")
F.extract_machines("本日47,500玉 コンプリート")
ok(F._LAST_EXTRACT_META == [], "I14b 次のno-match callで前回分が残らない")

# --- I15. Final Residual Proof: 一連の処理後、_MACHINE_EXTRACTION_METAは空 ---
ok(len(F._MACHINE_EXTRACTION_META) == 0,
   f"I15 一連のテスト完了後、_MACHINE_EXTRACTION_META残留 = 0件(got size={len(F._MACHINE_EXTRACTION_META)})")

# ══════════════════════════════════════════════════════════════════════════
# J. CC-QUALITY-3E5 — E_GENERIC handle-shape observability + summary persistence
#    parserのaccept/reject挙動は一切変えず、E_GENERIC candidateのunderscore有無を
#    fixed 2値enumとして追加観測できることと、EXTRACT系telemetryがartifact expiry
#    後も参照できるようstdout/GITHUB_STEP_SUMMARYへ残ることを検証する。
# ══════════════════════════════════════════════════════════════════════════

# --- J1/J2. shape分類: underscoreの有無だけをfixed enumとして判定する ---
_meta_underscore = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "ene_kyobashi")
ok(_meta_underscore is not None and _meta_underscore["shape"] == "underscore",
   f"J1 underscoreを含むE_GENERIC candidateはshape=underscore (got={_meta_underscore})")

_meta_no_underscore = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "efeverキン肉マン")
ok(_meta_no_underscore is not None and _meta_no_underscore["shape"] == "no_underscore",
   f"J2 underscoreを含まないE_GENERIC candidateはshape=no_underscore (got={_meta_no_underscore})")

# --- J3. Cross Matrix: underscore x resolved/unresolved の4象限が混線しない ---
F.reset_quality_counters()
_j_uu = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "ene_kyobashi")          # underscore
_j_ur = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "ene_test")              # underscore
_j_nr = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "efeverキン肉マン")       # no_underscore
_j_nu = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "e86ｰエイティシックス")   # no_underscore
F._record_extraction_telemetry(_j_uu, resolved=False)  # 1. underscore + unresolved
F._record_extraction_telemetry(_j_ur, resolved=True)   # 2. underscore + resolved
F._record_extraction_telemetry(_j_nr, resolved=True)   # 3. no_underscore + resolved
F._record_extraction_telemetry(_j_nu, resolved=False)  # 4. no_underscore + unresolved
_jc = F.get_quality_counters()
ok(_jc.get("EXTRACT_E_GENERIC_SHAPE_UNDERSCORE_UNRESOLVED") == 1, f"J3a underscore+unresolved=1 (got={_jc})")
ok(_jc.get("EXTRACT_E_GENERIC_SHAPE_UNDERSCORE_RESOLVED") == 1, f"J3b underscore+resolved=1 (got={_jc})")
ok(_jc.get("EXTRACT_E_GENERIC_SHAPE_NO_UNDERSCORE_RESOLVED") == 1, f"J3c no_underscore+resolved=1 (got={_jc})")
ok(_jc.get("EXTRACT_E_GENERIC_SHAPE_NO_UNDERSCORE_UNRESOLVED") == 1, f"J3d no_underscore+unresolved=1 (got={_jc})")

# --- J4. 既存run bucketは shape追加後も従来通り併存する(破壊されていない) ---
# ene_kyobashi/ene_test(underscore)とe86ｰエイティシックス(no_underscore, J3のno_underscore+unresolved)は
# いずれもASCII run=2のため同じ0_2 bucketへ入る(H8と同じ仕様・回帰ではない)。
ok(_jc.get("EXTRACT_E_GENERIC_RUN_0_2_UNRESOLVED") == 2,
   f"J4a run bucket 0_2_unresolvedはshape追加後も従来通り加算される(ene_kyobashi+e86の2件) (got={_jc})")
ok(_jc.get("EXTRACT_E_GENERIC_RUN_0_2_RESOLVED") == 1,
   f"J4a2 run bucket 0_2_resolvedも従来通り加算される(ene_test) (got={_jc})")
ok(_jc.get("EXTRACT_E_GENERIC_RUN_3_5_RESOLVED") == 1,
   f"J4b efeverキン肉マン(run=5)は従来通りrun bucket 3_5_resolvedへも加算される (got={_jc})")

# --- J5. Cardinality: shape追加後もtelemetry keyの理論上限は候補内容に依存せず固定 ---
_max_l = 2 * 2
_max_e = 3 * 2
_max_e_shape = 2 * 2  # underscore/no_underscore x resolved/unresolved
_max_series = len(F._SERIES_ANCHOR_INDICES) * 2 * 2
_max_path = 2
_max_total_j = _max_l + _max_e + _max_e_shape + _max_series + _max_path
ok(_max_total_j < 210, f"J5 shape追加後もtelemetry key理論上限は固定({_max_total_j}件、動的keyなし)")

# --- J6. Privacy: shape判定を経てもraw candidate文字列はカウンタ/summaryへ混入しない ---
F.reset_quality_counters()
_SECRET_HANDLE = "ene_kyobashi_this_raw_string_must_never_leak_xyz999"
_meta_secret = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, _SECRET_HANDLE)
F._record_extraction_telemetry(_meta_secret, resolved=False)
with tempfile.TemporaryDirectory() as td:
    _p = Path(td) / "complete_quality_test_j.json"
    F.write_quality_summary(str(_p))
    _serialized = _p.read_text(encoding="utf-8")
    ok(_SECRET_HANDLE not in _serialized, "J6a raw handle文字列がquality summaryファイルに含まれない")
    ok(all(isinstance(v, int) for v in json.loads(_serialized)["counts"].values()),
       "J6b shape追加後もcountsの値は全て整数のみ")

# --- J7. Summary output (zero): quality shardは存在するが全telemetryが0でも固定行として表示される ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"COLLECTED": 0, "SAVED_SUPABASE": 0}, "meta": {"run_number": "1"}}),
        encoding="utf-8",
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("🔬 Extraction Telemetry" in out, "J7a quality shardが存在すればExtraction Telemetryセクションが出力される")
    ok("l_generic_0_1: resolved=0 unresolved=0" in out, "J7b L_GENERIC 0_1が未加算でも0として固定表示される")
    ok("e_generic_shape_underscore: resolved=0 unresolved=0" in out, "J7c E shape underscoreが未加算でも0として固定表示される")
    ok("extraction_path_single: 0" in out, "J7d extraction pathが未加算でも0として固定表示される")

# --- J8. Summary output (nonzero): 実際の値が正しく表示される ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    _nonzero_counts = {
        "COLLECTED": 10,
        "EXTRACT_L_GENERIC_RUN_2PLUS_RESOLVED": 3,
        "EXTRACT_E_GENERIC_RUN_0_2_UNRESOLVED": 2,
        "EXTRACT_E_GENERIC_SHAPE_UNDERSCORE_UNRESOLVED": 2,
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_PRESENT_RESOLVED": 1,
        "EXTRACTION_PATH_SINGLE": 4,
        "EXTRACTION_PATH_MULTI": 6,
    }
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": _nonzero_counts, "meta": {"run_number": "2"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("l_generic_2plus: resolved=3 unresolved=0" in out, f"J8a L_GENERIC 2plus resolved=3が正しく表示される")
    ok("e_generic_0_2: resolved=0 unresolved=2" in out, f"J8b E_GENERIC 0_2 unresolved=2が正しく表示される")
    ok("e_generic_shape_underscore: resolved=0 unresolved=2" in out, f"J8c E shape underscore unresolved=2が正しく表示される")
    # CC-QUALITY-3G1: anchor別表示はNONE/PRESENTを合算せず4次元のまま出力する
    ok("series[hokuto_anchor]: none_resolved=0 none_unresolved=0 present_resolved=1 present_unresolved=0 total=1" in out,
       f"J8d series anchorはNONE/PRESENTを合算せず4次元で個別表示される")
    ok("series_boundary_present: resolved=1 unresolved=0" in out, f"J8e series boundary aggregate(present)が正しく合算される")
    ok("extraction_path_single: 4" in out and "extraction_path_multi: 6" in out, f"J8f extraction pathが正しく表示される")
    # CC-QUALITY-3G1: 発火していないanchorも固定21件として毎回表示される(3E5時点の
    # nonzero-onlyポリシーから変更。cardinalityは常にlen(_SERIES_ANCHOR_SLUGS)件で確定)
    ok("series[garo_anchor]: none_resolved=0 none_unresolved=0 present_resolved=0 present_unresolved=0 total=0" in out,
       "J8g nonzeroでないanchorも0件行として固定表示される(3G1で仕様変更)")

# --- J9. Missing shard semantics: quality shard自体が存在しない場合はセクション自体を出さない ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("🔬 Extraction Telemetry" not in out,
       "J9 quality shardが1つもなければExtraction Telemetryは出力されない(missing≠0の既存方針を維持)")

# --- J10. GITHUB_STEP_SUMMARY: 同じtelemetryがstdoutと同様にstep summaryファイルへも書かれる ---
import os as _os
_orig_step_summary_env = _os.environ.get("GITHUB_STEP_SUMMARY")
try:
    with tempfile.TemporaryDirectory() as td:
        _summary_path = Path(td) / "step_summary.md"
        _summary_path.write_text("", encoding="utf-8")
        _os.environ["GITHUB_STEP_SUMMARY"] = str(_summary_path)
        F.reset_quality_counters()
        _meta_step = F._classify_pattern_bucket(F._E_GENERIC_PATTERN_IDX, "ene_kyobashi")
        F._record_extraction_telemetry(_meta_step, resolved=False)
        M._print_extraction_telemetry(F.get_quality_counters())
        _summary_content = _summary_path.read_text(encoding="utf-8")
        ok("Extraction Telemetry" in _summary_content, "J10a GITHUB_STEP_SUMMARYへExtraction Telemetryセクションが書かれる")
        ok("E_GENERIC Handle Shape" in _summary_content, "J10b GITHUB_STEP_SUMMARYへhandle shape表が書かれる")
        ok("ene_kyobashi" not in _summary_content, "J10c GITHUB_STEP_SUMMARYにもraw candidate文字列は含まれない")
finally:
    if _orig_step_summary_env is None:
        _os.environ.pop("GITHUB_STEP_SUMMARY", None)
    else:
        _os.environ["GITHUB_STEP_SUMMARY"] = _orig_step_summary_env

# --- J11. Behavior Preservation: 3E5実装後もpattern/slug/anchor件数は不変 ---
ok(len(F.MACHINE_PATTERNS) == 33, f"J11a MACHINE_PATTERNS件数は33のまま不変(got={len(F.MACHINE_PATTERNS)})")
ok(len(F._SERIES_ANCHOR_INDICES) == 21, f"J11b series anchor件数は21のまま不変(got={len(F._SERIES_ANCHOR_INDICES)})")
ok(F.extract_machine("e牙狼12がコンプリート達成") == "e牙狼12",
   "J11c 既存extract_machine()の返却値はshape追加後も不変")

F._MACHINE_EXTRACTION_META.clear()
F.reset_quality_counters()

# ══════════════════════════════════════════════════════════════════════════
# K. CC-QUALITY-3G1 — Series anchor boundary observability(表示のみ)
#    fetch_complete_info.py側の生カウンタ(anchor×boundary×outcomeの84キー)は
#    3E3時点から既に個別に記録済みで、本フェーズでは一切変更しない。
#    merge_complete_data.py側の表示だけがNONE/PRESENTを合算していた問題を修正した
#    ことを検証する。producer/parser/resolverは対象外。
# ══════════════════════════════════════════════════════════════════════════

# --- K1. Schema: 21 anchors x 4 counters = 84(producer側は不変であることの確認) ---
ok(len(F._SERIES_ANCHOR_INDICES) == 21, f"K1a series anchor件数は21(3G1でも不変, got={len(F._SERIES_ANCHOR_INDICES)})")
ok(len(M._SERIES_ANCHOR_SLUGS) == 21, f"K1b merge側のanchor slugリストも21件(got={len(M._SERIES_ANCHOR_SLUGS)})")
ok(len(F.MACHINE_PATTERNS) == 33, f"K1c MACHINE_PATTERNS件数は33のまま不変(got={len(F.MACHINE_PATTERNS)})")
_theoretical_series_keys = len(M._SERIES_ANCHOR_SLUGS) * 2 * 2
ok(_theoretical_series_keys == 84, f"K1d series telemetryの理論key数は84(21anchor x boundary2 x outcome2, got={_theoretical_series_keys})")

# --- K2. Exact Boundary Split: 2anchor分の合成countsで4次元が独立して保たれる ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    _k2_counts = {
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_NONE_RESOLVED": 2,
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_NONE_UNRESOLVED": 3,
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_PRESENT_RESOLVED": 0,
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 4,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_NONE_RESOLVED": 1,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_NONE_UNRESOLVED": 0,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_PRESENT_RESOLVED": 1,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 2,
    }
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": _k2_counts, "meta": {"run_number": "3"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("series[hokuto_anchor]: none_resolved=2 none_unresolved=3 present_resolved=0 present_unresolved=4 total=9" in out,
       f"K2a hokuto_anchorの4次元が独立して正しく表示される")
    ok("series[garo_anchor]: none_resolved=1 none_unresolved=0 present_resolved=1 present_unresolved=2 total=4" in out,
       f"K2b garo_anchorの4次元が独立して正しく表示される(旧設計ではNONE+PRESENTが合算され区別不能だった)")

# --- K3. Aggregate Consistency: 21anchor合計 == aggregate表の値 ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    _k3_counts = {
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_NONE_RESOLVED": 5,
        "EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 3,
        "EXTRACT_SERIES_VALVRAVE_ANCHOR_BOUNDARY_NONE_UNRESOLVED": 2,
        "EXTRACT_SERIES_VALVRAVE_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 5,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_PRESENT_RESOLVED": 1,
    }
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": _k3_counts, "meta": {"run_number": "4"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    # NONE resolved合計=5, NONE unresolved合計=2, PRESENT resolved合計=1, PRESENT unresolved合計=8
    ok("series_boundary_none: resolved=5 unresolved=2" in out, f"K3a aggregate NONEが21anchor合計と一致する")
    ok("series_boundary_present: resolved=1 unresolved=8" in out, f"K3b aggregate PRESENTが21anchor合計と一致する(3G blocker解消の直接証拠)")

# --- K4. PRESENT-only Evidence: aggregate PRESENT unresolved=8が複数anchorに分散していても再構成できる ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    _k4_counts = {
        "EXTRACT_SERIES_TOKYOGHOUL_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 3,
        "EXTRACT_SERIES_GARO_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 5,
    }
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": _k4_counts, "meta": {"run_number": "5"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("series_boundary_present: resolved=0 unresolved=8" in out, "K4a aggregate PRESENT unresolved=8(3件+5件の合計)")
    ok("series[tokyoghoul_anchor]: none_resolved=0 none_unresolved=0 present_resolved=0 present_unresolved=3 total=3" in out,
       "K4b どのanchorが8件中3件を占めるか個別に特定できる(3G blocker解消)")
    ok("series[garo_anchor]: none_resolved=0 none_unresolved=0 present_resolved=0 present_unresolved=5 total=5" in out,
       "K4c どのanchorが8件中5件を占めるか個別に特定できる(3G blocker解消)")

# --- K5. Zero Run: 全カウンタ0でも21anchor全件が0行として表示される ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"COLLECTED": 0}, "meta": {"run_number": "6"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("🔬 Extraction Telemetry" in out, "K5a zero runでもshardが存在すればExtraction Telemetryは出力される")
    _zero_anchor_lines = [f"series[{slug}]: none_resolved=0 none_unresolved=0 present_resolved=0 present_unresolved=0 total=0"
                          for slug in M._SERIES_ANCHOR_SLUGS]
    ok(all(line in out for line in _zero_anchor_lines), "K5b 21anchor全件が0行として固定表示される(欠落なし)")
    ok("l_generic_0_1: resolved=0 unresolved=0" in out, "K5c L/E/E-shapeセクションは3G1導入後も既存通り出力される")
    ok("extraction_path_single: 0" in out, "K5d Extraction Pathセクションも既存通り出力される")

# --- K6. stdout: aggregate + anchor detailの両方が存在する ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"EXTRACT_SERIES_HOKUTO_ANCHOR_BOUNDARY_PRESENT_UNRESOLVED": 1}, "meta": {}}),
        encoding="utf-8",
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("series_boundary_present: resolved=0 unresolved=1" in out, "K6a stdoutにaggregate Series Boundaryが出力される")
    ok("series[hokuto_anchor]:" in out, "K6b stdoutにanchor別detail行が出力される")

# --- K7. GITHUB_STEP_SUMMARY: aggregate + 21anchor detail + PRESENT個別値が保持される ---
_orig_k7_env = _os.environ.get("GITHUB_STEP_SUMMARY")
try:
    with tempfile.TemporaryDirectory() as td:
        _k7_summary_path = Path(td) / "step_summary_k7.md"
        _k7_summary_path.write_text("", encoding="utf-8")
        _os.environ["GITHUB_STEP_SUMMARY"] = str(_k7_summary_path)
        F.reset_quality_counters()
        _k7_meta = F._classify_pattern_bucket(F.MACHINE_PATTERN_SLUGS.index("garo_anchor"), "牙狼はひりつく感じ")
        F._record_extraction_telemetry(_k7_meta, resolved=False)
        M._print_extraction_telemetry(F.get_quality_counters())
        _k7_content = _k7_summary_path.read_text(encoding="utf-8")
        ok("Series Anchor Boundary" in _k7_content, "K7a GITHUB_STEP_SUMMARYへanchor detail見出しが書かれる")
        ok("| garo_anchor | 0 | 0 | 0 | 1 | 1 |" in _k7_content,
           "K7b GITHUB_STEP_SUMMARYでgaro_anchorのPRESENT unresolved=1が個別行として残る")
        ok("牙狼はひりつく感じ" not in _k7_content, "K7c GITHUB_STEP_SUMMARYにもraw candidate文字列は含まれない")
finally:
    if _orig_k7_env is None:
        _os.environ.pop("GITHUB_STEP_SUMMARY", None)
    else:
        _os.environ["GITHUB_STEP_SUMMARY"] = _orig_k7_env

# --- K8. Privacy: secret-likeなraw文字列がstdout/summaryどちらにも出ない ---
F.reset_quality_counters()
_K8_SECRET = "3G1_this_raw_candidate_must_never_leak_zzz888"
_k8_meta = F._classify_pattern_bucket(F.MACHINE_PATTERN_SLUGS.index("tekken_anchor"), _K8_SECRET + "鉄拳6")
F._record_extraction_telemetry(_k8_meta, resolved=True)
import io as _io_k8, contextlib as _ctx_k8
_buf_k8 = _io_k8.StringIO()
with _ctx_k8.redirect_stdout(_buf_k8):
    M._print_extraction_telemetry(F.get_quality_counters())
ok(_K8_SECRET not in _buf_k8.getvalue(), "K8 anchor detail表示にもraw candidate文字列は一切含まれない")

# --- K9. Regression: 既存L/E/E-shape/pathのkey名・出力は3G1導入前後で不変 ---
F.reset_quality_counters()
_k9_l = F._classify_pattern_bucket(F._L_GENERIC_PATTERN_IDX, "LINEからチェック")
F._record_extraction_telemetry(_k9_l, resolved=False)
_k9_out = {}
_buf_k9 = _io_k8.StringIO()
with _ctx_k8.redirect_stdout(_buf_k9):
    M._print_extraction_telemetry(F.get_quality_counters())
ok("l_generic_2plus: resolved=0 unresolved=1" in _buf_k9.getvalue(), "K9 L_GENERICの出力key/formatは3G1導入後も不変")

# --- K10. Parser Behavior Gate: fetch_complete_info.pyの抽出結果は3G1前後で不変 ---
ok(F.extract_machine("e牙狼12がコンプリート達成") == "e牙狼12", "K10a extract_machine()の返却値は3G1でも不変")
ok(F.extract_machines("北斗も達成、バジリスクも達成でコンプリート") == ["北斗も達成", "バジリスクも達成"],
   "K10b extract_machines()の返却値・順序・cardinalityは3G1でも不変(表示のみの変更であることの直接証拠)")

F._MACHINE_EXTRACTION_META.clear()
F.reset_quality_counters()

# ══════════════════════════════════════════════════════════════════════════
# L. CC-QUALITY-3H — valvrave_anchor限定 resolver fallback(T3-C)
#    original-first・fail-open・raw_machine/truncated候補は一切永続化しない。
#    3G3のREAD-ONLY監査でmaster/alias全件回帰0件・A→B誤解決0件を確認した
#    唯一のanchor(valvrave_anchor)にのみ適用する。他anchorには一切影響しない。
# ══════════════════════════════════════════════════════════════════════════

class _TableResolver:
    """raw_name -> 固定結果のlookup tableを持つfakeリゾルバ(実DB/ネットワーク非依存)。
    T3のoriginal→truncatedという2段階resolve呼び出し順序を検証するため、
    _FakeResolver(単一固定結果のみ)とは別に用意する。"""
    def __init__(self, table: dict):
        self._table = table
        self.resolve_calls: list[str] = []
        self.save_unknown_calls: list[str] = []

    def resolve(self, raw_name):
        self.resolve_calls.append(raw_name)
        return self._table.get(raw_name)

    def save_unknown(self, raw_name, source_url=""):
        self.save_unknown_calls.append(raw_name)


def _run_t3_case(machine_text: str, table: dict, series_slug: str = "valvrave_anchor"):
    """1entryをsupabase_write_complete()に通し、(fake_resolver, quality_counters)を返す。"""
    F.reset_quality_counters()
    F._MACHINE_EXTRACTION_META.clear()
    entry = {"id": "t3test", "x_url": "https://x.com/foo/status/9", "machine": machine_text}
    pidx = F.MACHINE_PATTERN_SLUGS.index(series_slug)
    meta = F._classify_pattern_bucket(pidx, machine_text)
    if meta is not None:
        F._MACHINE_EXTRACTION_META[id(entry)] = meta
    fake = _TableResolver(table)
    orig_get_resolver = MR.get_resolver
    try:
        MR.get_resolver = lambda: fake
        _with_sb_env_and_request(lambda: F.supabase_write_complete([entry]))
    finally:
        MR.get_resolver = orig_get_resolver
    return fake, F.get_quality_counters()


# --- L1/L14. Positive: original unresolved, truncated(identity token保持)で解決する ---
_L1_TABLE = {"ヴァルヴレイヴ2": {"official_name": "L革命機ヴァルヴレイヴ2", "machine_id": "mid-valvrave-2"}}
_l1_fake, _l1_c = _run_t3_case("ヴァルヴレイヴ2も達成", _L1_TABLE)
ok(_l1_fake.resolve_calls == ["ヴァルヴレイヴ2も達成", "ヴァルヴレイヴ2"],
   f"L1a original→truncatedの順で2回resolveが呼ばれる (got={_l1_fake.resolve_calls})")
ok(_l1_fake.save_unknown_calls == [], "L1b fallback成功時はsave_unknownが呼ばれない")
ok(_l1_c.get("T3_VALVRAVE_ATTEMPTED") == 1, f"L1c ATTEMPTED=1 (got={_l1_c})")
ok(_l1_c.get("T3_VALVRAVE_RESOLVED") == 1, f"L1d RESOLVED=1 (got={_l1_c})")
ok(_l1_c.get("T3_VALVRAVE_UNRESOLVED") is None, "L1e UNRESOLVEDは加算されない")
ok(_l1_c.get("MACHINE_RESOLVED") == 1, "L1f 最終結果はMACHINE_RESOLVEDとして1回のみ加算される")
ok(_l1_c.get("MACHINE_UNRESOLVED") is None, "L1g MACHINE_UNRESOLVEDは加算されない(二重カウントなし)")

# --- L2/L15. Negative: bare valvrave(identity tokenなし)はfallback自体を試みない ---
_l2_fake, _l2_c = _run_t3_case("ヴァルヴレイヴも達成", {})
ok(_l2_fake.resolve_calls == ["ヴァルヴレイヴも達成"], f"L2a identity tokenなしなら2回目のresolveを呼ばない (got={_l2_fake.resolve_calls})")
ok(_l2_fake.save_unknown_calls == ["ヴァルヴレイヴも達成"], "L2b save_unknownはORIGINAL文字列で呼ばれる")
ok(_l2_c.get("T3_VALVRAVE_ATTEMPTED") is None, "L2c ATTEMPTEDは加算されない(ineligible)")
ok(_l2_c.get("MACHINE_UNRESOLVED") == 1, "L2d 既存のfail-open unresolved挙動を維持")

# --- L3/L16. Wrong generation: 存在しない世代番号はA→Bにならず、fail-openのまま ---
for _gen in ["0", "1", "3"]:
    _fake_g, _c_g = _run_t3_case(f"ヴァルヴレイヴ{_gen}も達成", {})  # tableにgen一致なし
    ok(_fake_g.resolve_calls == [f"ヴァルヴレイヴ{_gen}も達成", f"ヴァルヴレイヴ{_gen}"],
       f"L3a gen={_gen}: truncatedでも2回目resolveは試みるが誤った機種へは解決しない")
    ok(_fake_g.save_unknown_calls == [f"ヴァルヴレイヴ{_gen}も達成"], f"L3b gen={_gen}: save_unknownはORIGINAL")
    ok(_c_g.get("T3_VALVRAVE_UNRESOLVED") == 1, f"L3c gen={_gen}: UNRESOLVEDとして正しく加算される")

# --- L4/L17. Wrong type: 型不一致は誤ってresolveされない(既存type_okガード) ---
_L4_TABLE = {"ヴァルヴレイヴ2": {"official_name": "L革命機ヴァルヴレイヴ2", "machine_id": "mid-valvrave-2"}}
_l4_fake, _l4_c = _run_t3_case("eヴァルヴレイヴ2は達成", _L4_TABLE)
# resolverはfakeなので型ガード自体はmachine_resolver.resolve()側の責務(3G3で実DB確認済み)。
# ここではT3層が「resolverの戻り値をそのまま使うだけ」で独自の型判定を行わないことを確認する。
ok(_l4_fake.resolve_calls == ["eヴァルヴレイヴ2は達成", "eヴァルヴレイヴ2"],
   f"L4a T3層はresolver呼び出しのみで型判定を行わない(got={_l4_fake.resolve_calls})")

# --- L5/L18. Original already resolves: fallbackは一切試みられない ---
_L5_TABLE = {"L革命機ヴァルヴレイヴ2も達成": {"official_name": "L革命機ヴァルヴレイヴ2", "machine_id": "mid-valvrave-2"}}
_l5_fake, _l5_c = _run_t3_case("L革命機ヴァルヴレイヴ2も達成", _L5_TABLE)
ok(_l5_fake.resolve_calls == ["L革命機ヴァルヴレイヴ2も達成"], f"L5a originalが成功すれば2回目resolveは呼ばれない (got={_l5_fake.resolve_calls})")
ok(_l5_c.get("T3_VALVRAVE_ATTEMPTED") is None, "L5b ATTEMPTEDは加算されない")
ok(_l5_c.get("MACHINE_RESOLVED") == 1, "L5c machine_id/official_nameはoriginalの結果のまま")

# --- L6/L19. Non-Valvrave anchors: boundary+identity tokenがあってもT3は発火しない ---
_non_valvrave_cases = [
    ("garo_anchor", "牙狼12は達成"),
    ("tokyoghoul_anchor", "東京喰種2は達成"),
    ("kabaneri_anchor", "カバネリ2は達成"),
    ("lycoris_anchor", "リコリス2は達成"),
    ("karakuri_anchor", "からくりサーカス2は達成"),
]
for _slug, _text in _non_valvrave_cases:
    _fake_nv, _c_nv = _run_t3_case(_text, {}, series_slug=_slug)
    ok(_fake_nv.resolve_calls == [_text], f"L6 {_slug}: T3は発火せず1回のみresolveが呼ばれる (got={_fake_nv.resolve_calls})")
    ok(_c_nv.get("T3_VALVRAVE_ATTEMPTED") is None, f"L6 {_slug}: ATTEMPTEDは加算されない(allowlist外)")

# --- L7/L20. Parentheses safety: 括弧内の助詞相当文字列はboundaryとして検出されない ---
_l7_meta = F._classify_pattern_bucket(F._VALVRAVE_ANCHOR_IDX, "ヴァルヴレイヴ（は）2")
ok(_l7_meta["boundary"] is False, f"L7a 括弧内の「は」はboundaryとして検出されない(既存の括弧マスク仕様、変更なし) (got={_l7_meta})")
_l7_fb = F._derive_valvrave_t3_fallback(_l7_meta, "ヴァルヴレイヴ（は）2")
ok(_l7_fb is None, "L7b boundary非検出のためfallback候補はNone")

# --- L8/L21. Cardinality/Order/Slot regression: T3導入後もparser出力は完全に不変 ---
ok(F.extract_machines("北斗も達成、バジリスクも達成でコンプリート") == ["北斗も達成", "バジリスクも達成"],
   "L8a extract_machines()の返却値・順序・cardinalityはT3導入後も不変")
ok(F.extract_machine("e牙狼12がコンプリート達成") == "e牙狼12", "L8b extract_machine()の返却値もT3導入後も不変")

# --- L9/L22. Unknown Machine Semantics: A(成功)/B(失敗)/C(ineligible)でsave_unknown呼び出しが正確 ---
# A: fallback成功 -> save_unknown 0回
_l9a_fake, _ = _run_t3_case("ヴァルヴレイヴ2も達成", _L1_TABLE)
ok(len(_l9a_fake.save_unknown_calls) == 0, "L9a fallback成功時、save_unknown呼び出し回数=0")
# B: fallback試行したが失敗 -> save_unknown 1回、ORIGINAL
_l9b_fake, _ = _run_t3_case("ヴァルヴレイヴ99も達成", {})
ok(_l9b_fake.save_unknown_calls == ["ヴァルヴレイヴ99も達成"], f"L9b fallback失敗時、save_unknown=1回・ORIGINAL (got={_l9b_fake.save_unknown_calls})")
# C: identity token無しでineligible -> 2回目resolve呼ばれない、save_unknown 1回、ORIGINAL
_l9c_fake, _l9c_c = _run_t3_case("ヴァルヴレイヴが", {})
ok(len(_l9c_fake.resolve_calls) == 1, "L9c ineligibleなら2回目のresolve呼び出し自体が発生しない")
ok(_l9c_fake.save_unknown_calls == ["ヴァルヴレイヴが"], "L9d ineligible時もsave_unknownはORIGINAL")

# --- L10/L23. Telemetry Count: 4パターンでATTEMPTED/RESOLVED/UNRESOLVEDの整合性を確認 ---
# success
_, _l10a_c = _run_t3_case("ヴァルヴレイヴ2も達成", _L1_TABLE)
ok(_l10a_c.get("T3_VALVRAVE_ATTEMPTED") == 1 and _l10a_c.get("T3_VALVRAVE_RESOLVED") == 1
   and _l10a_c.get("T3_VALVRAVE_UNRESOLVED") is None, f"L10a success: attempted=1 resolved=1 unresolved=0 (got={_l10a_c})")
# failure after second resolve
_, _l10b_c = _run_t3_case("ヴァルヴレイヴ99も達成", {})
ok(_l10b_c.get("T3_VALVRAVE_ATTEMPTED") == 1 and _l10b_c.get("T3_VALVRAVE_UNRESOLVED") == 1
   and _l10b_c.get("T3_VALVRAVE_RESOLVED") is None, f"L10b failure: attempted=1 resolved=0 unresolved=1 (got={_l10b_c})")
# identity-ineligible
_, _l10c_c = _run_t3_case("ヴァルヴレイヴが", {})
ok(_l10c_c.get("T3_VALVRAVE_ATTEMPTED") is None and _l10c_c.get("T3_VALVRAVE_RESOLVED") is None
   and _l10c_c.get("T3_VALVRAVE_UNRESOLVED") is None, f"L10c ineligible: attempted=0 resolved=0 unresolved=0 (got={_l10c_c})")
# original already resolved
_, _l10d_c = _run_t3_case("L革命機ヴァルヴレイヴ2も達成", _L5_TABLE)
ok(_l10d_c.get("T3_VALVRAVE_ATTEMPTED") is None, f"L10d original resolved: attempted=0 (got={_l10d_c})")

# --- L11/L24. Telemetry Summary(merge_complete_data.py): zero / nonzero 両方確認 ---
with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"COLLECTED": 0}, "meta": {"run_number": "7"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("t3_valvrave_attempted: 0" in out and "t3_valvrave_resolved: 0" in out and "t3_valvrave_unresolved: 0" in out,
       "L11a zero runでもT3 valvrave fallback3keyが固定表示される")

with tempfile.TemporaryDirectory() as td:
    fake_root = Path(td)
    (fake_root / "public").mkdir()
    (fake_root / "public" / "complete_quality_handle_a.json").write_text(
        json.dumps({"counts": {"T3_VALVRAVE_ATTEMPTED": 3, "T3_VALVRAVE_RESOLVED": 2, "T3_VALVRAVE_UNRESOLVED": 1},
                    "meta": {"run_number": "8"}}), encoding="utf-8"
    )
    out, _, _ = _run_main_with_fixture(fake_root)
    ok("t3_valvrave_attempted: 3" in out and "t3_valvrave_resolved: 2" in out and "t3_valvrave_unresolved: 1" in out,
       f"L11b nonzero値が正しく表示され、attempted=resolved+unresolvedの整合性が保たれる")

# --- L12/L25. GITHUB_STEP_SUMMARY: T3セクションも同様に永続化される・raw文字列は含まれない ---
_orig_l12_env = _os.environ.get("GITHUB_STEP_SUMMARY")
try:
    with tempfile.TemporaryDirectory() as td:
        _l12_summary_path = Path(td) / "step_summary_l12.md"
        _l12_summary_path.write_text("", encoding="utf-8")
        _os.environ["GITHUB_STEP_SUMMARY"] = str(_l12_summary_path)
        F.reset_quality_counters()
        F._qcount("T3_VALVRAVE_ATTEMPTED")
        F._qcount("T3_VALVRAVE_RESOLVED")
        M._print_extraction_telemetry(F.get_quality_counters())
        _l12_content = _l12_summary_path.read_text(encoding="utf-8")
        ok("T3 Valvrave Fallback" in _l12_content, "L12a GITHUB_STEP_SUMMARYへT3セクション見出しが書かれる")
        ok("| attempted | 1 |" in _l12_content and "| resolved | 1 |" in _l12_content,
           "L12b GITHUB_STEP_SUMMARYへT3の値が正しく書かれる")
finally:
    if _orig_l12_env is None:
        _os.environ.pop("GITHUB_STEP_SUMMARY", None)
    else:
        _os.environ["GITHUB_STEP_SUMMARY"] = _orig_l12_env

# --- L13. Privacy: T3経路でもraw candidate/truncated候補がどこにも漏れない ---
_L13_SECRET_SUFFIX = "3H_never_leak_zzz777"
_L13_TABLE = {}  # 常に未解決
_l13_fake, _l13_c = _run_t3_case(f"ヴァルヴレイヴ2{_L13_SECRET_SUFFIX}", _L13_TABLE)
_buf_l13 = _io_k8.StringIO()
with _ctx_k8.redirect_stdout(_buf_l13):
    M._print_extraction_telemetry(F.get_quality_counters())
ok(_L13_SECRET_SUFFIX not in _buf_l13.getvalue(), "L13a T3 telemetry出力にraw candidate/truncated文字列が含まれない")
with tempfile.TemporaryDirectory() as td:
    _p13 = Path(td) / "complete_quality_test_l13.json"
    F.write_quality_summary(str(_p13))
    _l13_summary = _p13.read_text(encoding="utf-8")
    ok(_L13_SECRET_SUFFIX not in _l13_summary, "L13b write_quality_summary()出力にもraw candidateが含まれない")

# --- L26. 3E3A correlation safety: T3導入後も_MACHINE_EXTRACTION_METAが残留しない ---
F._MACHINE_EXTRACTION_META.clear()
_run_t3_case("ヴァルヴレイヴ2も達成", _L1_TABLE)
_run_t3_case("ヴァルヴレイヴ99も達成", {})
_run_t3_case("ヴァルヴレイヴが", {})
ok(len(F._MACHINE_EXTRACTION_META) == 0, f"L26 T3を経由する全パターン後も_MACHINE_EXTRACTION_META残留=0件(got size={len(F._MACHINE_EXTRACTION_META)})")

F._MACHINE_EXTRACTION_META.clear()
F.reset_quality_counters()

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
