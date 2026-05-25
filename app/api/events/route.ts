import { NextRequest, NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase";

// ─── 型定義 ────────────────────────────────────────────────────────────────

type EventRow = {
  id: string;
  store_id: string | null;
  store_name: string | null;
  pref: string | null;
  area: string | null;
  date: string | null;
  event_name: string | null;
  detail: string | null;
  cast_names: string[] | null;
  x_url: string | null;
  source_url: string | null;
  source: string | null;
  highlight: boolean;
  created_at: string;
  updated_at: string;
  // image_url は意図的に含めない
};

type EventsResponse = {
  data: EventRow[];
  count: number;
};

type ErrorResponse = {
  error: string;
};

// ─── ルートハンドラ ────────────────────────────────────────────────────────

export async function GET(
  req: NextRequest
): Promise<NextResponse<EventsResponse | ErrorResponse>> {
  try {
    const { searchParams } = req.nextUrl;

    // クエリパラメータのパース
    const limitRaw = parseInt(searchParams.get("limit") ?? "200", 10);
    const limit    = Number.isNaN(limitRaw) ? 200 : Math.min(Math.max(limitRaw, 1), 1000);
    const pref     = searchParams.get("pref")     ?? null;
    const store    = searchParams.get("store")    ?? null;
    const storeId  = searchParams.get("store_id") ?? null;
    const date     = searchParams.get("date")     ?? null;

    const supabase = createAdminClient();

    // image_url は SELECT から意図的に除外
    let query = supabase
      .from("events")
      .select(
        "id, store_id, store_name, pref, area, date, event_name, detail, " +
        "cast_names, x_url, source_url, source, highlight, created_at, updated_at"
      )
      .eq("ng_flag", false)
      .order("date", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(limit);

    if (pref)    query = query.eq("pref", pref);
    if (date)    query = query.eq("date", date);
    if (storeId) query = query.eq("store_id", storeId);  // 完全一致（優先）
    if (store)   query = query.ilike("store_name", `%${store}%`);

    const { data, error } = await query;

    if (error) {
      console.error("[api/events] Supabase error:", error.message);
      return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }

    const rows = (data ?? []) as EventRow[];
    return NextResponse.json({ data: rows, count: rows.length });
  } catch (e) {
    console.error("[api/events] Unexpected error:", e);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
