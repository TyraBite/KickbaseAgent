import { useEffect, useMemo, useState } from "react";
import type { BidPremiumEntry, DashboardSnapshot, PositionNeed } from "../types";
import { MIN_N_FOR_PERCENTILE_SPREAD, suggestBid, type TransfermarktRow } from "../lib/derive";
import { Badge, POSITION_ABBR, Row, SignalBadge, TeamCrest } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { fmtNum, fmtPct, fmtSigned, trendArrow, trendClass } from "../format";

// cost_per_point bewusst weggelassen (redundant zu Signal, schneller Port
// s. Plan - echter Feld-Audit folgt spaeter).
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };
const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
type Anbieter = "all" | "kickbase" | "mitspieler";
type SortKey = "auction" | "price" | "signal" | "trend" | "ml" | "name";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "auction", label: "Auktion (Standard)" },
  { value: "price", label: "Preis" },
  { value: "signal", label: "Signal" },
  { value: "trend", label: "Trend 7T" },
  { value: "ml", label: "ML-Prognose" },
  { value: "name", label: "Spieler (A-Z)" },
];

function sortRows(rows: TransfermarktRow[], key: SortKey): TransfermarktRow[] {
  const sorted = [...rows];
  switch (key) {
    case "auction":
      sorted.sort((a, b) => (a.auction_remaining_seconds ?? Infinity) - (b.auction_remaining_seconds ?? Infinity));
      break;
    case "price":
      sorted.sort((a, b) => a.price - b.price);
      break;
    case "signal":
      sorted.sort((a, b) => (b.signal ?? -Infinity) - (a.signal ?? -Infinity));
      break;
    case "trend":
      sorted.sort((a, b) => (b.market_value_change_7d ?? -Infinity) - (a.market_value_change_7d ?? -Infinity));
      break;
    case "ml":
      sorted.sort((a, b) => (b.ml_prediction ?? -Infinity) - (a.ml_prediction ?? -Infinity));
      break;
    case "name":
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      break;
  }
  return sorted;
}

const HINT =
  "Signal > 1,25 = deutlich unter Fairwert, < 0,80 = Prämie (siehe MDs/methodik.md). Rot markierte Auktionen laufen vor dem nächsten 22-Uhr-Marktwert-Update ab.";

