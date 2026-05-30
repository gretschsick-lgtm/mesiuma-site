"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

type Ev = {
  id: number; date: string; store: string; pref: string;
  area: string; event: string; detail: string; cast?: string;
  x_url?: string; image_url?: string;
};

const AREA_ORDER = ["関東","関西","東海","九州","東北","北海道","中国・四国"];
const CAST_NG    = ["ご来店の際","場合があります","この条件","絞り込む","注意ください"];
const STORE_NG   = ["この条件","絞り込む","通常稼働","景品入荷"];
const DATE_RE    = /^\d{4}\/\d{2}\/\d{2}/;
const DOW = ["日","月","火","水","木","金","土"];

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  green: "#00aa55", green2: "#008844",
  text: "#222222", sub: "#555555", muted: "#888888", dim: "#cccccc",
};

function normalizePref(p: string): string {
  if (!p) return p;
  if (/[都道府県]$/.test(p)) return p;
  const MAP: Record<string,string> = {
    "北海道":"北海道","東京":"東京都","大阪":"大阪府","京都":"京都府",
  };
  return MAP[p] ?? p + "県";
}

function cleanCast(cast?: string) {
  if (!cast) return "";
  if (CAST_NG.some(w => cast.includes(w))) return "";
  return cast.replace(/来店.*$/, "").replace(/^.*(演者|ライター|出演)\s*/, "").trim();
}

function isValidStore(store: string) {
  return !STORE_NG.some(w => store.includes(w)) && !DATE_RE.test(store) && store.length > 1;
}

function isRaiten(ev: Ev) {
  return (ev.event || "").includes("来店") || (ev.cast || "").includes("来店");
}

function dateFmt(mmdd: string) {
  const [mm, dd] = mmdd.split("/");
  if (!mm || !dd) return mmdd;
  const d = new Date(new Date().getFullYear(), Number(mm) - 1, Number(dd));
  const dow = DOW[d.getDay()];
  const isWeekend = d.getDay() === 0 || d.getDay() === 6;
  return (
    <span style={{
      background: C.green, color: "#fff",
      fontSize: 12, fontWeight: 800, padding: "3px 10px",
      borderRadius: 4, display: "inline-flex", alignItems: "center", gap: 4,
    }}>
      {mm}/{dd}
      <span style={{ opacity: isWeekend ? 1 : 0.85, fontWeight: 700 }}>（{dow}）</span>
    </span>
  );
}

