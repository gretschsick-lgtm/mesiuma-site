"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";

// ─── X アカウント設定 ──────────────────────────────────────────
const X_ACCOUNT = "mesiuma77";

// ─── 型 ─────────────────────────────────────────────────────
type Ev = {
  id: string | number;
  date: string;
  store: string;
  pref: string;
  area: string;
  event: string;
  detail: string;
  cast?: string;
  highlight?: boolean;
  x_url?: string;
  image_url?: string;
  url?: string;
  source?: string;
};
type YtVideo = { id: string; title: string; published: string; thumbnail?: string };
type PickupStore = { id: string; name: string; pref?: string; area?: string; note?: string; image_url?: string; x_url?: string; hp_url?: string };
type StoreMachine = { hours?: string; entry_rule?: string; address?: string; pachinko_total?: number; slot_total?: number };
type CompleteEntry = { id: string; date: string; time: string; store: string; machine: string; slot_number: string; image_url: string; x_url: string; };

// ─── 定数 ───────────────────────────────────────────────────
const PICKUP_NOTE_NG = ["高設定","設定6","設定5","甘い","甘釘","爆裂","出玉","モーニング","イブニング","激アツ","公約"];

const AREA_ORDER = ["関東","関西","東海","九州","東北","北海道","中国・四国"];
const CAST_NG    = ["ご来店の際","場合があります","この条件","絞り込む","注意ください"];
const STORE_NG   = ["この条件","絞り込む","通常稼働","景品入荷","パチンコ店","スロット店","大阪ホール","スーパーホール"];
const DATE_RE    = /^\d{4}\/\d{2}\/\d{2}/;

const PREF_SUFFIX: Record<string, string> = {
  "北海道":"北海道","東京":"東京都","大阪":"大阪府","京都":"京都府",
  "北海道道":"北海道","東京都":"東京都","大阪府":"大阪府","京都府":"京都府",
};
function normalizePref(p: string): string {
  if (!p) return p;
  if (PREF_SUFFIX[p]) return PREF_SUFFIX[p];
  if (/[都道府県]$/.test(p)) return p;
  return p + "県";
}

function cleanCast(cast?: string) {
  if (!cast) return "";
  if (CAST_NG.some(w => cast.includes(w))) return "";
  return cast
    .replace(/来店.*$/, "")
    .replace(/^.*(演者|ライター|出演)\s*/, "")
    .replace(/^[\s）)）、。,.\-─　]+/, "")
    .replace(/[\s）)）、。,.\-─　]+$/, "")
    .trim();
}
function safeImg(url?: string): string {
  if (!url) return "";
  return url;
}

function isValidStore(store: string) {
  if (STORE_NG.some(w => store.includes(w))) return false;
  if (DATE_RE.test(store)) return false;
  return store.length > 1;
}

function getEvType(ev: Ev): "raiten" | "satsuei" | "torisai" | "shunen" | "shindai" | "normal" {
  const event = ev.event || "";
  const cast  = ev.cast  || "";
  if (event.includes("来店") || cast.includes("来店") || event.includes("タレント") || event.includes("演者")) return "raiten";
  if (event.includes("撮影") || (cast.includes("撮影") && !CAST_NG.some(w=>cast.includes(w)))) return "satsuei";
  if (event.includes("取材") || event.includes("調査員")) return "torisai";
  if (event.includes("周年") || event.includes("リニューアル")) return "shunen";
  if (event.includes("新台") || event.includes("新装") || event.includes("オープン")) return "shindai";
  return "normal";
}

const STORE_URLS: Record<string, { x?: string; hp?: string }> = {
  "スロパチステーション":   { x:"https://x.com/slopachi_st",       hp:"https://slopachi.com" },
  "ぱちタウンコレクション": { x:"https://x.com/pachitown",          hp:"https://p-town.dmm.com" },
  "パチ＆スロ必勝本":       { x:"https://x.com/hisshobon",          hp:"https://hisshobon.jp" },
  "スロセレ":               { x:"https://x.com/srocele" },
  "フェスメディアX":        { x:"https://x.com/fes_media" },
  "1GAME":                  { x:"https://x.com/1game_ch",           hp:"https://1game.jp" },
  "回胴アドベンチャー":     { x:"https://x.com/kaidou_adv" },
  "BASHtv":                 { x:"https://x.com/BASH_tv",            hp:"https://bashtv.jp" },
  "PLUS MADE":              { x:"https://x.com/plusmade_slot" },
  "デリカツ":               { x:"https://x.com/deli_katsu" },
  "エースプロ":             { x:"https://x.com/acepro_slot" },
  "マルハン":  { x:"https://x.com/maruhan_jp",     hp:"https://www.maruhan.co.jp" },
  "ピーアーク":{ x:"https://x.com/piarc_official", hp:"https://www.p-arc.co.jp" },
  "楽園":      { x:"https://x.com/rakuen_hall",    hp:"https://www.rakuen-g.com" },
  "ガーデン":  { x:"https://x.com/garden_hall",    hp:"https://www.garden-g.com" },
  "キコーナ":  { x:"https://x.com/kikona_hall",    hp:"https://www.kikona.co.jp" },
  "エスパス":  { x:"https://x.com/espace_hall",    hp:"https://www.espace.co.jp" },
  "ダイナム":  { x:"https://x.com/dynam_japan",    hp:"https://www.dynam.jp" },
  "ガイア":    { x:"https://x.com/gaia_corp",      hp:"https://www.gaia-net.jp" },
};
function getLink(store: string) {
  for (const [k, v] of Object.entries(STORE_URLS)) if (store.includes(k)) return v;
  return {};
}

// カラー定数（DMMぱちタウン風ライトテーマ）
const C = {
  bg:     "#f5f5f5",
  white:  "#ffffff",
  border: "#e0e0e0",
  red:    "#e60000",
  red2:   "#cc0000",
  orange: "#ff6600",
  text:   "#222222",
  sub:    "#555555",
  muted:  "#888888",
  dim:    "#cccccc",
};

const EV_STYLE = {
  raiten:  { border:"#e60000", bg:"#fff5f5", label:"来店演者", badge:"#e60000", dot:"#e60000" },
  satsuei: { border:"#9933cc", bg:"#faf5ff", label:"撮影",    badge:"#9933cc", dot:"#9933cc" },
  torisai: { border:"#0066cc", bg:"#f5f9ff", label:"取材",    badge:"#0066cc", dot:"#0066cc" },
  shunen:  { border:"#cc8800", bg:"#fffbf0", label:"周年",    badge:"#cc8800", dot:"#cc8800" },
  shindai: { border:"#009933", bg:"#f0fff5", label:"新台",    badge:"#009933", dot:"#009933" },
  normal:  { border:"#e0e0e0", bg:"#ffffff", label:"",        badge:"#ff6600", dot:"#ffaa00" },
};

// 曜日ラベル
const DOW = ["日","月","火","水","木","金","土"];

function DateBadge({ mmdd }: { mmdd: string }) {
  const [mm, dd] = mmdd.split("/");
  if (!mm || !dd) return <span>{mmdd}</span>;
  const now = new Date();
  const d = new Date(now.getFullYear(), Number(mm) - 1, Number(dd));
  const dow = DOW[d.getDay()];
  const isWeekend = d.getDay() === 0 || d.getDay() === 6;
  return (
    <span style={{
      background: C.red, color: "#fff",
      fontSize: 12, fontWeight: 800, padding: "3px 10px",
      borderRadius: 4, letterSpacing: "0.02em",
      display: "inline-flex", alignItems: "center", gap: 4,
    }}>
      {mm}/{dd}
      <span style={{ opacity: isWeekend ? 1 : 0.85, fontWeight: 700 }}>（{dow}）</span>
    </span>
  );
}

