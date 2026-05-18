import type { Metadata } from "next";
import HomeClient from "./home-client";

export const metadata: Metadata = {
  title: "メシウマ稼働 | 全国パチスロイベント・来店演者情報",
  description: "メシウマ稼働株式会社が厳選する全国のパチスロイベント情報。来店演者スケジュール・取材日程・メシマズ店舗一覧をリアルタイムで確認。関東・関西・東海・九州対応。",
  keywords: ["パチスロ","イベント","来店","演者","スケジュール","取材","メシウマ稼働","高設定示唆","パチスロイベント","来店演者","全国","関東","関西","東海","九州","北海道"],
  openGraph: {
    title: "メシウマ稼働 | 全国パチスロイベント・来店演者情報",
    description: "全国のパチスロイベント・来店演者スケジュールをリアルタイムで確認。メシウマ稼働株式会社公式サイト。",
    url: "https://mesiuma-site.vercel.app",
    siteName: "メシウマ稼働",
    locale: "ja_JP",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "メシウマ稼働 | 全国パチスロイベント・来店演者情報",
    description: "全国のパチスロイベント・来店演者スケジュールをリアルタイムで確認。",
    site: "@mesiuma_kadou",
  },
  alternates: {
    canonical: "https://mesiuma-site.vercel.app",
  },
};

export default function Page() {
  return <HomeClient />;
}