export default function RaitenPage() {
  const [events, setEvents] = useState<Ev[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [search, setSearch] = useState("");
  const [area, setArea] = useState("全て");
  const [pref, setPref] = useState("全て");
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
  const [calYear, setCalYear] = useState(() => new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(() => new Date().getMonth());
  const [calDay, setCalDay] = useState<string | null>(null);
  const [selectedEv, setSelectedEv] = useState<Ev | null>(null);

  useEffect(() => {
    fetch("/events_public.json").then(r => r.json()).then(d => {
      const evs: Ev[] = (d.events || []).map((ev: Ev) => ({ ...ev, pref: normalizePref(ev.pref) }));
      setEvents(evs.filter(isRaiten));
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, []);

  const todayStr = useMemo(() => {
    const n = new Date();
    return `${String(n.getMonth()+1).padStart(2,"0")}/${String(n.getDate()).padStart(2,"0")}`;
  }, []);

  const areas = useMemo(() => {
    const s = new Set(events.filter(e => isValidStore(e.store)).map(e => e.area || "その他"));
    return ["全て", ...AREA_ORDER.filter(a => s.has(a)), ...Array.from(s).filter(a => !AREA_ORDER.includes(a))];
  }, [events]);

  const prefs = useMemo(() => {
    const s = new Set(
      events.filter(e => isValidStore(e.store) && (area === "全て" || e.area === area))
            .map(e => e.pref).filter(Boolean)
    );
    return ["全て", ...Array.from(s).sort()];
  }, [events, area]);

  const grouped = useMemo(() => {
    const q = search.toLowerCase();
    const filtered = events.filter(ev => {
      if (!isValidStore(ev.store)) return false;
      if (!ev.date || ev.date < todayStr) return false;
      if (area !== "全て" && ev.area !== area) return false;
      if (pref !== "全て" && ev.pref !== pref) return false;
      if (q && ![ev.store, ev.pref, ev.area, ev.cast, ev.event, ev.detail].some(f => f?.toLowerCase().includes(q))) return false;
      return true;
    });
    const map = new Map<string, Ev[]>();
    filtered.forEach(ev => {
      const d = ev.date || "日付不明";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(ev);
    });
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [events, search, area, pref, todayStr]);

  const total = grouped.reduce((n, [, evs]) => n + evs.length, 0);

  const renderCard = (ev: Ev) => {
    const cast = cleanCast(ev.cast);
    return (
      <div key={ev.id} onClick={() => setSelectedEv(ev)} style={{
        background: "#f0fff8", border: `1px solid ${C.green}44`,
        borderLeft: `4px solid ${C.green}`,
        borderRadius: 6, padding: "14px 14px 14px 16px",
        display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer",
        transition: "box-shadow .15s",
      }}
        onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = `0 2px 12px ${C.green}33`; }}
        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
      >
        <div style={{
          width: 52, minWidth: 52, height: 52, borderRadius: 6,
          background: C.green + "22", border: `1px solid ${C.green}44`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 22, flexShrink: 0,
        }}>🎤</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center", marginBottom: 5 }}>
            {ev.date && dateFmt(ev.date)}
            <span style={{ background: C.green, color: "#fff", fontSize: 11, fontWeight: 800, padding: "3px 9px", borderRadius: 3 }}>来店演者</span>
            {ev.pref && <span style={{ color: C.muted, fontSize: 11 }}>{ev.pref}</span>}
          </div>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 4, lineHeight: 1.3 }}>{ev.store}</div>
          <div style={{ fontSize: 12, color: C.green, fontWeight: 700, marginBottom: cast ? 5 : 0 }}>
            {ev.event}
            {ev.detail && ev.detail !== ev.event && (
              <span style={{ color: C.muted, fontWeight: 400, marginLeft: 6 }}>{ev.detail}</span>
            )}
          </div>
          {cast && (
            <span style={{
              display: "inline-block",
              background: C.green + "14", border: `1px solid ${C.green}44`,
              color: C.green, fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 999,
            }}>👤 {cast}</span>
          )}
        </div>

        {ev.x_url && (
          <div onClick={e => e.stopPropagation()}>
            <a href={ev.x_url} target="_blank" rel="noopener noreferrer" style={{
              background: "#111", color: "#fff", width: 36, height: 32,
              display: "flex", alignItems: "center", justifyContent: "center",
              borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700,
            }}>𝕏</a>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* モーダル */}
      {selectedEv && (() => {
        const ev = selectedEv;
        const cast = cleanCast(ev.cast);
        const mapQ = encodeURIComponent(`${ev.store} ${ev.pref || ""}`);
        const embedSrc = `https://maps.google.com/maps?q=${mapQ}&output=embed&hl=ja&z=16`;
        return (
          <div onClick={() => setSelectedEv(null)} style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,.6)", backdropFilter: "blur(3px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
          }}>
            <div onClick={e => e.stopPropagation()} style={{
              background: C.white, border: `2px solid ${C.green}`,
              borderRadius: 12, maxWidth: 520, width: "100%",
              maxHeight: "90vh", overflowY: "auto",
              boxShadow: "0 8px 40px rgba(0,0,0,.25)",
            }}>
              <div style={{ width: "100%", height: 200, borderRadius: "10px 10px 0 0", overflow: "hidden" }}>
                <iframe src={embedSrc} width="100%" height="200"
                  style={{ border: 0, display: "block" }} allowFullScreen loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade" />
              </div>
              <div style={{ padding: "18px 20px 22px" }}>
                <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 12 }}>
                  {ev.date && dateFmt(ev.date)}
                  <span style={{ background: C.green, color: "#fff", fontWeight: 800, fontSize: 12, padding: "3px 10px", borderRadius: 3 }}>来店演者</span>
                  {ev.pref && (
                    <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 3, border: `1px solid ${C.border}` }}>
                      {ev.pref}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 22, fontWeight: 900, color: C.text, marginBottom: 4, lineHeight: 1.25 }}>{ev.store}</div>
                {ev.area && <div style={{ color: C.muted, fontSize: 12, marginBottom: 14 }}>{ev.area}</div>}
                {cast && (
                  <div style={{
                    background: C.green + "10", border: `1px solid ${C.green}33`,
                    borderRadius: 8, padding: "10px 14px", marginBottom: 14,
                  }}>
                    <div style={{ color: C.muted, fontSize: 10, marginBottom: 3 }}>来店演者</div>
                    <div style={{ color: C.green, fontWeight: 900, fontSize: 15 }}>👤 {cast}</div>
                  </div>
                )}
                {ev.detail && ev.detail !== ev.event && (
                  <div style={{ background: "#f8f8f8", borderRadius: 6, padding: "12px", fontSize: 12, color: C.sub, lineHeight: 1.7, marginBottom: 14, border: `1px solid ${C.border}` }}>
                    {ev.detail}
                  </div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <a href={`https://www.google.co.jp/maps/search/${mapQ}`} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                      background: "#e8f5ee", color: "#22aa55", border: "1px solid #aaddbb",
                      padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                    📍 Googleマップで探す
                  </a>
                  {ev.x_url && (
                    <a href={ev.x_url} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                        background: "#111", color: "#fff", border: "1px solid #333",
                        padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                      𝕏 ツイートを見る
                    </a>
                  )}
                </div>
                <button onClick={() => setSelectedEv(null)} style={{
                  marginTop: 12, width: "100%", background: "#f5f5f5",
                  border: `1px solid ${C.border}`, color: C.muted,
                  padding: "9px", borderRadius: 6, cursor: "pointer", fontSize: 12,
                }}>閉じる</button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ヘッダー */}
      <header style={{ position: "sticky", top: 0, zIndex: 200, background: C.white, borderBottom: `3px solid ${C.green}`, boxShadow: "0 2px 8px rgba(0,0,0,.08)" }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", height: 52, gap: 16 }}>
          <Link href="/" style={{ color: C.muted, textDecoration: "none", fontSize: 13 }}>← トップ</Link>
          <span style={{ color: C.border }}>|</span>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 4, height: 18, background: C.green, borderRadius: 2 }} />
            <span style={{ fontSize: 16, fontWeight: 900, color: C.text }}>来店カレンダー</span>
          </div>
          <Link href="/cast" style={{ marginLeft: "auto", background: C.green, color: "#fff", fontSize: 12, fontWeight: 700, padding: "5px 14px", borderRadius: 5, textDecoration: "none", whiteSpace: "nowrap" }}>
            👤 社員・演者一覧
          </Link>
        </div>
      </header>

      {/* サブヘッダー */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "18px 16px 16px" }}>
          <div style={{ background: `linear-gradient(135deg, ${C.green2} 0%, ${C.green} 100%)`, borderRadius: 8, padding: "14px 20px", display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 32 }}>📅</span>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 900, color: "#fff", margin: 0 }}>来店カレンダー</h1>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,.85)", margin: "3px 0 0" }}>演者・社員の来店イベントをカレンダーと一覧で確認</p>
            </div>
          </div>

          {/* 検索バー */}
          <div style={{ display: "flex", gap: 8, maxWidth: 600, marginTop: 14 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: C.muted, fontSize: 16, pointerEvents: "none" }}>🔍</span>
              <input
                value={search}
                onChange={e => { setSearch(e.target.value); setCalDay(null); }}
                placeholder="店舗名・地域・演者名で検索"
                style={{
                  width: "100%", padding: "10px 14px 10px 38px",
                  background: "#fff", border: `1px solid ${C.border}`,
                  borderRadius: 4, color: C.text, fontSize: 14,
                  outline: "none", boxSizing: "border-box",
                }}
                onFocus={e => (e.target.style.borderColor = C.green)}
                onBlur={e => (e.target.style.borderColor = C.border)}
              />
            </div>
          </div>

          {loaded && (
            <div style={{ marginTop: 8, fontSize: 12, color: C.muted }}>
              <span style={{ color: C.green, fontWeight: 700 }}>{total}</span>件の来店イベント
            </div>
          )}
        </div>
      </div>

      {/* メインコンテンツ */}
      <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px 80px" }}>

        {/* フィルターバー */}
        <div style={{ background: C.white, borderRadius: 6, border: `1px solid ${C.border}`, padding: "14px 16px", marginTop: 16, marginBottom: 4 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2, whiteSpace: "nowrap" }}>エリア</span>
            {areas.map(a => (
              <button key={a} onClick={() => { setArea(a); setPref("全て"); }} style={{
                background: area === a ? C.green : "#f5f5f5",
                border: `1px solid ${area === a ? C.green : C.border}`,
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
                  background: pref === p ? "#f0fff8" : "#f5f5f5",
                  border: `1px solid ${pref === p ? C.green : C.border}`,
                  color: pref === p ? C.green : C.sub,
                  fontSize: 11, fontWeight: 700, padding: "4px 11px",
                  borderRadius: 999, cursor: "pointer",
                }}>{p}</button>
              ))}
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginTop: 8 }}>
            {(["list", "calendar"] as const).map(m => (
              <button key={m} onClick={() => { setViewMode(m); setCalDay(null); }} style={{
                background: viewMode === m ? C.green : "#f5f5f5",
                border: `1px solid ${viewMode === m ? C.green : C.border}`,
                color: viewMode === m ? "#fff" : C.muted,
                fontSize: 12, fontWeight: 700, padding: "5px 12px",
                borderRadius: 4, cursor: "pointer",
              }}>
                {m === "list" ? "☰ リスト" : "📅 カレンダー"}
              </button>
            ))}
          </div>
        </div>

        {!loaded && <div style={{ color: C.dim, padding: 60, textAlign: "center" }}>読み込み中...</div>}
        {loaded && grouped.length === 0 && (
          <div style={{ color: C.muted, padding: 60, textAlign: "center" }}>該当する来店イベントがありません</div>
        )}

        {/* カレンダービュー */}
        {viewMode === "calendar" && loaded && (() => {
          const yr = calYear, mo = calMonth;
          const firstDay = new Date(yr, mo, 1).getDay();
          const daysInMonth = new Date(yr, mo + 1, 0).getDate();
          const moStr = String(mo + 1).padStart(2, "0");
          const dayMap = new Map<string, Ev[]>();
          grouped.forEach(([date, evs]) => {
            const [mm, dd] = date.split("/");
            if (mm === moStr) dayMap.set(dd, evs);
          });
          const cells: (number | null)[] = [...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];
          while (cells.length % 7 !== 0) cells.push(null);

          return (
            <div style={{ marginTop: 16, background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 20, marginBottom: 16 }}>
                <button onClick={() => { const d = new Date(yr, mo - 1, 1); setCalYear(d.getFullYear()); setCalMonth(d.getMonth()); setCalDay(null); }}
                  style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.sub, width: 36, height: 36, borderRadius: 6, cursor: "pointer", fontSize: 18 }}>‹</button>
                <span style={{ color: C.text, fontWeight: 900, fontSize: 16 }}>{yr}年 {mo + 1}月</span>
                <button onClick={() => { const d = new Date(yr, mo + 1, 1); setCalYear(d.getFullYear()); setCalMonth(d.getMonth()); setCalDay(null); }}
                  style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.sub, width: 36, height: 36, borderRadius: 6, cursor: "pointer", fontSize: 18 }}>›</button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2, marginBottom: 4 }}>
                {["日", "月", "火", "水", "木", "金", "土"].map((d, i) => (
                  <div key={d} style={{ textAlign: "center", fontSize: 11, fontWeight: 700, color: i === 0 ? "#e60000" : i === 6 ? "#0066cc" : C.muted, padding: "4px 0" }}>{d}</div>
                ))}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2 }}>
                {cells.map((day, idx) => {
                  if (!day) return <div key={idx} />;
                  const dd = String(day).padStart(2, "0");
                  const dayEvs = dayMap.get(dd) || [];
                  const isSelected = calDay === dd;
                  const today = new Date();
                  const isToday = today.getFullYear() === yr && today.getMonth() === mo && today.getDate() === day;
                  return (
                    <div key={idx} onClick={() => setCalDay(isSelected ? null : dd)} style={{
                      background: isSelected ? "#f0fff8" : C.white,
                      border: `1px solid ${isSelected ? C.green : C.border}`,
                      borderRadius: 4, padding: "6px 4px 4px", textAlign: "center",
                      cursor: dayEvs.length ? "pointer" : "default", minHeight: 50,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: isToday ? 900 : 500, color: isToday ? C.green : idx % 7 === 0 ? "#e60000" : idx % 7 === 6 ? "#0066cc" : C.text, marginBottom: 3 }}>{day}</div>
                      {dayEvs.length > 0 && (
                        <>
                          <div style={{ display: "flex", gap: 2, justifyContent: "center", marginBottom: 2 }}>
                            <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
                          </div>
                          <div style={{ fontSize: 9, color: C.green, fontWeight: 700 }}>{dayEvs.length}</div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
              {calDay && (() => {
                const dayEvs = dayMap.get(calDay) || [];
                return (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, paddingBottom: 10, borderBottom: `1px solid ${C.border}` }}>
                      {dateFmt(`${moStr}/${calDay}`)}
                      <span style={{ color: C.muted, fontSize: 12 }}>{dayEvs.length}件</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {dayEvs.map(ev => renderCard(ev))}
                    </div>
                  </div>
                );
              })()}
            </div>
          );
        })()}

        {/* リストビュー */}
        {viewMode === "list" && grouped.map(([date, evs]) => (
          <div key={date} style={{ marginTop: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10, paddingBottom: 8, borderBottom: `2px solid ${C.green}` }}>
              {dateFmt(date)}
              <span style={{ color: C.muted, fontSize: 12 }}>{evs.length}件</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {evs.map(ev => renderCard(ev))}
            </div>
          </div>
        ))}
      </div>

      <footer style={{ textAlign: "center", padding: "24px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
