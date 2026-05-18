"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

// meshimazu_stores.json の型
// 追加する際はこの形式でstoresに追加してください
type Store = {
  id: string;
  name: string;          // 店舗名
  pref: string;          // 都道府県（例: "東京都"）
  area: string;          // エリア（例: "関東"）
  date: string;          // 取材日（例: "05/18"）
  detail: string;        // 取材内容・コメント
  result?: string;       // 結果・一言（例: "3万負け", "完封負け"）
  youtube_url?: string;  // YouTube動画URL
  x_url?: string;        // Xポスト URL
  image_url?: string;    // 画像URL
  machines?: string[];   // 打った機種
};

const AREA_ORDER = ["関東","関西","東海","九州","東北","北海道","中国・四国"];

const DOW = ["日","月","火","水","木","金","土"];
function DateBadge({ mmdd }: { mmdd: string }) {
  const [mm, dd] = mmdd.split("/");
  if (!mm || !dd) return <span style={{ background: "#e60000", color: "#fff", fontSize: 12, fontWeight: 800, padding: "3px 10px", borderRadius: 4 }}>{mmdd}</span>;
  const now = new Date();
  const d = new Date(now.getFullYear(), Number(mm) - 1, Number(dd));
  const dow = DOW[d.getDay()];
  return (
    <span style={{ background: "#e60000", color: "#fff", fontSize: 12, fontWeight: 800, padding: "3px 10px", borderRadius: 4, display: "inline-flex", alignItems: "center", gap: 3 }}>
      {mm}/{dd}（{dow}）
    </span>
  );
}

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", red2: "#cc0000", text: "#222222",
  sub: "#555555", muted: "#888888", dim: "#cccccc",
};

