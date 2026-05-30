"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { MEMBERS } from "./members";

type Ev = {
  id: number; date: string; store: string; pref: string;
  event: string; detail: string; cast?: string; image_url?: string;
};

const CAST_NG  = ["ご来店の際","場合があります","この条件","絞り込む","注意ください"];
const STORE_NG = ["この条件","絞り込む","通常稼働","景品入荷"];
const DATE_RE  = /^\d{4}\/\d{2}\/\d{2}/;

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", orange: "#ff6600", text: "#222222",
  sub: "#555555", muted: "#888888", dim: "#cccccc",
};

const DOW = ["日","月","火","水","木","金","土"];

function dateFmt(mmdd: string) {
  const [mm, dd] = mmdd.split("/");
  if (!mm || !dd) return mmdd;
  const d = new Date(new Date().getFullYear(), Number(mm)-1, Number(dd));
  return `${mm}/${dd}（${DOW[d.getDay()]}）`;
}

function cleanCast(cast?: string) {
  if (!cast) return "";
  if (CAST_NG.some(w => cast.includes(w))) return "";
  return cast.replace(/来店.*$/, "").replace(/^.*(演者|ライター|出演)\s*/, "").trim();
}

function isValidStore(s: string) {
  return !STORE_NG.some(w => s.includes(w)) && !DATE_RE.test(s) && s.length > 1;
}

function isRaiten(ev: Ev) {
  return (ev.event || "").includes("来店") || (ev.cast || "").includes("来店");
}

