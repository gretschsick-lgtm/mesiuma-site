import { NextRequest, NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase";

// ─── 型定義 ────────────────────────────────────────────────────────────────

type CompleteReportRow = {
  id: string;
  date: string | null;
  report_time: string | null;
  store_name: string | null;
  store_id: string | null;
  machine: string | null;
  slot_number: string | null;
  x_url: string;
  collected_at: string;
  // image_url は意図的に含めない
};

type CompleteResponse = {
  data: CompleteReportRow[];
  count: number;
};

type ErrorResponse = {
  error: string;
};

// ─── ルートハンドラ ────────────────────────────────────────────────────────

export async function GET(
  req: NextRequest
): Promise<NextResponse<CompleteResponse | ErrorResponse>> {
  try {
    const { searchParams } = req.nextUrl;

    // クエリパラメータのパース
    const limitRaw = parseInt(searchParams.get("limit") ?? "300", 10);
    const limit    = Number.isNaN(limitRaw) ? 300 : Math.min(Math.max(limitRaw, 1), 1000);
    const store    = searchParams.get("store") ?? null;
    const date     = searchParams.get("date")  ?? null;

    const supabase = createAdminClient();

    // image_url は SELECT から意図的に除外
    // complete_reports には ng_flag カラムがないため除外フィルタは不要
    let query = supabase
      .from("complete_reports")
      .select(
        "id, date, report_time, store_name, store_id, machine, slot_number, x_url, collected_at"
      )
      .order("date", { ascending: false })
      .order("report_time", { ascending: false })
      .limit(limit);

    if (date)  query = query.eq("date", date);
    if (store) query = query.ilike("store_name", `%${store}%`);

    const { data, error } = await query;

    if (error) {
      console.error("[api/complete] Supabase error:", error.message);
      return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }

    const rows = (data ?? []) as CompleteReportRow[];
    return NextResponse.json({ data: rows, count: rows.length });
  } catch (e) {
    console.error("[api/complete] Unexpected error:", e);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
