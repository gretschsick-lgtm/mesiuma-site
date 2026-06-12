"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

// ─── 型 ────────────────────────────────────────────────────────────────
type CompleteEntry = {
  id: string;
  date: string;
  time: string;
  store: string;
  machine: string;
  seat?: string;
  slot_number?: string;
  x_url?: string;
};

type Event = {
  id?: string;
  store?: string;
  store_name?: string;
  date?: string;
  area?: string;
  pref?: string;
};

type MachineStore = {
  store_id: string;
  store_name: string;
  pref?: string;
  city?: string;
  machines?: unknown[];
};

// ─── ユーティリティ ──────────────────────────────────────────────────
function fmtNum(n: number) {
  return n.toLocaleString("ja-JP");
}

function StatCard({
  label,
  value,
  sub,
  color = "blue",
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: "blue" | "green" | "orange" | "purple" | "red";
}) {
  const colors = {
    blue: "from-blue-500 to-blue-700",
    green: "from-green-500 to-green-700",
    orange: "from-orange-400 to-orange-600",
    purple: "from-purple-500 to-purple-700",
    red: "from-red-500 to-red-700",
  };
  return (
    <div
      className={`bg-gradient-to-br ${colors[color]} rounded-xl p-4 text-white shadow-lg`}
    >
      <div className="text-sm opacity-80 mb-1">{label}</div>
      <div className="text-3xl font-bold">{fmtNum(Number(value))}</div>
      {sub && <div className="text-xs opacity-70 mt-1">{sub}</div>}
    </div>
  );
}

