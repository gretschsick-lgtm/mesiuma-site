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


# ══════════════════════════════════════════════════════════════════════════
# CC-AUTO-4 — select_run_rotated_handles() (github.run_number ベース rotation)
# ══════════════════════════════════════════════════════════════════════════

# --- I. 383/200(現行eligible数)で2連続run(偶数run_number, 奇数run_number)がfull coverage ---
h383 = make_handles(383)
winA = F.select_run_rotated_handles(h383, 200, 100)   # 偶数run_number
winB = F.select_run_rotated_handles(h383, 200, 101)   # 奇数run_number
ok(len(winA) == 200 and len(winB) == 200, "I1 各runのtarget数は200")
union = {h for h,_ in winA} | {h for h,_ in winB}
ok(len(union) == 383, "I2 隣接する2 run(run_number偶奇)でunion=383/383(full coverage)")

# --- J. rerun安定性: 同じrun_numberなら常に同じ結果 ---
ok(F.select_run_rotated_handles(h383, 200, 100) == F.select_run_rotated_handles(h383, 200, 100),
   "J1 同じrun_numberなら同じtarget(rerun安全)")
ok(F.select_run_rotated_handles(h383, 200, 5) == F.select_run_rotated_handles(h383, 200, 105),
   "J2 偶奇が同じrun_number同士は同じwindow(5と105は共に奇数)")

# --- K. 10 runs: 隣接run pairが常にfull coverageであることを確認 ---
for n in range(10):
    a = F.select_run_rotated_handles(h383, 200, n)
    b = F.select_run_rotated_handles(h383, 200, n+1)
    u = {h for h,_ in a} | {h for h,_ in b}
    ok(len(u) == 383, f"K-{n} run{n}/run{n+1}のunionが常にfull coverage")

# --- L. 11 actual runs相当(異なるrun_number列)でも重複問わず全部coverage ---
seen = set()
for n in [100,101,102,103,104,150,151,200,201,999,1000]:
    win = F.select_run_rotated_handles(h383, 200, n)
    seen.update(h for h,_ in win)
ok(len(seen) == 383, "L1 実運用相当の11run_number列でfull coverage")

# --- M. window内重複なし ---
for n in (0,1,2,999):
    win = F.select_run_rotated_handles(h383, 200, n)
    ok(len({h for h,_ in win}) == len(win), f"M-{n} window内重複なし")

# --- N. 将来N>2W(一般化cycle設計) ---
h401 = make_handles(401)  # window=200, 401>2*200=400 → 一般化cycleが必要
num_windows_401 = -(-401 // 200)  # ceil(401/200) = 3
seen401 = set()
for n in range(num_windows_401):
    win = F.select_run_rotated_handles(h401, 200, n)
    ok(len(win) == 200, f"N-{n} N=401でも各windowは200件")
    seen401.update(h for h,_ in win)
ok(len(seen401) == 401, "N-union 401件(N>2W)でもnum_windows回のrunでfull coverage(383固定に依存しない一般化)")

h1000 = make_handles(1000)
num_windows_1000 = -(-1000 // 200)  # 5
seen1000 = set()
for n in range(num_windows_1000):
    seen1000.update(h for h,_ in F.select_run_rotated_handles(h1000, 200, n))
ok(len(seen1000) == 1000, "N2 N=1000(大規模一般化cycle)でもnum_windows回でfull coverage")

# --- O. 境界値 ---
ok(F.select_run_rotated_handles([], 200, 5) == [], "O1 total=0で例外なし")
h1 = make_handles(1)
ok(F.select_run_rotated_handles(h1, 200, 5) == h1, "O2 total=1はそのまま全件")
h199 = make_handles(199)
ok(F.select_run_rotated_handles(h199, 200, 3) == h199, "O3 total<window(199<200)はそのまま全件")
h200 = make_handles(200)
ok(F.select_run_rotated_handles(h200, 200, 7) == h200, "O4 total=window(200=200)はそのまま全件")
h201 = make_handles(201)
a201 = F.select_run_rotated_handles(h201, 200, 0)
b201 = F.select_run_rotated_handles(h201, 200, 1)
ok(len({h for h,_ in a201} | {h for h,_ in b201}) == 201, "O5 total=201(window*2>=totalの境界)でも2runでfull coverage")
h400 = make_handles(400)
a400 = F.select_run_rotated_handles(h400, 200, 0)
b400 = F.select_run_rotated_handles(h400, 200, 1)
ok(len({h for h,_ in a400} | {h for h,_ in b400}) == 400, "O6 total=400(window*2==totalちょうど)でも2runでfull coverage")

# --- P. run_number欠損/不正値でも例外なし(fail-open) ---
ok(len(F.select_run_rotated_handles(h383, 200, None)) == 200, "P1 run_number=Noneでも例外なし")
ok(F.select_run_rotated_handles(h383, 200, None) == F.select_run_rotated_handles(h383, 200, 0),
   "P2 run_number=Noneはrun_number=0相当(安全側デフォルト)")
ok(len(F.select_run_rotated_handles(h383, 200, "not_a_number")) == 200, "P3 不正な文字列でも例外なし(fail-open)")
ok(len(F.select_run_rotated_handles(h383, 200, "42")) == 200, "P4 文字列型の数値(env var由来)も正常動作")
ok(F.select_run_rotated_handles(h383, 200, "42") == F.select_run_rotated_handles(h383, 200, 42),
   "P5 文字列'42'と整数42は同じ結果(GITHUB_RUN_NUMBER環境変数は文字列で渡る)")

# --- Q. count同値tie(呼び出し側sort結果を尊重し、関数自体は入力順を保持) ---
tied = [("hZ", {"count": 5}), ("hA", {"count": 5})] + make_handles(400)
win = F.select_run_rotated_handles(tied, 200, 0)
ok(win[0] == ("hZ", {"count": 5}), "Q1 入力順(tie-break済み前提)を関数は変更しない")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
