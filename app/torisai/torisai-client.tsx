"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

type Ev = {
  id: number;
  date: string;
  store: string;
  pref: string;
  area: string;
  event: string;
  detail: string;
  cast?: string;
  x_url?: string;
  image_url?: string;
};

const AREA_ORDER = ["関東","関西","東海","九州","東北","北海道","中国・四国"];
const STORE_NG   = ["この条件","絞り込む","通常稼働","景品入荷"];
const DATE_RE    = /^\d{4}\/\d{2}\/\d{2}/;
const CAST_NG    = ["ご来店の際","場合があります","この条件","絞り込む","注意ください"];

const PREF_SUFFIX: Record<string, string> = {
  "北海道":"北海道","東京":"東京都","大阪":"大阪府","京都":"京都府",
  "北海道道":"北海道","東京都":"東京都","大阪府":"大阪府","京都府":"京都府",
};
function normalizePref(p: string): string {
  if (!p) return p;
  if (PREF_SUFFIX[p]) return PREF_SUFFIX[p];
  if (/[都道府県]$/.test(p)) return p;
  return p + "県";
}
function cleanCast(cast?: string) {
  if (!cast) return "";
  if (CAST_NG.some(w => cast.includes(w))) return "";
  return cast.replace(/来店.*$/, "").replace(/^.*(演者|ライター|出演)\s*/, "").trim();
}
function isValidStore(store: string) {
  if (STORE_NG.some(w => store.includes(w))) return false;
  if (DATE_RE.test(store)) return false;
  return store.length > 1;
}

const STORE_URLS: Record<string, { x?: string; hp?: string }> = {
  "スロパチステーション":   { x:"https://x.com/slopachi_st",  hp:"https://slopachi.com" },
  "ぱちタウンコレクション": { x:"https://x.com/pachitown" },
  "パチ＆スロ必勝本":       { x:"https://x.com/hisshobon",    hp:"https://hisshobon.jp" },
  "スロセレ":               { x:"https://x.com/srocele" },
  "フェスメディアX":        { x:"https://x.com/fes_media" },
  "1GAME":                  { x:"https://x.com/1game_ch",      hp:"https://1game.jp" },
  "回胴アドベンチャー":     { x:"https://x.com/kaidou_adv" },
  "BASHtv":                 { x:"https://x.com/BASH_tv",       hp:"https://bashtv.jp" },
  "PLUS MADE":              { x:"https://x.com/plusmade_slot" },
  "デリカツ":               { x:"https://x.com/deli_katsu" },
  "エースプロ":             { x:"https://x.com/acepro_slot" },
};
function getLink(store: string) {
  for (const [k, v] of Object.entries(STORE_URLS)) if (store.includes(k)) return v;
  return {};
}

const DOW = ["日","月","火","水","木","金","土"];
function DateBadge({ mmdd }: { mmdd: string }) {
  const [mm, dd] = mmdd.split("/");
  if (!mm || !dd) return <span>{mmdd}</span>;
  const now = new Date();
  const d = new Date(now.getFullYear(), Number(mm) - 1, Number(dd));
  const dow = DOW[d.getDay()];
  const isWeekend = d.getDay() === 0 || d.getDay() === 6;
  return (
    <span style={{
      background: "#0066cc", color: "#fff",
      fontSize: 12, fontWeight: 800, padding: "3px 10px",
      borderRadius: 4, display: "inline-flex", alignItems: "center", gap: 3,
    }}>
      {mm}/{dd}
      <span style={{ opacity: isWeekend ? 1 : 0.85, fontWeight: 700 }}>（{dow}）</span>
    </span>
  );
}

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", blue: "#0066cc", text: "#222222",
  sub: "#555555", muted: "#888888", dim: "#cccccc",
  orange: "#ff6600",
};

// 取材メディア一覧（取材元の名称を表示）
const MEDIA_LABELS: Record<string, string> = {
  "スロパチステーション": "スロパチST",
  "パチ＆スロ必勝本": "必勝本",
  "スロセレ": "スロセレ",
  "フェスメディアX": "フェスメディア",
  "1GAME": "1GAME",
  "回胴アドベンチャー": "回胴ADV",
  "BASHtv": "BASHtv",
  "PLUS MADE": "PLUS MADE",
  "デリカツ": "デリカツ",
  "エースプロ": "エースプロ",
  "ぱちタウンコレクション": "ぱちタウン",
};
function getMediaLabel(store: string): string {
  for (const [k, v] of Object.entries(MEDIA_LABELS)) {
    if (store.includes(k)) return v;
  }
  return store;
}

