import { useEffect, useMemo, useState } from "react";
import type { BidPremiumEntry, MlMetrics, PositionNeed } from "../types";
import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, suggestBid, type SpekulationRow } from "../lib/derive";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { Badge, PositionBadge, Row, TeamCrest } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { useModalOpenTracking } from "../lib/modalOpenTracker";
import { useViewMode } from "../lib/useViewMode";

type SortKey = "auction" | "ml" | "roi" | "price" | "trend" | "name";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "auction", label: "Auktion" },
  { value: "ml", label: "Prognose 1T" },
  { value: "roi", label: "Rendite%" },
  { value: "price", label: "Preis" },
  { value: "trend", label: "Trend 7T" },
  { value: "name", label: "Spieler (A-Z)" },
];

// Schwellen aus echten Verteilungen (kickbase.db/ml_prediction_log.jsonl,
// siehe HANDOFF.md), keine geratenen Werte.
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };

// Methodik-Hinweis 1:1 aus der bestehenden index.html übernommen (mit Umlauten).
const HINT =
  "Kauf-und-Wiederverkauf-Kandidaten, nur Systemangebote (Festpreis = Marktwert, kein Mitspieler-Aufschlag), positive Prognose 1T. " +
  "Prognose 1T ist nur eine 1-Tages-Vorhersage – Spekulation stützt sich auf den laufenden Trend, nicht allein aufs Modell. Prognose 3T ist rein informativ, fließt nicht in Auswahl/Sortierung ein. Rot markierte Auktionen laufen vor dem nächsten 22-Uhr-Update ab, ⏰ zusätzlich wenn nur noch bis zu 60 Minuten bleiben.";

function sortRows(rows: SpekulationRow[], key: SortKey): SpekulationRow[] {
  const sorted = [...rows];
  switch (key) {
    case "auction":
      sorted.sort(
        (a, b) => (a.auction_remaining_seconds ?? Infinity) - (b.auction_remaining_seconds ?? Infinity)
      );
      break;
    case "ml":
      sorted.sort((a, b) => (b.ml_prediction ?? -Infinity) - (a.ml_prediction ?? -Infinity));
      break;
    case "roi":
      sorted.sort((a, b) => b.roi_pct - a.roi_pct);
      break;
    case "price":
      sorted.sort((a, b) => a.price - b.price);
      break;
    case "trend":
      sorted.sort((a, b) => (b.market_value_change_7d ?? -Infinity) - (a.market_value_change_7d ?? -Infinity));
      break;
    case "name":
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      break;
  }
  return sorted;
}

// row.auction_status kommt bereits fertig berechnet aus buildSpekulationRows()
// (derive.ts::auctionStatus(), DST-sicher via parseIsoZ) - hier NICHT nochmal
// aus auction_expires_at neu ableiten, das war vorher dupliziert und bei
// kaputtem auction_expires_at schlechter als der Fallback der geteilten
// Funktion (siehe Review-Fund 2026-07-29). auction_urgent ist ebenfalls
// clientseitig in derive.ts berechnet, nicht serverseitig.