// Auktions-Status kommt clientseitig aus buildTransfermarktRows() statt als
// fertiger Server-String - `rows`/`now` kommen vom gemeinsamen Ticker in
// App.tsx (Konsolidierung mit SpekulationTab.tsx, siehe HANDOFF.md Task 17).
export default function TransfermarktTab({
  data,
  rows,
  now,
}: {
  data: DashboardSnapshot;
  rows: TransfermarktRow[];
  now: number;
}) {
  const thresholds = data.signal_thresholds;

  const [position, setPosition] = useState("all");
  const [anbieter, setAnbieter] = useState<Anbieter>("kickbase");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("auction");
  const [selected, setSelected] = useState<TransfermarktRow | null>(null);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = rows.filter((r) => {
      if (position !== "all" && r.position !== position) return false;
      if (anbieter === "kickbase" && !r.is_system_offer) return false;
      if (anbieter === "mitspieler" && r.is_system_offer) return false;
      if (q && !`${r.name} ${r.team_name ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
    return sortRows(filtered, sortKey);
  }, [rows, position, anbieter, search, sortKey]);

  const columns: TableColumn<TransfermarktRow>[] = [
    {
      key: "name",
      label: "Spieler",
      sortValue: (r) => r.name,
      render: (r) => (
        <div className="flex flex-wrap items-center gap-2">
          <TeamCrest teamName={r.team_name} />
          <span className="font-medium text-slate-900 dark:text-slate-50">{r.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[r.position] ?? r.position}</span>
        </div>
      ),
    },
    { key: "price", label: "Preis", align: "right", sortValue: (r) => r.price, render: (r) => fmtNum(r.price) },
    { key: "price_delta_pct", label: "Delta%", align: "right", sortValue: (r) => r.price_delta_pct, render: (r) => fmtPct(r.price_delta_pct) },
    {
      key: "offering_username",
      label: "Anbieter",
      sortValue: (r) => (r.is_system_offer ? "Kickbase" : r.offering_username),
      render: (r) => (r.is_system_offer ? "Kickbase" : r.offering_username ?? ""),
    },
    { key: "average_points", label: "Schnitt", align: "right", sortValue: (r) => r.average_points, render: (r) => fmtNum(r.average_points) },
    { key: "signal", label: "Signal", align: "right", sortValue: (r) => r.signal, render: (r) => <SignalBadge signal={r.signal} thresholds={thresholds} /> },
    {
      key: "market_value_change_7d",
      label: "Trend 7T",
      align: "right",
      sortValue: (r) => r.market_value_change_7d,
      render: (r) => (
        <span className={trendClass(r.market_value_change_7d)}>
          {trendArrow(r.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(r.market_value_change_7d)}
        </span>
      ),
    },
    { key: "ml_prediction", label: "ML-Prognose", align: "right", sortValue: (r) => r.ml_prediction, render: (r) => fmtSigned(r.ml_prediction) },
    {
      key: "starting_rank",
      label: "Startelf-Rang",
      align: "right",
      sortValue: (r) => r.starting_rank,
      render: (r) => r.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>,
    },
    {
      key: "affordable",
      label: "Leistbar",
      sortValue: (r) => (r.affordable ? 1 : 0),
      render: (r) => <Badge tone={r.affordable ? "good" : "crit"}>{r.affordable ? "ja" : "nein"}</Badge>,
    },
    {
      key: "bid_suggestion",
      label: "Gebotsempfehlung",
      align: "right",
      sortValue: (r) => (r.is_system_offer ? suggestBid(r, data.bid_premium_history ?? [])?.p75 ?? null : null),
      render: (r) => {
        if (!r.is_system_offer) return <span className="text-slate-400 dark:text-slate-500">n/v</span>;
        const suggestion = suggestBid(r, data.bid_premium_history ?? []);
        if (!suggestion || suggestion.p75 <= 0) return <span className="text-slate-400 dark:text-slate-500">n/v</span>;
        return `${fmtNum(suggestion.p75)} (n=${suggestion.n})`;
      },
    },
    {
      key: "auction",
      label: "Auktion",
      sortValue: (r) => r.auction_remaining_seconds,
      render: (r) =>
        r.auction_urgent ? (
          <Badge tone="crit">{r.auction_status}</Badge>
        ) : (
          r.auction_status ?? <span className="text-slate-400 dark:text-slate-500">unbekannt</span>
        ),
    },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Position
          <select value={position} onChange={(e) => setPosition(e.target.value)} className={selectClass}>
            <option value="all">Alle</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Anbieter
          <select value={anbieter} onChange={(e) => setAnbieter(e.target.value as Anbieter)} className={selectClass}>
            <option value="all">Alle</option>
            <option value="kickbase">Nur Kickbase</option>
            <option value="mitspieler">Nur Mitspieler</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Sortieren nach
          <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className={selectClass}>
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Spieler/Verein suchen…"
          className="min-w-[200px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {visible.length} von {rows.length} Angeboten
        </span>
      </div>
      <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

const selectClass =
  "rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

function TransfermarktDetailModal({
  row,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: TransfermarktRow;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const suggestion = row.is_system_offer ? suggestBid(row, bidHistory) : null;
  const hasValidSuggestion = !!suggestion && suggestion.p75 > 0;
  const need = positionNeed[row.position];

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <Row label="Preis">{fmtNum(row.price)}</Row>
          {row.is_system_offer ? (
            hasValidSuggestion && suggestion && suggestion.n < MIN_N_FOR_PERCENTILE_SPREAD ? (
              <Row label="Orientierungsgebot">
                {fmtNum(suggestion.p75)} (geringe Datenbasis, n={suggestion.n})
              </Row>
            ) : hasValidSuggestion && suggestion ? (
              <>
                <Row label="Gebot für ~50%">{fmtNum(suggestion.p50)}</Row>
                <Row label="Gebot für ~75%">{fmtNum(suggestion.p75)}</Row>
                <Row label="Gebot für ~90%">{fmtNum(suggestion.p90)}</Row>
                <Row label="Basis">{suggestion.n} ähnliche historische Käufe</Row>
              </>
            ) : (
              <Row label="Gebotsempfehlung">Keine historischen Vergleichskäufe dieser Position</Row>
            )
          ) : (
            <Row label="Gebotsempfehlung">Nur für Kickbase-Systemangebote verfügbar</Row>
          )}
          {need && <Row label={`Ligabedarf ${row.position}`}>{Math.round(need.avg_coverage * 100)}% Deckung bei {need.n_rivals} Gegnern</Row>}
        </dl>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Historischer Vergleichswert aus abgeschlossenen Käufen dieser Liga — keine Garantie, echte Konkurrenzgebote sind beim blinden Verfahren nie sichtbar.
        </p>
      </div>
    </div>
  );
}
