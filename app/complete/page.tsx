"use client";

import { useEffect, useState, useMemo, useCallback } from "react";

type CompleteEntry = {
  id: string;
  date: string;
  time: string;
  store: string;
  machine: string;
  slot_number: string;
  text: string;
  images: string[];
  image_url: string;
  x_url: string;
  collected_at: string;
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

function CompleteCard({ entry }: { entry: CompleteEntry }) {
  const [imgErr, setImgErr] = useState(false);

  return (
    <div style={{
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: 10,
      overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
    }}>
      {entry.image_url && !imgErr && (
        <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", background: "#f0f0f0", overflow: "hidden" }}>
          <img
            src={entry.image_url}
            alt={`${entry.store} ${entry.machine}`}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={() => setImgErr(true)}
          />
          {entry.time && (
            <span style={{
              position: "absolute", top: 8, right: 8,
              background: "rgba(0,0,0,0.65)", color: "#fff",
              fontSize: 11, fontWeight: 700, padding: "2px 7px",
              borderRadius: 4, backdropFilter: "blur(4px)",
            }}>
              {entry.time}
            </span>
          )}
        </div>
      )}

      <div style={{ padding: "10px 12px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7, flexWrap: "wrap" }}>
          <span style={{
            background: C.gold, color: "#fff",
            fontSize: 10, fontWeight: 700, padding: "2px 7px",
            borderRadius: 20, letterSpacing: 0.3, whiteSpace: "nowrap",
          }}>
            🏆 コンプリート
          </span>
          {entry.slot_number && (
            <span style={{
              background: "#f0f8ff", color: "#0055cc",
              fontSize: 10, fontWeight: 700, padding: "2px 7px",
              borderRadius: 4, border: "1px solid #bbddff", whiteSpace: "nowrap",
            }}>
              {entry.slot_number}番台
            </span>
          )}
          {!entry.image_url && entry.time && (
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

        {entry.images.length > 1 && (
          <div style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(entry.images.length - 1, 3)}, 1fr)`,
            gap: 3, marginBottom: 9,
          }}>
            {entry.images.slice(1, 4).map((img, i) => (
              <img key={i} src={img} alt=""
                style={{ width: "100%", aspectRatio: "1", objectFit: "cover", borderRadius: 4 }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            ))}
          </div>
        )}

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

export default function CompletePage() {
  const [entries, setEntries] = useState<CompleteEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await fetch(`/complete_info.json?t=${Date.now()}`);
      const data: CompleteEntry[] = await res.json();
      setEntries(data);
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

  // 日付ごとにグループ化（新しい順）
  const grouped = useMemo(() => {
    const map = new Map<string, CompleteEntry[]>();
    for (const e of entries) {
      const d = e.date || "";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(e);
    }
    // 各日付内を時刻降順に
    for (const [, list] of map) {
      list.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
    }
    // 日付を新しい順に並べた配列で返す
    return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  }, [entries]);

  // JST (UTC+9) で「今日」を判定
  const todayStr = (() => {
    const d = new Date(Date.now() + 9 * 60 * 60 * 1000);
    return d.toISOString().slice(0, 10);
  })();
  const todayCount = entries.filter(e => e.date === todayStr).length;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <div style={{
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%)",
        color: "#fff", padding: "16px 16px 16px",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <a href="/" style={{ color: "#aaa", fontSize: 12, textDecoration: "none" }}>← トップ</a>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "8px 0 0" }}>
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
        </div>
      </div>

      {/* 更新バー */}
      <div style={{
        background: C.white, borderBottom: `1px solid ${C.border}`,
        padding: "8px 16px", position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 13, color: C.text, fontWeight: 700 }}>
            全 {entries.length} 件
            {grouped.length > 1 && (
              <span style={{ fontSize: 11, color: C.muted, fontWeight: 400, marginLeft: 8 }}>
                ({grouped.length}日分)
              </span>
            )}
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
      </div>

      {/* コンテンツ */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "14px 12px 60px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
            読み込み中...
          </div>
        ) : grouped.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🎰</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 6 }}>
              コンプリート情報はまだありません
            </div>
            <div style={{ fontSize: 12, color: C.muted }}>スクリプト実行後に反映されます</div>
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
        © メシウマ稼働株式会社 — データは自動収集・5分ごと自動更新
      </div>
    </div>
  );
}
