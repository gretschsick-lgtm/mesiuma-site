"use client";

import React, { useEffect, useState, useMemo, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { track } from "@vercel/analytics";

// ── 型定義 ──────────────────────────────────────────────────────────────────
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
  floor_map_url?: string | null;
  is_low_rental?: boolean;
  lottery_time?: string | null;
};

type MachineRate = { rate: string; count: number };
type NewMachine  = { name: string; type?: "pachinko" | "slot" };
type MachineInfo = {
  hours?: string;
  entry_rule?: string;
  address?: string;
  x_url?: string;
  hp_url?: string;
  line_url?: string;
  floor_map_url?: string;
  pachinko?: MachineRate[];
  slot?: MachineRate[];
  pachinko_total?: number;
  slot_total?: number;
  new_machines?: NewMachine[];
  updated_at?: string;
  photo_url?: string;
  pworld_url?: string;
};

type Event = {
  id: string | number;
  date: string;
  store: string;
  pref: string;
  area: string;
  event: string;
  detail: string;
  cast: string;
  highlight: string | boolean;
  image_url: string;
  x_url: string;
  url: string;
  source: string;
};

// ── カラー定数 ───────────────────────────────────────────────────────────────
const C = {
  bg:     "#f0f0f0",
  white:  "#ffffff",
  border: "#e0e0e0",
  red:    "#e60000",
  text:   "#222222",
  sub:    "#444444",
  muted:  "#888888",
  dim:    "#cccccc",
  sectionBg: "#f7f7f7",
};

// ── ユーティリティ ────────────────────────────────────────────────────────────
function getEventBadge(eventType: string): { color: string; bg: string; border: string } {
  const t = eventType || "";
  if (t.includes("来店"))   return { color: "#cc3300", bg: "#fff0ed", border: "#ffbbaa" };
  if (t.includes("取材"))   return { color: "#0055bb", bg: "#eef3ff", border: "#aabbee" };
  if (t.includes("撮影") || t.includes("ロケ")) return { color: "#007744", bg: "#edfff5", border: "#aaddc8" };
  if (t.includes("通常稼働")) return { color: "#666", bg: "#f5f5f5", border: "#ddd" };
  const hue = [...t].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  return { color: `hsl(${hue},60%,35%)`, bg: `hsl(${hue},80%,96%)`, border: `hsl(${hue},50%,80%)` };
}

function formatDate(date: string): string {
  const [m, d] = date.split("/");
  if (!m || !d) return date;
  return `${parseInt(m)}月${parseInt(d)}日`;
}

function isToday(date: string): boolean {
  const d = new Date();
  const today = `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
  return date === today;
}

function isFuture(date: string): boolean {
  const d = new Date();
  const today = `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
  return date >= today;
}

// ── スタイルヘルパー ──────────────────────────────────────────────────────────
function btnStyle(bg: string, small = false): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: 5,
    background: bg, color: "#fff",
    padding: small ? "5px 10px" : "8px 16px",
    borderRadius: 5, fontSize: small ? 12 : 13, fontWeight: 700,
    textDecoration: "none",
  };
}

// ── セクション見出し（P-World風） ────────────────────────────────────────────
function SectionHead({ icon, title, count }: { icon: string; title: string; count?: number }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "14px 20px",
      background: "#222", color: "#fff",
      borderRadius: "8px 8px 0 0",
    }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <span style={{ fontSize: 16, fontWeight: 900, letterSpacing: "0.05em" }}>{title}</span>
      {count !== undefined && count > 0 && (
        <span style={{
          marginLeft: "auto", fontSize: 12, fontWeight: 700,
          background: C.red, color: "#fff",
          padding: "2px 8px", borderRadius: 10,
        }}>{count}件</span>
      )}
    </div>
  );
}

// ── 情報行（ラベル＋値） ─────────────────────────────────────────────────────
function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", gap: 0, alignItems: "flex-start",
      borderBottom: `1px solid ${C.border}`,
    }}>
      <div style={{
        fontSize: 12, color: C.muted, fontWeight: 700,
        background: "#f5f5f5", padding: "10px 14px",
        flexShrink: 0, width: 90, borderRight: `1px solid ${C.border}`,
        display: "flex", alignItems: "center",
      }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: C.sub, padding: "10px 14px", flex: 1, lineHeight: 1.6 }}>
        {children}
      </div>
    </div>
  );
}