export default function SpekulationTab({
  rows,
  now,
  mlMetrics,
  mlMetrics3d,
  bidHistory,
  positionNeed,
}: {
  rows: SpekulationRow[];
  now: number;
  mlMetrics: MlMetrics | null;
  mlMetrics3d: MlMetrics | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
}) {
  const mae = liveModelMae(mlMetrics);
  const mae3d = liveModelMae(mlMetrics3d);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("auction");
  const [selected, setSelected] = useState<SpekulationRow | null>(null);
  const [viewMode, setViewMode] = useViewMode("kickbaseagent_view_spekulation");

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : rows;
    return sortRows(filtered, sortKey);
  }, [rows, search, sortKey]);

  if (!rows.length) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Aktuell keine Spekulations-Kandidaten mit positiver Prognose 1T auf dem Markt.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Spieler suchen…"
          className="min-w-[220px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Sortieren nach
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
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
            <SpekulationCard key={r.player_id} row={r} now={now} onSelect={() => setSelected(r)} />
          ))}
        </div>
      ) : (
        <SpekulationTable rows={visible} now={now} onSelect={setSelected} />
      )}
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
      {selected && (
        <SpekulationDetailModal
          row={selected}
          now={now}
          mae={mae}
          mae3d={mae3d}
          bidHistory={bidHistory}
          positionNeed={positionNeed}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function SpekulationCard({
  row,
  now,
  onSelect,
}: {
  row: SpekulationRow;
  now: number;
  onSelect: () => void;
}) {
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
      <CardHeader row={row} />
      <dl className="space-y-1.5 text-sm">
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
        <Row label="Preis">{fmtNum(row.price)}</Row>
        <Row label="Rendite%">{row.roi_pct.toFixed(1)}%</Row>
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)}{" "}
            {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Auktion">
          <AuctionValue row={row} now={now} />
        </Row>
      </dl>
    </div>
  );
}

function SpekulationTable({
  rows,
  now,
  onSelect,
}: {
  rows: SpekulationRow[];
  now: number;
  onSelect: (row: SpekulationRow) => void;
}) {
  const columns: TableColumn<SpekulationRow>[] = [
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
    { key: "price", label: "Preis", align: "right", sortValue: (r) => r.price, render: (r) => fmtNum(r.price) },
    { key: "roi_pct", label: "Rendite%", align: "right", sortValue: (r) => r.roi_pct, render: (r) => `${r.roi_pct.toFixed(1)}%` },
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
      key: "auction",
      label: "Auktion",
      sortValue: (r) => r.auction_remaining_seconds,
      render: (r) => <AuctionValue row={r} now={now} />,
    },
  ];

  return <SortableTable columns={columns} rows={rows} rowKey={(r) => r.player_id} onRowClick={onSelect} />;
}

function SpekulationDetailModal({
  row,
  now,
  mae,
  mae3d,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: SpekulationRow;
  now: number;
  mae: number | null;
  mae3d: number | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const suggestion = suggestBid(row, bidHistory);
  const hasValidSuggestion = !!suggestion && suggestion.p75 > 0;
  const need = positionNeed[row.position];

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <CardHeader row={row} />
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
              {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)}{" "}
              {fmtSigned(row.market_value_change_7d)}
            </span>
          </Row>
          <Row label="Preis">{fmtNum(row.price)}</Row>
          <Row label="3-Monats-Tief">{fmtNum(row.market_value_low_92d)}</Row>
          <Row label="3-Monats-Hoch">{fmtNum(row.market_value_high_92d)}</Row>
          <Row label="Rendite%">{row.roi_pct.toFixed(1)}%</Row>
          <Row label="Auktion">
            <AuctionValue row={row} now={now} />
          </Row>
          {hasValidSuggestion && suggestion && suggestion.n < MIN_N_FOR_PERCENTILE_SPREAD ? (
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
          )}
          {need && <Row label={`Ligabedarf ${row.position}`}>{Math.round(need.avg_coverage * 100)}% Deckung bei {need.n_rivals} Gegnern</Row>}
        </dl>
      </div>
    </div>
  );
}

function CardHeader({ row }: { row: SpekulationRow }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <TeamCrest teamName={row.team_name} />
      <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
      <PositionBadge position={row.position} />
    </div>
  );
}

function AuctionValue({ row }: { row: SpekulationRow; now: number }) {
  if (row.auction_critical) return <Badge tone="crit">⏰ {row.auction_status ?? "unbekannt"}</Badge>;
  if (row.auction_urgent) return <Badge tone="crit">{row.auction_status ?? "unbekannt"}</Badge>;
  if (!row.auction_status && !row.auction_expires_at) {
    return <span className="text-slate-400 dark:text-slate-500">unbekannt</span>;
  }
  return <>{row.auction_status ?? "unbekannt"}</>;
}
