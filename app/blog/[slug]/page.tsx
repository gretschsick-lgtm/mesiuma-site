"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type Post = {
  id: string;
  title: string;
  date: string;
  author: string;
  tags: string[];
  summary: string;
  content: string;
  image: string;
};

const C = {
  bg: "#f5f5f5", white: "#ffffff", border: "#e0e0e0",
  red: "#e60000", text: "#222222", sub: "#444444",
  muted: "#888888", dim: "#cccccc",
};

function renderContent(text: string) {
  return text.split("\n").map((line, i) => {
    if (line.startsWith("## ")) return (
      <h2 key={i} style={{
        color: C.text, fontSize: 18, fontWeight: 900,
        margin: "28px 0 10px", paddingBottom: 6,
        borderBottom: `2px solid ${C.red}`,
      }}>
        {line.replace("## ", "")}
      </h2>
    );
    if (line.startsWith("# ")) return (
      <h1 key={i} style={{ color: C.text, fontSize: 22, fontWeight: 900, margin: "24px 0 12px" }}>
        {line.replace("# ", "")}
      </h1>
    );
    if (line === "") return <br key={i} />;
    return <p key={i} style={{ margin: "0 0 12px", lineHeight: 1.85, color: C.sub }}>{line}</p>;
  });
}

export default function BlogPostPage() {
  const params = useParams();
  const slug = params?.slug as string;
  const [post, setPost] = useState<Post | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;
    fetch("/blog_posts.json").then(r => r.json()).then((posts: Post[]) => {
      const found = posts.find(p => p.id === slug);
      if (found) setPost(found);
      else setNotFound(true);
    }).catch(() => setNotFound(true));
  }, [slug]);

  if (notFound) return (
    <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
        <div style={{ color: C.muted, marginBottom: 12 }}>記事が見つかりません</div>
        <Link href="/blog" style={{ color: C.red, fontSize: 13 }}>← ブログ一覧へ</Link>
      </div>
    </div>
  );

  if (!post) return (
    <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ color: C.muted }}>読み込み中...</div>
    </div>
  );

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ヘッダー */}
      <header style={{
        position: "sticky", top: 0, zIndex: 100,
        background: C.white, borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
      }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", gap: 16, height: 52 }}>
          <Link href="/blog" style={{ color: C.muted, textDecoration: "none", fontSize: 13 }}>← ブログ一覧</Link>
          <span style={{ color: C.border }}>|</span>
          <Link href="/" style={{ color: C.muted, textDecoration: "none", fontSize: 12 }}>トップ</Link>
        </div>
      </header>

      <div style={{ maxWidth: 760, margin: "0 auto", padding: "28px 16px 80px" }}>

        {/* メタ情報 */}
        <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
          <span style={{ background: "#fff0f0", color: C.red, fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 3, border: `1px solid #ffaaaa` }}>
            📅 {post.date}
          </span>
          {post.tags.map(t => (
            <span key={t} style={{ background: "#f5f5f5", color: C.muted, fontSize: 11, padding: "3px 9px", borderRadius: 3, border: `1px solid ${C.border}` }}>
              #{t}
            </span>
          ))}
        </div>

        {/* タイトル */}
        <h1 style={{ color: C.text, fontSize: 24, fontWeight: 900, lineHeight: 1.4, marginBottom: 8, borderLeft: `4px solid ${C.red}`, paddingLeft: 14 }}>
          {post.title}
        </h1>
        <div style={{ color: C.muted, fontSize: 12, marginBottom: 24 }}>by {post.author}</div>

        {/* 本文 */}
        <div style={{
          background: C.white, border: `1px solid ${C.border}`,
          borderRadius: 8, padding: "24px 24px",
        }}>
          {renderContent(post.content)}
        </div>

        {/* フッターナビ */}
        <div style={{ marginTop: 28, display: "flex", justifyContent: "space-between", borderTop: `1px solid ${C.border}`, paddingTop: 20 }}>
          <Link href="/blog" style={{ color: C.red, fontSize: 13, textDecoration: "none", fontWeight: 700 }}>← 記事一覧に戻る</Link>
          <Link href="/" style={{ color: C.muted, fontSize: 13, textDecoration: "none" }}>トップへ →</Link>
        </div>
      </div>

      <footer style={{ textAlign: "center", padding: "24px 16px", borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11 }}>
        © メシウマ稼働株式会社
      </footer>
    </div>
  );
}