// ── 貸し玉バー ───────────────────────────────────────────────────────────────
function RateBar({ rate, count, total, isPachinko }: {
  rate: string; count: number; total: number; isPachinko: boolean;
}) {
  const pct = total > 0 ? Math.round(count / total * 100) : 0;
  const barBg   = isPachinko ? "#f5d090" : "#c0d8f0";
  const barFill  = isPachinko ? "#cc7700" : "#2266cc";
  const labelClr = isPachinko ? "#996600" : "#0044aa";
  const countClr = isPachinko ? "#663300" : "#002266";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 16px",
      background: isPachinko ? "#fff9f0" : "#f0f6ff",
      border: `1px solid ${isPachinko ? "#f5d090" : "#88aadd"}`,
      borderRadius: 6,
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: labelClr, minWidth: 100 }}>{rate}</span>
      <div style={{ flex: 1, background: barBg, borderRadius: 3, height: 8, overflow: "hidden" }}>
        <div style={{ height: "100%", borderRadius: 3, background: barFill, width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: 16, fontWeight: 900, color: countClr, minWidth: 70, textAlign: "right" }}>
        {count}<span style={{ fontSize: 11, marginLeft: 2, fontWeight: 400 }}>台</span>
      </span>
      <span style={{ fontSize: 11, color: C.muted, minWidth: 36 }}>{pct}%</span>
    </div>
  );
}

