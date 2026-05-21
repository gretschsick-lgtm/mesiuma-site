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
  pachinko?: MachineRate[];
  slot?: MachineRate[];
  pachinko_total?: number;
  slot_total?: number;
  new_machines?: NewMachine[];
  updated_at?: string;
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

const C = {
  bg: "#f0f0f0", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", text: "#222222", sub: "#444444",
  muted: "#888888", dim: "#cccccc",
};

// イベント種別ごとの色設定
function getEventBadge(eventType: string): { color: string; bg: string; border: string } {
  const t = eventType || "";
  if (t.includes("来店")) return { color: "#cc3300", bg: "#fff0ed", border: "#ffbbaa" };
  if (t.includes("取材")) return { color: "#0055bb", bg: "#eef3ff", border: "#aabbee" };
  if (t.includes("撮影") || t.includes("ロケ")) return { color: "#007744", bg: "#edfff5", border: "#aaddc8" };
  if (t.includes("通常稼働")) return { color: "#666", bg: "#f5f5f5", border: "#ddd" };
  // その他は色相ハッシュで割り当て
  const hue = [...t].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  return { color: `hsl(${hue},60%,35%)`, bg: `hsl(${hue},80%,96%)`, border: `hsl(${hue},50%,80%)` };
}

function formatDate(date: string): string {
  // "05/20" → "5月20日"
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
      // 店舗名で機種情報を照合
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

        {/* ===== 店舗情報カード ===== */}
        <div style={{
          background: C.white, border: `1px solid ${C.border}`,
          borderRadius: 8, padding: "20px 24px", marginBottom: 20,
          borderTop: `4px solid ${C.red}`,
        }}>
          <h1 style={{ fontSize: 22, fontWeight: 900, color: C.text, margin: "0 0 12px", lineHeight: 1.3 }}>
            🏪 {store.name}
          </h1>

          {/* バッジ行 */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
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
            {events.length > 0 && (
              <span style={{ background: "#fff0f0", color: C.red, fontSize: 12, padding: "3px 10px", borderRadius: 3, border: `1px solid #ffcccc`, fontWeight: 700 }}>
                イベント実績 {events.length}件
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
          </div>

          {/* 住所 */}
          {store.address && (
            <div style={{ fontSize: 13, color: C.sub, marginBottom: 10, display: "flex", gap: 6, alignItems: "flex-start" }}>
              <span style={{ flexShrink: 0 }}>📮</span>
              <span>{store.address}</span>
            </div>
          )}

          {/* 抽選・整列 */}
          {store.lottery_time && (
            <div style={{
              background: "#fffbe8", border: "1px solid #f0d060", borderRadius: 6,
              padding: "8px 14px", marginBottom: 12,
              display: "inline-flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: "#996600" }}>🎰 整列情報</span>
              <span style={{ fontSize: 13, color: "#664400" }}>
                整列開始：<strong>{store.lottery_time}</strong>
              </span>
            </div>
          )}

          {/* リンクボタン */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
            {store.hp_url && (
              <a href={store.hp_url} target="_blank" rel="noopener noreferrer" style={btnStyle(C.red)}>
                🌐 公式サイト
              </a>
            )}
            {store.x_url && (
              <a href={store.x_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#000")}>
                𝕏 X（旧Twitter）
              </a>
            )}
            {store.map_url && (
              <a href={store.map_url} target="_blank" rel="noopener noreferrer" style={btnStyle("#4285f4")}>
                🗺 地図を見る
              </a>
            )}
          </div>
        </div>

        {/* ===== 台数・機種情報 ===== */}
        {machineInfo && (machineInfo.pachinko_total || machineInfo.slot_total || machineInfo.new_machines?.length) && (
          <div style={{
            background: C.white, border: `1px solid ${C.border}`,
            borderRadius: 8, padding: "16px 20px", marginBottom: 20,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <SectionTitle color="#e67e00">台数・設置機種</SectionTitle>
              {machineInfo.updated_at && (
                <span style={{ fontSize: 10, color: C.muted }}>
                  {machineInfo.updated_at.slice(5, 10).replace("-", "/")} 更新
                </span>
              )}
            </div>

            {/* 営業時間・入場ルール */}
            {(machineInfo.hours || machineInfo.entry_rule) && (
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                {machineInfo.hours && (
                  <span style={{ fontSize: 13, color: C.sub, background: "#f8f8f8", padding: "4px 12px", borderRadius: 4, border: `1px solid ${C.border}` }}>
                    🕐 {machineInfo.hours}
                  </span>
                )}
                {machineInfo.entry_rule && (
                  <span style={{ fontSize: 13, color: C.sub, background: "#f8f8f8", padding: "4px 12px", borderRadius: 4, border: `1px solid ${C.border}` }}>
                    🎟 {machineInfo.entry_rule}
                  </span>
                )}
              </div>
            )}

            {/* パチンコ・スロット台数 */}
            {(machineInfo.pachinko_total || machineInfo.slot_total) && (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
                {(machineInfo.pachinko_total ?? 0) > 0 && (
                  <div style={{
                    background: "#fff5e8", border: "1px solid #f5c060",
                    borderRadius: 6, padding: "10px 16px", minWidth: 140,
                  }}>
                    <div style={{ fontSize: 11, color: "#996600", fontWeight: 700, marginBottom: 4 }}>🎰 パチンコ</div>
                    <div style={{ fontSize: 22, fontWeight: 900, color: "#663300", lineHeight: 1 }}>
                      {machineInfo.pachinko_total}<span style={{ fontSize: 12, marginLeft: 2 }}>台</span>
                    </div>
                    {machineInfo.pachinko && machineInfo.pachinko.length > 0 && (
                      <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {machineInfo.pachinko.map((r, i) => (
                          <span key={i} style={{ fontSize: 11, color: "#664400", background: "#ffeebb", borderRadius: 3, padding: "1px 6px" }}>
                            {r.rate} {r.count}台
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {(machineInfo.slot_total ?? 0) > 0 && (
                  <div style={{
                    background: "#f0f8ff", border: "1px solid #88aadd",
                    borderRadius: 6, padding: "10px 16px", minWidth: 140,
                  }}>
                    <div style={{ fontSize: 11, color: "#0044aa", fontWeight: 700, marginBottom: 4 }}>🎮 スロット</div>
                    <div style={{ fontSize: 22, fontWeight: 900, color: "#002266", lineHeight: 1 }}>
                      {machineInfo.slot_total}<span style={{ fontSize: 12, marginLeft: 2 }}>台</span>
                    </div>
                    {machineInfo.slot && machineInfo.slot.length > 0 && (
                      <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {machineInfo.slot.map((r, i) => (
                          <span key={i} style={{ fontSize: 11, color: "#002266", background: "#d0e8ff", borderRadius: 3, padding: "1px 6px" }}>
                            {r.rate} {r.count}台
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {(machineInfo.pachinko_total || 0) + (machineInfo.slot_total || 0) > 0 && (
                  <div style={{
                    background: "#f5f5f5", border: `1px solid ${C.border}`,
                    borderRadius: 6, padding: "10px 16px", minWidth: 100,
                    display: "flex", flexDirection: "column", justifyContent: "center",
                  }}>
                    <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginBottom: 4 }}>合計</div>
                    <div style={{ fontSize: 22, fontWeight: 900, color: C.text, lineHeight: 1 }}>
                      {(machineInfo.pachinko_total || 0) + (machineInfo.slot_total || 0)}
                      <span style={{ fontSize: 12, marginLeft: 2 }}>台</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 新台機種リスト */}
            {machineInfo.new_machines && machineInfo.new_machines.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.sub, marginBottom: 8 }}>
                  🆕 新台・注目機種（{machineInfo.new_machines.length}機種）
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {machineInfo.new_machines.map((m, i) => (
                    <span key={i} style={{
                      fontSize: 12, padding: "3px 10px", borderRadius: 4,
                      background: m.type === "pachinko" ? "#fff5e8" : m.type === "slot" ? "#f0f8ff" : "#f5f5f5",
                      color: m.type === "pachinko" ? "#663300" : m.type === "slot" ? "#002266" : C.sub,
                      border: `1px solid ${m.type === "pachinko" ? "#f5c060" : m.type === "slot" ? "#88aadd" : C.dim}`,
                    }}>
                      {m.name}
                      {m.type && (
                        <span style={{ marginLeft: 4, fontSize: 10, opacity: 0.7 }}>
                          {m.type === "pachinko" ? "パチ" : "スロ"}
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ===== フロアマップ ===== */}
        {store.floor_map_url && (
          <div style={{
            background: C.white, border: `1px solid ${C.border}`,
            borderRadius: 8, padding: "16px 20px", marginBottom: 20,
          }}>
            <SectionTitle color="#4285f4">フロアマップ</SectionTitle>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={store.floor_map_url}
              alt="フロアマップ"
              style={{ maxWidth: "100%", borderRadius: 6, border: `1px solid ${C.border}`, display: "block" }}
              loading="lazy"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
            />
          </div>
        )}

        {/* ===== 今後のイベント ===== */}
        {upcomingEvents.length > 0 && (
          <section style={{ marginBottom: 20 }}>
            <SectionTitle color="#007700">今後のイベント（{upcomingEvents.length}件）</SectionTitle>
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

        {/* ===== 過去のイベント ===== */}
        {pastEvents.length > 0 && (
          <section style={{ marginBottom: 20 }}>
            <SectionTitle color={C.muted}>過去のイベント（{pastEvents.length}件）</SectionTitle>
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
          <div style={{ textAlign: "center", padding: "48px 0", color: C.muted, background: C.white, borderRadius: 8 }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>📭</div>
            <div style={{ fontSize: 14 }}>イベント情報はまだありません</div>
          </div>
        )}

        <div style={{ marginTop: 24, paddingTop: 16, borderTop: `1px solid ${C.border}`, display: "flex", gap: 16 }}>
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

function btnStyle(bg: string): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: 5,
    background: bg, color: "#fff",
    padding: "7px 14px", borderRadius: 5, fontSize: 13, fontWeight: 700,
    textDecoration: "none",
  };
}

function SectionTitle({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <div style={{ width: 4, height: 18, background: color, borderRadius: 2, flexShrink: 0 }} />
      <h2 style={{ fontSize: 15, fontWeight: 900, color: "#333", margin: 0 }}>{children}</h2>
    </div>
  );
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

  // cast が意味のある文字列か判定（ゴミデータが多い）
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
      {/* 今日のバッジ */}
      {today && (
        <div style={{ background: "#00aa44", color: "#fff", fontSize: 11, fontWeight: 900, padding: "3px 12px", textAlign: "center", letterSpacing: "0.1em" }}>
          ★ 本日開催
        </div>
      )}

      <div style={{ padding: "12px 16px" }}>
        {/* 日付・タグ行 */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          {/* 日付 */}
          <span style={{
            background: upcoming ? (today ? "#00aa44" : "#e8fff0") : "#f5f5f5",
            color: upcoming ? (today ? "#fff" : "#006600") : C.muted,
            fontSize: 13, fontWeight: 900, padding: "3px 10px", borderRadius: 4,
            border: upcoming ? (today ? "none" : "1px solid #aaddaa") : `1px solid ${C.dim}`,
            whiteSpace: "nowrap",
          }}>
            📅 {formatDate(ev.date)}
          </span>

          {/* イベント種別 */}
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

          {/* キャスト */}
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

          {/* ハイライト */}
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

        {/* 画像 */}
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

        {/* 詳細テキスト */}
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

        {/* Xリンク */}
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
