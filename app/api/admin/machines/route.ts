import { NextRequest, NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase";
import { normalizeMachineName, addMachineMaster, addAlias } from "@/lib/machines";
import type { MachineMaster } from "@/lib/machines";

// GET /api/admin/machines — 機種マスタ一覧
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = req.nextUrl;
    const type   = searchParams.get("type");   // "slot" | "pachinko"
    const search = searchParams.get("q");      // 機種名部分一致
    const limit  = Math.min(parseInt(searchParams.get("limit") ?? "200", 10), 500);

    const supabase = createAdminClient();
    let query = supabase
      .from("machines_master")
      .select("id, official_name, manufacturer, brand, type, normalized_name, is_active, release_date")
      .order("official_name")
      .limit(limit);

    if (type === "slot" || type === "pachinko") query = query.eq("type", type);
    if (search) query = query.ilike("official_name", `%${search}%`);

    const { data, error } = await query;
    if (error) {
      console.error("[api/admin/machines] GET error:", error.message);
      return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
    return NextResponse.json({ data: data ?? [], count: (data ?? []).length });
  } catch (e) {
    console.error("[api/admin/machines] Unexpected:", e);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// POST /api/admin/machines — 新規機種追加 または エイリアス追加
// body: { action: "add_machine", official_name, type, manufacturer?, release_date? }
//       { action: "add_alias",   machine_id,    alias_name, confidence? }
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const action = body?.action as string;

    if (action === "add_machine") {
      const { official_name, type, manufacturer, release_date } = body;
      if (!official_name || !type) {
        return NextResponse.json({ error: "official_name と type は必須です" }, { status: 400 });
      }
      if (type !== "slot" && type !== "pachinko") {
        return NextResponse.json({ error: "type は slot または pachinko のみ有効です" }, { status: 400 });
      }
      const machine = await addMachineMaster(official_name, type, manufacturer, release_date);
      return NextResponse.json({ data: machine }, { status: 201 });
    }

    if (action === "add_alias") {
      const { machine_id, alias_name, confidence } = body;
      if (!machine_id || !alias_name) {
        return NextResponse.json({ error: "machine_id と alias_name は必須です" }, { status: 400 });
      }
      // normalized_alias の重複確認
      const supabase = createAdminClient();
      const normalized = normalizeMachineName(alias_name);
      const { data: existingRaw } = await supabase
        .from("machines_aliases")
        .select("id, machine_id")
        .eq("normalized_alias", normalized)
        .maybeSingle();
      const existing = existingRaw as { id: string; machine_id: string } | null;
      if (existing) {
        return NextResponse.json(
          { error: `"${alias_name}" の正規化形 "${normalized}" は既に登録済みです (machine_id: ${existing.machine_id})` },
          { status: 409 }
        );
      }
      const alias = await addAlias(machine_id, alias_name, confidence ?? 1.0);
      return NextResponse.json({ data: alias }, { status: 201 });
    }

    return NextResponse.json(
      { error: 'action は "add_machine" または "add_alias" のみ有効です' },
      { status: 400 }
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[api/admin/machines] POST error:", msg);
    if (msg.includes("duplicate") || msg.includes("unique")) {
      return NextResponse.json({ error: "既に同じ official_name または normalized_alias が存在します" }, { status: 409 });
    }
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
