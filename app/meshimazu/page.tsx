import type { Metadata } from "next";
import MeshimazuClient from "./meshimazu-client";

export const metadata: Metadata = {
  title: "メシマズ店舗取材一覧",
  description: "メシウマ稼働株式会社が実際に取材・調査したメシマズ認定店舗の一覧。各店舗の取材レポート・動画・調査結果をまとめて確認。",
  keywords: ["メシマズ","店舗取材","パチスロ","調査","レポート","メシウマ稼働株式会社","認定店舗","取材一覧"],
  openGraph: {
    title: "メシマズ店舗取材一覧 | メシウマ稼働株式会社",
    description: "メシウマ稼働株式会社が実際に取材・調査したメシマズ認定店舗の一覧と取材レポート。",
    url: "https://mesiuma-site.vercel.app/meshimazu",
  },
  alternates: { canonical: "https://mesiuma-site.vercel.app/meshimazu" },
};

export default function MeshimazuPage() {
  return <MeshimazuClient />;
}
