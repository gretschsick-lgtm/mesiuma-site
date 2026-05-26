"use client";

import { useEffect, useState, useMemo, useCallback } from "react";

type CompleteEntry = {
  id: string;
  date: string;
  time: string;
  store: string;
  machine: string;
  machine_type?: "slot" | "pachinko";
  slot_number: string;
  text: string;
  images?: string[];
  image_url?: string;
  video_url?: string;
  x_url: string;
  collected_at: string;
};

type RankItem = { rank: number; name: string; count: number; x_url?: string };

// チェーン名のみ（支店名なし）判定
const CHAIN_ONLY_NAMES = new Set(["マルハン","キコーナ","ダイナム","楽園","ガイア","キャッスル","ガーデン","ゼント","ZENT","エスパス"]);
function isChainOnly(name: string) { return CHAIN_ONLY_NAMES.has(name) || name.length <= 4; }

type MonthlyData = {
  month: string;
  label: string;
  stores: RankItem[];
  slot_machines: RankItem[];
  pachinko_machines: RankItem[];
  total_count: number;
};

type RankingData = {
  generated_at: string;
  monthly: MonthlyData[];
  total: {
    stores: RankItem[];
    slot_machines: RankItem[];
    pachinko_machines: RankItem[];
    total_count: number;
  };
};

const C = {
  bg: "#f5f5f5",
  white: "#ffffff",
  border: "#e0e0e0",
  red: "#e60000",
  gold: "#c9910a",
  text: "#222222",
  sub: "#555555",
  muted: "#888888",
  dim: "#ddd",
};

const RANK_COLORS = ["#f5c518", "#b0b0b0", "#cd7f32", "#4a90d9", "#4a90d9",
  "#aaaaaa", "#aaaaaa", "#aaaaaa", "#aaaaaa", "#aaaaaa"];
const RANK_LABELS = ["🥇", "🥈", "🥉", "4位", "5位", "6位", "7位", "8位", "9位", "10位"];

const DOW = ["日", "月", "火", "水", "木", "金", "土"];

function fmtDate(dateStr: string) {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const isTodayDate = d.toDateString() === today.toDateString();
  const isYesterday = d.toDateString() === yesterday.toDateString();
  const label = isTodayDate ? "今日" : isYesterday ? "昨日" : null;
  const mmdd = `${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})`;
  return label ? `${label} ${mmdd}` : mmdd;
}

function fmtMonth(ym: string) {
  const [y, m] = ym.split("-");
  return `${y}年${parseInt(m)}月`;
}