// ─── メイン ──────────────────────────────────────────────────────────
export default function AdminPage() {
  const [completeData, setCompleteData] = useState<CompleteEntry[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [storeCount, setStoreCount] = useState(0);
  const [machineStores, setMachineStores] = useState<MachineStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [now] = useState(new Date());

  useEffect(() => {
    Promise.all([
      fetch("/complete_info.json").then((r) => r.json()).catch(() => []),
      fetch("/events_public.json").then((r) => r.json()).then((d) => d?.events ?? d ?? []).catch(() => []),
      fetch("/areas.json")
        .then((r) => r.json())
        .then((areas: Record<string, Record<string, unknown[]>>) => {
          const count = Object.values(areas).reduce(
            (a, pref) =>
              a +
              Object.values(pref).reduce((b, c) => b + (c as unknown[]).length, 0),
            0
          );
          setStoreCount(count);
        })
        .catch(() => {}),
      fetch("/store_machines.json").then((r) => r.json()).catch(() => []),
    ]).then(([complete, ev, , mach]) => {
      setCompleteData(complete);
      setEvents(ev);
      setMachineStores(mach);
      setLoading(false);
    });
  }, []);

  // コンプリート統計
  const completeStats = useMemo(() => {
    if (!completeData.length) return null;

    // 日付別件数
    const byDate: Record<string, number> = {};
    for (const e of completeData) {
      byDate[e.date] = (byDate[e.date] || 0) + 1;
    }
    const sortedDates = Object.entries(byDate).sort((a, b) =>
      b[0].localeCompare(a[0])
    );

    // 機種別（上位10）
    const byMachine: Record<string, number> = {};
    for (const e of completeData) {
      if (e.machine) byMachine[e.machine] = (byMachine[e.machine] || 0) + 1;
    }
    const topMachines = Object.entries(byMachine)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    // 店舗別（上位10）
    const byStore: Record<string, number> = {};
    for (const e of completeData) {
      if (e.store) byStore[e.store] = (byStore[e.store] || 0) + 1;
    }
    const topStores = Object.entries(byStore)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    return { sortedDates, topMachines, topStores };
  }, [completeData]);

  // イベント統計
  const eventStats = useMemo(() => {
    if (!events.length) return null;

    // 都道府県別
    const byPref: Record<string, number> = {};
    for (const e of events) {
      const p = e.pref || e.area || "不明";
      byPref[p] = (byPref[p] || 0) + 1;
    }
    const topPref = Object.entries(byPref)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    // 今日以降のイベント
    const todayStr = now.toISOString().slice(0, 10);
    const upcoming = events.filter((e) => (e.date || "") >= todayStr).length;

    return { topPref, upcoming };
  }, [events, now]);

  // 機種データがある店舗の都道府県別
  const machinesByPref = useMemo(() => {
    const byPref: Record<string, number> = {};
    for (const s of machineStores) {
      const p = s.pref || "不明";
      byPref[p] = (byPref[p] || 0) + 1;
    }
    return Object.entries(byPref)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
  }, [machineStores]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-white text-xl">読み込み中...</div>
      </div>
    );
  }

  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const latestDate = completeData[0]?.date || "";

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* ヘッダー */}
      <div className="bg-gradient-to-r from-gray-900 to-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">📊 管理ダッシュボード</h1>
            <p className="text-sm text-gray-400 mt-1">
              {now.toLocaleDateString("ja-JP", {
                year: "numeric",
                month: "long",
                day: "numeric",
                weekday: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
          <Link
            href="/"
            className="text-sm text-blue-400 hover:text-blue-300 transition"
          >
            ← サイトに戻る
          </Link>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
        {/* ─── サマリーカード ─── */}
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-4">📦 データサマリー</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="登録店舗数" value={storeCount} sub="全国47都道府県" color="blue" />
            <StatCard label="台数データ店舗" value={machineStores.length} sub={`${fmtNum(machineStores.length)} / ${fmtNum(storeCount)}`} color="green" />
            <StatCard label="コンプリート総数" value={completeData.length} sub={`最新: ${latestDate}`} color="orange" />
            <StatCard label="イベント数" value={events.length} sub={eventStats ? `今後: ${eventStats.upcoming}件` : ""} color="purple" />
          </div>
        </section>

        {/* ─── コンプリート分析 ─── */}
        <section className="grid md:grid-cols-2 gap-6">
          {/* 日付別件数 */}
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <h3 className="text-base font-bold text-orange-400 mb-4">
              🎰 コンプリート（日付別）
            </h3>
            <div className="space-y-2">
              {completeStats?.sortedDates.slice(0, 10).map(([date, cnt]) => {
                const isToday = date === todayStr;
                const max = completeStats.sortedDates[0]?.[1] || 1;
                const pct = Math.round((cnt / max) * 100);
                return (
                  <div key={date} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className={isToday ? "text-orange-400 font-bold" : "text-gray-300"}>
                        {isToday ? "🔴 " : ""}{date}
                      </span>
                      <span className="text-white font-mono">{cnt}件</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isToday ? "bg-orange-500" : "bg-orange-800"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 機種別ランキング */}
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <h3 className="text-base font-bold text-purple-400 mb-4">
              🏆 機種別コンプリートランキング
            </h3>
            <div className="space-y-2">
              {completeStats?.topMachines.map(([machine, cnt], i) => {
                const max = completeStats.topMachines[0]?.[1] || 1;
                const pct = Math.round((cnt / max) * 100);
                const medals = ["🥇", "🥈", "🥉"];
                return (
                  <div key={machine} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-300 truncate max-w-[200px]">
                        {medals[i] || `${i + 1}.`} {machine}
                      </span>
                      <span className="text-white font-mono ml-2">{cnt}</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple-700 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* ─── 店舗別コンプリート ─── */}
        <section className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-base font-bold text-green-400 mb-4">
            🏪 コンプリート報告が多い店舗 TOP10
          </h3>
          <div className="grid md:grid-cols-2 gap-x-8 gap-y-2">
            {completeStats?.topStores.map(([store, cnt], i) => (
              <div key={store} className="flex items-center justify-between text-sm py-1 border-b border-gray-800">
                <span className="text-gray-300">
                  <span className="text-gray-500 mr-2">{i + 1}.</span>
                  {store}
                </span>
                <span className="text-green-400 font-mono font-bold">{cnt}件</span>
              </div>
            ))}
          </div>
        </section>

        {/* ─── 台数データカバレッジ ─── */}
        <section className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-base font-bold text-blue-400 mb-4">
            🗾 台数データ取得済み都道府県
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {machinesByPref.map(([pref, cnt]) => (
              <div key={pref} className="bg-gray-800 rounded-lg p-2 text-center">
                <div className="text-xs text-gray-400">{pref}</div>
                <div className="text-white font-bold">{cnt}店</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-3">
            ※ 全国{fmtNum(storeCount)}店舗中 {machineStores.length}店舗取得済み
            （{Math.round((machineStores.length / storeCount) * 100)}%）
          </p>
        </section>

        {/* ─── 分析ツールリンク ─── */}
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-4">🔗 外部ツール</h2>
          <div className="grid md:grid-cols-3 gap-4">
            <a
              href="https://vercel.com/dashboard"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-900 border border-gray-700 hover:border-blue-500 rounded-xl p-4 transition group"
            >
              <div className="text-blue-400 text-lg mb-1">▲ Vercel Analytics</div>
              <div className="text-sm text-gray-400 group-hover:text-gray-300">
                ページビュー・訪問者数・Core Web Vitals
              </div>
            </a>
            <a
              href="https://github.com/gretschsick-lgtm/mesiuma-site/actions"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-900 border border-gray-700 hover:border-green-500 rounded-xl p-4 transition group"
            >
              <div className="text-green-400 text-lg mb-1">⚡ GitHub Actions</div>
              <div className="text-sm text-gray-400 group-hover:text-gray-300">
                自動収集スクリプトの実行ログ
              </div>
            </a>
            <a
              href="https://x.com/search?q=%E3%82%B3%E3%83%B3%E3%83%97%E3%83%AA%E3%83%BC%E3%83%88%E6%A9%9F%E8%83%BD%E7%99%BA%E5%8B%95+%E7%95%AA%E5%8F%B0&f=live"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-900 border border-gray-700 hover:border-sky-500 rounded-xl p-4 transition group"
            >
              <div className="text-sky-400 text-lg mb-1">𝕏 X 検索</div>
              <div className="text-sm text-gray-400 group-hover:text-gray-300">
                コンプリート情報リアルタイム確認
              </div>
            </a>
          </div>
        </section>

        {/* ─── 自動収集スケジュール ─── */}
        <section className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-base font-bold text-yellow-400 mb-4">
            ⏱ 自動収集スケジュール
          </h3>
          <div className="space-y-3">
            {[
              {
                name: "コンプリート情報",
                schedule: "30分ごと (JST 15〜翌2時)",
                file: "update_complete.yml",
                color: "orange",
              },
              {
                name: "イベント情報",
                schedule: "3時間ごと（6並列）",
                file: "update_events.yml",
                color: "blue",
              },
              {
                name: "台数・機種データ",
                schedule: "3時間ごと（8地域並列）",
                file: "update_machines.yml",
                color: "green",
              },
            ].map((item) => (
              <div
                key={item.name}
                className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
              >
                <div>
                  <div className="text-sm font-medium text-white">{item.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{item.file}</div>
                </div>
                <div className="text-sm text-yellow-300 font-mono">{item.schedule}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
