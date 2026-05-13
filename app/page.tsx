"use client";

import { useEffect, useState } from "react";

type EventType = {
  id: number;
  date: string;
  store: string;
  pref: string;
  area: string;
  event: string;
  detail: string;
  cast?: string;
  x_url?: string;
};

export default function Page() {
  const [events, setEvents] = useState<EventType[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/events_public.json")
      .then((res) => res.json())
      .then((data) => setEvents(data.events || []));
  }, []);

  const filtered = events.filter((e) => {
    const s = search.toLowerCase();
    return (
      e.store?.toLowerCase().includes(s) ||
      e.area?.toLowerCase().includes(s) ||
      e.pref?.toLowerCase().includes(s) ||
      e.cast?.toLowerCase().includes(s)
    );
  });

  return (
    <main style={{ minHeight: "100vh", background: "#0b0b0b", color: "#fff", fontFamily: "sans-serif" }}>
      <header style={{ padding: 24, borderBottom: "1px solid #222", position: "sticky", top: 0, background: "#0b0b0bee", zIndex: 10 }}>
        <h1 style={{ color: "#ff7b00", fontSize: 36, fontWeight: 900 }}>メシウマ稼働株式会社</h1>
        <p style={{ color: "#aaa", marginBottom: 16 }}>〜 メシマズなくしてメシウマなし 〜</p>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="店舗名・地域・演者名で検索"
          style={{ width: "100%", maxWidth: 520, padding: 14, background: "#151515", color: "#fff", border: "1px solid #333", borderRadius: 10 }}
        />
        <p style={{ color: "#888", marginTop: 10 }}>掲載件数：{filtered.length}件</p>
      </header>

      <section style={{ padding: 24, display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))", gap: 16 }}>
        {filtered.map((ev) => (
          <div key={ev.id} style={{ background: "#151515", border: "1px solid #292929", borderRadius: 16, padding: 18 }}>
            <div style={{ color: "#ff7b00", fontWeight: 700 }}>{ev.area || ev.pref}</div>
            <h2 style={{ fontSize: 22, margin: "8px 0" }}>{ev.store}</h2>
            <p style={{ color: "#aaa" }}>{ev.date}</p>
            <p style={{ fontSize: 17, fontWeight: 700 }}>🔥 {ev.event}</p>
            <p style={{ color: "#ccc" }}>{ev.detail}</p>
            {ev.cast && <p style={{ color: "#ffd27a" }}>👤 {ev.cast}</p>}
            {ev.x_url && (
              <a href={ev.x_url} target="_blank" style={{ display: "inline-block", marginTop: 10, padding: "9px 14px", background: "#ff7b00", color: "#fff", borderRadius: 10, textDecoration: "none", fontWeight: 700 }}>
                店舗Xを見る
              </a>
            )}
          </div>
        ))}
      </section>
    </main>
  );
}
