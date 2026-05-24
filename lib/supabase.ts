import { createClient as createSupabaseClient } from "@supabase/supabase-js";

// ─── 型定義 ────────────────────────────────────────────────────────────────

export type Store = {
  id: string;
  name: string;
  pref: string | null;
  area: string | null;
  address: string | null;
  hp_url: string | null;
  x_url: string | null;
  dmm_id: string | null;
  pworld_id: string | null;
  ng_flag: boolean;
  ng_reason: string | null;
  meshiuma_score: number;
  event_count_30d: number;
  complete_count_30d: number;
  cast_count_30d: number;
  created_at: string;
  updated_at: string;
};

export type CastMember = {
  id: number;
  name: string;
  slug: string | null;
  x_url: string | null;
  profile_url: string | null;
  ng_flag: boolean;
  ng_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Event = {
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
  ng_flag: boolean;
  // image_url はDB上に存在するが SELECT・表示しない
  created_at: string;
  updated_at: string;
};

export type CompleteReport = {
  id: string;
  date: string | null;
  report_time: string | null;
  store_name: string | null;
  store_id: string | null;
  machine: string | null;
  slot_number: string | null;
  x_url: string;
  // image_url はDB上に存在するが SELECT・表示しない
  collected_at: string;
};

export type FetchLog = {
  id: number;
  job_name: string;
  started_at: string | null;
  finished_at: string | null;
  status: "success" | "partial" | "failed" | null;
  fetched_count: number;
  new_count: number;
  duplicate_count: number;
  error_count: number;
  error_detail: string | null;
  created_at: string;
};

export type FetchState = {
  job_name: string;
  last_success_at: string | null;
  last_run_at: string | null;
  updated_at: string;
};

export type Database = {
  public: {
    Tables: {
      stores:           { Row: Store };
      cast_members:     { Row: CastMember };
      events:           { Row: Event };
      complete_reports: { Row: CompleteReport };
      fetch_logs:       { Row: FetchLog };
      fetch_state:      { Row: FetchState };
    };
  };
};

// ─── クライアント（遅延初期化）────────────────────────────────────────────

let _supabase: ReturnType<typeof createSupabaseClient<Database>> | null = null;

function getBrowserClient(): ReturnType<typeof createSupabaseClient<Database>> {
  if (_supabase) return _supabase;
  const url  = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) {
    throw new Error(
      "[lib/supabase.ts] NEXT_PUBLIC_SUPABASE_URL または NEXT_PUBLIC_SUPABASE_ANON_KEY が未設定です。" +
      " .env.local を確認してください。"
    );
  }
  _supabase = createSupabaseClient<Database>(url, anon);
  return _supabase;
}

/**
 * サーバーサイド専用クライアント（service_role key）
 * API Routes / Server Actions / Python スクリプトからの書き込みに使用。
 * ブラウザには絶対に渡さないこと。
 */
export function createAdminClient() {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!serviceKey) {
    throw new Error(
      "[lib/supabase.ts] SUPABASE_SERVICE_ROLE_KEY が未設定です。" +
      " サーバーサイドのみで使用してください。"
    );
  }
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!url) {
    throw new Error(
      "[lib/supabase.ts] NEXT_PUBLIC_SUPABASE_URL が未設定です。" +
      " .env.local を確認してください。"
    );
  }
  return createSupabaseClient<Database>(url, serviceKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}

// ─── 共通クエリヘルパー ────────────────────────────────────────────────────

/** NG除外済みイベント一覧（日付降順） */
export async function getPublicEvents(options?: {
  limit?: number;
  fromDate?: string;
  pref?: string;
}) {
  const { limit = 200, fromDate, pref } = options ?? {};

  let query = getBrowserClient()
    .from("events")
    .select(
      // image_url は意図的に SELECT から除外
      "id, store_id, store_name, pref, area, date, event_name, detail, " +
      "cast_names, x_url, source_url, source, highlight, created_at"
    )
    .eq("ng_flag", false)
    .order("date", { ascending: false })
    .limit(limit);

  if (fromDate) query = query.gte("date", fromDate);
  if (pref)     query = query.eq("pref", pref);

  const { data, error } = await query;
  if (error) throw error;
  return data ?? [];
}

/** NG除外済みコンプリート報告（日付・時刻降順） */
export async function getPublicCompleteReports(limit = 300) {
  const { data, error } = await getBrowserClient()
    .from("complete_reports")
    .select(
      // image_url は意図的に SELECT から除外
      "id, date, report_time, store_name, machine, slot_number, x_url, collected_at"
    )
    .order("date", { ascending: false })
    .order("report_time", { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data ?? [];
}

/** 最新の fetch_logs（管理画面用） */
export async function getRecentFetchLogs(limit = 50) {
  const { data, error } = await getBrowserClient()
    .from("fetch_logs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data ?? [];
}

/** fetch_state を取得（差分取得の基準時刻として使用） */
export async function getFetchState(jobName: string): Promise<FetchState | null> {
  const { data, error } = await getBrowserClient()
    .from("fetch_state")
    .select("*")
    .eq("job_name", jobName)
    .single();

  if (error) return null;
  return data;
}
