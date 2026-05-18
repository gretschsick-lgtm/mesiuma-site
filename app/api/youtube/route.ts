import { NextResponse } from "next/server";

export const revalidate = 1800; // 30分キャッシュ

export async function GET() {
  try {
    // チャンネルページからchannelIDを取得
    const pageRes = await fetch("https://www.youtube.com/@mesiuma_kadou", {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "ja,en;q=0.9",
      },
      next: { revalidate: 1800 },
    });

    const html = await pageRes.text();

    // channel_id を RSS リンクから抽出
    const cidMatch = html.match(/channel_id=(UC[A-Za-z0-9_-]+)/);
    if (!cidMatch) {
      return NextResponse.json({ error: "channel_id not found" }, { status: 404 });
    }
    const channelId = cidMatch[1];

    // RSS フィードを取得
    const rssRes = await fetch(
      `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`,
      { next: { revalidate: 1800 } }
    );
    const xml = await rssRes.text();

    // 最新動画を抽出（最初のentry）
    const videos: { id: string; title: string; published: string }[] = [];
    const entryRegex = /<entry>([\s\S]*?)<\/entry>/g;
    let m;
    while ((m = entryRegex.exec(xml)) !== null && videos.length < 5) {
      const entry = m[1];
      const idM = entry.match(/<yt:videoId>([^<]+)<\/yt:videoId>/);
      const titleM = entry.match(/<title>([^<]+)<\/title>/);
      const pubM = entry.match(/<published>([^<]+)<\/published>/);
      if (idM && titleM) {
        videos.push({
          id: idM[1],
          title: titleM[1],
          published: pubM?.[1] ?? "",
        });
      }
    }

    if (!videos.length) {
      return NextResponse.json({ error: "no videos" }, { status: 404 });
    }

    return NextResponse.json({ latest: videos[0], recent: videos, channelId });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
