import type { Metadata } from "next";
import CastClient from "./cast-client";

export const metadata: Metadata = {
  title: "社員・演者一覧",
  description: "メシウマ稼働株式会社に所属する社員・演者の一覧とプロフィール。来店スケジュールをまとめて確認できます。",
  keywords: ["メシウマ稼働株式会社","社員","演者","来店","スケジュール","プロフィール","パチスロ"],
  openGraph: {
    title: "社員・演者一覧 | メシウマ稼働株式会社",
    description: "メシウマ稼働株式会社に所属する社員・演者の一覧と来店スケジュール。",
    url: "https://mesiuma-site.vercel.app/cast",
  },
  alternates: { canonical: "https://mesiuma-site.vercel.app/cast" },
};

export default function CastPage() {
  return <CastClient />;
}