function CompleteCard({ entry }: { entry: CompleteEntry }) {
  return (
    <div style={{
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: 10,
      overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
    }}>
      <div style={{ padding: "10px 12px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7, flexWrap: "wrap" }}>
          <span style={{
            background: C.gold, color: "#fff",
            fontSize: 10, fontWeight: 700, padding: "2px 7px",
            borderRadius: 20, letterSpacing: 0.3, whiteSpace: "nowrap",
          }}>
            🏆 コンプリート
          </span>
          {entry.machine_type === "pachinko" && (
            <span style={{
              background: "#e8f5e9", color: "#2e7d32",
              fontSize: 10, fontWeight: 700, padding: "2px 7px",
              borderRadius: 20, border: "1px solid #a5d6a7", whiteSpace: "nowrap",
            }}>
              🎯 パチンコ
            </span>
          )}
          {entry.slot_number && (
            <span style={{
              background: "#f0f8ff", color: "#0055cc",
              fontSize: 10, fontWeight: 700, padding: "2px 7px",
              borderRadius: 4, border: "1px solid #bbddff", whiteSpace: "nowrap",
            }}>
              {entry.slot_number}番台
            </span>
          )}
          {entry.video_url && (
            <span style={{
              background: "#1a1a2e", color: "#fff",
              fontSize: 10, fontWeight: 700, padding: "2px 7px",
              borderRadius: 4, whiteSpace: "nowrap",
            }}>
              🎬 動画
            </span>
          )}
          {entry.time && (
            <span style={{ fontSize: 11, color: C.muted, marginLeft: "auto" }}>{entry.time}</span>
          )}
        </div>

        {entry.machine && (
          <div style={{ fontSize: 15, fontWeight: 800, color: C.text, marginBottom: 3, lineHeight: 1.4 }}>
            {entry.machine}
          </div>
        )}

        {entry.store && (
          <div style={{ fontSize: 12, color: C.sub, marginBottom: 7, display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ flexShrink: 0 }}>📍</span>
            <span style={{ fontWeight: 600 }}>{entry.store}</span>
          </div>
        )}

        {entry.text && (
          <div style={{
            fontSize: 11, color: C.muted, lineHeight: 1.65, marginBottom: 9,
            display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
          } as React.CSSProperties}>
            {entry.text}
          </div>
        )}

        {/* 動画（mp4 は inline 再生、m3u8 は X リンクのサムネ表示） */}
        {entry.video_url && entry.video_url.includes(".mp4") ? (
          <video
            src={entry.video_url}
            controls
            muted
            playsInline
            preload="metadata"
            style={{
              width: "100%", display: "block",
              maxHeight: 300, borderRadius: 6, marginBottom: 9,
              background: "#000",
            }}
          />
        ) : entry.video_url ? (
          /* HLS (m3u8) → サムネ + X へのリンク */
          <a href={entry.x_url} target="_blank" rel="noopener noreferrer" style={{ display: "block", textDecoration: "none", marginBottom: 9 }}>
            <div style={{
              position: "relative", borderRadius: 6, overflow: "hidden",
              background: "#111",
            }}>
              {entry.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={entry.image_url} alt="" style={{ width: "100%", display: "block", maxHeight: 260, objectFit: "cover", opacity: 0.75 }} />
              )}
              <div style={{
                position: entry.image_url ? "absolute" : "relative",
                inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                padding: entry.image_url ? 0 : "28px 0",
              }}>
                <div style={{
                  width: 52, height: 52, borderRadius: "50%",
                  background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff"><path d="M8 5v14l11-7z"/></svg>
                </div>
              </div>
            </div>
          </a>
        ) : entry.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={entry.image_url}
            alt=""
            style={{
              width: "100%", display: "block",
              maxHeight: 260, objectFit: "cover",
              borderRadius: 6, marginBottom: 9,
            }}
            loading="lazy"
          />
        ) : null}

        {entry.x_url && (
          <a href={entry.x_url} target="_blank" rel="noopener noreferrer" style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            fontSize: 11, color: "#1d9bf0", textDecoration: "none",
            padding: "4px 10px", border: "1px solid #1d9bf0", borderRadius: 20,
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Xで見る
          </a>
        )}
      </div>
    </div>
  );
}

function RankingRow({ item, type }: { item: RankItem; type: "store" | "machine" }) {
  const isTop3 = item.rank <= 3;
  const canLink = type === "store" && item.x_url && !isChainOnly(item.name);
  const chainOnly = type === "store" && isChainOnly(item.name);

  const inner = (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "9px 12px",
      background: isTop3 ? (item.rank === 1 ? "linear-gradient(90deg,#fffbea,#fff9e0)" : C.white) : C.white,
      borderBottom: `1px solid ${C.border}`,
      cursor: canLink ? "pointer" : "default",
      boxSizing: "border-box",
      width: "100%",
    }}>
      {/* 順位バッジ */}
      <div style={{
        width: 30, height: 30, borderRadius: "50%",
        background: RANK_COLORS[item.rank - 1],
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: item.rank <= 3 ? 15 : 12,
        fontWeight: 800, color: "#fff",
        flexShrink: 0,
      }}>
        {item.rank <= 3 ? RANK_LABELS[item.rank - 1] : item.rank}
      </div>
      {/* 名前 + X リンク（2行） */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: 700,
          color: canLink ? "#1d9bf0" : C.text,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          lineHeight: 1.3,
        }}>
          {item.name}
          {chainOnly && <span style={{ fontSize: 9, color: C.muted, fontWeight: 400, marginLeft: 4 }}>（支店不明）</span>}
        </div>
        {canLink && <div style={{ fontSize: 10, color: "#1d9bf0", marginTop: 2 }}>𝕏 アカウントを見る →</div>}
      </div>
      {/* 件数（右端・固定幅） */}
      <div style={{
        flexShrink: 0,
        textAlign: "right",
        width: 52,
      }}>
        <span style={{
          fontSize: 18, fontWeight: 900,
          color: isTop3 ? C.gold : C.sub,
          lineHeight: 1,
        }}>
          {item.count}
        </span>
        <span style={{ fontSize: 10, color: C.muted, marginLeft: 2 }}>回</span>
      </div>
    </div>
  );

  if (canLink) {
    return (
      <a href={item.x_url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>
        {inner}
      </a>
    );
  }
  return inner;
}

