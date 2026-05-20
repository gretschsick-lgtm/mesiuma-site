import type { Metadata } from "next";
import BlogClient from "./blog-client";

export const metadata: Metadata = {
  title: "ブログ",
  description: "メシウマ稼働株式会社のブログ。パチスロ攻略・立ち回り・動画紹介・イベント情報など最新コンテンツを発信。",
  keywords: ["パチスロ","ブログ","攻略","立ち回り","動画","メシウマ稼働株式会社","スロット","イベント情報"],
  openGraph: {
    title: "ブログ | メシウマ稼働株式会社",
    description: "パチスロ攻略・立ち回り・動画紹介など最新コンテンツを発信。",
    url: "https://mesiuma-site.vercel.app/blog",
  },
  alternates: { canonical: "https://mesiuma-site.vercel.app/blog" },
};

export default function BlogPage() {
  return <BlogClient />;
}
