#!/usr/bin/env python3
"""NS-9 discover_store_x のユニットテスト（純粋関数中心・DB/ネット非依存）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import discover_store_x as D

PASS = 0
FAIL = 0

def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {msg}")
    else:
        FAIL += 1
        print(f"  ❌ FAIL  {msg}")


def cls(hp, handles, rejected=None, manager=None, dbmap=None, sid="S1"):
    return D.classify_confidence(hp, handles, set(rejected or []), set(manager or []),
                                 dict(dbmap or {}), sid)


# 1. official store page → HIGH
r = cls("https://yasuda-asaka.example.jp/", ["yasuda_asaka"])
ok(r["confidence"] == "HIGH" and r["handle"] == "yasuda_asaka", "1 公式店舗ページの単一X → HIGH")

# 2. chain official/HQ page → HIGH にしない
r = cls("https://www.maruhan.co.jp/shop/123", ["maruhan_official"])
ok(r["confidence"] == "NONE" and r["reason"] == "chain_hq_domain", "2 チェーン本部ドメイン → HIGHにしない")

# 3. DMM official-like external (店舗固有ドメインでない一般) — v1では店舗HP以外は入力されない前提だが
#    店舗固有ドメインに単一handleがあればHIGH（DMM条件はv1対象外の確認）
r = cls("https://espace-seibu.example.jp/", ["espaceseibu1"])
ok(r["confidence"] == "HIGH", "3 店舗固有サイトの単一公式X → HIGH")

# 4. search-only（HPにXリンク無し）→ auto-write 禁止（NONE）
r = cls("https://someshop.example.jp/", [])
ok(r["confidence"] == "NONE" and r["reason"] == "no_x_link_on_page", "4 HPにXリンク無し → auto-write禁止")

# 5. manager account のみ → auto-write 禁止（LOW）
r = cls("https://shop.example.jp/", ["tencho_shimizu"], manager=["tencho_shimizu"])
ok(r["confidence"] == "LOW" and r["handle"] is None, "5 managerアカウントのみ → auto-write禁止")

# 6. same handle 別store → conflict（LOW）
r = cls("https://shop.example.jp/", ["group_x"], dbmap={"group_x": "OTHER"}, sid="S1")
ok(r["confidence"] == "LOW" and "other_store" in r["reason"], "6 同一handleが別store → conflict")

# 6b. same handle 自店に既存 → HIGH（自店なら競合でない）
r = cls("https://shop.example.jp/", ["self_x"], dbmap={"self_x": "S1"}, sid="S1")
ok(r["confidence"] == "HIGH", "6b 同一handleが自店 → 競合でない")

# 7. existing x_url → overwrite 禁止（gate 1 で落ちる）
g = D.safety_gate({"id": "S1", "name": "n", "pref": "東京都", "x_url": "https://x.com/exist"},
                  "newhandle", {}, set(), set())
ok(not g["ok"] and "1_x_url_is_null" in g["fail"], "7 既存x_url → overwrite禁止(gate1)")

# 8. rejected handle → write 禁止（classify LOW & gate9）
r = cls("https://shop.example.jp/", ["badx"], rejected=["badx"])
ok(r["confidence"] == "LOW", "8a rejected handle → classify LOW")
g = D.safety_gate({"id": "S1", "name": "n", "pref": "東京都", "x_url": None}, "badx", {}, {"badx"}, set())
ok(not g["ok"] and "9_not_rejected_handle" in g["fail"], "8b rejected handle → gate9で落ちる")

# 9. duplicate normalization（大小/@/twitter.com を正規化して同一視）
ok(D.norm_handle("@Yasuda_Asaka") == "yasuda_asaka", "9a norm: @と大小")
hs = D.extract_handles('<a href="https://twitter.com/Foo_Bar">x</a> <a href="https://x.com/foo_bar">y</a>')
ok(hs == ["foo_bar"], "9b extract: twitter.com/x.com 大小 重複排除")

# 10. no candidate → NONE（write対象なし）
r = cls("https://shop.example.jp/", [])
ok(r["confidence"] == "NONE", "10 候補なし → NONE(NO_OP相当)")

# 11. repeated run → idempotent（同じ入力で同じ結果・純粋関数）
a = cls("https://shop.example.jp/", ["abc_shop"])
b = cls("https://shop.example.jp/", ["abc_shop"])
ok(a == b, "11 同一入力 → 同一結果(冪等)")

# 12. partial source failure（fetch=None を run が errors として扱う: fetch差し替えで確認）
#     ここでは extract_handles が空文字/None を安全に処理することを確認
ok(D.extract_handles("") == [] and D.extract_handles(None) == [], "12 空/None HTML → 例外なく空")

# 13. rate-limit / fetch失敗相当 → handle無し扱い
ok(D.classify_confidence("https://s.example.jp/", [], set(), set(), {}, "S1")["confidence"] == "NONE",
   "13 取得失敗(handle無) → NONE")

# 14. malformed URL / handle → 除外
hs = D.extract_handles('<a href="https://x.com/ab">too short</a> <a href="https://x.com/good_one">ok</a>')
ok(hs == ["good_one"], "14a 短すぎhandle(2字)除外")
ok(not D.valid_handle("bad-handle!") and D.valid_handle("good_1"), "14b handle形式判定")

# 15. canonical mismatch（ambiguous 複数handle → LOW, auto-write しない）
r = cls("https://shop.example.jp/", ["shop_a", "shop_b"])
ok(r["confidence"] == "LOW" and "ambiguous" in r["reason"], "15 複数handle曖昧 → LOW(auto-write禁止)")

# 16. 共有hp_url(法人/グループページ) → HIGHにしない
r = D.classify_confidence("https://hamatomo.co.jp/business/amusement/", ["rakuen_official"],
                          set(), set(), {}, "S1", hp_is_shared=True)
ok(r["confidence"] == "NONE" and r["reason"] == "shared_corporate_hp", "16 共有hp_url → HIGHにしない")

# 16b. 共有でなければ通常評価
r = D.classify_confidence("https://shop-specific.example.jp/", ["shop_x"],
                          set(), set(), {}, "S1", hp_is_shared=False)
ok(r["confidence"] == "HIGH", "16b 非共有hp_url単一handle → HIGH")

# 17. portal/blog/SNS 基盤ドメイン判定
ok(D.is_portal_host("https://m.site777.jp/x") and D.is_portal_host("https://storename.ameblo.jp/")
   and D.is_portal_host("https://foo.wixsite.com/bar"), "17a portal/blog/SNS host → True")
ok(not D.is_portal_host("https://yasuda-asaka.example.jp/"), "17b 店舗固有ドメイン → portalでない")
ok(D.host_of("https://www.Example.co.jp/path") == "example.co.jp", "17c host_of: www除去+小文字")

# gate 総合: 正常HIGHは全gate PASS
g = D.safety_gate({"id": "S1", "name": "やすだ朝霞店", "pref": "埼玉県", "x_url": None, "ng_flag": False},
                  "yasuda_asaka", {"yasuda_asaka": "S1"}, set(), set())
ok(g["ok"], "gate 正常HIGH → 全PASS")

# gate: ng_flag(manual block) → gate10
g = D.safety_gate({"id": "S1", "name": "n", "pref": "東京都", "x_url": None, "ng_flag": True},
                  "h_ok", {}, set(), set())
ok(not g["ok"] and "10_not_manual_block" in g["fail"], "gate manual block(ng_flag) → gate10")

# ── NS-9A automation: retry / state / structural guard（純粋関数）──
NOW = 1_000_000.0
DAY = 86400

# 18. retry_days: 分類ごとの間隔
ok(D.retry_days("single_handle_on_official_store_site") == 7, "18a candidate → 7日")
ok(D.retry_days("hp_fetch_failed") == 2, "18b fetch失敗 → 2日")
ok(D.retry_days("shared_corporate_hp") == 90, "18c 共有法人HP → 90日")
ok(D.retry_days("only_rejected_or_manager_handles") >= 3650, "18d manager/rejected → 長期skip")
ok(D.retry_days("unknown_reason") == D.RETRY_DAYS["_default"], "18e 未知 → default")

# 19. is_due: 未探索 / 期限到来 / 期限前
ok(D.is_due("X", {}, NOW) is True, "19a 未探索 → due")
ok(D.is_due("X", {"X": {"next_retry_at_ts": NOW - 10}}, NOW) is True, "19b 期限超過 → due")
ok(D.is_due("X", {"X": {"next_retry_at_ts": NOW + DAY}}, NOW) is False, "19c 期限前 → not due")

# 20. auto_write_allowed: 構造的多重ガード
import os as _os
_os.environ.pop("DISCOVERY_AUTO_WRITE", None)
ok(D.auto_write_allowed(True) is False, "20a flagのみ(env無) → 書込不可")
_os.environ["DISCOVERY_AUTO_WRITE"] = "1"
ok(D.auto_write_allowed(False) is False, "20b envのみ(flag無) → 書込不可")
ok(D.auto_write_allowed(True) is True, "20c flag+env両方 → 書込可")
_os.environ.pop("DISCOVERY_AUTO_WRITE", None)

# 21. run: candidate-only（auto_write既定OFF）→ DB書込0・state更新・冪等
FAKE = {
    "s_hp":   ('<a href="https://x.com/machi_shop">x</a>', {"id": "s_hp", "name": "まちの店", "pref": "東京都", "hp_url": "https://machi-shop-unique.example.jp/", "x_url": None, "is_active": True, "ng_flag": False}),
    "s_none": ('<p>no link</p>', {"id": "s_none", "name": "リンク無店", "pref": "千葉県", "hp_url": "https://none-unique.example.jp/", "x_url": None, "is_active": True, "ng_flag": False}),
}
def fake_ctx(monkey_db):
    return dict(
        db=monkey_db,
        handles={},
        rejected=set(), excluded_manager=set(),
        verified_store_ids=set(),
        db_handle_to_store={},
        manual_block_ids=set(),
        shared_hosts=set(),
    )
# build_context / fetch を差し替えて run を実行
_orig_build = D.build_context
_orig_fetch = D.fetch_html
D.build_context = lambda: fake_ctx([FAKE["s_hp"][1], FAKE["s_none"][1]])
def _fake_fetch(url):
    for k, (html, st) in FAKE.items():
        if st["hp_url"] == url:
            return html
    return None
try:
    st_state = {}
    r1 = D.run(limit=10, dry_run=False, pilot_ids=None, report_path=None,
               fetch=_fake_fetch, auto_write=False, state=st_state, now=NOW, persist_state=False)
    ok(r1["mode"] == "CANDIDATE_ONLY", "21a auto_write OFF → CANDIDATE_ONLY")
    ok(len(r1["written"]) == 0, "21b DB書込 0件")
    ok(r1["stats"]["high"] == 1 and r1["stats"]["scanned"] == 2, "21c HIGH検出1 / scanned2")
    ok("s_hp" in st_state and st_state["s_hp"]["candidate_handle"] == "machi_shop", "21d state更新(candidate handle保存)")
    ok(st_state["s_hp"]["next_retry_at_ts"] == NOW + 7 * DAY, "21e candidateのnext_retry=7日")
    ok(st_state["s_none"]["next_retry_at_ts"] == NOW + 30 * DAY, "21f no_x_linkのnext_retry=30日")

    # 22. 2回目 run（同じnow）→ 全店 not due → scanned=0（冪等・無駄再探索なし）
    r2 = D.run(limit=10, dry_run=False, pilot_ids=None, report_path=None,
               fetch=_fake_fetch, auto_write=False, state=st_state, now=NOW, persist_state=False)
    ok(r2["stats"]["scanned"] == 0, "22 2回目(期限前) → scanned0(冪等/無駄なし)")

    # 23. 期限到来後 → 再探索される
    r3 = D.run(limit=10, dry_run=False, pilot_ids=None, report_path=None,
               fetch=_fake_fetch, auto_write=False, state=st_state, now=NOW + 100 * DAY, persist_state=False)
    ok(r3["stats"]["scanned"] == 2, "23 期限到来後 → 再探索される")

    # 24. 同一handleが複数店 → group account として除外（write候補にしない）
    dup_db = [
        {"id": "d1", "name": "店1", "pref": "東京都", "hp_url": "https://uniq1.example.jp/", "x_url": None, "is_active": True, "ng_flag": False},
        {"id": "d2", "name": "店2", "pref": "東京都", "hp_url": "https://uniq2.example.jp/", "x_url": None, "is_active": True, "ng_flag": False},
    ]
    D.build_context = lambda: fake_ctx(dup_db)
    def _dup_fetch(url):
        return '<a href="https://x.com/group_corp">x</a>'
    rd = D.run(limit=10, dry_run=False, pilot_ids=None, report_path=None,
               fetch=_dup_fetch, auto_write=False, state={}, now=NOW, persist_state=False)
    ok(rd["stats"]["high"] == 0, "24 同一handle複数店 → HIGH除外(group account)")

    # 25. circuit breaker: fetch失敗が大半 → BLOCKED
    many = [{"id": f"f{i}", "name": f"店{i}", "pref": "東京都", "hp_url": f"https://f{i}.example.jp/",
             "x_url": None, "is_active": True, "ng_flag": False} for i in range(12)]
    D.build_context = lambda: fake_ctx(many)
    rc = D.run(limit=20, dry_run=False, pilot_ids=None, report_path=None,
               fetch=lambda u: None, auto_write=False, state={}, now=NOW, persist_state=False)
    ok(rc["mode"] == "BLOCKED" and rc["circuit"]["tripped"], "25 fetch失敗急増 → circuit BLOCKED")
finally:
    D.build_context = _orig_build
    D.fetch_html = _orig_fetch

print(f"\n=> PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
