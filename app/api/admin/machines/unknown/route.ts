import { NextRequest, NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase";
import { getUnknownMachines, approveUnknownMachine } from "@/lib/machines";
import type { UnknownMachine } from "@/lib/machines";

// GET /api/admin/machines/unknown — 未解決機種一覧
// ?status=pending|approved|rejected|ignored (default: pending)
// ?limit=100
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = req.nextUrl;
    const statusParam = searchParams.get("status") ?? "pending";
    const limit = Math.min(parseInt(searchParams.get("limit") ?? "100", 10), 500);

    const validStatuses: UnknownMachine["status"][] = ["pending", "approved", "rejected", "ignored"];
    const status = validStatuses.includes(statusParam as UnknownMachine["status"])
      ? (statusParam as UnknownMachine["status"])
      : "pending";

    const data = await getUnknownMachines(status, limit);
    return NextResponse.json({ data, count: data.length });
  } catch (e) {
    console.error("[api/admin/machines/unknown] GET error:", e);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// PATCH /api/admin/machines/unknown — 未解決機種の処理
// body (承認・既存マスタへのエイリアス追加):
//   { action: "approve", id, existing_machine_id }
// body (承認・新規マスタ作成):
//   { action: "approve", id, new_official_name, new_type?, new_manufacturer? }
// body (棄却・無視):
//   { action: "reject" | "ignore", id }
export async function PATCH(req: NextRequest) {
  try {
    const body = await req.json();
    const { action, id } = body;

    if (!id) {
      return NextResponse.json({ error: "id は必須です" }, { status: 400 });
    }

    const supabase = createAdminClient();

    if (action === "approve") {
      const { existing_machine_id, new_official_name, new_type, new_manufacturer } = body;

      if (!existing_machine_id && !new_official_name) {
        return NextResponse.json(
          { error: "existing_machine_id または new_official_name のいずれかが必要です" },
          { status: 400 }
        );
      }

      const result = await approveUnknownMachine(id, {
        existingMachineId: existing_machine_id,
        newOfficialName:   new_official_name,
        newType:           new_type,
        newManufacturer:   new_manufacturer,
      });
      return NextResponse.json({ data: result });
    }

    if (action === "reject" || action === "ignore") {
      const status: UnknownMachine["status"] = action === "reject" ? "rejected" : "ignored";
      // unknown_machines の Update 型が Database に未定義のため any キャスト
      // 要確認: Database 型に Insert/Update を追加すれば不要になる
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { error } = await (supabase as any)
        .from("unknown_machines")
        .update({ status })
        .eq("id", id);
      if (error) throw error;
      return NextResponse.json({ data: { id, status } });
    }

    return NextResponse.json(
      { error: 'action は "approve", "reject", "ignore" のいずれかを指定してください' },
      { status: 400 }
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[api/admin/machines/unknown] PATCH error:", msg);
    if (msg.includes("not found")) {
      return NextResponse.json({ error: "指定された ID が見つかりません" }, { status: 404 });
    }
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
