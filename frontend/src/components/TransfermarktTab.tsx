import { useEffect, useMemo, useState } from "react";
import type { BidPremiumEntry, DashboardSnapshot, PositionNeed } from "../types";
import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, normalizeSearchText, suggestBid, type TransfermarktRow } from "../lib/derive";
import { Badge, PositionBadge, Row, SignalBadge, TeamCrest } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { budgetTone, fmtNum, fmtPct, fmtSigned, trendArrow, trendClass } from "../format";
import { useViewMode } from "../lib/useViewMode";
import { StatusLabelRow } from "./EigenesTeamTab";

// cost_per_point bewusst weggelassen (redundant zu Signal, schneller Port
// s. Plan - echter Feld-Audit folgt spaeter).
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
type Anbieter = "all" | "kickbase" | "mitspieler";
type SortKey = "auction" | "price" | "signal" | "trend" | "ml" | "name";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "auction", label: "Auktion" },
  { value: "price", label: "Preis" },
  { value: "signal", label: "Signal" },
  { value: "trend", label: "Trend 7T" },
  { value: "ml", label: "Prognose 1T" },
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
  "Signal > 1,25 = deutlich unter Fairwert, < 0,80 = Prämie (siehe MDs/methodik.md). Rot markierte Auktionen laufen vor dem nächsten 22-Uhr-Marktwert-Update ab, ⏰ zusätzlich wenn nur noch bis zu 60 Minuten bleiben.";

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
  const mae = liveModelMae(data.ml_metrics);
  const mae3d = liveModelMae(data.ml_metrics_3d ?? null);

  const [position, setPosition] = useState("all");
  const [anbieter, setAnbieter] = useState<Anbieter>("kickbase");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("auction");
  const [selected, setSelected] = useState<TransfermarktRow | null>(null);
  const [viewMode, setViewMode] = useViewMode("kickbaseagent_view_transfermarkt");

  const visible = useMemo(() => {
    const q = normalizeSearchText(search.trim());
    const filtered = rows.filter((r) => {
      if (position !== "all" && r.position !== position) return false;
      if (anbieter === "kickbase" && !r.is_system_offer) return false;
      if (anbieter === "mitspieler" && r.is_system_offer) return false;
      if (q && !normalizeSearchText(`${r.name} ${r.team_name ?? ""}`).includes(q)) return false;
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
          <PositionBadge position={r.position} />
        </div>
      ),
    },
    { key: "price", label: "Preis", align: "right", sortValue: (r) => r.price, render: (r) => fmtNum(r.price) },
    {
      key: "ml_prediction",
      label: "Prognose 1T",
      align: "right",
      sortValue: (r) => r.ml_prediction,
      render: (r) => (
        <span className={trendClass(r.ml_prediction)}>
          {trendArrow(r.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(r.ml_prediction)}
        </span>
      ),
    },
    {
      key: "ml_prediction_3d",
      label: "Prognose 3T",
      align: "right",
      sortValue: (r) => r.ml_prediction_3d,
      render: (r) => (
        <span className={trendClass(r.ml_prediction_3d)}>
          {trendArrow(r.ml_prediction_3d, ML_PREDICTION_3D_THRESHOLDS)} {fmtSigned(r.ml_prediction_3d)}
        </span>
      ),
    },
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
    {
      key: "starting_rank",
      label: "Startelf-Rang",
      align: "right",
      sortValue: (r) => r.starting_rank,
      render: (r) => r.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>,
    },
    { key: "average_points", label: "Schnitt", align: "right", sortValue: (r) => r.average_points, render: (r) => fmtNum(r.average_points) },
    { key: "signal", label: "Signal", align: "right", sortValue: (r) => r.signal, render: (r) => <SignalBadge signal={r.signal} thresholds={thresholds} /> },
    { key: "price_delta_pct", label: "Delta%", align: "right", sortValue: (r) => r.price_delta_pct, render: (r) => fmtPct(r.price_delta_pct) },
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
        r.auction_critical ? (
          <Badge tone="crit">⏰ {r.auction_status}</Badge>
        ) : r.auction_urgent ? (
          <Badge tone="crit">{r.auction_status}</Badge>
        ) : (
          r.auction_status ?? <span className="text-slate-400 dark:text-slate-500">unbekannt</span>
        ),
    },
    {
      key: "offering_username",
      label: "Anbieter",
      sortValue: (r) => (r.is_system_offer ? "Kickbase" : r.offering_username),
      render: (r) => (r.is_system_offer ? "Kickbase" : r.offering_username ?? ""),
    },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-xs text-slate-500 dark:text-slate-400">Kapital</span>{" "}
          <span className={`font-medium tabular-nums ${budgetTone(data.own_budget_exact)}`}>{fmtNum(data.own_budget_exact)}</span>
        </div>
        <div>
          <span className="text-xs text-slate-500 dark:text-slate-400">Budget</span>{" "}
          <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(data.own_available_budget)}</span>
        </div>
      </div>
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
        <div className="flex overflow-hidden rounded-lg border border-slate-300 text-sm dark:border-slate-700">
          <button
            type="button"
            onClick={() => setViewMode("cards")}
            className={`px-3 py-2 ${viewMode === "cards" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Karten
          </button>
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className={`px-3 py-2 ${viewMode === "table" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Liste
          </button>
        </div>
      </div>
      {viewMode === "cards" ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {visible.map((r) => (
            <TransfermarktCard
              key={r.player_id}
              row={r}
              bidHistory={data.bid_premium_history ?? []}
              thresholds={thresholds}
              onSelect={() => setSelected(r)}
            />
          ))}
        </div>
      ) : (
        <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
      )}
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Marktwert-Update: Kickbase aktualisiert Marktwerte täglich um 22:00 Uhr.</p>
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          mae={mae}
          mae3d={mae3d}
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

export function TransfermarktDetailModal({
  row,
  mae,
  mae3d,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: TransfermarktRow;
  mae: number | null;
  mae3d: number | null;
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
            <PositionBadge position={row.position} />
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <Row label="Prognose 1T">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          <Row label="Prognose 3T">
            <span className={trendClass(row.ml_prediction_3d)}>
              {trendArrow(row.ml_prediction_3d, ML_PREDICTION_3D_THRESHOLDS)} {fmtSigned(row.ml_prediction_3d)}
            </span>
            {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
          </Row>
          <Row label="Trend 7T">
            <span className={trendClass(row.market_value_change_7d)}>
              {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
            </span>
          </Row>
          <Row label="Preis">{fmtNum(row.price)}</Row>
          <Row label="3-Monats-Tief">{fmtNum(row.market_value_low_92d)}</Row>
          <Row label="3-Monats-Hoch">{fmtNum(row.market_value_high_92d)}</Row>
          <Row label="Delta%">{fmtPct(row.price_delta_pct)}</Row>
          <Row label="Auktion">
            {row.auction_critical ? (
              <Badge tone="crit">⏰ {row.auction_status}</Badge>
            ) : row.auction_urgent ? (
              <Badge tone="crit">{row.auction_status}</Badge>
            ) : (
              row.auction_status ?? <span className="text-slate-400 dark:text-slate-500">unbekannt</span>
            )}
          </Row>
          <Row label="Anbieter">{row.is_system_offer ? "Kickbase" : row.offering_username ?? "—"}</Row>
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
      </div>
    </div>
  );
}

export function TransfermarktCard({
  row,
  bidHistory,
  thresholds,
  onSelect,
}: {
  row: TransfermarktRow;
  bidHistory: BidPremiumEntry[];
  thresholds: DashboardSnapshot["signal_thresholds"];
  onSelect: () => void;
}) {
  const suggestion = row.is_system_offer ? suggestBid(row, bidHistory) : null;
  const hasValidSuggestion = !!suggestion && suggestion.p75 > 0;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-600"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TeamCrest teamName={row.team_name} />
        <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        <PositionBadge position={row.position} />
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Preis">{fmtNum(row.price)}</Row>
        <Row label="Prognose 1T">
          <span className={trendClass(row.ml_prediction)}>
            {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
          </span>
        </Row>
        <Row label="Prognose 3T">
          <span className={trendClass(row.ml_prediction_3d)}>
            {trendArrow(row.ml_prediction_3d, ML_PREDICTION_3D_THRESHOLDS)} {fmtSigned(row.ml_prediction_3d)}
          </span>
        </Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <StatusLabelRow value={row.status_label} />
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Auktion">
          {row.auction_critical ? (
            <Badge tone="crit">⏰ {row.auction_status}</Badge>
          ) : row.auction_urgent ? (
            <Badge tone="crit">{row.auction_status}</Badge>
          ) : (
            row.auction_status ?? <span className="text-slate-400 dark:text-slate-500">unbekannt</span>
          )}
        </Row>
        <Row label="Gebotsempfehlung">
          {row.is_system_offer && hasValidSuggestion && suggestion ? (
            `${fmtNum(suggestion.p75)} (n=${suggestion.n})`
          ) : (
            <span className="text-slate-400 dark:text-slate-500">n/v</span>
          )}
        </Row>
      </dl>
    </div>
  );
}
