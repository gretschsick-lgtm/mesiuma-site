/**
 * 機種名マスタシステム — TypeScript 版
 *
 * スクレイピング取得した機種名を machines_master の正式名称に解決する。
 * DB 保存前に必ず resolveMachine() を通すこと（CLAUDE.md 参照）。
 */

import { createAdminClient } from "@/lib/supabase";
import type { SupabaseClient } from "@supabase/supabase-js";

// ─── 型定義 ────────────────────────────────────────────────────────────────

export type MachineMaster = {
  id: string;
  official_name: string;
  manufacturer: string | null;
  brand: string | null;
  type: "slot" | "pachinko";
  normalized_name: string;
  release_date: string | null;
  source_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type MachineAlias = {
  id: string;
  machine_id: string;
  alias_name: string;
  normalized_alias: string;
  confidence: number; // 0.0 〜 1.0
  created_at: string;
};

export type UnknownMachine = {
  id: string;
  raw_name: string;
  normalized_raw_name: string | null;
  source_site: string | null;
  source_url: string | null;
  detected_at: string;
  count: number;
  status: "pending" | "approved" | "rejected" | "ignored";
};

export type MachineResolveResult = {
  machine_id: string;
  official_name: string;
  normalized_name: string;
  confidence: number;
  match_type: "exact" | "alias" | "fuzzy";
};

// ─── 正規化関数 ────────────────────────────────────────────────────────────

const PREFIX_RE =
  /^(スマスロ|L|パチスロ|スロット|SLOT)/i;

/**
 * 機種名を照合用に正規化する（DB 保存には使わない）。
 * - 全角英数字 → 半角（Unicode NFKC 正規化で処理済みの想定）
 * - 接頭辞除去: スマスロ / L / パチスロ / スロット / SLOT
 * - 小文字化・空白除去
 */
export function normalizeMachineName(name: string): string {
  if (!name) return "";
  // NFKC 正規化（ブラウザ・Node.js 両対応）
  let n = name.normalize("NFKC").trim();
  // 接頭辞を繰り返し除去
  let prev = "";
  while (n !== prev) {
    prev = n;
    n = n.replace(PREFIX_RE, "").trim();
  }
  return n.toLowerCase().replace(/[\s\u3000]/g, "");
}

// ─── 類似度計算（LCS ratio・Python の SequenceMatcher.ratio() 相当）───────

function lcsLength(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[] = new Array(n + 1).fill(0);
  for (let i = 1; i <= m; i++) {
    let prev = 0;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prev + 1 : Math.max(dp[j], dp[j - 1]);
      prev = tmp;
    }
  }
  return dp[n];
}

function stringSimilarity(a: string, b: string): number {
  if (a === b) return 1.0;
  if (!a || !b) return 0.0;
  const lcs = lcsLength(a, b);
  return (2 * lcs) / (a.length + b.length);
}

// ─── 機種解決 ─────────────────────────────────────────────────────────────

/**
 * 機種名を解決して MachineResolveResult を返す。
 * 類似度 85% 未満の場合は null を返す（呼び出し元が unknown_machines に保存すること）。
 *
 * 解決順序:
 *   1. exact match  — machines_master.normalized_name と完全一致
 *   2. alias match  — machines_aliases.normalized_alias と完全一致
 *   3. fuzzy match  — SequenceMatcher ratio ≥ 0.85
 */
export async function resolveMachine(
  rawName: string,
  supabase: SupabaseClient = createAdminClient()
): Promise<MachineResolveResult | null> {
  if (!rawName?.trim()) return null;

  const norm = normalizeMachineName(rawName);
  if (!norm) return null;

  // 1. 完全一致
  const { data: exactRow } = await supabase
    .from("machines_master")
    .select("id, official_name, normalized_name")
    .eq("normalized_name", norm)
    .eq("is_active", true)
    .maybeSingle();

  if (exactRow) {
    return {
      machine_id:    exactRow.id,
      official_name: exactRow.official_name,
      normalized_name: exactRow.normalized_name,
      confidence:    1.0,
      match_type:    "exact",
    };
  }

  // 2. エイリアス一致
  const { data: aliasRow } = await supabase
    .from("machines_aliases")
    .select("machine_id, normalized_alias, confidence, machines_master(id, official_name, normalized_name)")
    .eq("normalized_alias", norm)
    .maybeSingle();

  if (aliasRow) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const master = (aliasRow as any).machines_master as { official_name: string; normalized_name: string } | null;
    if (master) {
      return {
        machine_id:    aliasRow.machine_id,
        official_name: master.official_name,
        normalized_name: master.normalized_name,
        confidence:    Number(aliasRow.confidence),
        match_type:    "alias",
      };
    }
  }

  // 3. ファジーマッチ（全件ロードして類似度計算）
  const { data: allMachines } = await supabase
    .from("machines_master")
    .select("id, official_name, normalized_name")
    .eq("is_active", true)
    .order("official_name");

  let bestScore = 0.849;
  let bestMachine: { id: string; official_name: string; normalized_name: string } | null = null;

  for (const m of allMachines ?? []) {
    const score = stringSimilarity(norm, m.normalized_name);
    if (score > bestScore) {
      bestScore = score;
      bestMachine = m;
    }
  }

  if (bestMachine) {
    return {
      machine_id:    bestMachine.id,
      official_name: bestMachine.official_name,
      normalized_name: bestMachine.normalized_name,
      confidence:    Math.round(bestScore * 1000) / 1000,
      match_type:    "fuzzy",
    };
  }

  return null;
}