// ─── ページ ─────────────────────────────────────────────────
export default function Page() {
  const [events, setEvents]   = useState<Ev[]>([]);
  const [storeHp, setStoreHp] = useState<Record<string,string>>({});
  const [loaded, setLoaded]   = useState(false);
  const [search, setSearch]   = useState("");
  const [area, setArea]       = useState("全て");
  const [pref, setPref]       = useState("全て");
  const [viewMode, setViewMode] = useState<"list"|"calendar">("list");
  const [showAll, setShowAll]   = useState(false);
  const [calYear, setCalYear]   = useState(() => new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(() => new Date().getMonth());
  const [calDay, setCalDay]     = useState<string|null>(null);
  const [selectedEv, setSelectedEv] = useState<Ev | null>(null);
  const [ytVideos, setYtVideos] = useState<YtVideo[]>([]);
  const [ytErr, setYtErr]       = useState(false);
  const [manualPickups, setManualPickups] = useState<PickupStore[]>([]);
  const [storeMachines, setStoreMachines] = useState<Record<string, StoreMachine>>({});
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [showFavorites, setShowFavorites] = useState(false);
  const [showRecordingsModal, setShowRecordingsModal] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [storeIdMap, setStoreIdMap] = useState<Record<string, string>>({});
  const [completeEntries, setCompleteEntries] = useState<CompleteEntry[]>([]);
  const router = useRouter();

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 640);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("favorites");
      if (saved) setFavorites(new Set<string>(JSON.parse(saved)));
    } catch {}
  }, []);


  useEffect(() => {
    fetch("/events_public.json").then(r=>r.json()).then(d=>{
      const evs: Ev[] = (Array.isArray(d) ? d : (d.events || [])).map((ev: Ev) => ({ ...ev, pref: normalizePref(ev.pref) }));
      setEvents(evs);
      setLoaded(true);
    }).catch(()=>setLoaded(true));
    fetch("/store_hp.json").then(r=>r.json()).then(setStoreHp).catch(()=>{});
    fetch("/pickup_stores.json").then(r=>r.json()).then(d=>setManualPickups(d.manual||[])).catch(()=>{});
    fetch("/store_machines.json").then(r=>r.json()).then(setStoreMachines).catch(()=>{});
    fetch("/store_ids.json").then(r=>r.json()).then(setStoreIdMap).catch(()=>{});
    fetch("/complete_info.json").then(r=>r.json()).then((d: CompleteEntry[]) => {
      const todayStr = new Date().toISOString().slice(0, 10);
      setCompleteEntries(d.filter(e => e.date === todayStr).slice(0, 20));
    }).catch(()=>{});
  }, []);

  useEffect(() => {
    const f = () => fetch("/api/youtube").then(r=>r.json()).then(d=>{
      if (d.recent?.length) setYtVideos(d.recent.slice(0, 4)); else setYtErr(true);
    }).catch(()=>setYtErr(true));
    f();
    const t = setInterval(f, 30*60*1000);
    return ()=>clearInterval(t);
  }, []);

  const areas = useMemo(() => {
    const s = new Set(events.filter(e=>isValidStore(e.store)).map(e=>e.area||"その他"));
    return ["全て",...AREA_ORDER.filter(a=>s.has(a)),...Array.from(s).filter(a=>!AREA_ORDER.includes(a))];
  }, [events]);

  const prefs = useMemo(() => {
    const s = new Set(
      events.filter(e=>isValidStore(e.store)&&(area==="全て"||e.area===area))
            .map(e=>e.pref).filter(p=>p && p !== "不明" && p !== "全国")
    );
    return ["全て",...Array.from(s).sort()];
  }, [events, area]);

  const handleArea = (a: string) => { setArea(a); setPref("全て"); setShowAll(false); setShowFavorites(false); };
  const handleFavorites = () => { setShowFavorites(v => !v); setArea("全て"); setPref("全て"); setSearch(""); setShowAll(false); setCalDay(null); };

  const toggleFavorite = (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    const key = String(id);
    setFavorites(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      try { localStorage.setItem("favorites", JSON.stringify(Array.from(next))); } catch {}
      return next;
    });
  };

  const todayStr = useMemo(() => {
    const now = new Date();
    return `${String(now.getMonth()+1).padStart(2,"0")}/${String(now.getDate()).padStart(2,"0")}`;
  }, []);

  const grouped = useMemo(() => {
    const s = search.toLowerCase();
    const filtered = events.filter(ev => {
      if (!isValidStore(ev.store)) return false;
      if (!ev.date) return false;
      if (ev.date < todayStr) return false;
      if (showFavorites && !favorites.has(String(ev.id))) return false;
      if (!showFavorites && area !== "全て" && ev.area !== area) return false;
      if (!showFavorites && pref !== "全て" && ev.pref !== pref) return false;
      if (s && ![ev.store,ev.pref,ev.area,ev.cast,ev.event,ev.detail].some(f=>f?.toLowerCase().includes(s))) return false;
      return true;
    });
    const map = new Map<string, Ev[]>();
    filtered.forEach(ev => {
      const d = ev.date || "日付不明";
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(ev);
    });
    return Array.from(map.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
  }, [events, search, area, pref, showFavorites, favorites]);

  const totalFiltered = grouped.reduce((n,[,evs])=>n+evs.length, 0);

  // 手動ピックアップから取材イベントがある店舗を除外
  const filteredManualPickups = useMemo(() => {
    const torisaiStores = new Set(
      events
        .filter(ev => ev.date >= todayStr && getEvType(ev) === "torisai")
        .map(ev => ev.store)
    );
    return manualPickups.filter(s => !torisaiStores.has(s.name));
  }, [events, manualPickups, todayStr]);

  // 自動ピックアップ: 毎日変わるアツいイベントを最大6件
  const autoPickups = useMemo(() => {
    const now = new Date();
    const limit = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7);
    const limitStr = `${String(limit.getMonth()+1).padStart(2,"0")}/${String(limit.getDate()).padStart(2,"0")}`;
    const manualNames = new Set(manualPickups.map(s => s.name));
    const typePriority: Record<string, number> = { raiten: 0, shunen: 1, shindai: 2, torisai: 3, satsuei: 4, normal: 9 };
    // 日付ベースの毎日変わるシード
    const seed = todayStr.replace(/\//g, "");
    const hash = (s: string) => {
      let h = 0;
      for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xfffffff;
      return h;
    };
    const candidates = events
      .filter(ev =>
        isValidStore(ev.store) &&
        ev.date && ev.date >= todayStr && ev.date <= limitStr &&
        getEvType(ev) !== "normal" &&
        !manualNames.has(ev.store) &&
        ev.store.length <= 25  // 長すぎる店舗名（文章化したもの）を除外
      )
      .sort((a, b) => {
        const dateDiff = a.date.localeCompare(b.date);
        if (dateDiff !== 0) return dateDiff;
        const typeDiff = typePriority[getEvType(a)] - typePriority[getEvType(b)];
        if (typeDiff !== 0) return typeDiff;
        return hash(a.store + seed) - hash(b.store + seed);
      });
    const seenStores = new Set<string>();
    const result: { store: string; pref: string; area: string; date: string; cast: string; image_url?: string; evType: string }[] = [];
    for (const ev of candidates) {
      if (seenStores.has(ev.store)) continue;
      seenStores.add(ev.store);
      const evType = getEvType(ev);
      result.push({ store: ev.store, pref: ev.pref, area: ev.area, date: ev.date, cast: cleanCast(ev.cast), image_url: safeImg(ev.image_url), evType });
      if (result.length >= 12) break;
    }
    return result;
  }, [events, manualPickups, todayStr]);

  // ─── 店舗マシンデータ検索（部分一致）──────────────────────
  const findStoreMachine = useMemo(() => {
    const keys = Object.keys(storeMachines);
    return (storeName: string): StoreMachine | null => {
      if (!storeName || keys.length === 0) return null;
      // 完全一致
      if (storeMachines[storeName]) return storeMachines[storeName];
      // 前方/後方部分一致
      const found = keys.find(k =>
        storeName.includes(k) || k.includes(storeName) ||
        storeName.replace(/[ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ０-９]/g, s => String.fromCharCode(s.charCodeAt(0) - 0xFEE0)).includes(k)
      );
      return found ? storeMachines[found] : null;
    };
  }, [storeMachines]);

  // ─── 店舗名 → /stores/{id} パス（部分一致）──────────────
  const getStoreHref = useCallback((storeName: string): string | null => {
    if (!storeName || Object.keys(storeIdMap).length === 0) return null;
    if (storeIdMap[storeName]) return `/stores/${storeIdMap[storeName]}`;
    const key = Object.keys(storeIdMap).find(k =>
      storeName.includes(k) || k.includes(storeName)
    );
    return key ? `/stores/${storeIdMap[key]}` : null;
  }, [storeIdMap]);

  // ─── 店舗収録（YouTubeイベント）──────────────────────────
  const storeRecordings = useMemo(() => {
    return events
      .filter(ev => {
        const url = ev.url || "";
        const src = ev.source || "";
        const hasYtUrl =
          url.includes("youtube.com/watch") ||
          url.includes("youtu.be/") ||
          url.includes("youtube.com/shorts/") ||
          (src.includes("youtube") && url.includes("youtube.com"));
        return hasYtUrl;
      })
      .filter(ev => isValidStore(ev.store))
      .slice(0, 200);
  }, [events]);

  // ─── イベントカード ──────────────────────────────────────
  const renderCard = (ev: Ev) => {
    const link   = getLink(ev.store);
    const cast   = cleanCast(ev.cast);
    const evType = getEvType(ev);
    const sty    = EV_STYLE[evType];
    const cardHp = link.hp || storeHp[ev.store] || "";
    const isSpecial = evType !== "normal";
    const imgSize = isMobile ? 52 : 64;
    const mach   = findStoreMachine(ev.store);

    const storeHref = getStoreHref(ev.store);
    return (
      <div key={ev.id} onClick={() => storeHref ? router.push(storeHref) : setSelectedEv(ev)} style={{
        background: sty.bg,
        border: `1px solid ${sty.border}44`,
        borderLeft: `3px solid ${sty.border}`,
        borderRadius: 8,
        padding: isMobile ? "10px 10px 10px 12px" : "14px 14px 14px 16px",
        display: "flex", alignItems: "flex-start", gap: isMobile ? 8 : 12,
        cursor: "pointer",
        transition: "box-shadow .15s",
      }}
        onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = `0 2px 12px ${sty.border}33`; }}
        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
      >
        {/* 左アイコン/画像 */}
        {safeImg(ev.image_url) ? (
          <div style={{ width: imgSize, minWidth: imgSize, height: imgSize, borderRadius: 6, overflow: "hidden", background: "#eee", flexShrink: 0 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={safeImg(ev.image_url)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} loading="lazy" />
          </div>
        ) : (
          <div style={{
            width: imgSize, minWidth: imgSize, height: imgSize,
            borderRadius: 6,
            background: sty.border + "18",
            border: `1px solid ${sty.border}33`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: isMobile ? 18 : 22, flexShrink: 0,
          }}>
            {evType === "raiten" ? "🎤" : evType === "satsuei" ? "📹" : evType === "torisai" ? "📡" : "🎰"}
          </div>
        )}

        {/* メイン情報 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* バッジ行 */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
            {ev.date && <DateBadge mmdd={ev.date} />}
            {isSpecial && (
              <span style={{
                background: sty.badge, color: "#fff",
                fontSize: isMobile ? 10 : 11, fontWeight: 800, padding: "2px 7px", borderRadius: 3,
              }}>{sty.label}</span>
            )}
            {ev.pref && ev.pref !== "不明" && (
              <span style={{ color: C.muted, fontSize: 10 }}>{ev.pref}</span>
            )}
          </div>

          {/* 店舗名 */}
          <div style={{ fontSize: isMobile ? 14 : 16, fontWeight: 800, color: C.text, marginBottom: 2, lineHeight: 1.3, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
            {ev.store}
          </div>

          {/* 台数・営業時間 */}
          {mach && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 3 }}>
              {(mach.pachinko_total || mach.slot_total) && (
                <span style={{ fontSize: 10, color: C.sub, display: "flex", alignItems: "center", gap: 2 }}>
                  🎰
                  {mach.pachinko_total ? `パチ${mach.pachinko_total}` : ""}
                  {mach.pachinko_total && mach.slot_total ? "/" : ""}
                  {mach.slot_total ? `スロ${mach.slot_total}` : ""}
                  台
                </span>
              )}
              {mach.hours && (
                <span style={{ fontSize: 10, color: C.sub }}>🕐 {mach.hours}</span>
              )}
              {mach.entry_rule && (
                <span style={{ fontSize: 10, background: "#f0f4ff", color: "#0055cc", padding: "1px 5px", borderRadius: 3, fontWeight: 700 }}>{mach.entry_rule}</span>
              )}
            </div>
          )}

          {/* イベント名 */}
          {ev.event && (
            <div style={{ fontSize: 11, color: isSpecial ? sty.badge : C.orange, fontWeight: 700, marginBottom: cast ? 4 : 0 }}>
              {ev.event}
              {!isMobile && ev.detail && ev.detail !== ev.event && (
                <span style={{ color: C.muted, fontWeight: 400, marginLeft: 5, fontSize: 10 }}>{ev.detail.slice(0, 40)}</span>
              )}
            </div>
          )}

          {/* 演者 */}
          {cast && cast.length < 30 && (
            <span style={{
              display: "inline-block",
              background: sty.badge + "14", border: `1px solid ${sty.badge}33`,
              color: sty.badge, fontSize: 10, fontWeight: 700,
              padding: "2px 7px", borderRadius: 999,
            }}>👤 {cast}</span>
          )}
        </div>

        {/* ハート＋リンクボタン */}
        <div onClick={e => e.stopPropagation()} style={{ display: "flex", flexDirection: "column", gap: 4, flexShrink: 0 }}>
          <button onClick={e => toggleFavorite(String(ev.id), e)} style={{
            background: favorites.has(String(ev.id)) ? "#ffe0e0" : "#f5f5f5",
            border: `1px solid ${favorites.has(String(ev.id)) ? "#ffaaaa" : C.border}`,
            color: favorites.has(String(ev.id)) ? "#e60000" : C.dim,
            width: isMobile ? 32 : 36, height: 30, borderRadius: 5, cursor: "pointer",
            fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all .15s",
          }}>{favorites.has(String(ev.id)) ? "❤️" : "🤍"}</button>
        </div>
        {!isMobile && (ev.x_url || link.x || cardHp) && (
          <div onClick={e => e.stopPropagation()} style={{
            display: "flex", flexDirection: "column", gap: 4, flexShrink: 0,
          }}>
            {(ev.x_url || link.x) && (
              <a href={ev.x_url || link.x} target="_blank" rel="noopener noreferrer" style={{
                background: "#111", color: "#fff",
                width: 36, height: 30,
                display: "flex", alignItems: "center", justifyContent: "center",
                borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700,
              }}>𝕏</a>
            )}
            {cardHp && (
              <a href={cardHp} target="_blank" rel="noopener noreferrer" style={{
                background: "#f0f4ff", border: "1px solid #aaccff",
                color: "#0055cc", width: 36, height: 30,
                display: "flex", alignItems: "center", justifyContent: "center",
                borderRadius: 5, textDecoration: "none", fontSize: 10, fontWeight: 700,
              }}>HP</a>
            )}
          </div>
        )}
      </div>
    );
  };

  // ─── 収録カード共通レンダラ ──────────────────────────────
  const renderRecordingCard = (ev: Ev, cardW: number, listRow = false) => {
    const ytUrl = ev.url || "";
    let videoId = "";
    const m1 = ytUrl.match(/[?&]v=([A-Za-z0-9_-]{11})/);
    const m2 = ytUrl.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
    const m3 = ytUrl.match(/\/shorts\/([A-Za-z0-9_-]{11})/);
    if (m1) videoId = m1[1];
    else if (m2) videoId = m2[1];
    else if (m3) videoId = m3[1];
    const thumb = videoId ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg` : safeImg(ev.image_url);
    const showPref = ev.pref && ev.pref !== "不明";

    if (listRow) {
      // モバイル一覧：横並びリスト行
      return (
        <a key={ev.id} href={ytUrl || "#"} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>
          <div style={{
            display: "flex", gap: 10, alignItems: "center",
            border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden",
            background: C.white, padding: 0,
            transition: "box-shadow .15s",
          }}
            onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 12px rgba(204,0,0,.18)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
          >
            {/* サムネイル */}
            <div style={{ position: "relative", width: 110, height: 72, flexShrink: 0, background: "#111", overflow: "hidden" }}>
              {thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumb} alt={ev.store} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} loading="lazy" />
              ) : (
                <div style={{ width: "100%", height: "100%", background: "linear-gradient(135deg,#1a1a1a,#333)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22 }}>🎬</div>
              )}
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", background: "rgba(204,0,0,.9)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "#fff", paddingLeft: 2 }}>▶</div>
              </div>
            </div>
            {/* 情報 */}
            <div style={{ flex: 1, minWidth: 0, padding: "8px 12px 8px 0" }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: C.text, lineHeight: 1.4, marginBottom: 4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" } as React.CSSProperties}>{ev.store}</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                {ev.date && <span style={{ fontSize: 11, color: C.red, fontWeight: 700 }}>{ev.date}</span>}
                {showPref && <span style={{ fontSize: 11, color: C.muted }}>{ev.pref}</span>}
                {ev.cast && <span style={{ fontSize: 11, color: "#9933cc", fontWeight: 600, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis", maxWidth: 120 }}>📹 {ev.cast}</span>}
              </div>
            </div>
          </div>
        </a>
      );
    }

    // カード表示（横スクロール・PCグリッド）
    return (
      <a key={ev.id} href={ytUrl || "#"} target="_blank" rel="noopener noreferrer"
        style={{ textDecoration: "none", ...(cardW ? { width: cardW, flexShrink: 0 } : {}), display: "flex" }}>
        <div style={{
          border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden",
          background: C.white, transition: "box-shadow .15s",
          display: "flex", flexDirection: "column", width: "100%",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 20px rgba(204,0,0,.2)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
        >
          <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", background: "#111", overflow: "hidden", flexShrink: 0 }}>
            {thumb ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={thumb} alt={ev.store} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} loading="lazy" />
            ) : (
              <div style={{ width: "100%", height: "100%", background: "linear-gradient(135deg,#1a1a1a,#333)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30 }}>🎬</div>
            )}
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.15)" }}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "rgba(204,0,0,.92)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, color: "#fff", paddingLeft: 3 }}>▶</div>
            </div>
            <div style={{ position: "absolute", top: 6, left: 6, background: "#9933cc", color: "#fff", fontSize: 9, fontWeight: 800, padding: "2px 7px", borderRadius: 3 }}>収録</div>
          </div>
          <div style={{ padding: "9px 10px", flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 72 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: C.text, lineHeight: 1.4, marginBottom: 4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{ev.store}</div>
            <div>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
                {ev.date && <span style={{ fontSize: 10, color: C.red, fontWeight: 700 }}>{ev.date}</span>}
                {showPref && <span style={{ fontSize: 10, color: C.muted }}>{ev.pref}</span>}
              </div>
              {ev.cast && (
                <div style={{ fontSize: 10, color: "#9933cc", fontWeight: 700, marginTop: 3, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>📹 {ev.cast}</div>
              )}
            </div>
          </div>
        </div>
      </a>
    );
  };

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Hiragino Kaku Gothic ProN','Noto Sans JP',sans-serif" }}>

      {/* ━━ 店舗収録一覧モーダル ━━ */}
      {showRecordingsModal && (
        <div onClick={() => setShowRecordingsModal(false)} style={{
          position: "fixed", inset: 0, zIndex: 1100,
          background: "rgba(0,0,0,.65)", backdropFilter: "blur(3px)",
          display: "flex", alignItems: "flex-end", justifyContent: "center",
          padding: 0,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: C.white, borderRadius: "16px 16px 0 0",
            width: "100%", maxWidth: 900,
            maxHeight: "90vh", overflowY: "auto",
            boxShadow: "0 -8px 40px rgba(0,0,0,.3)",
          }}>
            {/* ヘッダー */}
            <div style={{ position: "sticky", top: 0, background: C.white, zIndex: 1, borderBottom: `1px solid ${C.border}`, padding: "16px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 4, height: 20, background: "#cc0000", borderRadius: 2 }} />
                <span style={{ fontSize: 16, fontWeight: 800, color: C.text }}>📹 店舗収録</span>
                <span style={{ background: "#cc0000", color: "#fff", fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 3 }}>YouTube</span>
                <span style={{ fontSize: 12, color: C.muted }}>{storeRecordings.length}件</span>
              </div>
              <button onClick={() => setShowRecordingsModal(false)} style={{
                background: "#f5f5f5", border: `1px solid ${C.border}`,
                color: C.muted, width: 36, height: 36, borderRadius: 18,
                cursor: "pointer", fontSize: 18, display: "flex", alignItems: "center", justifyContent: "center",
              }}>✕</button>
            </div>
            {/* グリッド / リスト */}
            <div style={{ padding: "16px", display: isMobile ? "flex" : "grid", flexDirection: "column", gridTemplateColumns: isMobile ? undefined : "repeat(4,1fr)", gap: 10 }}>
              {storeRecordings.map(ev => renderRecordingCard(ev, 0, isMobile))}
            </div>
          </div>
        </div>
      )}

      {/* ━━ モーダル ━━ */}
      {selectedEv && (() => {
        const ev = selectedEv;
        const evType = getEvType(ev);
        const sty = EV_STYLE[evType];
        const cast = cleanCast(ev.cast);
        const link = getLink(ev.store);
        const hp = link.hp || storeHp[ev.store] || "";
        const mapQ = encodeURIComponent(`${ev.store} ${ev.pref || ""}`);
        const embedSrc = `https://maps.google.com/maps?q=${mapQ}&output=embed&hl=ja&z=16`;
        const mach = findStoreMachine(ev.store);
        return (
          <div onClick={() => setSelectedEv(null)} style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,.6)", backdropFilter: "blur(3px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
          }}>
            <div onClick={e => e.stopPropagation()} style={{
              background: C.white, border: `2px solid ${sty.border}`,
              borderRadius: 12, maxWidth: 520, width: "100%",
              maxHeight: "90vh", overflowY: "auto",
              boxShadow: `0 8px 40px rgba(0,0,0,.25)`,
            }}>
              <div style={{ width: "100%", height: 200, borderRadius: "10px 10px 0 0", overflow: "hidden" }}>
                <iframe src={embedSrc} width="100%" height="200"
                  style={{ border: 0, display: "block" }} allowFullScreen loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade" />
              </div>
              <div style={{ padding: "18px 20px 22px" }}>
                <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 12 }}>
                  {ev.date && <DateBadge mmdd={ev.date} />}
                  {evType !== "normal" && (
                    <span style={{ background: sty.badge, color: "#fff", fontWeight: 800, fontSize: 12, padding: "3px 10px", borderRadius: 3 }}>
                      {sty.label}
                    </span>
                  )}
                  {ev.pref && ev.pref !== "不明" && (
                    <span style={{ background: "#f5f5f5", color: C.muted, fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 3, border: `1px solid ${C.border}` }}>
                      {ev.pref}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 22, fontWeight: 900, color: C.text, marginBottom: 4, lineHeight: 1.25 }}>{ev.store}</div>
                {ev.area && <div style={{ color: C.muted, fontSize: 12, marginBottom: mach ? 8 : 14 }}>{ev.area}</div>}
                {/* 台数・営業時間・住所 */}
                {mach && (
                  <div style={{ background: "#f8f8f8", border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 14px", marginBottom: 14 }}>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      {(mach.pachinko_total || mach.slot_total) && (
                        <div>
                          <div style={{ fontSize: 10, color: C.muted, marginBottom: 2 }}>設置台数</div>
                          <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>
                            {mach.pachinko_total ? `パチ ${mach.pachinko_total}台` : ""}
                            {mach.pachinko_total && mach.slot_total ? "  " : ""}
                            {mach.slot_total ? `スロ ${mach.slot_total}台` : ""}
                          </div>
                        </div>
                      )}
                      {mach.hours && (
                        <div>
                          <div style={{ fontSize: 10, color: C.muted, marginBottom: 2 }}>営業時間</div>
                          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>🕐 {mach.hours}</div>
                        </div>
                      )}
                      {mach.entry_rule && (
                        <div>
                          <div style={{ fontSize: 10, color: C.muted, marginBottom: 2 }}>入場方法</div>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#0055cc" }}>{mach.entry_rule}</div>
                        </div>
                      )}
                    </div>
                    {mach.address && (
                      <div style={{ fontSize: 11, color: C.muted, marginTop: 8, lineHeight: 1.5 }}>📍 {mach.address}</div>
                    )}
                  </div>
                )}
                {cast && (
                  <div style={{
                    background: sty.badge + "10", border: `1px solid ${sty.badge}33`,
                    borderRadius: 8, padding: "10px 14px", marginBottom: 14,
                  }}>
                    <div style={{ color: C.muted, fontSize: 10, marginBottom: 3 }}>出演演者</div>
                    <div style={{ color: sty.badge, fontWeight: 900, fontSize: 15 }}>👤 {cast}</div>
                  </div>
                )}
                {ev.detail && ev.detail !== ev.event && (
                  <div style={{ background: "#f8f8f8", borderRadius: 6, padding: "12px", fontSize: 12, color: C.sub, lineHeight: 1.7, marginBottom: 14, border: `1px solid ${C.border}` }}>
                    {ev.detail}
                  </div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <a href={`https://www.google.co.jp/maps/search/${mapQ}`} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                      background: "#e8f5ee", color: "#22aa55", border: "1px solid #aaddbb",
                      padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                    📍 Googleマップで探す
                  </a>
                  {(ev.x_url || link.x) && (
                    <a href={ev.x_url || link.x} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                        background: "#111", color: "#fff", border: "1px solid #333",
                        padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                      𝕏 {ev.x_url ? "ツイートを見る" : "X公式アカウント"}
                    </a>
                  )}
                  {hp && (
                    <a href={hp} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                        background: "#f0f4ff", color: "#0055cc", border: "1px solid #aaccff",
                        padding: "11px", borderRadius: 8, textDecoration: "none", fontWeight: 700, fontSize: 13 }}>
                      🌐 ホール公式サイト
                    </a>
                  )}
                </div>
                <button onClick={() => setSelectedEv(null)} style={{
                  marginTop: 12, width: "100%", background: "#f5f5f5",
                  border: `1px solid ${C.border}`, color: C.muted,
                  padding: "9px", borderRadius: 6, cursor: "pointer", fontSize: 12,
                }}>閉じる</button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ━━ HEADER ━━ */}
      <header style={{
        position: "sticky", top: 0, zIndex: 200,
        background: "#fff",
        borderBottom: `3px solid ${C.red}`,
        boxShadow: "0 2px 8px rgba(0,0,0,.08)",
      }}>
        {/* PC: 1行レイアウト / モバイル: 2行レイアウト */}
        {isMobile ? (
          <div>
            {/* 1行目: ロゴ + 件数 */}
            <div style={{ padding: "0 14px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 42 }}>
              <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 7 }}>
                <div style={{ background: C.red, color: "#fff", fontWeight: 900, fontSize: 12, padding: "3px 6px", borderRadius: 4, lineHeight: 1 }}>🔥</div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 900, color: C.red, lineHeight: 1 }}>メシウマ稼働株式会社</div>
                  <div style={{ fontSize: 9, color: C.muted }}>全国パチスロイベント情報</div>
                </div>
              </Link>
              <span style={{ fontSize: 11, color: C.muted, fontWeight: 700 }}>
                {loaded ? <><span style={{ color: C.red, fontWeight: 800 }}>{events.length.toLocaleString()}</span>件</> : ""}
              </span>
            </div>
            {/* 2行目: タブ */}
            <nav style={{ display: "flex", borderTop: `1px solid ${C.border}` }}>
              {[
                { href: "/",          label: "ホーム",       icon: "🏠", active: true },
                { href: "/torisai",   label: "取材",         icon: "📡", active: false },
                { href: "/complete",  label: "コンプリート", icon: "🎰", active: false },
                { href: "/stores",    label: "ホール",       icon: "🔍", active: false },
                { href: "/blog",      label: "ブログ",       icon: "📝", active: false },
              ].map(({ href, label, icon, active }) => (
                <Link key={href} href={href} style={{
                  flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  padding: "6px 0", textDecoration: "none",
                  borderBottom: active ? `3px solid ${C.red}` : "3px solid transparent",
                  background: active ? "#fff5f5" : "transparent",
                }}>
                  <span style={{ fontSize: 16 }}>{icon}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: active ? C.red : C.muted, marginTop: 1 }}>{label}</span>
                </Link>
              ))}
            </nav>
          </div>
        ) : (
          <div style={{ maxWidth: 1160, margin: "0 auto", padding: "0 16px", display: "flex", alignItems: "center", height: 52, gap: 0 }}>
            {/* ロゴ */}
            <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 8, marginRight: 20, flexShrink: 0 }}>
              <div style={{ background: C.red, color: "#fff", fontWeight: 900, fontSize: 13, padding: "4px 8px", borderRadius: 4, lineHeight: 1 }}>🔥</div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 900, color: C.red, lineHeight: 1 }}>メシウマ稼働株式会社</div>
                <div style={{ fontSize: 9, color: C.muted, letterSpacing: "0.04em" }}>全国パチスロイベント情報</div>
              </div>
            </Link>
            {/* ナビタブ */}
            <nav style={{ display: "flex", alignItems: "stretch", flex: 1, gap: 0 }}>
              {[
                { href: "/",         label: "イベント情報",   sub: "取材来店、勝率など", icon: "🏪", active: true },
                { href: "/torisai", label: "店舗取材",       sub: "メディア取材一覧",   icon: "📡", active: false },
                { href: "/complete",label: "コンプリート",   sub: "設定確定・挙動速報",  icon: "🎰", active: false },
                { href: "/stores",  label: "ホール検索",     sub: "全国1,000店舗以上",  icon: "🔍", active: false },
                { href: "/blog",    label: "ブログ",         sub: "攻略、動画など",     icon: "📝", active: false },
              ].map(({ href, label, sub, icon, active }) => (
                <Link key={href} href={href} style={{
                  display: "flex", flexDirection: "column", justifyContent: "center",
                  padding: "0 16px", textDecoration: "none",
                  borderBottom: active ? `3px solid ${C.red}` : "3px solid transparent",
                  background: active ? "#fff5f5" : "transparent",
                  transition: "background .15s",
                  marginBottom: -3,
                }}>
                  <div style={{ fontSize: 13, fontWeight: 800, color: active ? C.red : C.text, display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 14 }}>{icon}</span> {label}
                  </div>
                  <div style={{ fontSize: 9, color: C.muted }}>{sub}</div>
                </Link>
              ))}
            </nav>
          </div>
        )}
      </header>

      {/* ━━ 検索エリア ━━ */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: isMobile ? "12px 10px 10px" : "18px 16px 16px" }}>
          {/* 検索バー */}
          <div style={{ display: "flex", gap: 8, maxWidth: isMobile ? "100%" : 600, marginBottom: 10 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: C.muted, fontSize: 15, pointerEvents: "none" }}>🔍</span>
              <input
                value={search}
                onChange={e => { setSearch(e.target.value); setCalDay(null); setShowAll(false); }}
                placeholder={isMobile ? "店舗名・地域・演者名" : "店舗名・駅名・地域・演者名で検索"}
                style={{
                  width: "100%", padding: isMobile ? "9px 10px 9px 32px" : "10px 14px 10px 38px",
                  background: "#fff", border: `1px solid ${C.border}`,
                  borderRadius: 6, color: C.text, fontSize: isMobile ? 14 : 14,
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color .2s",
                }}
                onFocus={e => (e.target.style.borderColor = C.red)}
                onBlur={e => (e.target.style.borderColor = C.border)}
              />
            </div>
            <button style={{
              background: C.red, color: "#fff",
              padding: "0 16px", border: "none", borderRadius: 6,
              fontSize: 14, fontWeight: 700, cursor: "pointer", flexShrink: 0,
            }}>検索</button>
          </div>

          {/* 人気キーワード */}
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: C.muted, fontWeight: 700, marginRight: 1, whiteSpace: "nowrap" }}>人気</span>
            {(isMobile
              ? ["蒲田","錦糸町","北千住","新宿","梅田","なんば","天神"]
              : ["蒲田","錦糸町","北千住","赤羽","新宿","池袋","立川","梅田","なんば","天神","博多","栄"]
            ).map(s => (
              <button key={s} onClick={() => { setSearch(search === s ? "" : s); setCalDay(null); setShowAll(false); }} style={{
                background: search === s ? C.red : "#f5f5f5",
                border: `1px solid ${search === s ? C.red : C.border}`,
                color: search === s ? "#fff" : C.sub,
                fontSize: 11, fontWeight: 600, padding: "3px 10px",
                borderRadius: 999, cursor: "pointer", transition: "all .15s",
              }}>{s}</button>
            ))}
          </div>

          {loaded && (
            <div style={{ marginTop: 8, fontSize: 11, color: C.muted }}>
              <span style={{ color: C.red, fontWeight: 700 }}>{totalFiltered}</span>件 / 全{events.length.toLocaleString()}件
            </div>
          )}
        </div>
      </div>

      {/* ━━ 店舗収録 ━━ */}
      {storeRecordings.length > 0 && (
        <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ maxWidth: 1160, margin: "0 auto", padding: "16px 16px 4px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 4, height: 20, background: "#cc0000", borderRadius: 2 }} />
                <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>📹 店舗収録</span>
                <span style={{ background: "#cc0000", color: "#fff", fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 3 }}>YouTube</span>
              </div>
              <button onClick={() => setShowRecordingsModal(true)} style={{
                background: "#f5f5f5", border: `1px solid ${C.border}`,
                color: C.sub, fontSize: 12, fontWeight: 700,
                padding: "5px 14px", borderRadius: 999, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 4,
                transition: "all .15s",
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "#fff0f0"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#cc0000"; (e.currentTarget as HTMLButtonElement).style.color = "#cc0000"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "#f5f5f5"; (e.currentTarget as HTMLButtonElement).style.borderColor = C.border; (e.currentTarget as HTMLButtonElement).style.color = C.sub; }}
              >
                一覧を見る <span style={{ fontSize: 14 }}>›</span>
              </button>
            </div>

            <div style={{ overflowX: "auto", paddingBottom: 16 }}>
              <div style={{ display: "flex", gap: 12 }}>
                {storeRecordings.slice(0, 10).map(ev => renderRecordingCard(ev, isMobile ? 160 : 200))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ━━ バナーエリア ━━ */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}` }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>

          {/* バナー3枚 PC:横並び / モバイル:縦積み */}
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(3, 1fr)", gap: 10 }}>

          {/* メシマズ取材バナー（赤） */}
          <Link href="/meshimazu" style={{ textDecoration: "none", display: "block" }}>
            <div style={{
              background: "linear-gradient(135deg, #aa0000 0%, #cc0000 50%, #e60000 100%)",
              borderRadius: 8, padding: isMobile ? "14px 16px" : "16px 22px",
              display: "flex", alignItems: "center", gap: 12,
              transition: "opacity .15s", height: "100%", boxSizing: "border-box",
              boxShadow: "0 2px 12px rgba(200,0,0,.35)",
            }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.opacity = "0.92"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.opacity = "1"; }}
            >
              <div style={{ fontSize: isMobile ? 30 : 36, flexShrink: 0 }}>😱</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: isMobile ? 15 : 17, fontWeight: 900, color: "#fff", marginBottom: 3, lineHeight: 1.3 }}>
                  メシマズ店舗取材一覧
                </div>
                {!isMobile && <div style={{ fontSize: 12, color: "rgba(255,255,255,.8)" }}>
                  メシマズ認定店舗の取材・調査レポートをまとめてチェック
                </div>}
              </div>
              <div style={{
                background: "rgba(255,255,255,.2)", color: "#fff",
                fontSize: 12, fontWeight: 700, padding: "6px 14px",
                borderRadius: 999, border: "1px solid rgba(255,255,255,.4)",
                whiteSpace: "nowrap", flexShrink: 0,
              }}>
                見る ›
              </div>
            </div>
          </Link>

          {/* 店舗取材バナー（青） */}
          <Link href="/torisai" style={{ textDecoration: "none", display: "block" }}>
            <div style={{
              background: "linear-gradient(135deg, #0044aa 0%, #0066cc 50%, #0088ee 100%)",
              borderRadius: 8, padding: isMobile ? "14px 16px" : "16px 22px",
              display: "flex", alignItems: "center", gap: 12,
              transition: "opacity .15s", height: "100%", boxSizing: "border-box",
              boxShadow: "0 2px 12px rgba(0,102,204,.3)",
            }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.opacity = "0.92"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.opacity = "1"; }}
            >
              <div style={{ fontSize: isMobile ? 30 : 36, flexShrink: 0 }}>📡</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: isMobile ? 15 : 17, fontWeight: 900, color: "#fff", marginBottom: 3 }}>
                  店舗取材一覧
                </div>
                {!isMobile && <div style={{ fontSize: 12, color: "rgba(255,255,255,.8)" }}>
                  メディア取材・調査員訪問イベントをまとめてチェック
                </div>}
              </div>
              <div style={{
                background: "rgba(255,255,255,.2)", color: "#fff",
                fontSize: 12, fontWeight: 700, padding: "6px 14px",
                borderRadius: 999, border: "1px solid rgba(255,255,255,.4)",
                whiteSpace: "nowrap", flexShrink: 0,
              }}>
                見る ›
              </div>
            </div>
          </Link>

          {/* 社員・演者一覧バナー（オレンジ） */}
          <Link href="/cast" style={{ textDecoration: "none", display: "block" }}>
            <div style={{
              background: "linear-gradient(135deg, #cc4400 0%, #ff6600 50%, #ff8833 100%)",
              borderRadius: 8, padding: isMobile ? "14px 16px" : "16px 22px",
              display: "flex", alignItems: "center", gap: 12,
              transition: "opacity .15s", height: "100%", boxSizing: "border-box",
              boxShadow: "0 2px 12px rgba(255,102,0,.3)",
            }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.opacity = "0.92"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.opacity = "1"; }}
            >
              <div style={{ fontSize: isMobile ? 30 : 36, flexShrink: 0 }}>🎬</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: isMobile ? 15 : 17, fontWeight: 900, color: "#fff", marginBottom: 3 }}>
                  社員・演者一覧
                </div>
                {!isMobile && <div style={{ fontSize: 12, color: "rgba(255,255,255,.8)" }}>
                  メシウマ稼働株式会社に所属する社員・演者の出演スケジュール
                </div>}
              </div>
              <div style={{
                background: "rgba(255,255,255,.2)", color: "#fff",
                fontSize: 12, fontWeight: 700, padding: "6px 14px",
                borderRadius: 999, border: "1px solid rgba(255,255,255,.4)",
                whiteSpace: "nowrap", flexShrink: 0,
              }}>
                見る ›
              </div>
            </div>
          </Link>

        </div>
        </div>
      </div>

      {/* ━━ ピックアップ メシマズ店舗 ━━ */}
      {(filteredManualPickups.length > 0 || autoPickups.length > 0) && (
        <div style={{ background: C.white, borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
          <div style={{ maxWidth: 1160, margin: "0 auto", padding: "16px 16px 4px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 4, height: 20, background: C.red, borderRadius: 2 }} />
                <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>ピックアップ メシマズ店舗</span>
              </div>
              <span style={{ fontSize: 11, color: C.muted }}>タップで絞り込み</span>
            </div>
            <div style={{ overflowX: "auto", paddingBottom: 14 }}>
              <div style={{ display: "flex", gap: 10, width: "max-content" }}>
                {/* 手動（PR）*/}
                {filteredManualPickups.map(s => {
                  const noteNg = s.note && PICKUP_NOTE_NG.some(w => s.note!.includes(w));
                  return (
                    <button key={s.id} onClick={() => { setSearch(s.name); setCalDay(null); setShowAll(false); window.scrollTo({ top: 500, behavior: "smooth" }); }} style={{
                      background: "#fff8f0", border: `2px solid ${C.red}`,
                      borderRadius: 10, padding: 0, cursor: "pointer",
                      width: 130, height: 172, flexShrink: 0, overflow: "hidden",
                      display: "flex", flexDirection: "column", textAlign: "left",
                      transition: "box-shadow .15s",
                    }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = `0 4px 16px ${C.red}44`; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                    >
                      {s.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={s.image_url} alt={s.name} style={{ width: "100%", height: 80, objectFit: "cover", display: "block" }} loading="lazy" />
                      ) : (
                        <div style={{ width: "100%", height: 80, background: `linear-gradient(135deg, #aa0000, ${C.red})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>😱</div>
                      )}
                      <div style={{ padding: "7px 9px 9px" }}>
                        <div style={{ display: "flex", gap: 4, marginBottom: 5 }}>
                          <span style={{ background: C.red, color: "#fff", fontSize: 9, fontWeight: 800, padding: "1px 6px", borderRadius: 2 }}>PR</span>
                          {s.pref && <span style={{ fontSize: 9, color: C.muted }}>{s.pref}</span>}
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 800, color: C.text, lineHeight: 1.3, marginBottom: s.note ? 4 : 0,
                          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{s.name}</div>
                        {s.note && !noteNg && <div style={{ fontSize: 10, color: C.sub, lineHeight: 1.4 }}>{s.note}</div>}
                        {noteNg && (
                          <div style={{ fontSize: 9, color: "#cc0000", fontWeight: 700, background: "#fff0f0", borderRadius: 3, padding: "2px 5px" }}>
                            ⚠️ 表現要確認
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
                {/* 自動ピックアップ */}
                {autoPickups.map(s => {
                  const sty = EV_STYLE[s.evType as keyof typeof EV_STYLE] ?? EV_STYLE.raiten;
                  const defaultBg: Record<string, string> = {
                    raiten:  "linear-gradient(135deg,#b30000,#e60000,#ff4444)",
                    shunen:  "linear-gradient(135deg,#996600,#cc8800,#ffaa00)",
                    shindai: "linear-gradient(135deg,#006622,#009933,#33cc66)",
                    torisai: "linear-gradient(135deg,#003380,#0066cc,#3399ff)",
                    satsuei: "linear-gradient(135deg,#661099,#9933cc,#cc66ff)",
                  };
                  const defaultIcon: Record<string, string> = {
                    raiten:"📅", shunen:"🎊", shindai:"✨", torisai:"📡", satsuei:"📹",
                  };
                  const defaultLabel: Record<string, string> = {
                    raiten:"来店イベント", shunen:"周年イベント", shindai:"新台情報", torisai:"取材", satsuei:"撮影",
                  };
                  const pickupHref = getStoreHref(s.store);
                  const pickupInner = (
                    <div style={{
                      background: "#f8f8f8", border: `2px solid ${sty.border}44`,
                      borderRadius: 10, cursor: "pointer",
                      width: 130, height: 172, flexShrink: 0, overflow: "hidden",
                      display: "flex", flexDirection: "column", textAlign: "left",
                    }}>
                      {s.image_url ? (
                        <div style={{ width: "100%", height: 80, overflow: "hidden", position: "relative" }}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={s.image_url} alt={s.store} style={{ width: "100%", height: "100%", objectFit: "cover" }} loading="lazy" />
                          <div style={{ position: "absolute", top: 5, left: 5, background: sty.badge, color: "#fff", fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 3 }}>
                            {sty.label || defaultLabel[s.evType] || ""}
                          </div>
                        </div>
                      ) : (
                        <div style={{ width: "100%", height: 80, background: defaultBg[s.evType] || defaultBg.raiten, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2 }}>
                          <div style={{ fontSize: 20, color: "#fff", lineHeight: 1 }}>{defaultIcon[s.evType] || "📅"}</div>
                          <div style={{ fontSize: 9, fontWeight: 900, color: "#fff", letterSpacing: 1, opacity: 0.9 }}>{defaultLabel[s.evType] || ""}</div>
                        </div>
                      )}
                      <div style={{ padding: "7px 9px 9px" }}>
                        <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                          <span style={{ background: sty.badge, color: "#fff", fontSize: 9, fontWeight: 800, padding: "1px 6px", borderRadius: 2 }}>{sty.label || s.evType}</span>
                          {s.pref && s.pref !== "不明" && <span style={{ fontSize: 9, color: C.muted }}>{s.pref}</span>}
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 800, color: C.text, lineHeight: 1.3, marginBottom: 3,
                          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{s.store}</div>
                        {s.cast && s.cast.length < 20 && <div style={{ fontSize: 10, color: C.sub }}>👤 {s.cast}</div>}
                        <div style={{ fontSize: 10, color: sty.badge, fontWeight: 700, marginTop: 2 }}>{s.date}</div>
                      </div>
                    </div>
                  );
                  return pickupHref ? (
                    <Link key={s.store} href={pickupHref} style={{ textDecoration: "none", flexShrink: 0 }}>
                      {pickupInner}
                    </Link>
                  ) : (
                    <button key={s.store} onClick={() => { setSearch(s.store); setCalDay(null); setShowAll(false); window.scrollTo({ top: 500, behavior: "smooth" }); }}
                      style={{ background: "none", border: "none", padding: 0, flexShrink: 0 }}>
                      {pickupInner}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ━━ コンプリート速報 ━━ */}
      {completeEntries.length > 0 && (
        <div style={{ background: C.white, borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
          <div style={{ maxWidth: 1160, margin: "0 auto", padding: "16px 16px 4px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 4, height: 20, background: "#c9910a", borderRadius: 2 }} />
                <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>🏆 本日のコンプリート</span>
                <span style={{ fontSize: 11, color: "#c9910a", fontWeight: 700, background: "#fff8e0", border: "1px solid #f0cc60", borderRadius: 10, padding: "1px 8px" }}>
                  {completeEntries.length}件
                </span>
              </div>
              <a href="/complete" style={{ fontSize: 12, color: C.red, fontWeight: 700, textDecoration: "none" }}>
                もっと見る →
              </a>
            </div>
            <div style={{ overflowX: "auto", paddingBottom: 14 }}>
              <div style={{ display: "flex", gap: 8, width: "max-content" }}>
                {completeEntries.map(entry => (
                  <a key={entry.id} href={entry.x_url || "/complete"} target={entry.x_url ? "_blank" : undefined}
                    rel={entry.x_url ? "noopener noreferrer" : undefined}
                    style={{ textDecoration: "none", flexShrink: 0 }}>
                    <div style={{
                      width: 130, height: 172, flexShrink: 0, overflow: "hidden",
                      border: "2px solid #f0cc60", borderRadius: 10,
                      background: "#fffdf0",
                      display: "flex", flexDirection: "column",
                    }}>
                      {entry.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={entry.image_url} alt={entry.machine}
                          style={{ width: "100%", height: 80, objectFit: "cover", display: "block", flexShrink: 0 }} loading="lazy" />
                      ) : (
                        <div style={{ width: "100%", height: 80, flexShrink: 0, background: "linear-gradient(135deg,#996600,#c9910a,#f0cc60)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30 }}>🏆</div>
                      )}
                      <div style={{ padding: "6px 8px 8px", display: "flex", flexDirection: "column", gap: 3, overflow: "hidden" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <span style={{ background: "#c9910a", color: "#fff", fontSize: 9, fontWeight: 800, padding: "1px 5px", borderRadius: 2, whiteSpace: "nowrap" }}>コンプ</span>
                          {entry.time && <span style={{ fontSize: 9, color: "#888", marginLeft: "auto", whiteSpace: "nowrap" }}>{entry.time}</span>}
                        </div>
                        {entry.machine && (
                          <div style={{ fontSize: 11, fontWeight: 800, color: C.text, lineHeight: 1.3,
                            overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" } as React.CSSProperties}>
                            {entry.machine}
                          </div>
                        )}
                        {entry.store && (
                          <div style={{ fontSize: 10, color: "#555", lineHeight: 1.3,
                            overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" } as React.CSSProperties}>
                            {entry.store}
                          </div>
                        )}
                        {entry.slot_number && (
                          <div style={{ fontSize: 9, color: "#0055cc", fontWeight: 700 }}>{entry.slot_number}番台</div>
                        )}
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ━━ YouTube ━━ */}
      <div style={{ background: C.white, borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", padding: "16px" }}>
          {/* セクションタイトル */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 4, height: 20, background: C.red, borderRadius: 2 }} />
              <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>最新動画</span>
            </div>
            <a href="https://www.youtube.com/@mesiuma_kadou" target="_blank" rel="noopener noreferrer"
              style={{ background: "#cc0000", color: "#fff", padding: "5px 14px", borderRadius: 5, textDecoration: "none", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
              ▶ チャンネルを見る
            </a>
          </div>

          {/* 4件グリッド */}
          {ytVideos.length > 0 ? (
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)",
              gap: 12,
            }}>
              {ytVideos.map((v, i) => (
                <a key={v.id} href={`https://www.youtube.com/watch?v=${v.id}`}
                  target="_blank" rel="noopener noreferrer"
                  style={{ textDecoration: "none", display: "flex", height: "100%" }}>
                  <div style={{
                    border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden",
                    transition: "box-shadow .15s", display: "flex", flexDirection: "column", width: "100%",
                  }}
                    onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 16px rgba(0,0,0,.12)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
                  >
                    {/* サムネイル */}
                    <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", background: "#111", overflow: "hidden", flexShrink: 0 }}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`}
                        alt={v.title}
                        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                        loading={i === 0 ? "eager" : "lazy"}
                      />
                      {/* 再生ボタン */}
                      <div style={{
                        position: "absolute", inset: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        background: "rgba(0,0,0,.15)",
                      }}>
                        <div style={{
                          width: 44, height: 44, borderRadius: "50%",
                          background: "rgba(204,0,0,.9)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 18, color: "#fff",
                        }}>▶</div>
                      </div>
                      {i === 0 && (
                        <div style={{
                          position: "absolute", top: 8, left: 8,
                          background: C.red, color: "#fff",
                          fontSize: 10, fontWeight: 800, padding: "2px 7px", borderRadius: 3,
                        }}>最新</div>
                      )}
                    </div>
                    {/* タイトル */}
                    <div style={{ padding: "10px 12px 12px", background: C.white, flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div style={{
                        fontSize: 12, fontWeight: 700, color: C.text, lineHeight: 1.5,
                        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                      }}>{v.title}</div>
                      {v.published && (
                        <div style={{ fontSize: 10, color: C.muted, marginTop: 5 }}>
                          {new Date(v.published).toLocaleDateString("ja-JP")}
                        </div>
                      )}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          ) : ytErr ? (
            <div style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, borderRadius: 8, padding: "24px", textAlign: "center" }}>
              <a href="https://www.youtube.com/@mesiuma_kadou" target="_blank" rel="noopener noreferrer"
                style={{ background: "#cc0000", color: "#fff", padding: "10px 24px", borderRadius: 6, textDecoration: "none", fontSize: 14, fontWeight: 700 }}>
                ▶ YouTubeを開く
              </a>
            </div>
          ) : (
            <div style={{
              display: "grid", gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)", gap: 12,
            }}>
              {[0,1,2,3].map(i => (
                <div key={i} style={{ background: "#f0f0f0", borderRadius: 8, aspectRatio: "16/9", animation: "pulse 1.5s ease-in-out infinite" }} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ━━ X バナー ━━ */}
      <div style={{ background: "#000", borderBottom: `1px solid #222`, marginBottom: 4 }}>
        <a
          href={`https://x.com/${X_ACCOUNT}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: "block", textDecoration: "none", maxWidth: 1160, margin: "0 auto", padding: "20px 16px" }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span style={{ fontSize: 32, fontWeight: 900, color: "#fff", lineHeight: 1 }}>𝕏</span>
              <div>
                <div style={{ color: "#fff", fontWeight: 800, fontSize: 15, lineHeight: 1.3 }}>専務アカウント</div>
                <div style={{ color: "#aaa", fontSize: 12, marginTop: 3 }}>@{X_ACCOUNT} ・ 最新のイベント情報・稼働実績はXで発信中</div>
              </div>
            </div>
            <div style={{ background: "#fff", color: "#000", padding: "9px 22px", borderRadius: 999, fontWeight: 800, fontSize: 13, whiteSpace: "nowrap", flexShrink: 0 }}>
              フォローする
            </div>
          </div>
        </a>
      </div>

      {/* ━━ メインコンテンツ ━━ */}
      <div style={{ maxWidth: 1160, margin: "0 auto", padding: `0 ${isMobile ? 10 : 16}px ${isMobile ? 72 : 80}px` }}>

        {/* フィルターバー */}
        <div style={{ background: C.white, borderRadius: 6, border: `1px solid ${C.border}`, padding: "14px 16px", marginTop: 16, marginBottom: 4 }}>

          {/* お気に入り＋リスト/カレンダー */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            {/* モバイルではボトムナビにあるので非表示 */}
            {!isMobile && (
              <button onClick={handleFavorites} style={{
                background: showFavorites ? "#ffe0e0" : "#f5f5f5",
                border: `1px solid ${showFavorites ? C.red : C.border}`,
                color: showFavorites ? C.red : C.muted,
                fontSize: 13, fontWeight: 800, padding: "6px 16px",
                borderRadius: 999, cursor: "pointer", transition: "all .15s",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span>{showFavorites ? "❤️" : "🤍"}</span>
                お気に入り
                {favorites.size > 0 && (
                  <span style={{
                    background: showFavorites ? C.red : C.dim,
                    color: "#fff", fontSize: 10, fontWeight: 900,
                    padding: "1px 7px", borderRadius: 999, minWidth: 18, textAlign: "center",
                  }}>{favorites.size}</span>
                )}
              </button>
            )}
            {isMobile && showFavorites && (
              <span style={{ fontSize: 12, color: C.red, fontWeight: 800 }}>❤️ お気に入り中</span>
            )}
            {isMobile && !showFavorites && <div />}
            <div style={{ display: "flex", gap: 6 }}>
              {(["list","calendar"] as const).map(m => (
                <button key={m} onClick={() => { setViewMode(m); setCalDay(null); }} style={{
                  background: viewMode === m ? C.red : "#f5f5f5",
                  border: `1px solid ${viewMode === m ? C.red : C.border}`,
                  color: viewMode === m ? "#fff" : C.muted,
                  fontSize: 12, fontWeight: 700, padding: "5px 12px",
                  borderRadius: 4, cursor: "pointer",
                }}>
                  {m === "list" ? "☰ リスト" : "📅 カレンダー"}
                </button>
              ))}
            </div>
          </div>

          {/* エリア（お気に入りOFF時のみ） */}
          {!showFavorites && (
            <>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2, whiteSpace: "nowrap" }}>エリア</span>
                {areas.map(a => (
                  <button key={a} onClick={() => handleArea(a)} style={{
                    background: area === a ? C.red : "#f5f5f5",
                    border: `1px solid ${area === a ? C.red : C.border}`,
                    color: area === a ? "#fff" : C.sub,
                    fontSize: 12, fontWeight: 700, padding: "5px 14px",
                    borderRadius: 999, cursor: "pointer", transition: "all .15s",
                  }}>{a}</button>
                ))}
              </div>
              {/* 都道府県 */}
              {prefs.length > 2 && (
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center", borderTop: `1px solid ${C.border}`, paddingTop: 8 }}>
                  <span style={{ fontSize: 11, color: C.muted, fontWeight: 700, marginRight: 2 }}>📍</span>
                  {prefs.map(p => (
                    <button key={p} onClick={() => setPref(p)} style={{
                      background: pref === p ? "#fff0f0" : "#f5f5f5",
                      border: `1px solid ${pref === p ? C.red : C.border}`,
                      color: pref === p ? C.red : C.sub,
                      fontSize: 11, fontWeight: 700, padding: "4px 11px",
                      borderRadius: 999, cursor: "pointer", transition: "all .15s",
                    }}>{p}</button>
                  ))}
                </div>
              )}
            </>
          )}

          {/* お気に入りON時のメッセージ */}
          {showFavorites && favorites.size === 0 && (
            <div style={{ textAlign: "center", padding: "12px 0 4px", color: C.muted, fontSize: 13 }}>
              イベントカードの 🤍 をタップしてお気に入りに追加できます
            </div>
          )}
        </div>

        {!loaded && <div style={{ color: C.dim, padding: 60, textAlign: "center", fontSize: 14 }}>読み込み中...</div>}
        {loaded && grouped.length === 0 && (
          <div style={{ color: C.muted, padding: 60, textAlign: "center", fontSize: 14 }}>該当するイベントがありません</div>
        )}

        {/* ── カレンダービュー ── */}
        {viewMode === "calendar" && loaded && (() => {
          const yr = calYear, mo = calMonth;
          const firstDay = new Date(yr, mo, 1).getDay();
          const daysInMonth = new Date(yr, mo + 1, 0).getDate();
          const moStr = String(mo + 1).padStart(2, "0");
          const dayMap = new Map<string, Ev[]>();
          grouped.forEach(([date, evs]) => {
            const [mm, dd] = date.split("/");
            if (mm === moStr) dayMap.set(dd, evs);
          });
          const cells: (number|null)[] = [...Array(firstDay).fill(null), ...Array.from({length:daysInMonth},(_,i)=>i+1)];
          while (cells.length % 7 !== 0) cells.push(null);
          return (
            <div style={{ marginTop: 16, background: C.white, borderRadius: 8, border: `1px solid ${C.border}`, padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 20, marginBottom: 16 }}>
                <button onClick={() => { const d=new Date(yr,mo-1,1); setCalYear(d.getFullYear()); setCalMonth(d.getMonth()); setCalDay(null); }}
                  style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.sub, width: 36, height: 36, borderRadius: 6, cursor: "pointer", fontSize: 18 }}>‹</button>
                <span style={{ color: C.text, fontWeight: 900, fontSize: 16 }}>{yr}年 {mo+1}月</span>
                <button onClick={() => { const d=new Date(yr,mo+1,1); setCalYear(d.getFullYear()); setCalMonth(d.getMonth()); setCalDay(null); }}
                  style={{ background: "#f5f5f5", border: `1px solid ${C.border}`, color: C.sub, width: 36, height: 36, borderRadius: 6, cursor: "pointer", fontSize: 18 }}>›</button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2, marginBottom: 4 }}>
                {["日","月","火","水","木","金","土"].map((d,i) => (
                  <div key={d} style={{ textAlign: "center", fontSize: 11, fontWeight: 700,
                    color: i===0?"#e60000":i===6?"#0066cc":C.muted, padding: "4px 0" }}>{d}</div>
                ))}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2 }}>
                {cells.map((day, idx) => {
                  if (!day) return <div key={idx} />;
                  const dd = String(day).padStart(2, "0");
                  const dayEvs = dayMap.get(dd) || [];
                  const isSelected = calDay === dd;
                  const hasRaiten = dayEvs.some(e=>getEvType(e)==="raiten");
                  const hasSatsuei = dayEvs.some(e=>getEvType(e)==="satsuei");
                  const hasTorisai = dayEvs.some(e=>getEvType(e)==="torisai");
                  const hasShunen = dayEvs.some(e=>getEvType(e)==="shunen");
                  const hasShindai = dayEvs.some(e=>getEvType(e)==="shindai");
                  const today = new Date();
                  const isToday = today.getFullYear()===yr && today.getMonth()===mo && today.getDate()===day;
                  return (
                    <div key={idx} onClick={() => setCalDay(isSelected ? null : dd)} style={{
                      background: isSelected ? "#fff0f0" : C.white,
                      border: `1px solid ${isSelected ? C.red : C.border}`,
                      borderRadius: 4, padding: "6px 4px 4px", textAlign: "center",
                      cursor: dayEvs.length ? "pointer" : "default", minHeight: 50,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: isToday ? 900 : 500,
                        color: isToday ? C.red : idx%7===0?"#e60000":idx%7===6?"#0066cc":C.text,
                        marginBottom: 3 }}>{day}</div>
                      {dayEvs.length > 0 && (
                        <>
                          <div style={{ display: "flex", gap: 2, justifyContent: "center", flexWrap: "wrap", marginBottom: 2 }}>
                            {hasRaiten  && <div style={{width:6,height:6,borderRadius:"50%",background:"#e60000"}}/>}
                            {hasSatsuei && <div style={{width:6,height:6,borderRadius:"50%",background:"#9933cc"}}/>}
                            {hasTorisai && <div style={{width:6,height:6,borderRadius:"50%",background:"#0066cc"}}/>}
                            {hasShunen  && <div style={{width:6,height:6,borderRadius:"50%",background:"#cc8800"}}/>}
                            {hasShindai && <div style={{width:6,height:6,borderRadius:"50%",background:"#009933"}}/>}
                          </div>
                          <div style={{ fontSize: 9, color: C.orange, fontWeight: 700 }}>{dayEvs.length}</div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 14, justifyContent: "center", marginTop: 12 }}>
                {[["#e60000","来店演者"],["#9933cc","撮影"],["#0066cc","取材"],["#cc8800","周年"],["#009933","新台"]].map(([c,l])=>(
                  <div key={l} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{width:8,height:8,borderRadius:"50%",background:c}}/>
                    <span style={{fontSize:10,color:C.muted}}>{l}</span>
                  </div>
                ))}
              </div>
              {calDay && (() => {
                const dayEvs = dayMap.get(calDay) || [];
                return (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, paddingBottom: 10, borderBottom: `1px solid ${C.border}` }}>
                      <DateBadge mmdd={`${moStr}/${calDay}`} />
                      <span style={{ color: C.muted, fontSize: 12 }}>{dayEvs.length}件</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {dayEvs.map(ev => renderCard(ev))}
                    </div>
                  </div>
                );
              })()}
            </div>
          );
        })()}

        {/* ── リストビュー ── */}
        {viewMode === "list" && (() => {
          const SHOW_COUNT = 20;
          let count = 0, cutIdx = grouped.length;
          for (let i = 0; i < grouped.length; i++) {
            count += grouped[i][1].length;
            if (count >= SHOW_COUNT) { cutIdx = i + 1; break; }
          }
          const visible = showAll ? grouped : grouped.slice(0, cutIdx);
          const remaining = grouped.length - cutIdx;
          const remainingEvs = showAll ? 0 : grouped.slice(cutIdx).reduce((n,[,e])=>n+e.length, 0);

          return (
            <>
              {visible.map(([date, evs]) => (
                <div key={date} style={{ marginTop: 20 }}>
                  <div style={{
                    display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                    marginBottom: 10, paddingBottom: 8, borderBottom: `2px solid ${C.red}`,
                  }}>
                    <DateBadge mmdd={date} />
                    <span style={{ color: C.muted, fontSize: 12 }}>{evs.length}件</span>
                    {evs.filter(e=>getEvType(e)==="raiten").length > 0 && (
                      <span style={{
                        background: "#fff0f0", border: "1px solid #ffaaaa",
                        color: "#e60000", fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 3,
                      }}>🎤 来店演者 {evs.filter(e=>getEvType(e)==="raiten").length}件</span>
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {evs.map(ev => renderCard(ev))}
                  </div>
                </div>
              ))}

              {/* もっと見るボタン */}
              {!showAll && remaining > 0 && (
                <div style={{ marginTop: 24 }}>
                  <button onClick={() => setShowAll(true)} style={{
                    width: "100%", background: C.white,
                    border: `1px solid ${C.red}`, color: C.red,
                    padding: "14px", borderRadius: 6,
                    fontSize: 14, fontWeight: 700, cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    transition: "background .15s",
                  }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "#fff0f0"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = C.white; }}
                  >
                    イベント一覧をもっと見る
                    <span style={{ background: C.red, color: "#fff", fontSize: 12, fontWeight: 800, padding: "2px 10px", borderRadius: 999 }}>
                      +{remainingEvs}件
                    </span>
                    <span>›</span>
                  </button>
                </div>
              )}

              {/* 折りたたむボタン */}
              {showAll && grouped.length > cutIdx && (
                <div style={{ marginTop: 24 }}>
                  <button onClick={() => { setShowAll(false); window.scrollTo({ top: 0, behavior: "smooth" }); }} style={{
                    width: "100%", background: "#f5f5f5",
                    border: `1px solid ${C.border}`, color: C.muted,
                    padding: "12px", borderRadius: 6,
                    fontSize: 13, fontWeight: 700, cursor: "pointer",
                  }}>
                    ↑ 先頭に戻る
                  </button>
                </div>
              )}
            </>
          );
        })()}
      </div>

      {/* ━━ モバイル ボトムナビ ━━ */}
      {isMobile && (
        <nav style={{
          position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 300,
          background: "#fff",
          borderTop: `1px solid ${C.border}`,
          boxShadow: "0 -2px 12px rgba(0,0,0,.08)",
          display: "flex", height: 56,
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}>
          {[
            { href: "/",         icon: "🏠", label: "ホーム",       active: true },
            { href: "/torisai",  icon: "📡", label: "取材",         active: false },
            { href: "/complete", icon: "🎰", label: "コンプリート", active: false },
            { href: "/stores",   icon: "🔍", label: "ホール",       active: false },
            { href: "/blog",     icon: "📝", label: "ブログ",       active: false },
          ].map(({ href, icon, label, active }) => (
            <Link key={href} href={href} style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 2,
              textDecoration: "none",
              color: active ? C.red : C.muted,
              borderTop: active ? `2px solid ${C.red}` : "2px solid transparent",
              background: active ? "#fff5f5" : "transparent",
              fontSize: 9, fontWeight: active ? 800 : 600,
            }}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>{icon}</span>
              {label}
            </Link>
          ))}
          <button onClick={handleFavorites} style={{
            flex: 1, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 2,
            border: "none", borderTop: showFavorites ? `2px solid ${C.red}` : "2px solid transparent",
            background: showFavorites ? "#fff5f5" : "transparent",
            cursor: "pointer",
            color: showFavorites ? C.red : C.muted,
            fontSize: 9, fontWeight: showFavorites ? 800 : 600,
            padding: 0, position: "relative",
          }}>
            <span style={{ fontSize: 18, lineHeight: 1 }}>{showFavorites ? "❤️" : "🤍"}</span>
            お気に入り
            {favorites.size > 0 && (
              <span style={{
                position: "absolute", top: 4, right: "calc(50% - 18px)",
                background: C.red, color: "#fff",
                fontSize: 9, fontWeight: 900, padding: "1px 4px",
                borderRadius: 999, minWidth: 16, textAlign: "center", lineHeight: 1.4,
              }}>{favorites.size}</span>
            )}
          </button>
        </nav>
      )}

      {/* ━━ 広告掲載募集 ━━ */}
      <div style={{ background: "#fff8f0", borderTop: "2px solid #e60000", padding: "32px 16px" }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <div style={{ width: 4, height: 22, background: "#e60000", borderRadius: 2 }} />
            <h2 style={{ fontSize: 18, fontWeight: 900, color: "#222", margin: 0 }}>📣 広告掲載・タイアップ募集</h2>
          </div>
          <p style={{ fontSize: 13, color: "#444", lineHeight: 1.8, margin: "0 0 20px" }}>
            メシウマ稼働株式会社は全国<strong>1,100店舗以上</strong>のパチンコ・パチスロホール情報を掲載する、
            業界特化型の情報プラットフォームです。<br />
            イベント告知・取材誘致・来店プロモーションなど、各種タイアップをご相談ください。
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{
              background: "#fff", border: "1px solid #e0e0e0", borderRadius: 10,
              padding: "16px 20px", flex: 1, minWidth: 200,
            }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "#e60000", marginBottom: 6 }}>🏪 ホール向け</div>
              <ul style={{ fontSize: 12, color: "#444", margin: 0, paddingLeft: 16, lineHeight: 2 }}>
                <li>取材・来店イベント掲載</li>
                <li>フロアマップ掲載</li>
                <li>ピックアップ店舗表示</li>
                <li>抽選時間・営業情報掲載</li>
              </ul>
            </div>
            <div style={{
              background: "#fff", border: "1px solid #e0e0e0", borderRadius: 10,
              padding: "16px 20px", flex: 1, minWidth: 200,
            }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "#0055cc", marginBottom: 6 }}>📺 メーカー・メディア向け</div>
              <ul style={{ fontSize: 12, color: "#444", margin: 0, paddingLeft: 16, lineHeight: 2 }}>
                <li>バナー広告掲載</li>
                <li>タイアップ記事</li>
                <li>新台情報スポンサード</li>
                <li>取材動画連携</li>
              </ul>
            </div>
          </div>
          <div style={{ marginTop: 20, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <a
              href="mailto:info@mesiuma.jp"
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                background: "#e60000", color: "#fff", fontWeight: 700,
                padding: "10px 24px", borderRadius: 8, fontSize: 14, textDecoration: "none",
              }}
            >
              ✉️ お問い合わせ（掲載のご相談）
            </a>
            <span style={{ fontSize: 11, color: "#888" }}>info@mesiuma.jp</span>
          </div>
        </div>
      </div>

      {/* ━━ FOOTER ━━ */}
      <footer style={{
        textAlign: "center", padding: "24px 16px",
        borderTop: `1px solid ${C.border}`, background: C.white, color: C.muted, fontSize: 11,
      }}>
        <Image src="/meshiuma.jpg" alt="" width={44} height={58}
          style={{ opacity: 0.4, marginBottom: 8, width: 32, height: "auto" }} />
        <div>© メシウマ稼働株式会社 — メシマズなくしてメシウマなし</div>
      </footer>
    </div>
  );
}
