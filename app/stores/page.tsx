"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";

type Store = {
  id: string;
  name: string;
  pref: string;
  area: string;
  city?: string | null;
  event_count: number;
  hp_url?: string | null;
  x_url?: string | null;
  address?: string | null;
  map_url?: string | null;
  is_low_rental?: boolean;
  lottery_time?: string | null;
};

type DmmStore = { name: string; dmm_id: string };
type AreasData = Record<string, Record<string, DmmStore[]>>;
type DisplayStore = Store & { dmm_id?: string; isEventless?: boolean };

const C = {
  bg: "#f0f0f0", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", text: "#222222", sub: "#444444",
  muted: "#888888", dim: "#cccccc", sidebar: "#fafafa",
  sideHead: "#333333",
};

const AREAS = ["北海道", "東北", "関東", "中部", "近畿", "中国・四国", "九州・沖縄"];

const PREFS_BY_AREA: Record<string, string[]> = {
  "北海道": ["北海道"],
  "東北": ["青森県","岩手県","宮城県","秋田県","山形県","福島県"],
  "関東": ["東京都","神奈川県","埼玉県","千葉県","茨城県","栃木県","群馬県"],
  "中部": ["愛知県","静岡県","新潟県","長野県","岐阜県","石川県","富山県","福井県","山梨県"],
  "近畿": ["大阪府","兵庫県","京都府","奈良県","滋賀県","三重県","和歌山県"],
  "中国・四国": ["広島県","岡山県","山口県","鳥取県","島根県","愛媛県","香川県","徳島県","高知県"],
  "九州・沖縄": ["福岡県","熊本県","鹿児島県","宮崎県","大分県","長崎県","佐賀県","沖縄県"],
};

