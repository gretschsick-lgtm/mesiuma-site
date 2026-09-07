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

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
