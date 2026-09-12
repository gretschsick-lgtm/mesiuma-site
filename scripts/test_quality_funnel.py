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

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
