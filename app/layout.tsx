import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_URL = "https://mesiuma-site.vercel.app";
const SITE_NAME = "メシウマ稼働";
const SITE_DESCRIPTION = "メシウマ稼働株式会社が厳選する全国のパチスロイベント情報。来店演者スケジュール・取材日程・メシマズ店舗一覧をリアルタイムで確認。";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} | 全国パチスロイベント・来店演者情報`,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  keywords: [
    "パチスロ","イベント","来店","演者","スケジュール","取材","メシウマ稼働",
    "パチスロイベント","来店演者","全国","関東","関西","東海","九州","北海道",
    "スロット","パチンコ","メシマズ","店舗取材","高設定","公約","調査員",
  ],
  authors: [{ name: "メシウマ稼働株式会社", url: SITE_URL }],
  creator: "メシウマ稼働株式会社",
  publisher: "メシウマ稼働株式会社",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  openGraph: {
    type: "website",
    locale: "ja_JP",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: `${SITE_NAME} | 全国パチスロイベント・来店演者情報`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary_large_image",
    site: "@mesiuma_kadou",
    creator: "@mesiuma_kadou",
  },
  alternates: {
    canonical: SITE_URL,
  },
  verification: {
    google: "g0rqOYZ7EyA9LGJ0T7LfIf5kFpfqvjsWrr3SXKyU7ig",
  },
};

const JSON_LD_ORGANIZATION = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "メシウマ稼働株式会社",
  url: SITE_URL,
  sameAs: [
    "https://www.youtube.com/@mesiuma_kadou",
    "https://x.com/mesiuma_kadou",
  ],
  description: SITE_DESCRIPTION,
};

const JSON_LD_WEBSITE = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: SITE_NAME,
  url: SITE_URL,
  description: SITE_DESCRIPTION,
  publisher: {
    "@type": "Organization",
    name: "メシウマ稼働株式会社",
  },
  potentialAction: {
    "@type": "SearchAction",
    target: {
      "@type": "EntryPoint",
      urlTemplate: `${SITE_URL}/?q={search_term_string}`,
    },
    "query-input": "required name=search_term_string",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ja"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD_ORGANIZATION) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD_WEBSITE) }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
