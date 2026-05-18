"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { MEMBERS } from "../members";
import type { Member } from "../members";

type Ev = {
  id: number; date: string; store: string; pref: string;
  event: string; detail: string; cast?: string;
};

const CAST_NG  = ["ご来店の際","場合があります","この条件","絞り込む","注意ください"];
const STORE_NG = ["この条件","絞り込む","通常稼働","景品入荷"];
const DATE_RE  = /^\d{4}\/\d{2}\/\d{2}/;

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  orange: "#ff6600", text: "#222222",
  sub: "#555555", muted: "#888888",
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

export default function CastProfilePage() {
  const params = useParams();
  const slug = params?.slug as string;
  const [events, setEvents] = useState<Ev[]>([]);

  const member: Member | undefined = MEMBERS.find(m => m.slug === slug);

  useEffect(() => {
    fetch("/events_public.json").then(r=>r.json()).then(d=>setEvents(d.events||[])).catch(()=>{});
  }, []);

  const todayStr = useMemo(() => {
    const n = new Date();
    return `${String(n.getMonth()+1).padStart(2,"0")}/${String(n.getDate()).padStart(2,"0")}`;
  }, []);

  const schedule = useMemo(() => {
    if (!member) return [];
    return events.filter(ev => {
      if (!isValidStore(ev.store) || !ev.date || ev.date < todayStr) return false;
      const cast = cleanCast(ev.cast);
      return cast === member.name || (ev.event || "").includes(member.name);
    }).sort((a,b) => a.date.localeCompare(b.date));
  }, [member, events, todayStr]);

  if (!member) {
    return (
      <div style={{ background: C.bg, minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center", fontFamily:"'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>
        <div style={{ textAlign:"center" }}>
          <div style={{ fontSize:48, marginBottom:16 }}>😶</div>
          <div style={{ color:C.muted, marginBottom:12 }}>メンバーが見つかりません</div>
          <Link href="/cast" style={{ color:C.orange, fontSize:13 }}>← 社員・演者一覧へ</Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: C.bg, minHeight:"100vh", color:C.text, fontFamily:"'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <header style={{ position:"sticky", top:0, zIndex:200, background:C.white, borderBottom:`3px solid ${C.orange}`, boxShadow:"0 2px 8px rgba(0,0,0,.08)" }}>
        <div style={{ maxWidth:760, margin:"0 auto", padding:"0 16px", display:"flex", alignItems:"center", height:52, gap:16 }}>
          <Link href="/cast" style={{ color:C.muted, textDecoration:"none", fontSize:13 }}>← 一覧に戻る</Link>
          <span style={{ color:C.border }}>|</span>
          <Link href="/" style={{ color:C.muted, textDecoration:"none", fontSize:12 }}>トップ</Link>
        </div>
      </header>

      <div style={{ maxWidth:760, margin:"0 auto", padding:"28px 16px 80px" }}>

        {/* プロフィールカード */}
        <div style={{ background:C.white, border:`1px solid ${C.border}`, borderRadius:12, overflow:"hidden", marginBottom:24, boxShadow:"0 2px 16px rgba(0,0,0,.06)" }}>
          {/* バナー */}
          <div style={{ height:80, background:`linear-gradient(135deg, #cc4400 0%, ${C.orange} 100%)` }} />
          {/* アバター＋情報 */}
          <div style={{ padding:"0 24px 24px" }}>
            <div style={{ display:"flex", alignItems:"flex-end", gap:16, marginTop:-36, marginBottom:16 }}>
              <div style={{ width:72, height:72, borderRadius:"50%", border:`3px solid ${C.white}`, background:"#f0f0f0", overflow:"hidden", flexShrink:0, boxShadow:`0 0 0 3px ${C.orange}` }}>
                {member.image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={member.image} alt={member.name} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
                ) : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:32 }}>👤</div>}
              </div>
              <div style={{ paddingBottom:4 }}>
                <div style={{ fontSize:22, fontWeight:900, color:C.text, lineHeight:1.2 }}>{member.name}</div>
                <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>{member.role}</div>
              </div>
            </div>

            {/* X リンク */}
            {member.x && (
              <a href={`https://x.com/${member.x}`} target="_blank" rel="noopener noreferrer"
                style={{ display:"inline-flex", alignItems:"center", gap:7, background:"#111", color:"#fff", padding:"8px 18px", borderRadius:6, textDecoration:"none", fontSize:13, fontWeight:700, marginBottom:member.bio?16:0 }}>
                𝕏 @{member.x}
              </a>
            )}

            {/* bio */}
            {member.bio && (
              <div style={{ fontSize:14, color:C.sub, lineHeight:1.8, background:"#f8f8f8", borderRadius:8, padding:"14px 16px", border:`1px solid ${C.border}`, marginTop: member.x ? 16 : 0 }}>
                {member.bio}
              </div>
            )}
          </div>
        </div>

        {/* 出演スケジュール */}
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16, paddingBottom:10, borderBottom:`2px solid ${C.orange}` }}>
          <div style={{ width:4, height:20, background:C.orange, borderRadius:2 }} />
          <span style={{ fontSize:16, fontWeight:900, color:C.text }}>出演スケジュール</span>
          <span style={{ fontSize:12, color:C.muted }}>今後の予定</span>
        </div>

        {schedule.length === 0 ? (
          <div style={{ background:C.white, borderRadius:8, border:`1px solid ${C.border}`, padding:"40px 20px", textAlign:"center", color:C.muted, fontSize:13 }}>
            現在予定されている出演スケジュールはありません
          </div>
        ) : (
          <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
            {schedule.map(ev => (
              <div key={ev.id} style={{ background:"#fff8f0", border:`1px solid ${C.orange}33`, borderLeft:`4px solid ${C.orange}`, borderRadius:8, padding:"12px 16px" }}>
                <div style={{ display:"flex", gap:6, marginBottom:7, flexWrap:"wrap", alignItems:"center" }}>
                  <span style={{ background:C.orange, color:"#fff", fontSize:12, fontWeight:800, padding:"3px 12px", borderRadius:4 }}>
                    {dateFmt(ev.date)}
                  </span>
                  {ev.pref && <span style={{ background:"#f5f5f5", color:C.muted, fontSize:11, padding:"2px 8px", borderRadius:3, border:`1px solid ${C.border}` }}>{ev.pref}</span>}
                </div>
                <div style={{ fontSize:16, fontWeight:800, color:C.text, marginBottom:3 }}>{ev.store}</div>
                <div style={{ fontSize:12, color:C.orange, fontWeight:700 }}>{ev.event}</div>
                {ev.detail && ev.detail !== ev.event && (
                  <div style={{ fontSize:11, color:C.muted, marginTop:4, lineHeight:1.6 }}>{ev.detail}</div>
                )}
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop:28, display:"flex", justifyContent:"space-between", borderTop:`1px solid ${C.border}`, paddingTop:20 }}>
          <Link href="/cast" style={{ color:C.orange, fontSize:13, textDecoration:"none", fontWeight:700 }}>← 一覧に戻る</Link>
          <Link href="/" style={{ color:C.muted, fontSize:13, textDecoration:"none" }}>トップへ →</Link>
        </div>
      </div>

      <footer style={{ textAlign:"center", padding:"24px 16px", borderTop:`1px solid ${C.border}`, background:C.white, color:C.muted, fontSize:11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
