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
type MachineTile = { name: string; type?: "pachinko" | "slot"; is_new?: boolean };
type MachineInfo = {
  hours?: string;
  entry_rule?: string;
  address?: string;
  x_url?: string;
  hp_url?: string;
  dmm_url?: string;    // DMM（将来対応）
  line_url?: string;
  floor_map_url?: string;
  pachinko?: MachineRate[];
  slot?: MachineRate[];
  pachinko_total?: number;
  slot_total?: number;
  machines_installed?: MachineTile[];
  new_machines?: MachineTile[];
  updated_at?: string;
  // photo_url は P-WORLD 由来のため転載禁止 — 型から除外
  pworld_url?: string;
  pworld_slug?: string;
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
  x_url: string;
  url: string;
  source: string;
  // image_url は転載禁止のため型から除外
};

// /api/events レスポンス行（Supabase 由来）
type ApiEventRow = {
  id: string;
  store_id: string | null;
  store_name: string | null;
  pref: string | null;
  area: string | null;
  date: string | null;
  event_name: string | null;
  detail: string | null;
  cast_names: string[] | null;
  x_url: string | null;
  source_url: string | null;
  source: string | null;
  highlight: boolean;
  created_at: string;
  updated_at: string;
};

function adaptApiEvent(e: ApiEventRow): Event {
  return {
    id:        e.id,
    date:      e.date      ?? "",
    store:     e.store_name ?? "",
    pref:      e.pref      ?? "",
    area:      e.area      ?? "",
    event:     e.event_name ?? "",
    detail:    e.detail    ?? "",
    cast:      (e.cast_names ?? []).join(" "),
    highlight: !!e.highlight,
    x_url:     e.x_url     ?? "",
    url:       e.source_url ?? "",
    source:    e.source    ?? "",
  };
}

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

