"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { track } from "@vercel/analytics";

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
type NewMachine = { name: string; type?: "pachinko" | "slot" };
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

type TabId = "info" | "pachinko" | "slot" | "events";

const C = {
  bg: "#f0f0f0", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", text: "#222222", sub: "#444444",
  muted: "#888888", dim: "#cccccc",
};

function getEventBadge(eventType: string): { color: string; bg: string; border: string } {
  const t = eventType || "";
  if (t.includes("来店")) return { color: "#cc3300", bg: "#fff0ed", border: "#ffbbaa" };
  if (t.includes("取材")) return { color: "#0055bb", bg: "#eef3ff", border: "#aabbee" };
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

export default function StoreDetailPage() {
  const params = useParams();
  const id = params?.id as string;

  const [store, setStore] = useState<Store | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [machineInfo, setMachineInfo] = useState<MachineInfo | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string | number>>(new Set());
  const [activeTab, setActiveTab] = useState<TabId>("info");

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

  const upcomingEvents = useMemo(() => events.filter(ev => isFuture(ev.date)), [events]);
  const pastEvents = useMemo(() => events.filter(ev => !isFuture(ev.date)), [events]);

  const toggleExpand = (evId: string | number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(evId)) next.delete(evId); else next.add(evId);
      return next;
    });
  };

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

  // タブ定義
  const tabs: { id: TabId; label: string; count?: number; show: boolean }[] = [
    { id: "info",     label: "基本情報",    show: true },
    { id: "pachinko", label: "パチンコ台数", count: machineInfo?.pachinko_total, show: !!(machineInfo?.pachinko_total) },
    { id: "slot",     label: "パチスロ台数", count: machineInfo?.slot_total,     show: !!(machineInfo?.slot_total) },
    { id: "events",   label: "最新情報",    count: events.length,               show: true },
  ];

  return (
    <div style={{ background: C.bg, minHeight: "100vh", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif", color: C.text }}>

      {/* ヘッダー */}
      <header style={{
        position: "sticky", top: 0, zIndex: 100,
        background: C.white, borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
      }}>
        <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", gap: 12, height: 52 }}>
          <Link href="/stores" style={{ color: C.muted, textDecoration: "none", fontSize: 13, whiteSpace: "nowrap" }}>← ホール検索</Link>
          <span style={{ color: C.border }}>|</span>
          <span style={{ color: C.text, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{store.name}</span>
        </div>
      </header>

      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "20px 16px 80px" }}>

        {/* ===== 店舗ヘッダーカード ===== */}
        <div style={{
          background: C.white, border: `1px solid ${C.border}`,
          borderRadius: 8, padding: "20px 24px", marginBottom: 0,
          borderTop: `4px solid ${C.red}`,
          borderBottomLeftRadius: 0, borderBottomRightRadius: 0,
        }}>
          <h1 style={{ fontSize: 22, fontWeight: 900, color: C.text, margin: "0 0 10px", lineHeight: 1.3 }}>
            🏪 {store.name}
          </h1>

          {/* バッジ行 */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {store.pref && (
              <span style={{ background: "#f0f0f0", color: C.sub, fontSize: 12, padding: "3px 10px", borderRadius: 3, fontWeight: 700 }}>
                📍 {store.pref}{store.city ? ` › ${store.city}` : ""}
              </span>
            )}
            {store.area && (
              <span style={{ background: "#f0f0f0", color: C.muted, fontSize: 12, padding: "3px 10px", borderRadius: 3 }}>
                {store.area}
              </span>
            )}
            {upcomingEvents.length > 0 && (
              <span style={{ background: "#e8fff0", color: "#007700", fontSize: 12, padding: "3px 10px", borderRadius: 3, border: "1px solid #aaddaa", fontWeight: 700 }}>
                ▶ 予定 {upcomingEvents.length}件
              </span>
            )}
            {store.is_low_rental && (
              <span style={{ background: "#e8f0ff", color: "#0055cc", fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 3, border: "1px solid #0055cc44" }}>
                💴 低貸し専門店
              </span>
            )}
            {machineInfo?.updated_at && (
              <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 11, padding: "3px 8px", borderRadius: 3 }}>
                P-World更新: {machineInfo.updated_at.slice(5, 10).replace("-", "/")}
              </span>
            )}
          </div>
        </div>

        {/* ===== タブナビ ===== */}
        <div style={{
          background: C.white, borderLeft: `1px solid ${C.border}`, borderRight: `1px solid ${C.border}`,
          display: "flex", overflowX: "auto",
          position: "sticky", top: 52, zIndex: 90,
          boxShadow: "0 2px 4px rgba(0,0,0,.06)",
        }}>
          {tabs.filter(t => t.show).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                flex: "0 0 auto",
                padding: "12px 18px",
                fontSize: 13, fontWeight: 700,
                border: "none", cursor: "pointer",
                background: activeTab === tab.id ? C.white : "#f8f8f8",
                color: activeTab === tab.id ? C.red : C.sub,
                borderBottom: activeTab === tab.id ? `3px solid ${C.red}` : "3px solid transparent",
                borderTop: "none", borderLeft: "none", borderRight: "none",
                whiteSpace: "nowrap",
                transition: "all 0.15s",
              }}
            >
              {tab.label}
              {tab.count !== undefined && tab.count > 0 && (
                <span style={{
                  marginLeft: 5, fontSize: 11, fontWeight: 900,
                  background: activeTab === tab.id ? C.red : C.dim,
                  color: activeTab === tab.id ? "#fff" : C.sub,
                  padding: "1px 6px", borderRadius: 10,
                }}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ===== タブコンテンツ ===== */}
        <div style={{
          background: C.white, border: `1px solid ${C.border}`,
          borderTop: "none", borderBottomLeftRadius: 8, borderBottomRightRadius: 8,
          padding: "20px 24px", marginBottom: 20,
        }}>

          {/* ── 基本情報 ── */}
          {activeTab === "info" && (
            <div>
              {/* 住所 */}
              {(store.address || machineInfo?.address) && (
                <InfoRow icon="📮" label="住所">
                  {store.address || machineInfo?.address}
                </InfoRow>
              )}

              {/* 営業時間 */}
              {machineInfo?.hours && (
                <InfoRow icon="🕐" label="営業時間">
                  {machineInfo.hours}
                </InfoRow>
              )}

              {/* 入場ルール */}
              {machineInfo?.entry_rule && (
                <InfoRow icon="🎟" label="入場ルール">
                  {machineInfo.entry_rule}
                </InfoRow>
              )}

              {/* 整列時間 */}
              {store.lottery_time && (
                <InfoRow icon="🎰" label="整列時間">
                  {store.lottery_time}
                </InfoRow>
              )}

              {/* 総台数 */}
              {(machineInfo?.pachinko_total || machineInfo?.slot_total) && (
                <InfoRow icon="🎮" label="総台数">
                  {[
                    machineInfo?.pachinko_total ? `パチンコ ${machineInfo.pachinko_total}台` : null,
                    machineInfo?.slot_total ? `スロット ${machineInfo.slot_total}台` : null,
                  ].filter(Boolean).join("　/　")}
                  {(machineInfo?.pachinko_total || 0) + (machineInfo?.slot_total || 0) > 0 && (
                    <span style={{ color: C.muted, marginLeft: 8, fontSize: 12 }}>
                      （合計 {(machineInfo?.pachinko_total || 0) + (machineInfo?.slot_total || 0)}台）
                    </span>
                  )}
                </InfoRow>
              )}

              {/* 店舗写真 */}
              {machineInfo?.photo_url && (
                <div style={{ marginTop: 16 }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={machineInfo.photo_url}
                    alt={store.name}
                    style={{ maxWidth: "100%", maxHeight: 220, objectFit: "cover", borderRadius: 6, border: `1px solid ${C.border}`, display: "block" }}
                    loading="lazy"
                    onError={e => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                  />
                </div>
              )}

              {/* リンクボタン */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 20 }}>
                {(store.hp_url || machineInfo?.hp_url) && (
                  <a href={store.hp_url || machineInfo?.hp_url} target="_blank" rel="noopener noreferrer" style={btnStyle(C.red)}>
                    🌐 公式サイト
                  </a>
                )}
                {(store.x_url || machineInfo?.x_url) && (
                  <a href={store.x_url || machineInfo?.x_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#000")}>
                    𝕏 X（旧Twitter）
                  </a>
                )}
                {machineInfo?.line_url && (
                  <a href={machineInfo.line_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#06C755")}>
                    💬 LINE
                  </a>
                )}
                {store.map_url && (
                  <a href={store.map_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#4285f4")}>
                    🗺 地図を見る
                  </a>
                )}
                {(store.floor_map_url || machineInfo?.floor_map_url) && (
                  <a href={store.floor_map_url || machineInfo?.floor_map_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#888")}>
                    🏢 フロアマップ
                  </a>
                )}
              </div>

              {/* データなし */}
              {!store.address && !machineInfo?.address && !machineInfo?.hours && !store.hp_url && !store.x_url && (
                <div style={{ textAlign: "center", padding: "32px 0", color: C.muted }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
                  <div style={{ fontSize: 13 }}>基本情報はまだ登録されていません</div>
                </div>
              )}
            </div>
          )}

          {/* ── パチンコ台数 ── */}
          {activeTab === "pachinko" && (
            <div>
              {/* 合計 */}
              <div style={{
                display: "flex", alignItems: "baseline", gap: 8, marginBottom: 20,
                paddingBottom: 16, borderBottom: `1px solid ${C.border}`,
              }}>
                <span style={{ fontSize: 13, color: C.sub }}>パチンコ合計</span>
                <span style={{ fontSize: 36, fontWeight: 900, color: "#663300", lineHeight: 1 }}>
                  {machineInfo?.pachinko_total}
                </span>
                <span style={{ fontSize: 16, color: C.sub }}>台</span>
              </div>

              {/* 貸し玉別内訳 */}
              {machineInfo?.pachinko && machineInfo.pachinko.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {machineInfo.pachinko.map((r, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "12px 16px", background: "#fff9f0",
                      border: "1px solid #f5d090", borderRadius: 6,
                    }}>
                      <span style={{ fontSize: 14, fontWeight: 700, color: "#996600", minWidth: 80 }}>
                        {r.rate}
                      </span>
                      <div style={{ flex: 1, background: "#f5d090", borderRadius: 3, height: 8, overflow: "hidden" }}>
                        <div style={{
                          height: "100%", borderRadius: 3,
                          background: "#cc7700",
                          width: machineInfo?.pachinko_total
                            ? `${Math.round(r.count / machineInfo.pachinko_total * 100)}%`
                            : "0%",
                        }} />
                      </div>
                      <span style={{ fontSize: 18, fontWeight: 900, color: "#663300", minWidth: 60, textAlign: "right" }}>
                        {r.count}<span style={{ fontSize: 12, marginLeft: 2 }}>台</span>
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "24px 0", color: C.muted, fontSize: 13 }}>
                  内訳データなし
                </div>
              )}

              {/* 新台（パチンコ） */}
              {machineInfo?.new_machines && machineInfo.new_machines.filter(m => m.type === "pachinko" || !m.type).length > 0 && (
                <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.sub, marginBottom: 10 }}>
                    🆕 新台・注目機種
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {machineInfo.new_machines
                      .filter(m => m.type === "pachinko" || !m.type)
                      .map((m, i) => (
                        <span key={i} style={{
                          fontSize: 12, padding: "4px 12px", borderRadius: 4,
                          background: "#fff5e8", color: "#663300",
                          border: "1px solid #f5c060",
                        }}>
                          {m.name}
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── パチスロ台数 ── */}
          {activeTab === "slot" && (
            <div>
              {/* 合計 */}
              <div style={{
                display: "flex", alignItems: "baseline", gap: 8, marginBottom: 20,
                paddingBottom: 16, borderBottom: `1px solid ${C.border}`,
              }}>
                <span style={{ fontSize: 13, color: C.sub }}>パチスロ合計</span>
                <span style={{ fontSize: 36, fontWeight: 900, color: "#002266", lineHeight: 1 }}>
                  {machineInfo?.slot_total}
                </span>
                <span style={{ fontSize: 16, color: C.sub }}>台</span>
              </div>

              {/* 貸しコイン別内訳 */}
              {machineInfo?.slot && machineInfo.slot.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {machineInfo.slot.map((r, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "12px 16px", background: "#f0f6ff",
                      border: "1px solid #88aadd", borderRadius: 6,
                    }}>
                      <span style={{ fontSize: 14, fontWeight: 700, color: "#0044aa", minWidth: 80 }}>
                        {r.rate}
                      </span>
                      <div style={{ flex: 1, background: "#c0d8f0", borderRadius: 3, height: 8, overflow: "hidden" }}>
                        <div style={{
                          height: "100%", borderRadius: 3,
                          background: "#2266cc",
                          width: machineInfo?.slot_total
                            ? `${Math.round(r.count / machineInfo.slot_total * 100)}%`
                            : "0%",
                        }} />
                      </div>
                      <span style={{ fontSize: 18, fontWeight: 900, color: "#002266", minWidth: 60, textAlign: "right" }}>
                        {r.count}<span style={{ fontSize: 12, marginLeft: 2 }}>台</span>
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "24px 0", color: C.muted, fontSize: 13 }}>
                  内訳データなし
                </div>
              )}

              {/* 新台（スロット） */}
              {machineInfo?.new_machines && machineInfo.new_machines.filter(m => m.type === "slot").length > 0 && (
                <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.sub, marginBottom: 10 }}>
                    🆕 新台・注目機種
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {machineInfo.new_machines
                      .filter(m => m.type === "slot")
                      .map((m, i) => (
                        <span key={i} style={{
                          fontSize: 12, padding: "4px 12px", borderRadius: 4,
                          background: "#f0f8ff", color: "#002266",
                          border: "1px solid #88aadd",
                        }}>
                          {m.name}
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── 最新情報（イベント） ── */}
          {activeTab === "events" && (
            <div>
              {/* 今後のイベント */}
              {upcomingEvents.length > 0 && (
                <section style={{ marginBottom: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                    <div style={{ width: 4, height: 18, background: "#007700", borderRadius: 2 }} />
                    <h2 style={{ fontSize: 15, fontWeight: 900, color: "#333", margin: 0 }}>
                      今後のイベント（{upcomingEvents.length}件）
                    </h2>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {upcomingEvents.map(ev => (
                      <EventCard
                        key={ev.id}
                        ev={ev}
                        upcoming
                        expanded={expandedIds.has(ev.id)}
                        onToggle={() => toggleExpand(ev.id)}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* 過去のイベント */}
              {pastEvents.length > 0 && (
                <section>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                    <div style={{ width: 4, height: 18, background: C.muted, borderRadius: 2 }} />
                    <h2 style={{ fontSize: 15, fontWeight: 900, color: "#333", margin: 0 }}>
                      過去のイベント（{pastEvents.length}件）
                    </h2>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {pastEvents.slice(0, 50).map(ev => (
                      <EventCard
                        key={ev.id}
                        ev={ev}
                        upcoming={false}
                        expanded={expandedIds.has(ev.id)}
                        onToggle={() => toggleExpand(ev.id)}
                      />
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
          )}
        </div>

        {/* フッターリンク */}
        <div style={{ paddingTop: 4, display: "flex", gap: 16 }}>
          <Link href="/stores" style={{ color: C.red, fontSize: 13, fontWeight: 700, textDecoration: "none" }}>← ホール検索に戻る</Link>
          <Link href="/" style={{ color: C.muted, fontSize: 13, textDecoration: "none" }}>トップへ →</Link>
        </div>
      </div>

      <footer style={{ textAlign: "center", padding: "20px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}

// ── ヘルパーコンポーネント ──────────────────────────────────────

function InfoRow({ icon, label, children }: { icon: string; label: string; children: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", gap: 12, alignItems: "flex-start",
      padding: "10px 0", borderBottom: `1px solid ${C.border}`,
    }}>
      <span style={{ fontSize: 16, flexShrink: 0, width: 24, textAlign: "center" }}>{icon}</span>
      <span style={{ fontSize: 13, color: C.muted, fontWeight: 700, flexShrink: 0, width: 80 }}>{label}</span>
      <span style={{ fontSize: 13, color: C.sub, flex: 1 }}>{children}</span>
    </div>
  );
}

function btnStyle(bg: string): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: 5,
    background: bg, color: "#fff",
    padding: "7px 14px", borderRadius: 5, fontSize: 13, fontWeight: 700,
    textDecoration: "none",
  };
}

function EventCard({
  ev, upcoming, expanded, onToggle,
}: {
  ev: Event; upcoming: boolean; expanded: boolean; onToggle: () => void;
}) {
  const badge = getEventBadge(ev.event);
  const today = isToday(ev.date);
  const detailLines = (ev.detail || "").split("\n").filter(l => l.trim());
  const hasLongDetail = detailLines.length > 4 || (ev.detail || "").length > 200;
  const displayLines = expanded ? detailLines : detailLines.slice(0, 4);

  const castClean = (ev.cast || "").replace(/[）)』」>]/g, "").trim();
  const validCast = castClean.length >= 2 && castClean.length <= 30 && !castClean.match(/^[ぁ-ん]{1,2}$/);

  return (
    <div style={{
      background: upcoming ? C.white : "#fafafa",
      border: `1px solid ${today ? "#00aa44" : upcoming ? "#ddeedd" : C.border}`,
      borderRadius: 7,
      borderLeft: today ? "4px solid #00aa44" : upcoming ? `4px solid #88cc88` : `4px solid ${C.dim}`,
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
            <span style={{
              background: badge.bg, color: badge.color,
              fontSize: 11, fontWeight: 700,
              padding: "3px 10px", borderRadius: 4,
              border: `1px solid ${badge.border}`,
              whiteSpace: "nowrap",
            }}>
              {ev.event}
            </span>
          )}

          {validCast && (
            <span style={{
              background: "#f5f0ff", color: "#6600cc",
              fontSize: 11, fontWeight: 700,
              padding: "3px 10px", borderRadius: 4,
              border: "1px solid #ccaaee",
              whiteSpace: "nowrap",
            }}>
              🎤 {castClean}
            </span>
          )}

          {ev.highlight && (
            <span style={{
              background: "#fffbe8", color: "#886600",
              fontSize: 10, fontWeight: 700,
              padding: "2px 8px", borderRadius: 4,
              border: "1px solid #ddcc66",
            }}>
              ★ 注目
            </span>
          )}
        </div>

        {ev.image_url && (
          <div style={{ marginBottom: 8 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={ev.image_url}
              alt=""
              style={{ maxWidth: "100%", maxHeight: 300, borderRadius: 6, border: `1px solid ${C.border}`, display: "block" }}
              loading="lazy"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
            />
          </div>
        )}

        {detailLines.length > 0 && (
          <div style={{
            fontSize: 13, color: upcoming ? C.sub : C.muted,
            lineHeight: 1.75, background: "#fafafa",
            border: `1px solid ${C.border}`, borderRadius: 5,
            padding: "10px 12px",
          }}>
            {displayLines.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
            {hasLongDetail && (
              <button
                onClick={onToggle}
                style={{
                  marginTop: 6, background: "none", border: "none",
                  color: C.red, fontSize: 12, cursor: "pointer", padding: 0, fontWeight: 700,
                }}
              >
                {expanded ? "▲ 折りたたむ" : `▼ 続きを見る（全${detailLines.length}行）`}
              </button>
            )}
          </div>
        )}

        {ev.x_url && (
          <div style={{ marginTop: 8 }}>
            <a
              href={ev.x_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                fontSize: 12, color: "#555", textDecoration: "none",
                background: "#f5f5f5", border: `1px solid ${C.border}`,
                borderRadius: 4, padding: "4px 10px",
              }}
            >
              𝕏 元ツイートを見る →
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