export default function MeshimazuPage() {
  const [stores, setStores]   = useState<Store[]>([]);
  const [updated, setUpdated] = useState("");
  const [loaded, setLoaded]   = useState(false);
  const [search, setSearch]   = useState("");
  const [area, setArea]       = useState("全て");
  const [selected, setSelected] = useState<Store | null>(null);

  useEffect(() => {
    fetch("/meshimazu_stores.json")
      .then(r => r.json())
      .then(d => {
        setStores(d.stores || []);
        setUpdated(d.updated || "");
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const areas = useMemo(() => {
    const s = new Set(stores.map(e => e.area).filter(Boolean));
    return ["全て", ...AREA_ORDER.filter(a => s.has(a)), ...Array.from(s).filter(a => !AREA_ORDER.includes(a))];
  }, [stores]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return stores.filter(st => {
      if (area !== "全て" && st.area !== area) return false;
      if (s && ![st.name, st.pref, st.detail, st.result, ...(st.machines||[])].some(f => f?.toLowerCase().includes(s))) return false;
      return true;
    });
  }, [stores, search, area]);

  // 日付でグループ化
  const grouped = useMemo(() => {
    const map = new Map<string, Store[]>();
    filtered.forEach(st => {
      const d = st.date || "日付不明";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(st);
    });
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0])); // 新しい順
  }, [filtered]);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* 詳細モーダル */}
      {selected && (
        <div onClick={() => setSelected(null)} style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,.6)", backdropFilter: "blur(3px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: C.white, borderRadius: 12, maxWidth: 520, width: "100%",
            maxHeight: "90vh", overflowY: "auto", boxShadow: "0 8px 40px rgba(0,0,0,.25)",
            border: `2px solid ${C.red}`,
          }}>
            {/* 画像 */}
            {selected.image_url && (
              <div style={{ width: "100%", aspectRatio: "16/9", overflow: "hidden", borderRadius: "10px 10px 0 0" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={selected.image_url} alt={selected.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              </div>
            )}
            <div style={{ padding: "20px 22px 24px" }}>
              <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 12 }}>
                {selected.date && <DateBadge mmdd={selected.date} />}
                <span style={{ background: "#fff0f0", color: C.red, fontWeight: 800, fontSize: 12, padding: "3px 10px", borderRadius: 3, border: `1px solid #ffaaaa` }}>
                  😱 メシマズ取材
                </span>
                {selected.pref && <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 12, padding: "3px 10px", borderRadius: 3, border: `1px solid ${C.border}` }}>{selected.pref}</span>}
              </div>

              <div style={{ fontSize: 22, fontWeight: 900, color: C.text, marginBottom: 4 }}>{selected.name}</div>
              {selected.area && <div style={{ color: C.muted, fontSize: 12, marginBottom: 14 }}>{selected.area}</div>}

              {selected.result && (
                <div style={{ background: "#fff0f0", border: "1px solid #ffaaaa", borderRadius: 8, padding: "12px 16px", marginBottom: 14 }}>
                  <div style={{ color: C.muted, fontSize: 10, marginBottom: 4 }}>取材結果</div>
                  <div style={{ color: C.red, fontWeight: 900, fontSize: 18 }}>😱 {selected.result}</div>
                </div>
              )}

              {selected.detail && (
                <div style={{ background: "#f8f8f8", border: `1px solid ${C.border}`, borderRadius: 6, padding: "14px", fontSize: 13, color: C.sub, lineHeight: 1.8, marginBottom: 14, whiteSpace: "pre-wrap" }}>
                  {selected.detail}
                </div>
              )}

              {selected.machines && selected.machines.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginBottom: 6 }}>打った機種</div>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {selected.machines.map(m => (
                      <span key={m} style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.sub, fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 4 }}>
                        🎰 {m}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {selected.youtube_url && (
                  <a href={selected.youtube_url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#cc0000", color: "#fff", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                    ▶ YouTube動画を見る
                  </a>
                )}
                {selected.x_url && (
                  <a href={selected.x_url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#111", color: "#fff", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                    𝕏 ポストを見る
                  </a>
                )}
                <a href={`https://www.google.co.jp/maps/search/${encodeURIComponent(selected.name + " " + (selected.pref||""))}`}
                  target="_blank" rel="noopener noreferrer"
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#e8f5ee", color: "#22aa55", border: "1px solid #aaddbb", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                  📍 Googleマップで探す
                </a>
              </div>

              <button onClick={() => setSelected(null)} style={{ marginTop: 12, width: "100%", background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.muted, padding: "9px", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>閉じる</button>
            </div>
          </div>
        </div>
      )}

      {/* ヘッダー */}
      <header style={{ position: "sticky", top: 0, zIndex: 200, background: C.white, borderBottom: `3px solid ${C.red}`, boxShadow: "0 2px 8px rgba(0,0,0,.08)" }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", height: 52, gap: 16 }}>
          <Link href="/" style={{ color: C.muted, textDecoration: "none", fontSize: 13, whiteSpace: "nowrap" }}>← トップ</Link>
          <span style={{ color: C.border }}>|</span>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 4, height: 18, background: C.red, borderRadius: 2 }} />
            <span style={{ fontSize: 16, fontWeight: 900, color: C.text }}>メシマズ店舗取材一覧</span>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            {updated && <span style={{ fontSize: 11, color: C.muted }}>更新: {updated}</span>}
            <span style={{ fontSize: 12, color: C.muted }}>
              {loaded && <><span style={{ color: C.red, fontWeight: 700 }}>{filtered.length}</span>件</>}
            </span>
          </div>
        </div>
      </header>

      {/* サブヘッダー */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "18px 16px 16px" }}>
          <div style={{
            background: "linear-gradient(135deg, #aa0000 0%, #cc0000 50%, #e60000 100%)",
            borderRadius: 8, padding: "14px 20px", marginBottom: 16,
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <span style={{ fontSize: 32 }}>😱</span>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 900, color: "#fff", margin: 0 }}>メシマズ店舗取材一覧</h1>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,.8)", margin: "3px 0 0" }}>
                メシウマ稼働株式会社が実際に取材した店舗のレポート
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, maxWidth: 500 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: C.muted, fontSize: 15, pointerEvents: "none" }}>🔍</span>
              <input
                value={search} onChange={e => setSearch(e.target.value)}
                placeholder="店舗名・エリア・機種名で検索"
                style={{ width: "100%", padding: "10px 14px 10px 36px", background: "#fff", border: `1px solid ${C.border}`, borderRadius: 4, color: C.text, fontSize: 14, outline: "none", boxSizing: "border-box", transition: "border-color .2s" }}
                onFocus={e => (e.target.style.borderColor = C.red)}
                onBlur={e => (e.target.style.borderColor = C.border)}
              />
            </div>
            <button style={{ background: C.red, color: "#fff", padding: "0 18px", border: "none", borderRadius: 4, fontSize: 14, fontWeight: 700, cursor: "pointer" }}>検索</button>
          </div>
        </div>
      </div>

      {/* メイン */}
      <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px 80px" }}>

        {/* エリアフィルター */}
        {areas.length > 1 && (
          <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 6, padding: "12px 14px", marginTop: 16, marginBottom: 16 }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2 }}>エリア</span>
              {areas.map(a => (
                <button key={a} onClick={() => setArea(a)} style={{
                  background: area === a ? C.red : "#f5f5f5",
                  border: `1px solid ${area === a ? C.red : C.border}`,
                  color: area === a ? "#fff" : C.sub,
                  fontSize: 12, fontWeight: 700, padding: "5px 14px",
                  borderRadius: 999, cursor: "pointer", transition: "all .15s",
                }}>{a}</button>
              ))}
            </div>
          </div>
        )}

        {!loaded && <div style={{ color: C.muted, padding: 60, textAlign: "center" }}>読み込み中...</div>}

        {/* 空の状態 */}
        {loaded && stores.length === 0 && (
          <div style={{ background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: "60px 20px", textAlign: "center", marginTop: 24 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>😌</div>
            <div style={{ color: C.text, fontWeight: 700, fontSize: 16, marginBottom: 8 }}>取材データ準備中</div>
            <div style={{ color: C.muted, fontSize: 13, lineHeight: 1.7 }}>
              メシウマ稼働株式会社の取材レポートをここに掲載していきます。<br />
              public/meshimazu_stores.json に店舗データを追加してください。
            </div>
          </div>
        )}

        {loaded && stores.length > 0 && filtered.length === 0 && (
          <div style={{ background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: "60px 20px", textAlign: "center", marginTop: 24 }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
            <div style={{ color: C.muted, fontSize: 14 }}>該当する店舗が見つかりません</div>
          </div>
        )}

        {/* 日付ごとリスト（新しい順） */}
        {grouped.map(([date, sts]) => (
          <div key={date} style={{ marginTop: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, paddingBottom: 8, borderBottom: `2px solid ${C.red}` }}>
              <DateBadge mmdd={date} />
              <span style={{ color: C.muted, fontSize: 12 }}>{sts.length}件</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {sts.map(st => (
                <div key={st.id} onClick={() => setSelected(st)} style={{
                  background: "#fff5f5", border: "1px solid #ffcccc",
                  borderLeft: `4px solid ${C.red}`, borderRadius: 6,
                  padding: "16px 16px 16px 18px",
                  display: "flex", alignItems: "flex-start", gap: 14,
                  cursor: "pointer", transition: "box-shadow .15s",
                }}
                  onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 14px rgba(230,0,0,.15)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
                >
                  {/* サムネ or アイコン */}
                  {st.image_url ? (
                    <div style={{ width: 80, minWidth: 80, height: 80, borderRadius: 6, overflow: "hidden", flexShrink: 0 }}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={st.image_url} alt={st.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} loading="lazy" />
                    </div>
                  ) : (
                    <div style={{ width: 52, minWidth: 52, height: 52, borderRadius: 6, background: "#ffd0d0", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, flexShrink: 0 }}>
                      😱
                    </div>
                  )}

                  <div style={{ flex: 1, minWidth: 0 }}>
                    {/* バッジ */}
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center", marginBottom: 5 }}>
                      <span style={{ background: C.red, color: "#fff", fontSize: 11, fontWeight: 800, padding: "2px 9px", borderRadius: 3 }}>メシマズ取材</span>
                      {st.pref && <span style={{ color: C.muted, fontSize: 11 }}>{st.pref}</span>}
                    </div>

                    {/* 店舗名 */}
                    <div style={{ fontSize: 17, fontWeight: 900, color: C.text, marginBottom: 4, lineHeight: 1.3 }}>{st.name}</div>

                    {/* 結果 */}
                    {st.result && (
                      <div style={{ fontSize: 13, color: C.red, fontWeight: 800, marginBottom: 4 }}>😱 {st.result}</div>
                    )}

                    {/* 詳細（2行まで） */}
                    {st.detail && (
                      <div style={{ fontSize: 12, color: C.sub, lineHeight: 1.6, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                        {st.detail}
                      </div>
                    )}

                    {/* 機種 */}
                    {st.machines && st.machines.length > 0 && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
                        {st.machines.map(m => (
                          <span key={m} style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.muted, fontSize: 10, padding: "2px 7px", borderRadius: 3 }}>🎰 {m}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* リンク */}
                  <div onClick={e => e.stopPropagation()} style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0 }}>
                    {st.youtube_url && (
                      <a href={st.youtube_url} target="_blank" rel="noopener noreferrer"
                        style={{ background: "#cc0000", color: "#fff", width: 36, height: 32, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700 }}>▶</a>
                    )}
                    {st.x_url && (
                      <a href={st.x_url} target="_blank" rel="noopener noreferrer"
                        style={{ background: "#111", color: "#fff", width: 36, height: 32, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700 }}>𝕏</a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <footer style={{ textAlign: "center", padding: "24px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社 — メシマズなくしてメシウマなし
      </footer>
    </div>
  );
}
