#!/usr/bin/env python3
"""
CC-AUTO-2 — select_rotated_handles() のユニットテスト。
production DB / network には一切依存しない（fixture純粋関数のみ）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import fetch_complete_info as F

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")


def make_handles(n):
    return [(f"h{i:03d}", {"count": n - i}) for i in range(n)]


# --- A. 383件 fixture・window=200・全24hourで確認 ---
handles383 = make_handles(383)
seen_union = set()
prev = None
for hour in range(24):
    win = F.select_rotated_handles(handles383, 200, hour)
    ok(len(win) == 200, f"A-{hour} window長は常に200")
    ok(len({h for h, _ in win}) == 200, f"A-{hour} window内に重複handleなし(no duplicate within same run)")
    seen_union.update(h for h, _ in win)
    # determinism: 同じhourなら同じ結果
    win2 = F.select_rotated_handles(handles383, 200, hour)
    ok(win == win2, f"A-{hour} 同じhourなら同じ結果(deterministic)")
    prev = win

ok(len(seen_union) == 383, "B1 24hour通しで383件全てが最低1回window入りする(wrap-around含め全coverage)")

# --- C. exactly 200件(window以下) ---
handles200 = make_handles(200)
for hour in (0, 12, 23):
    win = F.select_rotated_handles(handles200, 200, hour)
    ok(len(win) == 200 and {h for h,_ in win} == {h for h,_ in handles200},
       f"C-{hour} ちょうどwindow件数なら全件そのまま返る(rotation不要)")

# --- D. window未満(<200) ---
handles50 = make_handles(50)
for hour in (0, 10, 23):
    win = F.select_rotated_handles(handles50, 200, hour)
    ok(len(win) == 50 and win == handles50, f"D-{hour} window未満なら全件そのまま返る")

# --- E. 空リスト ---
ok(F.select_rotated_handles([], 200, 12) == [], "E1 空リストで例外なし")

# --- F. hour=0とhour=23で異なるwindowになる(実際にrotationしていることの確認) ---
win0 = F.select_rotated_handles(handles383, 200, 0)
win23 = F.select_rotated_handles(handles383, 200, 23)
ok(win0 != win23, "F1 hour=0とhour=23でwindowが異なる(固定top-200に戻っていない)")
ok({h for h,_ in win0} == {h for h,_ in handles383[:200]}, "F2 hour=0はoffset=0(先頭200件)")
ok({h for h,_ in win23} == {h for h,_ in (handles383[183:] + handles383[:183])[:200]},
   "F3 hour=23はoffset=max(=total-window)にちょうど到達")

# --- G. count同値時のtie-break安定性(呼び出し側でhandle名sortしている前提を関数側では
#         破壊しないことを確認。関数自体はsortをしないので順序をそのまま尊重する) ---
tied = [("hZ", {"count": 5}), ("hA", {"count": 5}), ("hM", {"count": 5})]
win = F.select_rotated_handles(tied, 200, 5)
ok(win == tied, "G1 window超過なしなら入力順をそのまま維持(呼び出し側のsort結果を尊重)")

# --- H. 1000件規模でも高速・例外なし(負荷確認の簡易チェック) ---
big = make_handles(1000)
win = F.select_rotated_handles(big, 200, 15)
ok(len(win) == 200, "H1 大規模リストでも正常動作")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
