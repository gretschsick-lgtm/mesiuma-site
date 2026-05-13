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
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/events_public.json")
      .then((res) => res.json())
      .then((data) => {
        setEvents(data.events || []);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  const filtered = events.filter((e) => {
    const s = search.toLowerCase();

    return (
      e.store?.toLowerCase().includes(s) ||
      e.area?.toLowerCase().includes(s) ||
      e.cast?.toLowerCase().includes(s)
    );
  });

  return (
    <main
      style={{
        background: "#0b0b0b",
        minHeight: "100vh",
        color: "#fff",
        fontFamily: "sans-serif",
      }}
    >
      {/* HEADER */}
      <div
        style={{
          borderBottom: "1px solid #222",
          padding: "24px",
          position: "sticky",
          top: 0,
          background: "#0b0b0bdd",
          backdropFilter: "blur(10px)",
          zIndex: 100,
        }}
      >
        <h1
          style={{
            fontSize: "42px",
            fontWeight: "bold",
            color: "#ff7b00",
            marginBottom: "10px",
          }}
        >
          メシウマ稼働株式会社
        </h1>

        <p
          style={{
            color: "#999",
            marginBottom: "20px",
          }}
        >
          〜 メシマズなくしてメシウマなし 〜
        </p>

        <input
          placeholder="店舗名・地域・演者名で検索"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: "100%",
            maxWidth: "500px",
            padding: "14px",
            borderRadius: "10px",
            border: "1px solid #333",
            background: "#151515",
            color: "#fff",
            fontSize: "16px",
          }}
        />
      </div>

      {/* CONTENT */}
      <div
        style={{
          padding: "30px",
          maxWidth: "1400px",
          margin: "0 auto",
        }}
      >
        {loading ? (
          <div
            style={{
              textAlign: "center",
              padding: "80px",
              color: "#888",
            }}
          >
            読み込み中...
          </div>
        ) : filtered.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "80px",
              color: "#888",
            }}
          >
            イベントがありません
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill,minmax(320px,1fr))",
              gap: "20px",
            }}
          >
            {filtered.map((ev) => (
              <div
                key={ev.id}
                style={{
                  background: "#151515",
                  border: "1px solid #262626",
                  borderRadius: "16px",
                  padding: "20px",
                  transition: "0.2s",
                }}
              >
                <div
                  style={{
                    color: "#ff7b00",
                    fontSize: "14px",
                    marginBottom: "6px",
                  }}
                >
                  {ev.area}
                </div>

                <div
                  style={{
                    fontSize: "24px",
                    fontWeight: "bold",
                    marginBottom: "10px",
                  }}
                >
                  {ev.store}
                </div>

                <div
                  style={{
                    color: "#aaa",
                    marginBottom: "10px",
                  }}
                >
                  {ev.date}
                </div>

                <div
                  style={{
                    fontSize: "18px",
                    color: "#fff",
                    marginBottom: "12px",
                    fontWeight: "bold",
                  }}
                >
                  🔥 {ev.event}
                </div>

                <div
                  style={{
                    color: "#ccc",
                    marginBottom: "12px",
                    lineHeight: 1.7,
                  }}
                >
                  {ev.detail}
                </div>

                {ev.cast && (
                  <div
                    style={{
                      marginBottom: "14px",
                      color: "#ffd27a",
                    }}
                  >
                    👤 {ev.cast}
                  </div>
                )}

                {ev.x_url && (
                  <a
                    href={ev.x_url}
                    target="_blank"
                    style={{
                      display: "inline-block",
                      padding: "10px 16px",
                      background: "#ff7b00",
                      color: "#fff",
                      borderRadius: "10px",
                      textDecoration: "none",
                      fontWeight: "bold",
                    }}
                  >
                    店舗Xを見る
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}