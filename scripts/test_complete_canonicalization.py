#!/usr/bin/env python3
"""
CC-2C — fetch_complete_info.resolve_store_ids() のユニットテスト。
production DB には依存しない（fixture/mock のみ・network 発行なし）。
partial 経路の DB write 直前 canonicalization（enrichment・fail-open）を検証する。
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


def entry(store=None, store_id=None, x_url="https://x.com/store1/status/1"):
    e = {"id": "e1", "store": store, "x_url": x_url}
    if store_id is not None:
        e["store_id"] = store_id
    return e


class FakeResolver:
    """store_resolver.StoreResolver 相当のミニマムfake(閾値/fuzzyロジックは持たず、
    テスト用の固定マッピングのみ)。実resolverのAPI(resolve/save_unknown/_ensure_loaded)
    と同じインターフェースを持つ。"""
    def __init__(self, mapping, fail_load=False):
        self._mapping = mapping   # raw_name -> resolved dict または None
        self._fail_load = fail_load
        self.loaded = False
        self.unknown_calls = []

    def _ensure_loaded(self):
        if self._fail_load:
            raise RuntimeError("simulated resolver load failure")
        self.loaded = True

    def resolve(self, name):
        return self._mapping.get(name)

    def save_unknown(self, name, x_url=""):
        self.unknown_calls.append((name, x_url))


# --- A. Exact resolved ---
r = FakeResolver({"マルハン東京店": {"store_id": "st1", "official_name": "マルハン東京店",
                                    "confidence": 1.0, "match_type": "exact"}})
entries = [entry(store="マルハン東京店")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(n_resolved == 1 and n_unresolved == 0, "A1 exact resolved件数")
ok(entries[0].get("store_id") == "st1", "A2 store_idがDB payload相当のentryに付与される")

# --- B. Fuzzy resolved (fakeでは resolve() の中身は同じ扱い。閾値ロジック自体はstore_resolver側の責務) ---
r = FakeResolver({"マルハン東京駅前": {"store_id": "st2", "official_name": "マルハン東京駅前店",
                                     "confidence": 0.92, "match_type": "fuzzy"}})
entries = [entry(store="マルハン東京駅前")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(n_resolved == 1, "B1 fuzzy resolved件数")
ok(entries[0]["store_id"] == "st2", "B2 fuzzy解決でもstore_id付与")

# --- C. Unresolved: reportは保存される(dropしない)・store_idなし ---
r = FakeResolver({})  # 何も解決しない
entries = [entry(store="謎の店舗123")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(n_resolved == 0 and n_unresolved == 1, "C1 unresolved件数")
ok("store_id" not in entries[0], "C2 未解決entryにstore_idキーが付かない(NULL相当)")
ok(len(entries) == 1, "C3 未解決でもentriesからdropされない(collector filterにしない)")
ok(r.unknown_calls == [("謎の店舗123", "https://x.com/store1/status/1")],
   "C4 未解決分はsave_unknown()に記録される(既存save_complete()と同じ挙動)")

# --- D. Resolver load failure: report保存継続・store_idなし・例外で落ちない ---
r = FakeResolver({}, fail_load=True)
entries = [entry(store="マルハン東京店")]
try:
    n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
    raised = False
except Exception:
    raised = True
ok(not raised, "D1 resolver load失敗でも例外が呼び出し元に伝播しない")
ok(len(entries) == 1 and "store_id" not in entries[0],
   "D2 resolver load失敗時もreportは保存継続(store_idなしのまま)")

# resolver自体が取得できない場合(get_resolver()がNoneを返す等)も同様にfail-open
entries2 = [entry(store="マルハン東京店")]
n_resolved2, n_unresolved2 = F.resolve_store_ids(entries2, resolver=None)
# resolver=None かつ get_resolver() が例外/None を返す環境(このテストプロセスには
# SUPABASE_SERVICE_ROLE_KEY が無い想定)でも entries は変更されず残る
ok(len(entries2) == 1, "D3 resolver未初期化でもentriesは保持される")

# --- E. Existing store_id already present: 上書きしない ---
r = FakeResolver({"マルハン東京店": {"store_id": "st_wrong", "official_name": "マルハン東京店",
                                    "confidence": 1.0, "match_type": "exact"}})
entries = [entry(store="マルハン東京店", store_id="st_existing")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(entries[0]["store_id"] == "st_existing", "E1 既存store_idは別解決結果で上書きされない")
ok(n_resolved == 0 and n_unresolved == 0, "E2 既存store_idありのentryはresolve()自体を呼ばない(スキップ)")

# --- F. Multiple entries: resolved/unresolved混在 ---
r = FakeResolver({"店A": {"store_id": "stA", "official_name": "店A", "confidence": 1.0, "match_type": "exact"}})
entries = [entry(store="店A"), entry(store="店B(未登録)"), entry(store=None), entry(store="")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(n_resolved == 1 and n_unresolved == 1, "F1 resolved/unresolved混在の集計が正しい")
ok(entries[0]["store_id"] == "stA", "F2 resolved分のみstore_id付与")
ok("store_id" not in entries[1], "F3 unresolved分はstore_id無し")
ok(len(entries) == 4, "F4 全entryが保存継続(store_name欠損分も含めdropしない)")

# --- G. Duplicate tweet id: resolve_store_ids自体はUPSERT semanticsに関与しない ---
# (idベースの重複排除は呼び出し元のdeduped生成ロジックの責務。ここでは
#  同一idのentryが複数来ても resolve_store_ids がクラッシュ・重複増殖しないことのみ確認)
r = FakeResolver({"店A": {"store_id": "stA", "official_name": "店A", "confidence": 1.0, "match_type": "exact"}})
entries = [entry(store="店A"), entry(store="店A")]  # 同一store名の2件(idは同じ"e1"だが対象外)
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(len(entries) == 2 and n_resolved == 2, "G1 同名重複entryでもクラッシュせず両方解決される")

# --- H. store_name が空/None: resolver呼び出し不要・report保存継続 ---
r = FakeResolver({})
entries = [entry(store=None), entry(store="")]
n_resolved, n_unresolved = F.resolve_store_ids(entries, resolver=r)
ok(n_resolved == 0 and n_unresolved == 0, "H1 store_name空/Noneはresolve試行自体をスキップ")
ok(len(entries) == 2, "H2 store_name空でもreportは保存継続")
ok(r.unknown_calls == [], "H3 store_name空はsave_unknownも呼ばれない(無駄なDB問い合わせをしない)")

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
