import type { Metadata } from "next";
import TorisaiClient from "./torisai-client";

export const metadata: Metadata = {
  title: "店舗取材一覧",
  description: "全国のパチスロホールへのメディア取材・調査員訪問イベントをまとめて確認。スロパチステーション・1GAMEなど主要メディアの取材日程を一覧表示。",
  keywords: ["パチスロ","取材","調査員","スロパチステーション","1GAME","BASHtv","店舗取材","メシウマ稼働","全国","関東","関西"],
  openGraph: {
    title: "店舗取材一覧 | メシウマ稼働",
    description: "全国パチスロホールへのメディア取材・調査員訪問イベントを一覧表示。",
    url: "https://mesiuma-site.vercel.app/torisai",
  },
  alternates: { canonical: "https://mesiuma-site.vercel.app/torisai" },
};

export default function TorisaiPage() {
  return <TorisaiClient />;
}
