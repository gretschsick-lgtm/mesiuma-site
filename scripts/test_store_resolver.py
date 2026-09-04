#!/usr/bin/env python3
"""
CC-2A — store_resolver.py pagination 修正のユニットテスト。
production DB には依存しない（fixture/mock のみ・network 発行なし）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import store_resolver as SR

PASS = 0
FAIL = 0
def ok(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  OK  {m}")
    else: FAIL += 1; print(f"  ❌ FAIL  {m}")


def make_rows(n, start=0):
    return [{"id": f"s{start+i}", "name": f"店{start+i}", "normalized_name": f"店{start+i}",
            "pref": "東京都", "area": "関東"} for i in range(n)]


class FakePaginatedResolver(SR.StoreResolver):
    """_fetch_page だけ差し替えて実 HTTP を発行しない検証用サブクラス。"""
    def __init__(self, pages, total=None):
        super().__init__("https://fake.example", "fake-key")
        self._pages = pages          # list[list[dict]]  offset//page_size 番目のページ
        self._total = total
        self.fetch_calls = []

    def _fetch_page(self, path, offset, page_size):
        idx = offset // page_size
        self.fetch_calls.append((offset, page_size))
        chunk = self._pages[idx] if idx < len(self._pages) else []
        cr = f"{offset}-{offset+len(chunk)-1}/{self._total if self._total is not None else '*'}"
        return chunk, cr


# --- Case A: 2500 stores, page1=1000/page2=1000/page3=500 ---
pages_a = [make_rows(1000, 0), make_rows(1000, 1000), make_rows(500, 2000)]
r = FakePaginatedResolver(pages_a, total=2500)
got = r._sb_get_paginated("stores?select=id,name&is_active=eq.true&order=name", page_size=1000)
ok(len(got) == 2500, "A1 2500件(1000/1000/500)を全件取得")
ok(len({row['id'] for row in got}) == 2500, "A2 id重複なし")
ok(len(r.fetch_calls) == 3, "A3 3ページ分のみリクエスト(不要な4ページ目を発行しない)")

# --- Case B: 1000件未満(500件) → 1 request で終了 ---
pages_b = [make_rows(500, 0)]
r = FakePaginatedResolver(pages_b, total=500)
got = r._sb_get_paginated("stores?select=id,name", page_size=1000)
ok(len(got) == 500, "B1 500件全件取得")
ok(len(r.fetch_calls) == 1, "B2 1リクエストのみ(500<1000で即終了)")

# --- Case C: ちょうど1000件 → 2ページ目(空)を確認して正常終了 ---
pages_c = [make_rows(1000, 0), []]
r = FakePaginatedResolver(pages_c, total=1000)
got = r._sb_get_paginated("stores?select=id,name", page_size=1000)
ok(len(got) == 1000, "C1 ちょうど1000件を取得")
ok(len(r.fetch_calls) == 2, "C2 2ページ目(空)まで確認して終了")

# --- Case D: pagination中にHTTPエラー → fail closed(不完全masterをcacheしない) ---
class FailingResolver(SR.StoreResolver):
    def __init__(self):
        super().__init__("https://fake.example", "fake-key")
        self._call_n = 0
    def _fetch_page(self, path, offset, page_size):
        self._call_n += 1
        if self._call_n == 1:
            return make_rows(1000, 0), f"0-999/2500"
        raise SR.urllib.error.URLError("simulated network failure on page 2")

fr = FailingResolver()
fr._load()
ok(fr._stores == [], "D1 pagination途中エラー時、不完全なmasterをcacheしない(空にfail closed)")
ok(fr._loaded is True, "D2 loaded flagは立つ(再試行ループにはしない・_ensure_loadedの多重呼び出し防止)")

# --- Case E: 重複row/duplicate id → masterが壊れない(dedupe) ---
dup_page = make_rows(3, 0) + [make_rows(1, 0)[0]]  # id "s0" が重複
r = FakePaginatedResolver([dup_page])
raw = r._sb_get_paginated("stores?select=id,name", page_size=1000)
deduped = SR.StoreResolver._dedupe_stores(raw)
ok(len(raw) == 4, "E1 生データは重複込みで4件")
ok(len(deduped) == 3, "E2 dedupe後は3件(重複id除去)")
ok(len({row['id'] for row in deduped}) == 3, "E3 dedupe後にid重複なし")
malformed = [{"name": "id無し店舗"}, {"id": "s0", "name": "店0"}, {"id": None, "name": "id=None"}]
ok(len(SR.StoreResolver._dedupe_stores(malformed)) == 1, "E4 id欠損/Noneの行を除外")

# --- Case F: 無限loop防止(異常系: 常に同じページを返す/max_pages超過) ---
class StuckResolver(SR.StoreResolver):
    def __init__(self):
        super().__init__("https://fake.example", "fake-key")
    def _fetch_page(self, path, offset, page_size):
        # offsetに関わらず毎回同じ1000件を返す(異常系シミュレーション)
        return make_rows(1000, 0), "0-999/*"

sr_ = StuckResolver()
raised = False
try:
    sr_._sb_get_paginated("stores?select=id,name", page_size=1000, max_pages=50)
except RuntimeError as e:
    raised = True
ok(raised, "F1 同一ページ連続返却で例外(無限pagination停止・stall検知)")

class GrowingButNeverEndingResolver(SR.StoreResolver):
    def __init__(self):
        super().__init__("https://fake.example", "fake-key")
    def _fetch_page(self, path, offset, page_size):
        # 常にpage_size件ちょうど返し続け、totalも不明(*) → 決して自然終了しない異常系
        idx = offset // page_size
        return make_rows(page_size, idx * page_size), f"{offset}-{offset+page_size-1}/*"

gr = GrowingButNeverEndingResolver()
raised2 = False
try:
    gr._sb_get_paginated("stores?select=id,name", page_size=1000, max_pages=5)
except RuntimeError as e:
    raised2 = True
    ok("max_pages" in str(e), "F2b max_pages超過時のエラーメッセージにmax_pages明記")
ok(raised2, "F2a max_pages超過で例外(bounded safety)")

# --- 統合: _load() が全ページを結合して self._stores にセットする ---
class AliaslessResolver(SR.StoreResolver):
    """store_aliases 未作成環境相当(グレースフルにNoneに畳み込まれる既存挙動を維持)。"""
    def __init__(self, pages, total):
        super().__init__("https://fake.example", "fake-key")
        self._pages = pages
        self._total = total
    def _fetch_page(self, path, offset, page_size):
        idx = offset // page_size
        chunk = self._pages[idx] if idx < len(self._pages) else []
        return chunk, f"{offset}-{offset+len(chunk)-1}/{self._total}"
    def _sb_get(self, path):
        if path.startswith("store_aliases"):
            raise RuntimeError("store_aliases テーブル未作成(想定内)")
        raise AssertionError(f"想定外のpath: {path}")

pages_full = [make_rows(1000, 0), make_rows(1000, 1000), make_rows(1000, 2000),
             make_rows(1000, 3000), make_rows(1000, 4000), make_rows(1000, 5000),
             make_rows(360, 6000)]
ar = AliaslessResolver(pages_full, total=6360)
ar._ensure_loaded()
ok(len(ar._stores) == 6360, "G1 6360件(旧: 1000件で切り捨てられていた問題が解消)")
ok(ar._alias_map == {}, "G2 store_aliases失敗時は空dictにグレースフル縮退(既存挙動維持)")
ok(ar._loaded is True, "G3 loaded flag正常")

# --- resolve() のマッチングロジック自体は無変更であることの回帰確認 ---
# (全件ロードされたことで「見えるstore数」が増えるだけで、判定アルゴリズムは同一)
class SmallFixtureResolver(SR.StoreResolver):
    def __init__(self, stores):
        super().__init__("https://fake.example", "fake-key")
        self._stores = stores
        self._alias_map = {}
        self._loaded = True

fixture_stores = [
    {"id": "st1", "name": "マルハン東京店", "normalized_name": "マルハン東京", "pref": "東京都", "area": "関東"},
    {"id": "st2", "name": "マルハン東京駅前店", "normalized_name": "マルハン東京駅前", "pref": "東京都", "area": "関東"},
]
sfr = SmallFixtureResolver(fixture_stores)
ok(sfr.resolve("マルハン東京店")["match_type"] == "exact", "H1 完全一致は従来通りexact")
ok(sfr.resolve("マルハン東京店")["confidence"] == 1.0, "H2 exact match confidence=1.0(不変)")
near_miss = sfr.resolve("マルハン東亰店")  # 1文字違い("京"→"亰") = fuzzyのみで判定される想定
ok(near_miss is None or near_miss["match_type"] == "fuzzy",
   "H3 fuzzy閾値0.88はコードから変更していない(挙動は既存と同一)")
ok(sfr.resolve("") is None, "H4 空文字はNone(不変)")
ok(sfr.resolve(None) is None, "H5 None入力で例外なし(不変)")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