export default function TorisaiPage() {
  const [events, setEvents]   = useState<Ev[]>([]);
  const [storeHp, setStoreHp] = useState<Record<string,string>>({});
  const [loaded, setLoaded]   = useState(false);
  const [search, setSearch]   = useState("");
  const [area, setArea]       = useState("全て");
  const [pref, setPref]       = useState("全て");
  const [selectedEv, setSelectedEv] = useState<Ev | null>(null);

  useEffect(() => {
    fetch("/events_public.json").then(r=>r.json()).then(d=>{
      const evs: Ev[] = (d.events || []).map((ev: Ev) => ({ ...ev, pref: normalizePref(ev.pref) }));
      // 取材・調査員イベントのみ
      const torisai = evs.filter(ev => {
        if (!isValidStore(ev.store)) return false;
        const e = ev.event || "";
        return e.includes("取材") || e.includes("調査員") || e.includes("メディア");
      });
      setEvents(torisai);
      setLoaded(true);
    }).catch(()=>setLoaded(true));
    fetch("/store_hp.json").then(r=>r.json()).then(setStoreHp).catch(()=>{});
  }, []);

  const areas = useMemo(() => {
    const s = new Set(events.map(e=>e.area||"その他").filter(Boolean));
    return ["全て",...AREA_ORDER.filter(a=>s.has(a)),...Array.from(s).filter(a=>!AREA_ORDER.includes(a))];
  }, [events]);

  const prefs = useMemo(() => {
    const s = new Set(
      events.filter(e=>area==="全て"||e.area===area).map(e=>e.pref).filter(Boolean)
    );
    return ["全て",...Array.from(s).sort()];
  }, [events, area]);

  const todayStr = useMemo(() => {
    const now = new Date();
    return `${String(now.getMonth()+1).padStart(2,"0")}/${String(now.getDate()).padStart(2,"0")}`;
  }, []);

  const grouped = useMemo(() => {
    const s = search.toLowerCase();
    const filtered = events.filter(ev => {
      if (!ev.date || ev.date < todayStr) return false;
      if (area !== "全て" && ev.area !== area) return false;
      if (pref !== "全て" && ev.pref !== pref) return false;
      if (s && ![ev.store,ev.pref,ev.event,ev.cast,ev.detail].some(f=>f?.toLowerCase().includes(s))) return false;
      return true;
    });
    const map = new Map<string, Ev[]>();
    filtered.forEach(ev => {
      const d = ev.date || "日付不明";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(ev);
    });
    return Array.from(map.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
  }, [events, search, area, pref]);

  const totalFiltered = grouped.reduce((n,[,evs])=>n+evs.length, 0);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* モーダル */}
      {selectedEv && (() => {
        const ev = selectedEv;
        const cast = cleanCast(ev.cast);
        const link = getLink(ev.store);
        const hp = link.hp || storeHp[ev.store] || "";
        const mapQ = encodeURIComponent(`${ev.store} ${ev.pref || ""}`);
        const embedSrc = `https://maps.google.com/maps?q=${mapQ}&output=embed&hl=ja&z=16`;
        return (
          <div onClick={() => setSelectedEv(null)} style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,.6)", backdropFilter: "blur(3px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
          }}>
            <div onClick={e => e.stopPropagation()} style={{
              background: C.white, borderRadius: 12, maxWidth: 520, width: "100%",
              maxHeight: "90vh", overflowY: "auto", boxShadow: "0 8px 40px rgba(0,0,0,.25)",
              border: `2px solid ${C.blue}`,
            }}>
              <div style={{ width: "100%", height: 200, borderRadius: "10px 10px 0 0", overflow: "hidden" }}>
                <iframe src={embedSrc} width="100%" height="200" style={{ border: 0, display: "block" }} allowFullScreen loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
              </div>
              <div style={{ padding: "18px 20px 22px" }}>
                <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 12 }}>
                  {ev.date && <DateBadge mmdd={ev.date} />}
                  <span style={{ background: "#e8f0ff", color: C.blue, fontWeight: 800, fontSize: 12, padding: "3px 10px", borderRadius: 3, border: `1px solid #aaccff` }}>📡 取材</span>
                  {ev.pref && <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 12, padding: "3px 10px", borderRadius: 3, border: `1px solid ${C.border}` }}>{ev.pref}</span>}
                </div>
                <div style={{ fontSize: 20, fontWeight: 900, color: C.text, marginBottom: 4 }}>{ev.store}</div>
                {ev.area && <div style={{ color: C.muted, fontSize: 12, marginBottom: 12 }}>{ev.area}</div>}
                <div style={{ fontSize: 13, color: C.blue, fontWeight: 700, marginBottom: cast ? 12 : 0 }}>{ev.event}</div>
                {cast && (
                  <div style={{ background: "#e8f0ff", border: "1px solid #aaccff", borderRadius: 8, padding: "10px 14px", marginBottom: 14 }}>
                    <div style={{ color: C.muted, fontSize: 10, marginBottom: 3 }}>出演メディア/担当者</div>
                    <div style={{ color: C.blue, fontWeight: 900, fontSize: 15 }}>📡 {cast}</div>
                  </div>
                )}
                {ev.detail && ev.detail !== ev.event && (
                  <div style={{ background: "#f8f8f8", borderRadius: 6, padding: "12px", fontSize: 12, color: C.sub, lineHeight: 1.7, marginBottom: 14, border: `1px solid ${C.border}` }}>
                    {ev.detail}
                  </div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <a href={`https://www.google.co.jp/maps/search/${mapQ}`} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#e8f5ee", color: "#22aa55", border: "1px solid #aaddbb", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                    📍 Googleマップで探す
                  </a>
                  {(ev.x_url || link.x) && (
                    <a href={ev.x_url || link.x} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#111", color: "#fff", border: "1px solid #333", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                      𝕏 {ev.x_url ? "ツイートを見る" : "X公式アカウント"}
                    </a>
                  )}
                  {hp && (
                    <a href={hp} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#f0f4ff", color: C.blue, border: "1px solid #aaccff", padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                      🌐 ホール公式サイト
                    </a>
                  )}
                </div>
                <button onClick={() => setSelectedEv(null)} style={{ marginTop: 12, width: "100%", background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.muted, padding: "9px", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>閉じる</button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ヘッダー */}
      <header style={{ position: "sticky", top: 0, zIndex: 200, background: C.white, borderBottom: `3px solid ${C.blue}`, boxShadow: "0 2px 8px rgba(0,0,0,.08)" }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", height: 52, gap: 16 }}>
          <Link href="/" style={{ color: C.muted, textDecoration: "none", fontSize: 13, whiteSpace: "nowrap" }}>
            ← トップ
          </Link>
          <span style={{ color: C.border }}>|</span>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 4, height: 18, background: C.blue, borderRadius: 2 }} />
            <span style={{ fontSize: 16, fontWeight: 900, color: C.text }}>店舗取材一覧</span>
          </div>
          <div style={{ marginLeft: "auto", fontSize: 12, color: C.muted }}>
            {loaded && <><span style={{ color: C.blue, fontWeight: 700 }}>{totalFiltered}</span>件</>}
          </div>
        </div>
      </header>

      {/* サブヘッダー */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "18px 16px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <span style={{ fontSize: 32 }}>📡</span>
            <div>
              <h1 style={{ fontSize: 20, fontWeight: 900, color: C.text, margin: 0 }}>店舗取材一覧</h1>
              <p style={{ fontSize: 12, color: C.muted, margin: "3px 0 0" }}>メディアによる店舗取材・調査員訪問イベントをまとめて確認</p>
            </div>
          </div>

          {/* 検索 */}
          <div style={{ display: "flex", gap: 8, maxWidth: 500, marginBottom: 12 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: C.muted, fontSize: 15, pointerEvents: "none" }}>🔍</span>
              <input
                value={search} onChange={e => setSearch(e.target.value)}
                placeholder="店舗名・エリア・メディア名で検索"
                style={{ width: "100%", padding: "10px 14px 10px 36px", background: "#fff", border: `1px solid ${C.border}`, borderRadius: 4, color: C.text, fontSize: 14, outline: "none", boxSizing: "border-box", transition: "border-color .2s" }}
                onFocus={e => (e.target.style.borderColor = C.blue)}
                onBlur={e => (e.target.style.borderColor = C.border)}
              />
            </div>
            <button style={{ background: C.blue, color: "#fff", padding: "0 18px", border: "none", borderRadius: 4, fontSize: 14, fontWeight: 700, cursor: "pointer" }}>検索</button>
          </div>
        </div>
      </div>

      {/* メイン */}
      <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px 80px" }}>

        {/* フィルター */}
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 6, padding: "12px 14px", marginTop: 16, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2 }}>エリア</span>
            {areas.map(a => (
              <button key={a} onClick={() => { setArea(a); setPref("全て"); }} style={{
                background: area === a ? C.blue : "#f5f5f5",
                border: `1px solid ${area === a ? C.blue : C.border}`,
                color: area === a ? "#fff" : C.sub,
                fontSize: 12, fontWeight: 700, padding: "5px 14px",
                borderRadius: 999, cursor: "pointer", transition: "all .15s",
              }}>{a}</button>
            ))}
          </div>
          {prefs.length > 2 && (
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center", borderTop: `1px solid ${C.border}`, paddingTop: 8 }}>
              <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2 }}>📍</span>
              {prefs.map(p => (
                <button key={p} onClick={() => setPref(p)} style={{
                  background: pref === p ? "#e8f0ff" : "#f5f5f5",
                  border: `1px solid ${pref === p ? C.blue : C.border}`,
                  color: pref === p ? C.blue : C.sub,
                  fontSize: 11, fontWeight: 700, padding: "4px 11px",
                  borderRadius: 999, cursor: "pointer", transition: "all .15s",
                }}>{p}</button>
              ))}
            </div>
          )}
        </div>

        {!loaded && <div style={{ color: C.muted, padding: 60, textAlign: "center" }}>読み込み中...</div>}
        {loaded && grouped.length === 0 && (
          <div style={{ background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: "60px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📡</div>
            <div style={{ color: C.muted, fontSize: 14 }}>該当する取材情報がありません</div>
          </div>
        )}

        {/* 日付ごとリスト */}
        {grouped.map(([date, evs]) => (
          <div key={date} style={{ marginTop: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, paddingBottom: 8, borderBottom: `2px solid ${C.blue}` }}>
              <DateBadge mmdd={date} />
              <span style={{ color: C.muted, fontSize: 12 }}>{evs.length}件</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {evs.map(ev => {
                const link = getLink(ev.store);
                const cast = cleanCast(ev.cast);
                const cardHp = link.hp || storeHp[ev.store] || "";
                return (
                  <div key={ev.id} onClick={() => setSelectedEv(ev)} style={{
                    background: "#f0f5ff",
                    border: "1px solid #aaccff",
                    borderLeft: `4px solid ${C.blue}`,
                    borderRadius: 6, padding: "14px 14px 14px 16px",
                    display: "flex", alignItems: "flex-start", gap: 12,
                    cursor: "pointer", transition: "box-shadow .15s",
                  }}
                    onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 12px rgba(0,102,204,.2)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
                  >
                    {/* アイコン */}
                    <div style={{ width: 48, minWidth: 48, height: 48, borderRadius: 6, background: "#c8deff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, flexShrink: 0 }}>
                      📡
                    </div>

                    {/* 情報 */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center", marginBottom: 5 }}>
                        <span style={{ background: C.blue, color: "#fff", fontSize: 11, fontWeight: 800, padding: "2px 9px", borderRadius: 3 }}>取材</span>
                        {ev.pref && <span style={{ color: C.muted, fontSize: 11 }}>{ev.pref}</span>}
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 3, lineHeight: 1.3 }}>{ev.store}</div>
                      <div style={{ fontSize: 12, color: C.blue, fontWeight: 700, marginBottom: cast ? 5 : 0 }}>{ev.event}</div>
                      {cast && (
                        <span style={{ display: "inline-block", background: "#d0e4ff", border: "1px solid #aaccff", color: C.blue, fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 999 }}>
                          📡 {cast}
                        </span>
                      )}
                    </div>

                    {/* リンク */}
                    {(ev.x_url || link.x || cardHp) && (
                      <div onClick={e => e.stopPropagation()} style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0 }}>
                        {(ev.x_url || link.x) && (
                          <a href={ev.x_url || link.x} target="_blank" rel="noopener noreferrer"
                            style={{ background: "#111", color: "#fff", width: 36, height: 32, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700 }}>𝕏</a>
                        )}
                        {cardHp && (
                          <a href={cardHp} target="_blank" rel="noopener noreferrer"
                            style={{ background: "#f0f4ff", border: "1px solid #aaccff", color: C.blue, width: 36, height: 32, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 5, textDecoration: "none", fontSize: 10, fontWeight: 700 }}>HP</a>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* フッター */}
      <footer style={{ textAlign: "center", padding: "24px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社 — メシマズなくしてメシウマなし
      </footer>
    </div>
  );
}