// ── メインコンポーネント ──────────────────────────────────────────────────────
export default function StoreDetailPage() {
  const params = useParams();
  const id = params?.id as string;

  const [store,       setStore]       = useState<Store | null>(null);
  const [events,      setEvents]      = useState<Event[]>([]);
  const [machineInfo, setMachineInfo] = useState<MachineInfo | null>(null);
  const [notFound,    setNotFound]    = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string | number>>(new Set());
  const [activeSection, setActiveSection] = useState("info");

  // セクション ref（スクロールスパイ用）
  const secInfo    = useRef<HTMLDivElement>(null);
  const secPachi   = useRef<HTMLDivElement>(null);
  const secSlot    = useRef<HTMLDivElement>(null);
  const secEvents  = useRef<HTMLDivElement>(null);

  // データ取得
  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetch("/stores.json").then(r => r.json()),
      fetch("/events_public.json").then(r => r.json()),
      fetch("/store_machines.json").then(r => r.json()).catch(() => ({})),
    ]).then(([stores, evData, machines]) => {
      const s = (stores as Store[]).find(s => s.id === id);
      if (!s) { setNotFound(true); return; }
      setStore(s);
      track("store_page_view", { store_id: id, store_name: s.name, pref: s.pref || "" });
      const allEvents: Event[] = Array.isArray(evData) ? evData : (evData.events || []);
      const storeEvents = allEvents.filter(ev => ev.store === s.name);
      storeEvents.sort((a, b) => b.date.localeCompare(a.date));
      setEvents(storeEvents);
      if (machines[s.name]) setMachineInfo(machines[s.name] as MachineInfo);
    }).catch(() => setNotFound(true));
  }, [id]);

  // スクロールスパイ
  useEffect(() => {
    const refs = [
      { id: "info",    ref: secInfo },
      { id: "pachinko", ref: secPachi },
      { id: "slot",    ref: secSlot },
      { id: "events",  ref: secEvents },
    ];
    const handler = () => {
      const scrollY = window.scrollY + 100;
      let current = "info";
      for (const { id: sid, ref } of refs) {
        if (ref.current && ref.current.offsetTop <= scrollY) {
          current = sid;
        }
      }
      setActiveSection(current);
    };
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  const upcomingEvents = useMemo(() => events.filter(ev => isFuture(ev.date)), [events]);
  const pastEvents     = useMemo(() => events.filter(ev => !isFuture(ev.date)),  [events]);

  const toggleExpand = (evId: string | number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(evId)) next.delete(evId); else next.add(evId);
      return next;
    });
  };

  function scrollTo(ref: React.RefObject<HTMLDivElement | null>) {
    if (!ref.current) return;
    const top = ref.current.offsetTop - 100;
    window.scrollTo({ top, behavior: "smooth" });
  }

  // ── エラー ・ ローディング ────────────────────────────────────────────────
  if (notFound) return (
    <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🏪</div>
        <div style={{ color: C.muted, marginBottom: 12 }}>店舗が見つかりません</div>
        <Link href="/stores" style={{ color: C.red, fontSize: 13 }}>← ホール検索へ</Link>
      </div>
    </div>
  );

  if (!store) return (
    <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ color: C.muted, fontFamily: "sans-serif" }}>読み込み中...</div>
    </div>
  );

  const hasPachinko = !!(machineInfo?.pachinko_total);
  const hasSlot     = !!(machineInfo?.slot_total);

  // スクロールナビに表示するタブ
  const navTabs = [
    { id: "info",     label: "基本情報",    ref: secInfo },
    ...(hasPachinko ? [{ id: "pachinko", label: "パチンコ台数", ref: secPachi }] : []),
    ...(hasSlot     ? [{ id: "slot",     label: "パチスロ台数", ref: secSlot  }] : []),
    { id: "events",  label: "最新情報",    ref: secEvents },
  ];

  const address   = store.address || machineInfo?.address;
  const hpUrl     = store.hp_url  || machineInfo?.hp_url;
  const xUrl      = store.x_url   || machineInfo?.x_url;
  const mapUrl    = store.map_url;
  const floorUrl  = store.floor_map_url || machineInfo?.floor_map_url;

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif", color: C.text }}>

      {/* ── グローバルヘッダー ────────────────────────────────── */}
      <header style={{
        position: "sticky", top: 0, zIndex: 100,
        background: "#1a1a1a", borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.3)",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", gap: 12, height: 48 }}>
          <Link href="/stores" style={{ color: "#aaa", textDecoration: "none", fontSize: 12, whiteSpace: "nowrap", flexShrink: 0 }}>
            ← ホール一覧
          </Link>
          <span style={{ color: "#555" }}>|</span>
          <span style={{ color: "#fff", fontSize: 13, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {store.name}
          </span>
        </div>
      </header>

      {/* ── セクションナビ（スクロールスパイ） ───────────────────── */}
      <div style={{
        position: "sticky", top: 48, zIndex: 90,
        background: C.white, borderBottom: `1px solid ${C.border}`,
        boxShadow: "0 2px 6px rgba(0,0,0,.06)",
        overflowX: "auto",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", display: "flex" }}>
          {navTabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => scrollTo(tab.ref)}
              style={{
                flex: "0 0 auto",
                padding: "11px 18px",
                fontSize: 13, fontWeight: 700,
                border: "none", cursor: "pointer",
                background: "transparent",
                color: activeSection === tab.id ? C.red : C.sub,
                borderBottom: activeSection === tab.id ? `3px solid ${C.red}` : "3px solid transparent",
                whiteSpace: "nowrap",
                transition: "all 0.15s",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 16px 80px" }}>

        {/* ── 店舗ヘッダーカード ─────────────────────────────────── */}
        <div style={{
          background: C.white, borderRadius: 8, marginBottom: 20,
          border: `1px solid ${C.border}`, overflow: "hidden",
          borderTop: `4px solid ${C.red}`,
        }}>
          {/* 店舗写真 */}
          {machineInfo?.photo_url && (
            <div style={{ width: "100%", height: 180, overflow: "hidden", background: "#eee" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={machineInfo.photo_url}
                alt={store.name}
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                loading="lazy"
                onError={e => { (e.currentTarget as HTMLImageElement).parentElement!.style.display = "none"; }}
              />
            </div>
          )}
          <div style={{ padding: "16px 20px" }}>
            <h1 style={{ fontSize: 20, fontWeight: 900, color: C.text, margin: "0 0 10px", lineHeight: 1.3 }}>
              {store.name}
            </h1>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {store.pref && (
                <span style={{ background: "#f0f0f0", color: C.sub, fontSize: 12, padding: "3px 10px", borderRadius: 3, fontWeight: 700 }}>
                  📍 {store.pref}{store.city ? ` ${store.city}` : ""}
                </span>
              )}
              {store.is_low_rental && (
                <span style={{ background: "#e8f0ff", color: "#0055cc", fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 3, border: "1px solid #0055cc44" }}>
                  💴 低貸し
                </span>
              )}
              {(machineInfo?.pachinko_total || machineInfo?.slot_total) && (
                <span style={{ background: "#f5f5f5", color: C.sub, fontSize: 12, padding: "3px 10px", borderRadius: 3 }}>
                  🎮 {[machineInfo?.pachinko_total && `パチ${machineInfo.pachinko_total}台`, machineInfo?.slot_total && `スロ${machineInfo.slot_total}台`].filter(Boolean).join("・")}
                </span>
              )}
              {upcomingEvents.length > 0 && (
                <span style={{ background: "#e8fff0", color: "#007700", fontSize: 12, padding: "3px 10px", borderRadius: 3, border: "1px solid #aaddaa", fontWeight: 700 }}>
                  ▶ 予定 {upcomingEvents.length}件
                </span>
              )}
              {machineInfo?.updated_at && (
                <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 11, padding: "3px 8px", borderRadius: 3 }}>
                  更新: {machineInfo.updated_at.slice(5, 10).replace("-", "/")}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════
            §1 基本情報
        ════════════════════════════════════════════════════════ */}
        <div ref={secInfo} style={{ marginBottom: 20 }}>
          <SectionHead icon="📋" title="基本情報" />
          <div style={{ background: C.white, border: `1px solid ${C.border}`, borderTop: "none", borderRadius: "0 0 8px 8px", overflow: "hidden" }}>
            {address && <InfoRow label="住所">{address}</InfoRow>}
            {machineInfo?.hours && <InfoRow label="営業時間">{machineInfo.hours}</InfoRow>}
            {machineInfo?.entry_rule && <InfoRow label="入場ルール">{machineInfo.entry_rule}</InfoRow>}
            {store.lottery_time && <InfoRow label="整列時間">{store.lottery_time}</InfoRow>}
            {(machineInfo?.pachinko_total || machineInfo?.slot_total) && (
              <InfoRow label="総台数">
                {[
                  machineInfo?.pachinko_total ? `パチンコ ${machineInfo.pachinko_total}台` : null,
                  machineInfo?.slot_total     ? `スロット ${machineInfo.slot_total}台`     : null,
                ].filter(Boolean).join("　/　")}
                <span style={{ color: C.muted, marginLeft: 8, fontSize: 12 }}>
                  （合計 {(machineInfo?.pachinko_total || 0) + (machineInfo?.slot_total || 0)}台）
                </span>
              </InfoRow>
            )}

            {/* データなし */}
            {!address && !machineInfo?.hours && !store.lottery_time && !machineInfo?.pachinko_total && (
              <div style={{ textAlign: "center", padding: "32px 0", color: C.muted }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
                <div style={{ fontSize: 13 }}>基本情報はまだ登録されていません</div>
              </div>
            )}

            {/* リンクボタン */}
            {(hpUrl || xUrl || machineInfo?.line_url || mapUrl || floorUrl) && (
              <div style={{ padding: "16px 20px", borderTop: `1px solid ${C.border}`, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {hpUrl     && <a href={hpUrl}              target="_blank" rel="noopener noreferrer" style={btnStyle(C.red,   true)}>🌐 公式サイト</a>}
                {xUrl      && <a href={xUrl}               target="_blank" rel="noopener noreferrer" style={btnStyle("#000",  true)}>𝕏 X</a>}
                {machineInfo?.line_url && <a href={machineInfo.line_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#06C755", true)}>💬 LINE</a>}
                {mapUrl    && <a href={mapUrl}             target="_blank" rel="noopener noreferrer" style={btnStyle("#4285f4", true)}>🗺 地図</a>}
                {floorUrl  && <a href={floorUrl}           target="_blank" rel="noopener noreferrer" style={btnStyle("#888",  true)}>🏢 フロアマップ</a>}
              </div>
            )}
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════
            §2 パチンコ台数
        ════════════════════════════════════════════════════════ */}
        {hasPachinko && (
          <div ref={secPachi} style={{ marginBottom: 20 }}>
            <SectionHead icon="🎯" title="パチンコ台数" />
            <div style={{ background: C.white, border: `1px solid ${C.border}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "20px" }}>

              {/* 合計 */}
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 16, paddingBottom: 16, borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 13, color: C.sub }}>パチンコ合計</span>
                <span style={{ fontSize: 40, fontWeight: 900, color: "#663300", lineHeight: 1 }}>{machineInfo?.pachinko_total}</span>
                <span style={{ fontSize: 16, color: C.sub }}>台</span>
              </div>

              {/* 貸し玉別内訳 */}
              {machineInfo?.pachinko && machineInfo.pachinko.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {machineInfo.pachinko.map((r, i) => (
                    <RateBar key={i} rate={r.rate} count={r.count} total={machineInfo?.pachinko_total || 0} isPachinko />
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "16px 0", color: C.muted, fontSize: 13 }}>内訳データなし</div>
              )}

              {/* 新台（パチンコ） */}
              {machineInfo?.new_machines && machineInfo.new_machines.filter(m => m.type === "pachinko" || !m.type).length > 0 && (
                <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.sub, marginBottom: 10 }}>🆕 新台・注目機種</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {machineInfo.new_machines
                      .filter(m => m.type === "pachinko" || !m.type)
                      .map((m, i) => (
                        <span key={i} style={{ fontSize: 12, padding: "4px 12px", borderRadius: 4, background: "#fff5e8", color: "#663300", border: "1px solid #f5c060" }}>
                          {m.name}
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════
            §3 パチスロ台数
        ════════════════════════════════════════════════════════ */}
        {hasSlot && (
          <div ref={secSlot} style={{ marginBottom: 20 }}>
            <SectionHead icon="🎰" title="パチスロ台数" />
            <div style={{ background: C.white, border: `1px solid ${C.border}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "20px" }}>

              {/* 合計 */}
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 16, paddingBottom: 16, borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 13, color: C.sub }}>パチスロ合計</span>
                <span style={{ fontSize: 40, fontWeight: 900, color: "#002266", lineHeight: 1 }}>{machineInfo?.slot_total}</span>
                <span style={{ fontSize: 16, color: C.sub }}>台</span>
              </div>

              {/* 貸しコイン別内訳 */}
              {machineInfo?.slot && machineInfo.slot.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {machineInfo.slot.map((r, i) => (
                    <RateBar key={i} rate={r.rate} count={r.count} total={machineInfo?.slot_total || 0} isPachinko={false} />
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "16px 0", color: C.muted, fontSize: 13 }}>内訳データなし</div>
              )}

              {/* 新台（スロット） */}
              {machineInfo?.new_machines && machineInfo.new_machines.filter(m => m.type === "slot").length > 0 && (
                <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.sub, marginBottom: 10 }}>🆕 新台・注目機種</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {machineInfo.new_machines
                      .filter(m => m.type === "slot")
                      .map((m, i) => (
                        <span key={i} style={{ fontSize: 12, padding: "4px 12px", borderRadius: 4, background: "#f0f8ff", color: "#002266", border: "1px solid #88aadd" }}>
                          {m.name}
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════
            §4 最新情報
        ════════════════════════════════════════════════════════ */}
        <div ref={secEvents} style={{ marginBottom: 20 }}>
          <SectionHead icon="📅" title="最新情報" count={events.length} />
          <div style={{ background: C.white, border: `1px solid ${C.border}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "20px" }}>

            {/* 今後 */}
            {upcomingEvents.length > 0 && (
              <section style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <div style={{ width: 4, height: 18, background: "#007700", borderRadius: 2 }} />
                  <h2 style={{ fontSize: 14, fontWeight: 900, color: "#333", margin: 0 }}>今後のイベント（{upcomingEvents.length}件）</h2>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {upcomingEvents.map(ev => (
                    <EventCard key={ev.id} ev={ev} upcoming expanded={expandedIds.has(ev.id)} onToggle={() => toggleExpand(ev.id)} />
                  ))}
                </div>
              </section>
            )}

            {/* 過去 */}
            {pastEvents.length > 0 && (
              <section>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <div style={{ width: 4, height: 18, background: C.muted, borderRadius: 2 }} />
                  <h2 style={{ fontSize: 14, fontWeight: 900, color: "#333", margin: 0 }}>過去のイベント（{pastEvents.length}件）</h2>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {pastEvents.slice(0, 50).map(ev => (
                    <EventCard key={ev.id} ev={ev} upcoming={false} expanded={expandedIds.has(ev.id)} onToggle={() => toggleExpand(ev.id)} />
                  ))}
                </div>
                {pastEvents.length > 50 && (
                  <div style={{ textAlign: "center", color: C.muted, fontSize: 12, marginTop: 8 }}>
                    他 {pastEvents.length - 50}件（最新50件を表示中）
                  </div>
                )}
              </section>
            )}

            {events.length === 0 && (
              <div style={{ textAlign: "center", padding: "48px 0", color: C.muted }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>📭</div>
                <div style={{ fontSize: 14 }}>イベント情報はまだありません</div>
              </div>
            )}
          </div>
        </div>

        {/* フッターリンク */}
        <div style={{ display: "flex", gap: 16 }}>
          <Link href="/stores" style={{ color: C.red, fontSize: 13, fontWeight: 700, textDecoration: "none" }}>← ホール一覧に戻る</Link>
          <Link href="/" style={{ color: C.muted, fontSize: 13, textDecoration: "none" }}>トップへ →</Link>
        </div>
      </div>

      <footer style={{ textAlign: "center", padding: "20px 16px", borderTop: `1px solid ${C.border}`, background: "#1a1a1a", color: "#666", fontSize: 11, marginTop: 20 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}

// ── EventCard ─────────────────────────────────────────────────────────────
function EventCard({
  ev, upcoming, expanded, onToggle,
}: {
  ev: Event; upcoming: boolean; expanded: boolean; onToggle: () => void;
}) {
  const badge = getEventBadge(ev.event);
  const today = isToday(ev.date);
  const detailLines = (ev.detail || "").split("\n").filter(l => l.trim());
  const hasLongDetail = detailLines.length > 4 || (ev.detail || "").length > 200;
  const displayLines  = expanded ? detailLines : detailLines.slice(0, 4);
  const castClean = (ev.cast || "").replace(/[）)』」>]/g, "").trim();
  const validCast = castClean.length >= 2 && castClean.length <= 30 && !castClean.match(/^[ぁ-ん]{1,2}$/);

  return (
    <div style={{
      background: upcoming ? C.white : "#fafafa",
      border: `1px solid ${today ? "#00aa44" : upcoming ? "#ddeedd" : C.border}`,
      borderRadius: 7,
      borderLeft: today ? "4px solid #00aa44" : upcoming ? "4px solid #88cc88" : `4px solid ${C.dim}`,
      overflow: "hidden",
    }}>
      {today && (
        <div style={{ background: "#00aa44", color: "#fff", fontSize: 11, fontWeight: 900, padding: "3px 12px", textAlign: "center", letterSpacing: "0.1em" }}>
          ★ 本日開催
        </div>
      )}
      <div style={{ padding: "12px 16px" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <span style={{
            background: upcoming ? (today ? "#00aa44" : "#e8fff0") : "#f5f5f5",
            color: upcoming ? (today ? "#fff" : "#006600") : C.muted,
            fontSize: 13, fontWeight: 900, padding: "3px 10px", borderRadius: 4,
            border: upcoming ? (today ? "none" : "1px solid #aaddaa") : `1px solid ${C.dim}`,
            whiteSpace: "nowrap",
          }}>
            📅 {formatDate(ev.date)}
          </span>
          {ev.event && (
            <span style={{ background: badge.bg, color: badge.color, fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 4, border: `1px solid ${badge.border}`, whiteSpace: "nowrap" }}>
              {ev.event}
            </span>
          )}
          {validCast && (
            <span style={{ background: "#f5f0ff", color: "#6600cc", fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 4, border: "1px solid #ccaaee", whiteSpace: "nowrap" }}>
              🎤 {castClean}
            </span>
          )}
          {ev.highlight && (
            <span style={{ background: "#fffbe8", color: "#886600", fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 4, border: "1px solid #ddcc66" }}>★ 注目</span>
          )}
        </div>

        {ev.image_url && (
          <div style={{ marginBottom: 8 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={ev.image_url} alt=""
              style={{ maxWidth: "100%", maxHeight: 300, borderRadius: 6, border: `1px solid ${C.border}`, display: "block" }}
              loading="lazy"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
            />
          </div>
        )}

        {detailLines.length > 0 && (
          <div style={{ fontSize: 13, color: upcoming ? C.sub : C.muted, lineHeight: 1.75, background: "#fafafa", border: `1px solid ${C.border}`, borderRadius: 5, padding: "10px 12px" }}>
            {displayLines.map((line, i) => <div key={i}>{line}</div>)}
            {hasLongDetail && (
              <button onClick={onToggle} style={{ marginTop: 6, background: "none", border: "none", color: C.red, fontSize: 12, cursor: "pointer", padding: 0, fontWeight: 700 }}>
                {expanded ? "▲ 折りたたむ" : `▼ 続きを見る（全${detailLines.length}行）`}
              </button>
            )}
          </div>
        )}

        {ev.x_url && (
          <div style={{ marginTop: 8 }}>
            <a href={ev.x_url} target="_blank" rel="noopener noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: "#555", textDecoration: "none", background: "#f5f5f5", border: `1px solid ${C.border}`, borderRadius: 4, padding: "4px 10px" }}>
              𝕏 元ツイートを見る →
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
