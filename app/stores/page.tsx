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
  bg: "#f0f0f0",
  white: "#ffffff",
  border: "#d8d8d8",
  red: "#e60000",
  blue: "#1e5fc4",
  green: "#009944",
  text: "#222222",
  sub: "#444444",
  muted: "#888888",
};

const ALL_PREFS = [
  "北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県",
  "東京都","神奈川県","埼玉県","千葉県","茨城県","栃木県","群馬県",
  "愛知県","静岡県","新潟県","長野県","岐阜県","石川県","富山県","福井県","山梨県",
  "大阪府","兵庫県","京都府","奈良県","滋賀県","三重県","和歌山県",
  "広島県","岡山県","山口県","鳥取県","島根県","愛媛県","香川県","徳島県","高知県",
  "福岡県","熊本県","鹿児島県","宮崎県","大分県","長崎県","佐賀県","沖縄県",
];

function StoreCard({ store }: { store: DisplayStore }) {
  const isEventless = !!store.isEventless;
  const hasEvent = store.event_count > 0;

  const initial = store.name.slice(0, 1);
  const hue = store.name.split("").reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  const thumbBg = `hsl(${hue},40%,55%)`;

  const card = (
    <div style={{
      background: C.white,
      borderBottom: `1px solid ${C.border}`,
      padding: "12px 14px",
      display: "flex",
      alignItems: "flex-start",
      gap: 12,
      position: "relative",
    }}>
      {/* 左サムネイル */}
      <div style={{ flexShrink: 0, textAlign: "center", width: 72 }}>
        <div style={{
          width: 72, height: 72,
          background: thumbBg,
          borderRadius: 4,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 28, fontWeight: 900, color: "#fff",
          position: "relative",
          overflow: "hidden",
        }}>
          {initial}
          {/* UP!バッジ */}
          {hasEvent && (
            <div style={{
              position: "absolute", bottom: 0, left: 0, right: 0,
              background: C.red, color: "#fff",
              fontSize: 11, fontWeight: 900, textAlign: "center",
              padding: "1px 0",
            }}>
              UP!
            </div>
          )}
        </div>
        {/* イベント件数 */}
        <div style={{ fontSize: 10, color: hasEvent ? C.red : C.muted, marginTop: 3, fontWeight: hasEvent ? 700 : 400 }}>
          {hasEvent ? `${store.event_count}実績` : "実績なし"}
        </div>
      </div>

      {/* 右: 情報 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* 店舗名 */}
        <div style={{
          fontSize: 15, fontWeight: 700,
          color: isEventless ? C.muted : C.text,
          marginBottom: 3, lineHeight: 1.4,
        }}>
          {store.name}
          {store.is_low_rental && (
            <span style={{
              marginLeft: 6, fontSize: 10, fontWeight: 700,
              color: C.blue, background: "#e8f0ff",
              border: `1px solid ${C.blue}44`,
              padding: "1px 5px", borderRadius: 3,
            }}>低貸し</span>
          )}
        </div>

        {/* 住所 */}
        {store.address && (
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 4, lineHeight: 1.4 }}>
            {store.address}
          </div>
        )}
        {!store.address && (
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 4 }}>
            {store.pref}{store.city ? ` ${store.city}` : ""}
          </div>
        )}

        {/* 抽選時刻 */}
        {store.lottery_time && (
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            background: "#fffbe8", border: "1px solid #f0d060",
            borderRadius: 3, padding: "2px 7px", marginBottom: 5,
            fontSize: 11, color: "#996600", fontWeight: 700,
          }}>
            🎰 抽選 {store.lottery_time}
          </div>
        )}

        {/* リンクバッジ行 */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center", marginTop: 2 }}>
          {store.hp_url && (
            <a href={store.hp_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                fontSize: 11, color: C.red, background: "#fff0f0",
                border: `1px solid #ffcccc`, borderRadius: 3,
                padding: "2px 8px", textDecoration: "none", whiteSpace: "nowrap",
              }}>
              🌐 公式HP
            </a>
          )}
          {store.x_url && (
            <a href={store.x_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                fontSize: 11, color: "#333", background: "#f5f5f5",
                border: "1px solid #ccc", borderRadius: 3,
                padding: "2px 8px", textDecoration: "none", whiteSpace: "nowrap",
              }}>
              𝕏 公式X
            </a>
          )}
          {store.map_url && (
            <a href={store.map_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                fontSize: 11, color: "#4285f4", background: "#f0f5ff",
                border: "1px solid #c8d8ff", borderRadius: 3,
                padding: "2px 8px", textDecoration: "none", whiteSpace: "nowrap",
              }}>
              🗺 地図
            </a>
          )}
        </div>
      </div>

      {/* 右端: データ公開ボタン */}
      {!isEventless && (
        <div style={{ flexShrink: 0, alignSelf: "flex-end" }}>
          <div style={{
            background: C.green, color: "#fff",
            fontSize: 11, fontWeight: 700,
            padding: "4px 10px", borderRadius: 3,
            whiteSpace: "nowrap",
          }}>
            データ公開
          </div>
        </div>
      )}
    </div>
  );

  return isEventless ? (
    <div key={store.id} style={{ opacity: 0.6 }}>{card}</div>
  ) : (
    <Link key={store.id} href={`/stores/${store.id}`} style={{ textDecoration: "none", display: "block" }}>
      {card}
    </Link>
  );
}

