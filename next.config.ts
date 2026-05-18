import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "www.sammy.co.jp" },
      { protocol: "https", hostname: "www.universal-777.com" },
      { protocol: "https", hostname: "www.sankyo-fever.jp" },
      { protocol: "https", hostname: "www.crossalpha.co.jp" },
      { protocol: "https", hostname: "www.yamasa.com" },
      { protocol: "https", hostname: "chonborista.com" },
      { protocol: "https", hostname: "pachigab.com" },
      { protocol: "https", hostname: "img.youtube.com" },
    ],
  },
};

export default nextConfig;