// ─── 管理ヘルパー ─────────────────────────────────────────────────────────

// 管理操作は既存テーブルの Insert/Update 型定義が不完全なため any キャストを使用
// 要確認: Database 型の全テーブルに Insert/Update を追加すれば不要になる
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyClient = any;

/** 未解決機種一覧（status=pending, count 降順） */
export async function getUnknownMachines(
  status: UnknownMachine["status"] = "pending",
  limit = 100
): Promise<UnknownMachine[]> {
  const sb: AnyClient = createAdminClient();
  const { data, error } = await sb
    .from("unknown_machines")
    .select("*")
    .eq("status", status)
    .order("count", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []) as UnknownMachine[];
}

/**
 * 未解決機種を承認する。
 * - existingMachineId 指定時: そのマスタへのエイリアスを追加して approved にする
 * - newOfficialName 指定時: 新規マスタを作成してエイリアスを追加する
 */
export async function approveUnknownMachine(
  unknownId: string,
  opts: { existingMachineId?: string; newOfficialName?: string; newType?: "slot" | "pachinko"; newManufacturer?: string }
): Promise<{ machine_id: string; official_name: string }> {
  const sb: AnyClient = createAdminClient();

  const { data: unknown, error: fetchErr } = await sb
    .from("unknown_machines").select("*").eq("id", unknownId).single();
  if (fetchErr || !unknown) throw fetchErr ?? new Error("not found");

  let machineId = opts.existingMachineId ?? "";
  let officialName = "";

  if (!machineId && opts.newOfficialName) {
    const normalized = normalizeMachineName(opts.newOfficialName);
    const { data: newMachine, error: insertErr } = await sb
      .from("machines_master")
      .insert({ official_name: opts.newOfficialName, type: opts.newType ?? "slot",
                manufacturer: opts.newManufacturer ?? null, normalized_name: normalized, is_active: true })
      .select("id, official_name").single();
    if (insertErr) throw insertErr;
    machineId    = newMachine.id;
    officialName = newMachine.official_name;
  } else {
    const { data: m } = await sb
      .from("machines_master").select("official_name").eq("id", machineId).single();
    officialName = m?.official_name ?? "";
  }

  const normAlias = normalizeMachineName(unknown.raw_name);
  await sb.from("machines_aliases")
    .upsert({ machine_id: machineId, alias_name: unknown.raw_name,
              normalized_alias: normAlias, confidence: 0.95 },
             { onConflict: "normalized_alias" });

  await sb.from("unknown_machines").update({ status: "approved" }).eq("id", unknownId);

  return { machine_id: machineId, official_name: officialName };
}

/** エイリアスを追加する */
export async function addAlias(
  machineId: string,
  aliasName: string,
  confidence = 1.0
): Promise<MachineAlias> {
  const sb: AnyClient = createAdminClient();
  const normalized = normalizeMachineName(aliasName);
  const { data, error } = await sb
    .from("machines_aliases")
    .insert({ machine_id: machineId, alias_name: aliasName, normalized_alias: normalized, confidence })
    .select("*").single();
  if (error) throw error;
  return data as MachineAlias;
}

/** machines_master に新規機種を追加する */
export async function addMachineMaster(
  officialName: string,
  type: "slot" | "pachinko",
  manufacturer?: string,
  releaseDate?: string
): Promise<MachineMaster> {
  const supabase: AnyClient = createAdminClient();
  const normalized = normalizeMachineName(officialName);
  const { data, error } = await supabase
    .from("machines_master")
    .insert({
      official_name:   officialName,
      type,
      manufacturer:    manufacturer ?? null,
      normalized_name: normalized,
      release_date:    releaseDate ?? null,
      is_active:       true,
    })
    .select("*")
    .single();
  if (error) throw error;
  return data as MachineMaster;
}
