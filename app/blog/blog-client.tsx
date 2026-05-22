"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Post = {
  id: string;
  title: string;
  date: string;
  author: string;
  tags: string[];
  summary: string;
  content: string;
  image: string;
  setting_images?: { url: string; caption: string }[];
};

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", text: "#222222", sub: "#555555",
  muted: "#888888", dim: "#cccccc", orange: "#ff6600",
};

export default function BlogPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [tag, setTag] = useState("全て");

  useEffect(() => {
    fetch("/blog_posts.json").then(r => r.json()).then(setPosts).catch(() => {});
  }, []);

  const allTags = ["全て", ...Array.from(new Set(posts.flatMap(p => p.tags)))];
  const filtered = tag === "全て" ? posts : posts.filter(p => p.tags.includes(tag));

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <header style={{
        position: "sticky", top: 0, zIndex: 100,
        background: C.white, borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
      }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", gap: 16, height: 52 }}>
          <Link href="/" style={{ color: C.muted, textDecoration: "none", fontSize: 13 }}>← トップ</Link>
          <span style={{ color: C.border }}>|</span>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 4, height: 18, background: C.red, borderRadius: 2 }} />
            <span style={{ fontSize: 16, fontWeight: 900, color: C.text }}>ブログ</span>
          </div>
        </div>
      </header>

      {/* サブヘッダー */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <span style={{ fontSize: 28 }}>📝</span>
            <h1 style={{ fontSize: 20, fontWeight: 900, color: C.text, margin: 0 }}>メシウマ稼働株式会社 ブログ</h1>
          </div>
          <p style={{ fontSize: 12, color: C.muted, margin: "0 0 16px" }}>
            パチスロ攻略・ホール情報・イベントレポートをお届け
          </p>

          {/* タグフィルター */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {allTags.map(t => (
              <button key={t} onClick={() => setTag(t)} style={{
                background: tag === t ? C.red : "#f5f5f5",
                border: `1px solid ${tag === t ? C.red : C.border}`,
                color: tag === t ? "#fff" : C.sub,
                fontSize: 12, fontWeight: 700, padding: "4px 14px",
                borderRadius: 999, cursor: "pointer", transition: "all .15s",
              }}>{t}</button>
            ))}
          </div>
        </div>
      </div>

      {/* 記事一覧 */}
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px 80px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {filtered.map(post => (
            <Link key={post.id} href={`/blog/${post.id}`} style={{ textDecoration: "none" }}>
              <div style={{
                background: C.white,
                border: `1px solid ${C.border}`,
                borderLeft: `4px solid ${C.red}`,
                borderRadius: 6,
                padding: "18px 20px",
                cursor: "pointer",
                transition: "box-shadow .15s",
                display: "flex",
                gap: 16,
                alignItems: "flex-start",
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 12px rgba(0,0,0,.1)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
              >
                {/* サムネイル */}
                {post.image && (
                  <div style={{ flexShrink: 0, width: 90, height: 68, borderRadius: 5, overflow: "hidden", background: "#f0f0f0", border: `1px solid ${C.border}` }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={post.image}
                      alt=""
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                      onError={e => { (e.currentTarget as HTMLImageElement).parentElement!.style.display = "none"; }}
                    />
                  </div>
                )}

                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* メタ行 */}
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ background: "#fff0f0", color: C.red, fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 3, border: `1px solid #ffaaaa` }}>
                      📅 {post.date}
                    </span>
                    {post.tags.slice(0, 3).map(t => (
                      <span key={t} style={{ background: "#f5f5f5", color: C.muted, fontSize: 11, padding: "2px 8px", borderRadius: 3, border: `1px solid ${C.border}` }}>
                        #{t}
                      </span>
                    ))}
                  </div>

                  {/* タイトル */}
                  <div style={{ fontSize: 16, fontWeight: 900, color: C.text, marginBottom: 6, lineHeight: 1.4 }}>
                    {post.title}
                  </div>

                  {/* サマリー */}
                  <div style={{ fontSize: 12, color: C.sub, lineHeight: 1.65, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {post.summary}
                  </div>

                  {/* 著者 */}
                  <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: C.muted }}>by {post.author}</span>
                    <span style={{ fontSize: 12, color: C.red, fontWeight: 700 }}>続きを読む ›</span>
                  </div>
                </div>
              </div>
            </Link>
          ))}

          {filtered.length === 0 && (
            <div style={{ background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: "60px 20px", textAlign: "center" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
              <div style={{ color: C.muted, fontSize: 14 }}>記事がありません</div>
            </div>
          )}
        </div>
      </div>

      <footer style={{ textAlign: "center", padding: "24px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