function MachineTabs({
  data,
  machineTabKey,
  setMachineTabKey,
}: {
  data: MonthlyData | RankingData["total"];
  machineTabKey: "slot" | "pachinko";
  setMachineTabKey: (k: "slot" | "pachinko") => void;
}) {
  const hasPachinko = (data.pachinko_machines?.length ?? 0) > 0;
  const list = machineTabKey === "pachinko" ? (data.pachinko_machines ?? []) : (data.slot_machines ?? []);
  return (
    <div>
      <div style={{ borderBottom: `1px solid ${C.border}`, background: "#f7f7f7", padding: "8px 12px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
          🎰 機種別TOP10
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", background: "#e2e2e2", borderRadius: 10, padding: 3, gap: 3 }}>
          {(["slot", "pachinko"] as const).map(k => (
            <button key={k} onClick={() => setMachineTabKey(k)}
              style={{
                padding: "9px 0", fontSize: 13, fontWeight: 800,
                border: "none", borderRadius: 8,
                background: machineTabKey === k ? (k === "slot" ? C.red : "#2563eb") : "transparent",
                color: machineTabKey === k ? "#fff" : k === "pachinko" && !hasPachinko ? C.dim : "#555",
                cursor: "pointer", transition: "all 0.15s", letterSpacing: 0.5,
              }}
            >
              {k === "slot" ? "🎰 スロット" : "🎯 パチンコ"}
            </button>
          ))}
        </div>
      </div>
      {list.length > 0 ? (
        list.map(item => <RankingRow key={item.rank} item={item} type="machine" />)
      ) : (
        <div style={{ padding: "20px", color: C.muted, fontSize: 12, textAlign: "center" }}>データなし</div>
      )}
    </div>
  );
}

function RankingSection({ ranking, isNarrow }: { ranking: RankingData; isNarrow: boolean }) {
  const latestMonth = ranking.monthly[0];
  const currentMonth = latestMonth?.month ?? "";
  const monthData = latestMonth;

  // 月セレクター
  const availableMonths = ranking.monthly.map(m => m.month);
  const [selectedMonth, setSelectedMonth] = useState(currentMonth);
  const selData = ranking.monthly.find(m => m.month === selectedMonth);

  const [monthMachineTab, setMonthMachineTab] = useState<"slot" | "pachinko">("slot");
  const [totalMachineTab, setTotalMachineTab] = useState<"slot" | "pachinko">("slot");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* 月間ランキング */}
      <div style={{
        background: C.white, borderRadius: 12,
        border: `1px solid ${C.border}`,
        overflow: "hidden",
        boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      }}>
        <div style={{
          background: "linear-gradient(90deg,#1a1a2e,#0f3460)",
          color: "#fff", padding: "14px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: 8,
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800 }}>📅 月間ランキング</div>
            <div style={{ fontSize: 11, color: "#aab", marginTop: 2 }}>
              {monthData ? `${fmtMonth(currentMonth)}: ${monthData.total_count}件` : "データなし"}
            </div>
          </div>
          {availableMonths.length > 1 && (
            <select
              value={selectedMonth}
              onChange={e => setSelectedMonth(e.target.value)}
              style={{
                fontSize: 12, padding: "4px 8px", borderRadius: 6,
                border: "1px solid #555", background: "#1a1a2e", color: "#fff",
                cursor: "pointer",
              }}
            >
              {availableMonths.map(ym => (
                <option key={ym} value={ym}>{fmtMonth(ym)}</option>
              ))}
            </select>
          )}
        </div>

        {selData ? (
          <div style={{ display: "grid", gridTemplateColumns: isNarrow ? "1fr" : "1fr 1fr", gap: 0 }}>
            {/* 店舗別 */}
            <div style={{ minWidth: 0 }}>
              <div style={{
                padding: "8px 14px", fontSize: 11, fontWeight: 700,
                color: C.sub, background: "#fafafa",
                borderBottom: `1px solid ${C.border}`,
                borderRight: isNarrow ? "none" : `1px solid ${C.border}`,
              }}>
                🏪 店舗別TOP10
              </div>
              {selData.stores.length > 0 ? (
                selData.stores.map(item => (
                  <div key={item.rank} style={{ borderRight: isNarrow ? "none" : `1px solid ${C.border}` }}>
                    <RankingRow item={item} type="store" />
                  </div>
                ))
              ) : (
                <div style={{ padding: "20px", color: C.muted, fontSize: 12, textAlign: "center" }}>データなし</div>
              )}
            </div>
            {/* 機種別 */}
            <div style={{ minWidth: 0 }}>
              <MachineTabs data={selData} machineTabKey={monthMachineTab} setMachineTabKey={setMonthMachineTab} />
            </div>
          </div>
        ) : (
          <div style={{ padding: "30px", color: C.muted, fontSize: 13, textAlign: "center" }}>
            {fmtMonth(selectedMonth)}のデータがありません
          </div>
        )}
      </div>

      {/* トータルランキング */}
      <div style={{
        background: C.white, borderRadius: 12,
        border: `1px solid ${C.border}`,
        overflow: "hidden",
        boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
      }}>
        <div style={{
          background: "linear-gradient(90deg,#7b2d00,#c9910a)",
          color: "#fff", padding: "14px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800 }}>🏆 トータルランキング</div>
            <div style={{ fontSize: 11, color: "#ffe", marginTop: 2 }}>
              累計 {ranking.total.total_count}件のコンプリート報告より
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: isNarrow ? "1fr" : "1fr 1fr", gap: 0 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{
              padding: "8px 14px", fontSize: 11, fontWeight: 700,
              color: C.sub, background: "#fafafa",
              borderBottom: `1px solid ${C.border}`,
              borderRight: isNarrow ? "none" : `1px solid ${C.border}`,
            }}>
              🏪 店舗別TOP10
            </div>
            {ranking.total.stores.length > 0 ? (
              ranking.total.stores.map(item => (
                <div key={item.rank} style={{ borderRight: isNarrow ? "none" : `1px solid ${C.border}` }}>
                  <RankingRow item={item} type="store" />
                </div>
              ))
            ) : (
              <div style={{ padding: "20px", color: C.muted, fontSize: 12, textAlign: "center" }}>データ収集中...</div>
            )}
          </div>
          <div style={{ minWidth: 0 }}>
            <MachineTabs data={ranking.total} machineTabKey={totalMachineTab} setMachineTabKey={setTotalMachineTab} />
          </div>
        </div>

        <div style={{ padding: "8px 14px", fontSize: 10, color: C.muted, background: "#fafafa", borderTop: `1px solid ${C.border}` }}>
          最終更新: {ranking.generated_at.replace("T", " ").slice(0, 16)}
        </div>
      </div>
    </div>
  );
}

export default function CompletePage() {
  const [entries, setEntries] = useState<CompleteEntry[]>([]);
  const [ranking, setRanking] = useState<RankingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<"feed" | "ranking">("feed");
  const [feedFilter, setFeedFilter] = useState<"all" | "slot" | "pachinko">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const check = () => setIsNarrow(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [resEntries, resRanking] = await Promise.all([
        fetch(`/complete_info.json?t=${Date.now()}`),
        fetch(`/complete_ranking.json?t=${Date.now()}`),
      ]);
      const data: CompleteEntry[] = await resEntries.json();
      setEntries(data);
      if (resRanking.ok) {
        const rankData: RankingData = await resRanking.json();
        setRanking(rankData);
      }
      setLastUpdated(new Date());
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(() => loadData(true), 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, []); // eslint-disable-line

  // 日付ごとにグループ化（機種名あるもののみ・新しい順）
  const grouped = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const map = new Map<string, CompleteEntry[]>();
    for (const e of entries) {
      if (!e.machine || !e.machine.trim()) continue;
      if (feedFilter === "slot" && e.machine_type === "pachinko") continue;
      if (feedFilter === "pachinko" && e.machine_type !== "pachinko") continue;
      if (q) {
        const hit =
          e.machine.toLowerCase().includes(q) ||
          e.store.toLowerCase().includes(q) ||
          (e.text || "").toLowerCase().includes(q);
        if (!hit) continue;
      }
      const d = e.date || "";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(e);
    }
    for (const [, list] of map) {
      list.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
    }
    return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  }, [entries, feedFilter, searchQuery]);

  const todayStr = (() => {
    const d = new Date(Date.now() + 9 * 60 * 60 * 1000);
    return d.toISOString().slice(0, 10);
  })();
  const todayCount = entries.filter(e => e.date === todayStr && e.machine && e.machine.trim()).length;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <div style={{
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%)",
        color: "#fff", padding: "16px 16px 0",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <a href="/" style={{ color: "#aaa", fontSize: 12, textDecoration: "none" }}>← トップ</a>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "8px 0 12px" }}>
            <div>
              <h1 style={{ margin: "0 0 2px", fontSize: 20, fontWeight: 800 }}>
                🏆 コンプリート情報
              </h1>
              <p style={{ margin: 0, fontSize: 12, color: "#99aacc" }}>
                店舗公式アカウントのコンプリート発生情報
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              {todayCount > 0 && (
                <div style={{ fontSize: 22, fontWeight: 900, color: "#ffd700" }}>
                  {todayCount}<span style={{ fontSize: 12, fontWeight: 400, color: "#aaa", marginLeft: 3 }}>件</span>
                </div>
              )}
              <div style={{ fontSize: 10, color: "#99aacc" }}>本日</div>
            </div>
          </div>

          {/* タブ */}
          <div style={{ display: "flex", gap: 4 }}>
            {([
              { key: "feed", label: "📋 コンプリート情報" },
              { key: "ranking", label: "🏆 ランキング" },
            ] as const).map(t => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                style={{
                  padding: "8px 16px", fontSize: 13, fontWeight: 700,
                  border: "none", borderRadius: "8px 8px 0 0",
                  cursor: "pointer",
                  background: tab === t.key ? C.bg : "rgba(255,255,255,0.12)",
                  color: tab === t.key ? C.text : "rgba(255,255,255,0.8)",
                  transition: "all 0.15s",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 更新バー */}
      <div style={{
        background: C.white, borderBottom: `1px solid ${C.border}`,
        padding: "8px 16px", position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 13, color: C.text, fontWeight: 700 }}>
            {searchQuery.trim()
              ? <>
                  <span style={{ color: C.red }}>
                    {grouped.reduce((n, [, list]) => n + list.length, 0)}件
                  </span>
                  <span style={{ fontSize: 11, color: C.muted, fontWeight: 400, marginLeft: 4 }}>
                    ヒット / 全{entries.length}件
                  </span>
                </>
              : <>
                  全 {entries.length} 件
                  {grouped.length > 1 && (
                    <span style={{ fontSize: 11, color: C.muted, fontWeight: 400, marginLeft: 8 }}>
                      ({grouped.length}日分)
                    </span>
                  )}
                </>
            }
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {lastUpdated && (
              <span style={{ fontSize: 11, color: C.muted }}>
                {lastUpdated.getHours()}:{String(lastUpdated.getMinutes()).padStart(2, "0")} 更新
              </span>
            )}
            <button
              onClick={() => loadData(true)}
              disabled={refreshing}
              style={{
                padding: "5px 12px", fontSize: 12, fontWeight: 700,
                background: refreshing ? C.dim : C.red, color: "#fff",
                border: "none", borderRadius: 20, cursor: refreshing ? "default" : "pointer",
              }}
            >
              {refreshing ? "更新中..." : "🔄 更新"}
            </button>
          </div>
        </div>
        {/* フィードフィルター + 検索（feedタブ表示時のみ） */}
        {tab === "feed" && (
          <div style={{ maxWidth: 900, margin: "6px auto 0", display: "flex", flexDirection: "column", gap: 6 }}>
            {/* 検索ボックス */}
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)",
                fontSize: 14, pointerEvents: "none", color: C.muted,
              }}>🔍</span>
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="機種名・店舗名で検索..."
                style={{
                  width: "100%", boxSizing: "border-box",
                  padding: "7px 34px 7px 32px",
                  fontSize: 13, borderRadius: 20,
                  border: `1px solid ${searchQuery ? C.red : C.border}`,
                  outline: "none", background: C.white, color: C.text,
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  style={{
                    position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer",
                    fontSize: 13, color: C.muted, padding: "2px 4px",
                  }}
                >✕</button>
              )}
            </div>
            {/* タイプフィルター */}
            <div style={{ display: "flex", gap: 6 }}>
              {([
                { key: "all", label: "すべて" },
                { key: "slot", label: "🎰 パチスロ" },
                { key: "pachinko", label: "🎯 パチンコ" },
              ] as const).map(f => (
                <button
                  key={f.key}
                  onClick={() => setFeedFilter(f.key)}
                  style={{
                    padding: "3px 12px", fontSize: 11, fontWeight: 700,
                    border: `1px solid ${feedFilter === f.key ? C.red : C.border}`,
                    borderRadius: 20,
                    background: feedFilter === f.key ? C.red : C.white,
                    color: feedFilter === f.key ? "#fff" : C.sub,
                    cursor: "pointer",
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* コンテンツ */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "14px 12px 60px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
            読み込み中...
          </div>
        ) : tab === "ranking" ? (
          ranking ? (
            <RankingSection ranking={ranking} isNarrow={isNarrow} />
          ) : (
            <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
              ランキングデータを取得中...
            </div>
          )
        ) : grouped.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>{searchQuery.trim() ? "🔍" : "🎰"}</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 6 }}>
              {searchQuery.trim() ? `「${searchQuery}」に一致する情報がありません` : "コンプリート情報はまだありません"}
            </div>
            <div style={{ fontSize: 12, color: C.muted }}>
              {searchQuery.trim()
                ? <button onClick={() => setSearchQuery("")} style={{ background: "none", border: "none", color: C.red, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>検索をクリア</button>
                : "スクリプト実行後に反映されます"
              }
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {grouped.map(([date, dateEntries]) => {
              const isToday = date === todayStr;
              const isNew = date >= todayStr;
              return (
                <div key={date}>
                  {/* 日付ヘッダー */}
                  <div style={{
                    display: "flex", alignItems: "center", gap: 10, marginBottom: 12,
                  }}>
                    <div style={{
                      background: isToday
                        ? "linear-gradient(90deg, #e60000, #ff4444)"
                        : isNew
                          ? C.gold
                          : "#888",
                      color: "#fff",
                      fontSize: 14, fontWeight: 800,
                      padding: "5px 14px", borderRadius: 20,
                      whiteSpace: "nowrap",
                    }}>
                      {isToday && "📅 "}
                      {fmtDate(date)}
                    </div>
                    <span style={{
                      fontSize: 12, color: C.muted,
                      background: C.white, border: `1px solid ${C.border}`,
                      padding: "3px 10px", borderRadius: 20,
                    }}>
                      {dateEntries.length}件
                    </span>
                    <div style={{ flex: 1, height: 1, background: C.border }} />
                  </div>

                  {/* カードグリッド */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                    gap: 12,
                  }}>
                    {dateEntries.map(entry => (
                      <CompleteCard key={entry.id} entry={entry} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ textAlign: "center", padding: "16px", fontSize: 11, color: C.muted, borderTop: `1px solid ${C.border}` }}>
        © メシウマ稼働株式会社
      </div>
    </div>
  );
}
