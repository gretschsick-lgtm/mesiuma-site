"use client";

import { useEffect, useState, useMemo } from "react";
import Image from "next/image";

type CompleteEntry = {
  id: string;
  date: string;
  store: string;
  machine: string;
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
  gold: "#d4a017",
  gold2: "#b8860b",
  text: "#222222",
  sub: "#555555",
  muted: "#888888",
};

function dateFmt(dateStr: string) {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const DOW = ["日", "月", "火", "水", "木", "金", "土"];
  return `${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})`;
}

function CompleteCard({ entry }: { entry: CompleteEntry }) {
  const [imgError, setImgError] = useState(false);

  return (
    <div style={{
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: 10,
      overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
    }}>
      {/* 画像エリア */}
      {entry.image_url && !imgError && (
        <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", background: "#f0f0f0" }}>
          <img
            src={entry.image_url}
            alt={`${entry.machine || "コンプリート"} ${entry.store}`}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={() => setImgError(true)}
          />
        </div>
      )}

      {/* コンテンツ */}
      <div style={{ padding: "12px 14px" }}>
        {/* バッジ + 日付 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{
            background: C.gold,
            color: "#fff",
            fontSize: 11,
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: 20,
            letterSpacing: 0.5,
          }}>
            🏆 コンプリート
          </span>
          <span style={{ fontSize: 12, color: C.muted }}>{dateFmt(entry.date)}</span>
        </div>

        {/* 機種名 */}
        {entry.machine && (
          <div style={{
            fontSize: 16,
            fontWeight: 700,
            color: C.text,
            marginBottom: 4,
            lineHeight: 1.4,
          }}>
            {entry.machine}
          </div>
        )}

        {/* 店舗名 */}
        {entry.store && (
          <div style={{
            fontSize: 13,
            color: C.sub,
            marginBottom: 8,
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}>
            <span>📍</span>
            <span>{entry.store}</span>
          </div>
        )}

        {/* ツイート本文（抜粋） */}
        {entry.text && (
          <div style={{
            fontSize: 12,
            color: C.muted,
            lineHeight: 1.6,
            marginBottom: 10,
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          } as React.CSSProperties}>
            {entry.text}
          </div>
        )}

        {/* 複数画像 */}
        {entry.images.length > 1 && (
          <div style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(entry.images.length, 3)}, 1fr)`,
            gap: 4,
            marginBottom: 10,
          }}>
            {entry.images.slice(1, 4).map((img, i) => (
              <img
                key={i}
                src={img}
                alt=""
                style={{
                  width: "100%",
                  aspectRatio: "1",
                  objectFit: "cover",
                  borderRadius: 4,
                }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            ))}
          </div>
        )}

        {/* X リンク */}
        {entry.x_url && (
          <a
            href={entry.x_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 12,
              color: "#1d9bf0",
              textDecoration: "none",
              padding: "4px 10px",
              border: "1px solid #1d9bf0",
              borderRadius: 20,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
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
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [filterMachine, setFilterMachine] = useState("");

  useEffect(() => {
    fetch("/complete_info.json")
      .then((r) => r.json())
      .then((data: CompleteEntry[]) => {
        setEntries(data);
        // デフォルト: 最新日付
        if (data.length > 0) {
          const latest = data.reduce((a, b) => a.date > b.date ? a : b).date;
          setSelectedDate(latest);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // 利用可能な日付一覧
  const availableDates = useMemo(() => {
    const dates = [...new Set(entries.map((e) => e.date))].sort().reverse();
    return dates;
  }, [entries]);

  // フィルタリング済みエントリ
  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (selectedDate && e.date !== selectedDate) return false;
      if (filterMachine && !e.machine.includes(filterMachine) && !e.store.includes(filterMachine)) return false;
      return true;
    });
  }, [entries, selectedDate, filterMachine]);

  // 機種名一覧（フィルター用）
  const machines = useMemo(() => {
    const m = [...new Set(entries.filter((e) => e.machine).map((e) => e.machine))];
    return m.sort();
  }, [entries]);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "sans-serif" }}>
      {/* ヘッダー */}
      <div style={{
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
        color: "#fff",
        padding: "20px 16px 16px",
      }}>
        <a href="/" style={{ color: "#aaa", fontSize: 12, textDecoration: "none" }}>← トップ</a>
        <h1 style={{ margin: "8px 0 4px", fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>
          🏆 コンプリート情報
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: "#aaa" }}>
          X（Twitter）から収集した全台コンプ・コンプリート制覇情報
        </p>
      </div>

      {/* フィルターバー */}
      <div style={{
        background: C.white,
        borderBottom: `1px solid ${C.border}`,
        padding: "12px 16px",
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        alignItems: "center",
      }}>
        {/* 日付選択 */}
        <select
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: `1px solid ${C.border}`,
            fontSize: 13,
            background: C.white,
            cursor: "pointer",
          }}
        >
          <option value="">全日程</option>
          {availableDates.map((d) => (
            <option key={d} value={d}>{dateFmt(d)}</option>
          ))}
        </select>

        {/* キーワードフィルター */}
        <input
          type="text"
          placeholder="機種名・店舗名で絞り込み"
          value={filterMachine}
          onChange={(e) => setFilterMachine(e.target.value)}
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: `1px solid ${C.border}`,
            fontSize: 13,
            minWidth: 160,
            flex: 1,
          }}
        />

        <span style={{ fontSize: 13, color: C.muted, marginLeft: "auto" }}>
          {filtered.length} 件
        </span>
      </div>

      {/* コンテンツ */}
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "16px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: C.muted }}>
            読み込み中...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{
            textAlign: "center",
            padding: "60px 0",
            color: C.muted,
          }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🎰</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
              コンプリート情報が見つかりませんでした
            </div>
            <div style={{ fontSize: 13 }}>
              スクリプトを実行して最新情報を収集してください
            </div>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 16,
          }}>
            {filtered.map((entry) => (
              <CompleteCard key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