// ── メシウマ指数（event_count → ★評価）────────────────────────────────────────
function meshiumaStars(eventCount: number): string {
  if (eventCount <= 0)  return "☆☆☆☆☆";
  if (eventCount <= 2)  return "★☆☆☆☆";
  if (eventCount <= 5)  return "★★☆☆☆";
  if (eventCount <= 10) return "★★★☆☆";
  if (eventCount <= 20) return "★★★★☆";
  return "★★★★★";
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

// ── 設置機種リスト ────────────────────────────────────────────────────────────
function MachineList({ machines, isPachinko }: { machines: MachineTile[]; isPachinko: boolean }) {
  const [showAll, setShowAll] = React.useState(false);
  if (machines.length === 0) return null;
  const LIMIT = 20;
  const visible = showAll ? machines : machines.slice(0, LIMIT);
  const newBg   = isPachinko ? "#fff5e8" : "#f0f8ff";
  const newClr  = isPachinko ? "#663300" : "#002266";
  const newBdr  = isPachinko ? "#f5c060" : "#88aadd";
  const normBg  = isPachinko ? "#fafafa" : "#f8faff";
  const normClr = isPachinko ? "#444"    : "#334";
  const normBdr = isPachinko ? "#ddd"    : "#ccd8ee";

  return (
    <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid #eee" }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#555", marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
        🎮 設置機種
        <span style={{ fontWeight: 400, fontSize: 12, color: "#888" }}>{machines.length}機種</span>
        {machines.some(m => m.is_new) && (
          <span style={{ fontSize: 11, background: "#e8fff0", color: "#006600", border: "1px solid #aaddaa", borderRadius: 4, padding: "1px 7px", fontWeight: 700 }}>
            🆕 新台あり
          </span>
        )}
      </div>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {visible.map((m, i) => (
          <span key={i} style={{
            fontSize: 12, padding: "4px 10px", borderRadius: 4,
            background: m.is_new ? newBg  : normBg,
            color:      m.is_new ? newClr : normClr,
            border:     `1px solid ${m.is_new ? newBdr : normBdr}`,
            fontWeight: m.is_new ? 700 : 400,
            position: "relative",
          }}>
            {m.is_new && <span style={{ fontSize: 9, color: "#009900", marginRight: 3 }}>NEW</span>}
            {m.name}
          </span>
        ))}
      </div>
      {machines.length > LIMIT && (
        <button
          onClick={() => setShowAll(v => !v)}
          style={{ marginTop: 10, background: "none", border: "none", color: "#e60000", fontSize: 12, cursor: "pointer", padding: 0, fontWeight: 700 }}
        >
          {showAll ? "▲ 折りたたむ" : `▼ もっと見る（残り${machines.length - LIMIT}機種）`}
        </button>
      )}
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
  const secInfo     = useRef<HTMLDivElement>(null);
  const secPachi    = useRef<HTMLDivElement>(null);
  const secSlot     = useRef<HTMLDivElement>(null);
  const secMachines = useRef<HTMLDivElement>(null);
  const secEvents   = useRef<HTMLDivElement>(null);

  // データ取得
  useEffect(() => {
    if (!id) return;
    // stores.json + store_machines.json を先に取得
    Promise.all([
      fetch("/stores.json").then(r => r.json()),
      fetch("/store_machines.json").then(r => r.json()).catch(() => ({})),
    ]).then(([stores, machines]) => {
      const s = (stores as Store[]).find(s => s.id === id);
      if (!s) { setNotFound(true); return; }
      setStore(s);
      track("store_page_view", { store_id: id, store_name: s.name, pref: s.pref || "" });
      if (machines[s.name]) setMachineInfo(machines[s.name] as MachineInfo);

      // 店舗ID確定後にイベントを /api/events で取得（store_id 完全一致）
      fetch(`/api/events?store_id=${encodeURIComponent(id)}&limit=200`)
        .then(r => r.json())
        .then(d => {
          const evs: Event[] = (d.data ?? []).map(adaptApiEvent);
          evs.sort((a, b) => b.date.localeCompare(a.date));
          setEvents(evs);
        })
        .catch(() => {});
    }).catch(() => setNotFound(true));
  }, [id]);

  // スクロールスパイ
  useEffect(() => {
    const refs = [
      { id: "info",     ref: secInfo },
      { id: "pachinko", ref: secPachi },
      { id: "slot",     ref: secSlot },
      { id: "machines", ref: secMachines },
      { id: "events",   ref: secEvents },
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

  const hasPachinko  = !!(machineInfo?.pachinko_total);
  const hasSlot      = !!(machineInfo?.slot_total);

  // 設置機種リスト（全機種）: machines_installed 優先、なければ new_machines にフォールバック
  const installed    = machineInfo?.machines_installed ?? machineInfo?.new_machines ?? [];
  const pachiInstalled = installed.filter(m => m.type === "pachinko" || !m.type);
  const slotInstalled  = installed.filter(m => m.type === "slot");
  const allMachines    = installed;
  // 新台セクションを独立表示するのはレートデータがない場合のみ
  const showStandaloneMachines = allMachines.length > 0 && !hasPachinko && !hasSlot;

  // スクロールナビに表示するタブ
  const navTabs = [
    { id: "info",     label: "基本情報",    ref: secInfo },
    ...(hasPachinko ? [{ id: "pachinko", label: "パチンコ台数", ref: secPachi }] : []),
    ...(hasSlot     ? [{ id: "slot",     label: "パチスロ台数", ref: secSlot  }] : []),
    ...(showStandaloneMachines ? [{ id: "machines", label: "設置機種", ref: secMachines }] : []),
    { id: "events",   label: "最新情報",    ref: secEvents },
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
          padding: "16px 20px",
        }}>
          {/* 店舗名 */}
          <h1 style={{ fontSize: 22, fontWeight: 900, color: C.text, margin: "0 0 10px", lineHeight: 1.3 }}>
            {store.name}
          </h1>

          {/* バッジ行 */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {store.pref && (
              <span style={{ background: "#f0f0f0", color: C.sub, fontSize: 12, padding: "3px 10px", borderRadius: 3, fontWeight: 700 }}>
                📍 {store.pref}{store.city ? ` ${store.city}` : ""}{store.area && store.area !== store.pref ? `（${store.area}）` : ""}
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
            {/* メシウマ指数（イベント実績ベース） */}
            <span style={{
              background: store.event_count > 0 ? "#fff8e0" : "#f5f5f5",
              color: store.event_count > 0 ? "#886600" : C.muted,
              fontSize: 12, fontWeight: 700,
              padding: "3px 10px", borderRadius: 3,
              border: `1px solid ${store.event_count > 0 ? "#eedd88" : C.border}`,
            }}>
              メシウマ指数 {meshiumaStars(store.event_count)}
            </span>
            {store.event_count > 0 && (
              <span style={{ background: "#fff8e0", color: "#886600", fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 3, border: "1px solid #eedd88" }}>
                ⭐ イベント {store.event_count}件
              </span>
            )}
            {upcomingEvents.length > 0 && (
              <span style={{ background: "#e8fff0", color: "#007700", fontSize: 12, padding: "3px 10px", borderRadius: 3, border: "1px solid #aaddaa", fontWeight: 700 }}>
                ▶ 予定 {upcomingEvents.length}件
              </span>
            )}
          </div>

          {/* 公式リンクボタン */}
          {(hpUrl || xUrl || machineInfo?.dmm_url || machineInfo?.pworld_url || mapUrl) && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {hpUrl                    && <a href={hpUrl}                    target="_blank" rel="noopener noreferrer" style={btnStyle(C.red,    true)}>🌐 公式サイト</a>}
              {xUrl                     && <a href={xUrl}                     target="_blank" rel="noopener noreferrer" style={btnStyle("#000",   true)}>𝕏 X</a>}
              {machineInfo?.dmm_url     && <a href={machineInfo.dmm_url}     target="_blank" rel="noopener noreferrer" style={btnStyle("#f60",   true)}>🎰 DMMで見る</a>}
              {machineInfo?.pworld_url  && <a href={machineInfo.pworld_url}  target="_blank" rel="noopener noreferrer" style={btnStyle("#0066cc", true)}>🏢 P-WORLDで見る</a>}
              {mapUrl                   && <a href={mapUrl}                   target="_blank" rel="noopener noreferrer" style={btnStyle("#4285f4", true)}>🗺 地図</a>}
            </div>
          )}
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
            {(hpUrl || xUrl || machineInfo?.dmm_url || machineInfo?.pworld_url || machineInfo?.line_url || mapUrl || floorUrl) && (
              <div style={{ padding: "16px 20px", borderTop: `1px solid ${C.border}`, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {hpUrl                    && <a href={hpUrl}                    target="_blank" rel="noopener noreferrer" style={btnStyle(C.red,    true)}>🌐 公式サイト</a>}
                {xUrl                     && <a href={xUrl}                     target="_blank" rel="noopener noreferrer" style={btnStyle("#000",   true)}>𝕏 X</a>}
                {machineInfo?.dmm_url     && <a href={machineInfo.dmm_url}     target="_blank" rel="noopener noreferrer" style={btnStyle("#f60",   true)}>🎰 DMMで見る</a>}
                {machineInfo?.pworld_url  && <a href={machineInfo.pworld_url}  target="_blank" rel="noopener noreferrer" style={btnStyle("#0066cc", true)}>🏢 P-WORLDで見る</a>}
                {machineInfo?.line_url    && <a href={machineInfo.line_url}    target="_blank" rel="noopener noreferrer" style={btnStyle("#06C755", true)}>💬 LINE</a>}
                {mapUrl                   && <a href={mapUrl}                   target="_blank" rel="noopener noreferrer" style={btnStyle("#4285f4", true)}>🗺 地図</a>}
                {floorUrl                 && <a href={floorUrl}                 target="_blank" rel="noopener noreferrer" style={btnStyle("#888",   true)}>🏢 フロアマップ</a>}
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

              {/* 設置機種（パチンコ） */}
              <MachineList machines={pachiInstalled} isPachinko />
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

              {/* 設置機種（スロット） */}
              <MachineList machines={slotInstalled} isPachinko={false} />
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════
            §3.5 設置機種（レートデータなし・機種名のみある場合）
        ════════════════════════════════════════════════════════ */}
        {showStandaloneMachines && (
          <div ref={secMachines} style={{ marginBottom: 20 }}>
            <SectionHead icon="🎮" title="設置機種" count={allMachines.length} />
            <div style={{ background: C.white, border: `1px solid ${C.border}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "20px" }}>
              {pachiInstalled.length > 0 && (
                <div style={{ marginBottom: slotInstalled.length > 0 ? 20 : 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#996600", marginBottom: 8 }}>🎯 パチンコ</div>
                  <MachineList machines={pachiInstalled} isPachinko />
                </div>
              )}
              {slotInstalled.length > 0 && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#0044aa", marginBottom: 8 }}>🎰 パチスロ</div>
                  <MachineList machines={slotInstalled} isPachinko={false} />
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
