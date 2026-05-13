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

const CSS = `
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0800;color:#fff3e0;font-family:Arial,sans-serif}
.header{position:sticky;top:0;z-index:10;background:rgba(13,8,0,.95);border-bottom:1px solid #3a1f00;padding:18px}
.logo{font-size:26px;font-weight:900;color:#ff8c00}
.sub{font-size:12px;color:#8a5a2b;margin-top:4px}
.hero{padding:70px 20px;text-align:center;background:radial-gradient(circle at center,#3a1600,#0d0800 65%)}
.hero h1{font-size:52px;color:#ff8c00;margin-bottom:12px}
.hero p{color:#b98245}
.search{margin-top:22px;width:100%;max-width:560px;padding:14px;border-radius:12px;border:1px solid #3a1f00;background:#160c00;color:#fff;font-size:16px}
.status{margin-top:14px;color:#ffb300;font-size:14px}
.grid{padding:24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:#1a0d00;border:1px solid #3a1f00;border-radius:16px;padding:18px;box-shadow:0 0 20px rgba(255,106,0,.08)}
.area{color:#ff8c00;font-size:13px;font-weight:700}
.store{font-size:22px;font-weight:900;margin:8px 0;color:#fff}
.date{color:#9d7147;font-size:13px;margin-bottom:8px}
.event{font-size:17px;font-weight:800;margin-bottom:8px}
.detail{color:#d6b58b;font-size:14px;line-height:1.6}
.cast{color:#ffcf75;margin-top:10px}
.x{display:inline-block;margin-top:12px;background:#ff6a00;color:#fff;padding:9px 14px;border-radius:10px;text-decoration:none;font-weight:700}
`;

export default function Page() {
  const [events, setEvents] = useState<EventType[]>([]);
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("/events_public.json")
      .then((res) => res.json())
      .then((data) => {
        setEvents(data.events || []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const filtered = events.filter((ev) => {
    const s = search.toLowerCase();
    return (
      ev.store?.toLowerCase().includes(s) ||
      ev.pref?.toLowerCase().includes(s) ||
      ev.area?.toLowerCase().includes(s) ||
      ev.cast?.toLowerCase().includes(s) ||
      ev.event?.toLowerCase().includes(s)
    );
  });

  return (
    <>
      <style>{CSS}</style>

      <header className="header">
        <div className="logo">メシウマ稼働株式会社</div>
        <div className="sub">メシマズなくしてメシウマなし</div>
      </header>

      <section className="hero">
        <h1>🔥 メシウマ稼働 🔥</h1>
        <p>全国パチスロイベント情報まとめ</p>

        <input
          className="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="店舗名・地域・演者名で検索"
        />

        <div className="status">
          {loaded ? `掲載件数：${filtered.length}件` : "読み込み中..."}
        </div>
      </section>

      <section className="grid">
        {filtered.map((ev) => (
          <article className="card" key={ev.id}>
            <div className="area">{ev.area || ev.pref}</div>
            <div className="store">{ev.store}</div>
            <div className="date">{ev.date}</div>
            <div className="event">🔥 {ev.event}</div>
            <div className="detail">{ev.detail}</div>
            {ev.cast && <div className="cast">👤 {ev.cast}</div>}
            {ev.x_url && (
              <a className="x" href={ev.x_url} target="_blank">
                店舗Xを見る
              </a>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
