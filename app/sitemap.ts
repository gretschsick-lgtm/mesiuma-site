import type { MetadataRoute } from "next";

const SITE_URL = "https://mesiuma-site.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: SITE_URL,                     lastModified: now, changeFrequency: "daily",   priority: 1.0 },
    { url: `${SITE_URL}/cast`,           lastModified: now, changeFrequency: "weekly",  priority: 0.9 },
    { url: `${SITE_URL}/complete`,       lastModified: now, changeFrequency: "hourly",  priority: 0.9 },
    { url: `${SITE_URL}/stores`,         lastModified: now, changeFrequency: "daily",   priority: 0.8 },
    { url: `${SITE_URL}/torisai`,        lastModified: now, changeFrequency: "daily",   priority: 0.8 },
    { url: `${SITE_URL}/meshimazu`,      lastModified: now, changeFrequency: "weekly",  priority: 0.8 },
    { url: `${SITE_URL}/raiten`,         lastModified: now, changeFrequency: "daily",   priority: 0.7 },
    { url: `${SITE_URL}/blog`,           lastModified: now, changeFrequency: "weekly",  priority: 0.6 },
  ];
}