export default function CastPage() {
  const [events, setEvents] = useState<Ev[]>([]);

  useEffect(() => {
    fetch("/events_public.json").then(r=>r.json()).then(d=>setEvents(d.events||[])).catch(()=>{});
  }, []);

  const todayStr = useMemo(() => {
    const n = new Date();
    return `${String(n.getMonth()+1).padStart(2,"0")}/${String(n.getDate()).padStart(2,"0")}`;
  }, []);

  // 来店スケジュール（全社員・演者）
  const raitenGrouped = useMemo(() => {
    const filtered = events.filter(ev => {
      if (!isValidStore(ev.store) || !ev.date || ev.date < todayStr) return false;
      return isRaiten(ev);
    });
    const map = new Map<string, Ev[]>();
    filtered.forEach(ev => {
      if (!map.has(ev.date)) map.set(ev.date, []);
      map.get(ev.date)!.push(ev);
    });
    return Array.from(map.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
  }, [events, todayStr]);

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <header style={{ position:"sticky", top:0, zIndex:200, background:C.white, borderBottom:`3px solid ${C.orange}`, boxShadow:"0 2px 8px rgba(0,0,0,.08)" }}>
        <div style={{ maxWidth:1160, margin:"0 auto", padding:"0 16px", display:"flex", alignItems:"center", height:52, gap:16 }}>
          <Link href="/" style={{ color:C.muted, textDecoration:"none", fontSize:13 }}>← トップ</Link>
          <span style={{ color:C.border }}>|</span>
          <div style={{ display:"flex", alignItems:"center", gap:7 }}>
            <div style={{ width:4, height:18, background:C.orange, borderRadius:2 }} />
            <span style={{ fontSize:16, fontWeight:900, color:C.text }}>社員・演者一覧</span>
          </div>
        </div>
      </header>

      {/* サブヘッダー */}
      <div style={{ background:C.white, borderBottom:`1px solid ${C.border}` }}>
        <div style={{ maxWidth:1160, margin:"0 auto", padding:"18px 16px 16px" }}>
          <div style={{ background:`linear-gradient(135deg, #cc4400 0%, ${C.orange} 100%)`, borderRadius:8, padding:"14px 20px", display:"flex", alignItems:"center", gap:12 }}>
            <span style={{ fontSize:32 }}>🎤</span>
            <div>
              <h1 style={{ fontSize:18, fontWeight:900, color:"#fff", margin:0 }}>メシウマ稼働株式会社 社員・演者一覧</h1>
              <p style={{ fontSize:12, color:"rgba(255,255,255,.85)", margin:"3px 0 0" }}>プロフィールをタップして出演スケジュールを確認</p>
            </div>
          </div>
        </div>
      </div>

      {/* 社員グリッド */}
      <div style={{ maxWidth:1160, margin:"0 auto", padding:"20px 16px 0" }}>
        {MEMBERS.length === 0 ? (
          <div style={{ background:C.white, borderRadius:8, border:`1px solid ${C.border}`, padding:"60px 20px", textAlign:"center" }}>
            <div style={{ fontSize:48, marginBottom:16 }}>🚧</div>
            <div style={{ fontSize:16, fontWeight:700, color:C.text, marginBottom:8 }}>社員情報を準備中です</div>
            <div style={{ fontSize:13, color:C.muted }}>app/cast/members.ts の MEMBERS に追加してください。</div>
          </div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(150px, 1fr))", gap:14 }}>
            {MEMBERS.map(member => (
              <Link key={member.slug} href={`/cast/${member.slug}`} style={{ textDecoration:"none" }}>
                <div style={{
                  background:C.white, border:`1px solid ${C.border}`,
                  borderRadius:10, overflow:"hidden",
                  textAlign:"center", display:"flex", flexDirection:"column",
                  transition:"box-shadow .15s", cursor:"pointer",
                }}
                  onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.boxShadow=`0 4px 16px ${C.orange}44`;}}
                  onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.boxShadow="none";}}>
                  <div style={{ width:"100%", aspectRatio:"1", background:"#f0f0f0", display:"flex", alignItems:"center", justifyContent:"center", overflow:"hidden" }}>
                    {member.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={member.image} alt={member.name} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
                    ) : <span style={{ fontSize:40 }}>👤</span>}
                  </div>
                  <div style={{ padding:"10px 10px 14px", borderTop:`1px solid ${C.border}` }}>
                    <div style={{ fontSize:14, fontWeight:900, color:C.text, marginBottom:3 }}>{member.name}</div>
                    <div style={{ fontSize:10, color:C.muted, marginBottom:member.x?4:0 }}>{member.role}</div>
                    {member.x && <div style={{ fontSize:10, color:"#888" }}>𝕏 @{member.x}</div>}
                    <div style={{ marginTop:7 }}>
                      <span style={{ background:`${C.orange}18`, border:`1px solid ${C.orange}44`, color:C.orange, fontSize:10, fontWeight:700, padding:"2px 10px", borderRadius:999 }}>プロフィール ›</span>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* 来店スケジュール */}
      <div style={{ maxWidth:1160, margin:"28px auto 0", padding:"0 16px 80px" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16, paddingBottom:10, borderBottom:`2px solid ${C.orange}` }}>
          <div style={{ width:4, height:20, background:C.orange, borderRadius:2 }} />
          <span style={{ fontSize:16, fontWeight:900, color:C.text }}>来店スケジュール</span>
          <span style={{ fontSize:12, color:C.muted, marginLeft:4 }}>直近の来店イベント</span>
        </div>

        {raitenGrouped.length === 0 ? (
          <div style={{ background:C.white, borderRadius:8, border:`1px solid ${C.border}`, padding:"40px 20px", textAlign:"center", color:C.muted, fontSize:13 }}>
            現在予定されている来店イベントはありません
          </div>
        ) : (
          <div style={{ display:"flex", flexDirection:"column", gap:20 }}>
            {raitenGrouped.map(([date, evs]) => {
              return (
                <div key={date}>
                  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:10 }}>
                    <span style={{ background:C.orange, color:"#fff", fontSize:12, fontWeight:800, padding:"3px 12px", borderRadius:4, display:"inline-flex", alignItems:"center", gap:4 }}>
                      {dateFmt(date)}
                    </span>
                    <span style={{ color:C.muted, fontSize:12 }}>{evs.length}件</span>
                  </div>
                  <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                    {evs.map(ev => {
                      const cast = cleanCast(ev.cast);
                      const member = MEMBERS.find(m => m.name === cast);
                      return (
                        <div key={ev.id} style={{ background:"#fff8f0", border:`1px solid ${C.orange}33`, borderLeft:`4px solid ${C.orange}`, borderRadius:7, padding:"12px 14px", display:"flex", alignItems:"flex-start", gap:12 }}>
                          <div style={{ width:42, height:42, borderRadius:6, background:`${C.orange}22`, border:`1px solid ${C.orange}44`, display:"flex", alignItems:"center", justifyContent:"center", fontSize:20, flexShrink:0 }}>🎤</div>
                          <div style={{ flex:1, minWidth:0 }}>
                            <div style={{ fontSize:15, fontWeight:800, color:C.text, marginBottom:3 }}>{ev.store}</div>
                            <div style={{ fontSize:12, color:C.orange, fontWeight:700, marginBottom:cast?5:0 }}>{ev.event}</div>
                            {cast && (
                              member ? (
                                <Link href={`/cast/${member.slug}`} onClick={e=>e.stopPropagation()} style={{ textDecoration:"none" }}>
                                  <span style={{ display:"inline-block", background:`${C.orange}14`, border:`1px solid ${C.orange}44`, color:C.orange, fontSize:11, fontWeight:700, padding:"2px 10px", borderRadius:999 }}>👤 {cast} ›</span>
                                </Link>
                              ) : (
                                <span style={{ display:"inline-block", background:`${C.orange}14`, border:`1px solid ${C.orange}44`, color:C.orange, fontSize:11, fontWeight:700, padding:"2px 10px", borderRadius:999 }}>👤 {cast}</span>
                              )
                            )}
                          </div>
                          {ev.pref && <span style={{ fontSize:11, color:C.muted, flexShrink:0 }}>{ev.pref}</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <footer style={{ textAlign:"center", padding:"24px 16px", borderTop:`1px solid ${C.border}`, background:C.white, color:C.muted, fontSize:11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