export default function StoresPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [areas, setAreas] = useState<AreasData>({});
  const [pref, setPref] = useState("");
  const [city, setCity] = useState("");
  const [query, setQuery] = useState("");
  const [lowRentalOnly, setLowRentalOnly] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch("/stores.json").then(r => r.json()),
      fetch("/areas.json").then(r => r.json()).catch(() => ({})),
    ]).then(([s, a]) => { setStores(s); setAreas(a); }).catch(() => {});
  }, []);

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
      const dmmList = areas[pref][city];
      const q = query.toLowerCase();
      const result = dmmList
        .filter(ds => !query || ds.name.toLowerCase().includes(q))
        .map(ds => {
          const matched = storeByName.get(ds.name);
          if (matched) return matched as DisplayStore;
          return {
            id: `dmm_${ds.dmm_id}`, name: ds.name, pref,
            area: "", event_count: 0, dmm_id: ds.dmm_id, isEventless: true,
          } as DisplayStore;
        })
        .filter(s => !lowRentalOnly || s.is_low_rental);
      return [
        ...result.filter(s => s.event_count > 0),
        ...result.filter(s => s.event_count === 0),
      ];
    }

    const result = stores.filter(s => {
      if (pref && s.pref !== pref) return false;
      if (lowRentalOnly && !s.is_low_rental) return false;
      if (query) {
        const q = query.toLowerCase();
        if (!s.name.toLowerCase().includes(q) && !s.pref.includes(query)) return false;
      }
      return true;
    }) as DisplayStore[];

    return result.sort((a, b) => b.event_count - a.event_count || a.name.localeCompare(b.name, "ja"));
  }, [stores, areas, pref, city, query, lowRentalOnly, storeByName]);

  const resultLabel = city ? `${pref} ${city}` : pref ? pref : "全国";

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif", color: C.text }}>

      {/* ヘッダー */}
      <header style={{
        background: C.white,
        borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 14px", height: 50, display: "flex", alignItems: "center", gap: 10 }}>
          <Link href="/" style={{ color: C.red, fontWeight: 900, fontSize: 15, textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0 }}>
            メシウマ稼働株式会社
          </Link>
          <div style={{ flex: 1 }} />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="店舗名で検索..."
            style={{
              width: "min(200px,40vw)", padding: "5px 12px", fontSize: 13,
              border: `1.5px solid ${C.border}`, borderRadius: 20,
              outline: "none", fontFamily: "inherit",
            }}
          />
        </div>
      </header>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "14px 0 60px" }}>

        {/* フィルター（DMMスタイル・ドロップダウン） */}
        <div style={{
          background: C.white,
          borderBottom: `1px solid ${C.border}`,
          padding: "10px 14px",
          display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
        }}>
          {/* 都道府県 */}
          <select
            value={pref}
            onChange={e => { setPref(e.target.value); setCity(""); }}
            style={{
              flex: "1 1 140px", minWidth: 120, maxWidth: 200,
              padding: "8px 10px", fontSize: 14,
              border: `2px solid ${pref ? C.red : C.border}`,
              borderRadius: 4, background: C.white,
              color: pref ? C.red : C.text,
              fontWeight: pref ? 700 : 400,
              fontFamily: "inherit", cursor: "pointer", outline: "none",
              appearance: "none",
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "right 10px center",
              paddingRight: 28,
            }}
          >
            <option value="">都道府県</option>
            {ALL_PREFS.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          {/* 市区町村 */}
          <select
            value={city}
            onChange={e => setCity(e.target.value)}
            disabled={cityOptions.length === 0}
            style={{
              flex: "1 1 140px", minWidth: 120, maxWidth: 200,
              padding: "8px 10px", fontSize: 14,
              border: `2px solid ${city ? C.red : C.border}`,
              borderRadius: 4, background: cityOptions.length === 0 ? "#f8f8f8" : C.white,
              color: city ? C.red : C.text,
              fontWeight: city ? 700 : 400,
              fontFamily: "inherit", cursor: cityOptions.length === 0 ? "default" : "pointer", outline: "none",
              appearance: "none",
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "right 10px center",
              paddingRight: 28,
            }}
          >
            <option value="">{pref ? `${pref}内 全域` : "市区町村"}</option>
            {cityOptions.map(([c, count]) => (
              <option key={c} value={c}>{c}（{count}件）</option>
            ))}
          </select>

          {/* 低貸しチェック */}
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" }}>
            <input
              type="checkbox"
              checked={lowRentalOnly}
              onChange={e => setLowRentalOnly(e.target.checked)}
              style={{ accentColor: C.red, width: 14, height: 14 }}
            />
            低貸し専門店のみ
          </label>
        </div>

        {/* 検索結果ヘッダー */}
        <div style={{
          background: C.white,
          padding: "10px 14px",
          borderBottom: `1px solid ${C.border}`,
          display: "flex", alignItems: "baseline", gap: 8,
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
            検索結果一覧
          </div>
          <div style={{ fontSize: 12, color: C.muted }}>
            ({resultLabel})
          </div>
          <div style={{ marginLeft: "auto", fontSize: 14, fontWeight: 700, color: C.text }}>
            {filtered.length.toLocaleString()}件
          </div>
        </div>

        {/* 店舗リスト */}
        <div style={{ background: C.white }}>
          {filtered.length === 0 && stores.length > 0 && (
            <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
              <div style={{ fontSize: 36, marginBottom: 10 }}>🔍</div>
              <div>該当するホールが見つかりません</div>
            </div>
          )}
          {filtered.length === 0 && stores.length === 0 && (
            <div style={{ textAlign: "center", padding: "60px 0", color: C.muted, fontSize: 13 }}>
              読み込み中...
            </div>
          )}
          {filtered.map(store => (
            <StoreCard key={store.id} store={store} />
          ))}
        </div>

      </div>

      <footer style={{
        textAlign: "center", padding: "16px",
        borderTop: `1px solid ${C.border}`,
        background: C.white, color: C.muted, fontSize: 11,
      }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