export default function StoresPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [areas, setAreas] = useState<AreasData>({});
  const [area, setArea] = useState("");
  const [pref, setPref] = useState("");
  const [city, setCity] = useState("");
  const [query, setQuery] = useState("");
  const [lowRentalOnly, setLowRentalOnly] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    Promise.all([
      fetch("/stores.json").then(r => r.json()),
      fetch("/areas.json").then(r => r.json()).catch(() => ({})),
    ]).then(([s, a]) => { setStores(s); setAreas(a); }).catch(() => {});
  }, []);

  const prefOptions = area ? (PREFS_BY_AREA[area] || []) : [];

  const cityOptions = useMemo(() => {
    if (!pref || !areas[pref]) return [];
    return Object.entries(areas[pref])
      .map(([c, list]) => [c, list.length] as [string, number])
      .sort((a, b) => b[1] - a[1]);
  }, [areas, pref]);

  const storeByName = useMemo(() => {
    const m = new Map<string, Store>();
    for (const s of stores) m.set(s.name, s);
    return m;
  }, [stores]);

  const filtered = useMemo((): DisplayStore[] => {
    if (city && pref && areas[pref]?.[city]) {
      // city選択時は areas.json の順序で表示、stores.json と名前照合
      const dmmList = areas[pref][city];
      const q = query.toLowerCase();
      const result = dmmList
        .filter(ds => !query || ds.name.toLowerCase().includes(q))
        .map(ds => {
          const matched = storeByName.get(ds.name);
          if (matched) return matched as DisplayStore;
          // stores.json にない場合（areas.json 更新後まだマージされていない店舗）
          return {
            id: `dmm_${ds.dmm_id}`, name: ds.name, pref,
            area, event_count: 0, dmm_id: ds.dmm_id, isEventless: true,
          } as DisplayStore;
        })
        .filter(s => !lowRentalOnly || s.is_low_rental);
      // イベントあり店舗を先頭に
      return [
        ...result.filter(s => s.event_count > 0),
        ...result.filter(s => s.event_count === 0),
      ];
    }

    const result = stores.filter(s => {
      if (area && s.area !== area) return false;
      if (pref && s.pref !== pref) return false;
      if (lowRentalOnly && !s.is_low_rental) return false;
      if (query) {
        const q = query.toLowerCase();
        if (!s.name.toLowerCase().includes(q) && !s.pref.includes(query)) return false;
      }
      return true;
    }) as DisplayStore[];

    // event_count 降順 → 名前順
    return result.sort((a, b) => b.event_count - a.event_count || a.name.localeCompare(b.name, "ja"));
  }, [stores, areas, area, pref, city, query, lowRentalOnly, storeByName]);

  // パンくずリスト
  const breadcrumbs = useMemo(() => {
    const crumbs: { label: string; onClick: () => void }[] = [
      { label: "全国", onClick: () => { setArea(""); setPref(""); setCity(""); } },
    ];
    if (area) crumbs.push({ label: area, onClick: () => { setPref(""); setCity(""); } });
    if (pref) crumbs.push({ label: pref, onClick: () => setCity("") });
    if (city) crumbs.push({ label: city, onClick: () => {} });
    return crumbs;
  }, [area, pref, city]);

  const showSidebar = !isMobile || sidebarOpen;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif", color: C.text }}>

      {/* ヘッダー */}
      <header style={{
        position: "sticky", top: 0, zIndex: 100,
        background: C.white, borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
      }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 12px", display: "flex", alignItems: "center", gap: 8, height: 52 }}>
          <Link href="/" style={{ color: C.red, fontWeight: 900, fontSize: isMobile ? 14 : 16, textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0 }}>
            メシウマ稼働
          </Link>
          {!isMobile && <><span style={{ color: C.border }}>|</span><span style={{ color: C.text, fontSize: 14, fontWeight: 700, whiteSpace: "nowrap" }}>全国ホール検索</span></>}
          <div style={{ flex: 1 }} />
          {/* 検索ボックス（ヘッダー） */}
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={isMobile ? "店舗名検索..." : "店舗名で検索..."}
            style={{
              width: isMobile ? "min(160px, 45vw)" : 220, padding: "6px 12px", fontSize: 13,
              border: `1.5px solid ${C.border}`, borderRadius: 20,
              outline: "none", fontFamily: "inherit", minWidth: 0,
            }}
          />
        </div>
      </header>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "12px 12px 80px", display: "flex", flexDirection: isMobile ? "column" : "row", gap: 16, alignItems: "flex-start" }}>

        {/* ===== サイドバー ===== */}
        {isMobile && (
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              width: "100%", padding: "10px",
              background: C.red, color: "#fff", border: "none",
              borderRadius: 6, fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}
          >
            {sidebarOpen ? "▲ エリア絞り込みを閉じる" : "▼ エリア・市区町村から絞り込む"}
          </button>
        )}

        {(showSidebar || !isMobile) && (
          <aside style={{
            width: isMobile ? "100%" : 220,
            flexShrink: 0,
            display: isMobile ? (sidebarOpen ? "block" : "none") : "block",
          }}>

            {/* エリア選択 */}
            <div style={{
              background: C.white, border: `1px solid ${C.border}`,
              borderRadius: 6, overflow: "hidden", marginBottom: 12,
            }}>
              <div style={{
                background: C.sideHead, color: C.white, padding: "8px 12px",
                fontSize: 12, fontWeight: 700, letterSpacing: "0.05em",
              }}>
                エリアから探す
              </div>
              <div>
                <button
                  onClick={() => { setArea(""); setPref(""); setCity(""); }}
                  style={{
                    display: "block", width: "100%", textAlign: "left",
                    padding: "8px 14px", fontSize: 13, border: "none", borderBottom: `1px solid ${C.border}`,
                    background: !area ? "#fff0f0" : C.white,
                    color: !area ? C.red : C.text,
                    fontWeight: !area ? 700 : 400, cursor: "pointer",
                  }}
                >
                  🗾 全国
                </button>
                {AREAS.map(a => (
                  <button
                    key={a}
                    onClick={() => { setArea(a); setPref(""); setCity(""); if (isMobile) setSidebarOpen(false); }}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "8px 14px", fontSize: 13, border: "none", borderBottom: `1px solid ${C.border}`,
                      background: area === a ? "#fff0f0" : C.white,
                      color: area === a ? C.red : C.text,
                      fontWeight: area === a ? 700 : 400, cursor: "pointer",
                    }}
                  >
                    {a}
                  </button>
                ))}
              </div>
            </div>

            {/* 都道府県リスト */}
            {prefOptions.length > 0 && (
              <div style={{
                background: C.white, border: `1px solid ${C.border}`,
                borderRadius: 6, overflow: "hidden", marginBottom: 12,
              }}>
                <div style={{
                  background: C.sideHead, color: C.white, padding: "8px 12px",
                  fontSize: 12, fontWeight: 700,
                }}>
                  都道府県
                </div>
                <div>
                  {prefOptions.map(p => {
                    const count = areas[p] ? Object.values(areas[p]).reduce((s, l) => s + l.length, 0) : null;
                    return (
                      <button
                        key={p}
                        onClick={() => { setPref(p); setCity(""); }}
                        style={{
                          display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center",
                          padding: "8px 14px", fontSize: 13, border: "none", borderBottom: `1px solid ${C.border}`,
                          background: pref === p ? "#fff0f0" : C.white,
                          color: pref === p ? C.red : C.text,
                          fontWeight: pref === p ? 700 : 400, cursor: "pointer",
                        }}
                      >
                        <span>{p}</span>
                        {count !== null && <span style={{ color: C.muted, fontSize: 11 }}>({count})</span>}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 市区町村リスト */}
            {cityOptions.length > 0 && (
              <div style={{
                background: C.white, border: `1px solid ${C.border}`,
                borderRadius: 6, overflow: "hidden", marginBottom: 12,
              }}>
                <div style={{
                  background: C.red, color: C.white, padding: "8px 12px",
                  fontSize: 12, fontWeight: 700,
                }}>
                  市区町村から絞り込む
                </div>
                <div style={{ maxHeight: isMobile ? 220 : 400, overflowY: "auto" }}>
                  <button
                    onClick={() => setCity("")}
                    style={{
                      display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center",
                      padding: "7px 14px", fontSize: 13, border: "none", borderBottom: `1px solid ${C.border}`,
                      background: !city ? "#fff0f0" : C.white,
                      color: !city ? C.red : C.text,
                      fontWeight: !city ? 700 : 400, cursor: "pointer",
                    }}
                  >
                    <span>全域</span>
                    <span style={{ color: C.muted, fontSize: 11 }}>
                      ({cityOptions.reduce((s, [, c]) => s + c, 0)})
                    </span>
                  </button>
                  {cityOptions.map(([c, count]) => (
                    <button
                      key={c}
                      onClick={() => { setCity(c); if (isMobile) setSidebarOpen(false); }}
                      style={{
                        display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center",
                        padding: "7px 14px", fontSize: 13, border: "none", borderBottom: `1px solid ${C.border}`,
                        background: city === c ? "#fff0f0" : C.white,
                        color: city === c ? C.red : C.text,
                        fontWeight: city === c ? 700 : 400, cursor: "pointer",
                      }}
                    >
                      <span>{c}</span>
                      <span style={{ color: city === c ? C.red : C.muted, fontSize: 11 }}>({count})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* オプションフィルター */}
            <div style={{
              background: C.white, border: `1px solid ${C.border}`,
              borderRadius: 6, overflow: "hidden",
            }}>
              <div style={{
                background: C.sideHead, color: C.white, padding: "8px 12px",
                fontSize: 12, fontWeight: 700,
              }}>
                絞り込みオプション
              </div>
              <div style={{ padding: "10px 14px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={lowRentalOnly}
                    onChange={e => setLowRentalOnly(e.target.checked)}
                    style={{ accentColor: C.red, width: 15, height: 15 }}
                  />
                  💴 低貸し専門店のみ
                </label>
              </div>
            </div>

          </aside>
        )}

        {/* ===== メインコンテンツ ===== */}
        <main style={{ flex: 1, minWidth: 0 }}>

          {/* パンくずリスト */}
          <nav style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 12, flexWrap: "wrap" }}>
            {breadcrumbs.map((crumb, i) => (
              <React.Fragment key={i}>
                {i > 0 && <span style={{ color: C.muted, fontSize: 12 }}>›</span>}
                <button
                  onClick={crumb.onClick}
                  disabled={i === breadcrumbs.length - 1}
                  style={{
                    background: "none", border: "none", padding: "2px 4px",
                    fontSize: 12, cursor: i === breadcrumbs.length - 1 ? "default" : "pointer",
                    color: i === breadcrumbs.length - 1 ? C.text : C.red,
                    fontWeight: i === breadcrumbs.length - 1 ? 700 : 400,
                    textDecoration: i < breadcrumbs.length - 1 ? "underline" : "none",
                  }}
                >
                  {crumb.label}
                </button>
              </React.Fragment>
            ))}
          </nav>

          {/* ページタイトル */}
          <div style={{
            background: C.white, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "14px 18px", marginBottom: 12,
            borderLeft: `4px solid ${C.red}`,
          }}>
            <h1 style={{ fontSize: 18, fontWeight: 900, margin: "0 0 4px", color: C.text }}>
              {city ? `${pref} ${city}のパチンコ・パチスロホール` :
               pref ? `${pref}のパチンコ・パチスロホール` :
               area ? `${area}のパチンコ・パチスロホール` :
               "全国のパチンコ・パチスロホール"}
            </h1>
            <div style={{ color: C.muted, fontSize: 12 }}>
              {filtered.length.toLocaleString()}件
              {city && pref && areas[pref]?.[city] && filtered.some(s => s.event_count > 0) && (
                <span style={{ marginLeft: 8, color: C.red }}>
                  ／ イベント実績あり {filtered.filter(s => s.event_count > 0).length}件
                </span>
              )}
              {!area && <span style={{ marginLeft: 8 }}>（全{stores.length.toLocaleString()}店舗収録）</span>}
            </div>
          </div>

          {/* 店舗リスト */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {filtered.map(store => {
              const isEventless = store.isEventless; // areas.jsonのみ・まだ未マージ（稀）
              const noEvent = !isEventless && store.event_count === 0;
              const card = (
                <div style={{
                  background: C.white, border: `1px solid ${C.border}`,
                  borderRadius: 6, padding: "10px 12px",
                  display: "flex", alignItems: "flex-start", gap: 10,
                  opacity: isEventless ? 0.55 : noEvent ? 0.78 : 1,
                  transition: "box-shadow .12s",
                }}
                  onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 2px 10px rgba(0,0,0,.1)")}
                  onMouseLeave={e => (e.currentTarget.style.boxShadow = "none")}
                >
                  {/* 左: イベント件数バッジ */}
                  <div style={{ flexShrink: 0, width: 46, textAlign: "center", paddingTop: 2 }}>
                    {store.event_count > 0 ? (
                      <div style={{
                        background: C.red, color: "#fff",
                        borderRadius: 4, padding: "3px 0", fontSize: 11, fontWeight: 900,
                        lineHeight: 1.2,
                      }}>
                        <div style={{ fontSize: 15, fontWeight: 900 }}>{store.event_count}</div>
                        <div style={{ fontSize: 9 }}>実績</div>
                      </div>
                    ) : (
                      <div style={{
                        background: "#f5f5f5", color: C.dim,
                        borderRadius: 4, padding: "3px 0", fontSize: 10, lineHeight: 1.2,
                      }}>
                        <div style={{ fontSize: 13 }}>—</div>
                        <div style={{ fontSize: 9 }}>なし</div>
                      </div>
                    )}
                  </div>

                  {/* 中: 店舗情報 */}
                  <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap", marginBottom: 2 }}>
                      <span style={{
                        fontSize: 14, fontWeight: 700,
                        color: isEventless || noEvent ? C.sub : C.red,
                        lineHeight: 1.4, wordBreak: "break-all",
                      }}>
                        {store.name}
                      </span>
                      {store.is_low_rental && (
                        <span style={{
                          background: "#e8f0ff", color: "#0055cc", fontSize: 10, fontWeight: 700,
                          padding: "1px 6px", borderRadius: 3, border: "1px solid #0055cc44",
                          whiteSpace: "nowrap", flexShrink: 0,
                        }}>
                          低貸し
                        </span>
                      )}
                    </div>

                    {/* 所在地 */}
                    {(!city || store.address) && (
                      <div style={{ fontSize: 12, color: C.muted, marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {!city && <span>📍 {store.pref}{store.city ? ` ${store.city}` : ""}</span>}
                        {store.address && <span style={{ marginLeft: !city ? 6 : 0 }}>{store.address}</span>}
                      </div>
                    )}

                    {/* アイコンリンク */}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {store.lottery_time && (
                        <span style={{ fontSize: 10, color: "#996600", background: "#fffbe8", border: "1px solid #f0d060", borderRadius: 3, padding: "1px 6px", whiteSpace: "nowrap" }}>
                          🎰 {store.lottery_time}
                        </span>
                      )}
                      {store.hp_url && (
                        <a href={store.hp_url} target="_blank" rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          style={{ fontSize: 10, color: C.red, border: `1px solid #ffcccc`, borderRadius: 3, padding: "1px 6px", textDecoration: "none", background: "#fff0f0", whiteSpace: "nowrap" }}>
                          🌐 HP
                        </a>
                      )}
                      {store.x_url && (
                        <a href={store.x_url} target="_blank" rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          style={{ fontSize: 10, color: "#222", border: "1px solid #ccc", borderRadius: 3, padding: "1px 6px", textDecoration: "none", background: "#f5f5f5", whiteSpace: "nowrap" }}>
                          𝕏
                        </a>
                      )}
                      {store.map_url && (
                        <a href={store.map_url} target="_blank" rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          style={{ fontSize: 10, color: "#4285f4", border: "1px solid #c8d8ff", borderRadius: 3, padding: "1px 6px", textDecoration: "none", background: "#f0f5ff", whiteSpace: "nowrap" }}>
                          🗺 地図
                        </a>
                      )}
                    </div>
                  </div>

                  {/* 右端: 詳細矢印 */}
                  {!isEventless && (
                    <div style={{ flexShrink: 0, alignSelf: "center", color: C.muted, fontSize: 16 }}>›</div>
                  )}
                </div>
              );

              return isEventless ? (
                <div key={store.id}>{card}</div>
              ) : (
                <Link key={store.id} href={`/stores/${store.id}`} style={{ textDecoration: "none", display: "block" }}>
                  {card}
                </Link>
              );
            })}
          </div>

          {filtered.length === 0 && stores.length > 0 && (
            <div style={{ textAlign: "center", padding: "60px 0", color: C.muted, background: C.white, borderRadius: 6 }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
              <div>該当するホールが見つかりません</div>
            </div>
          )}

          {filtered.length === 0 && stores.length === 0 && (
            <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
              <div style={{ fontSize: 13 }}>読み込み中...</div>
            </div>
          )}
        </main>
      </div>

      {/* 広告掲載募集 */}
      <div style={{ background: "#fff8f0", borderTop: "2px solid #e60000", padding: "20px 16px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontWeight: 900, fontSize: 14, color: "#222", marginBottom: 4 }}>📣 広告掲載・タイアップ募集</div>
            <div style={{ fontSize: 12, color: "#666", lineHeight: 1.7 }}>
              ホール情報掲載・取材誘致・フロアマップ掲載・バナー広告など、各種ご相談お気軽に。
            </div>
          </div>
          <a href="mailto:info@mesiuma.jp" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            background: "#e60000", color: "#fff", fontWeight: 700,
            padding: "9px 18px", borderRadius: 6, fontSize: 13, textDecoration: "none",
          }}>
            ✉️ お問い合わせ
          </a>
        </div>
      </div>

      <footer style={{ textAlign: "center", padding: "20px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
