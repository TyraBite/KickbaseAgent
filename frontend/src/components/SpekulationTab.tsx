import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { SpekulationRow } from "../types";
import { fmtNum, fmtSigned, formatDurationMs, trendArrow, trendClass } from "../format";

type SortKey = "auction" | "ml" | "roi" | "price" | "trend" | "name";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "auction", label: "Auktion (Standard)" },
  { value: "ml", label: "ML-Prognose" },
  { value: "roi", label: "Rendite%" },
  { value: "price", label: "Preis" },
  { value: "trend", label: "Trend 7T" },
  { value: "name", label: "Spieler (A-Z)" },
];

// Schwellen aus echten Verteilungen (kickbase.db/ml_prediction_log.jsonl,
// siehe HANDOFF.md), keine geratenen Werte.
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

const POSITION_ABBR: Record<string, string> = {
  Torwart: "TW",
  Abwehr: "ABW",
  Mittelfeld: "MF",
  Sturm: "ST",
};

// Methodik-Hinweis 1:1 aus der bestehenden index.html übernommen (mit Umlauten).
const HINT =
  "Kauf-und-Wiederverkauf-Kandidaten, nur Systemangebote (Festpreis = Marktwert, kein Mitspieler-Aufschlag), positive ML-Prognose. " +
  "ML-Prognose ist nur eine 1-Tages-Vorhersage – Spekulation stützt sich auf den laufenden Trend, nicht allein aufs Modell. Rot markierte Auktionen laufen vor dem nächsten 22-Uhr-Update ab.";

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

// Restzeit wird aus auction_expires_at bei jedem Render + alle 60s neu
// berechnet (kein sekundengenauer Ticker noetig) statt auf den naechsten
// 2h-Fetch zu warten. auction_urgent bleibt server-berechnet (haengt an der
// Europe/Berlin-22-Uhr-Cutoff-Logik, nicht in JS duplizieren).
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function auctionLabel(row: SpekulationRow, now: number): string {
  if (!row.auction_expires_at) return row.auction_status ?? "unbekannt";
  const remainingMs = new Date(row.auction_expires_at).getTime() - now;
  if (remainingMs <= 0) return "Frist abgelaufen";
  return `läuft ab in ${formatDurationMs(remainingMs)}`;
}

export default function SpekulationTab({ rows }: { rows: SpekulationRow[] }) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("auction");
  const [selected, setSelected] = useState<SpekulationRow | null>(null);
  const now = useNow(60_000);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : rows;
    return sortRows(filtered, sortKey);
  }, [rows, search, sortKey]);

  if (!rows.length) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Aktuell keine Spekulations-Kandidaten mit positiver ML-Prognose auf dem Markt.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
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
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
        {visible.map((r) => (
          <SpekulationCard key={r.name} row={r} now={now} onSelect={() => setSelected(r)} />
        ))}
      </div>
      {selected && <SpekulationDetailModal row={selected} now={now} onClose={() => setSelected(null)} />}
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
        <Row label="ML-Prognose">
          <span className={trendClass(row.ml_prediction)}>
            {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
          </span>
        </Row>
        <Row label="Rendite%">{row.roi_pct.toFixed(1)}%</Row>
        <Row label="Preis">{fmtNum(row.price)}</Row>
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

function SpekulationDetailModal({
  row,
  now,
  onClose,
}: {
  row: SpekulationRow;
  now: number;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

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
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <Row label="ML-Prognose">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
          </Row>
          <Row label="Rendite%">{row.roi_pct.toFixed(1)}%</Row>
          <Row label="Preis">{fmtNum(row.price)}</Row>
          <Row label="Trend 7T">
            <span className={trendClass(row.market_value_change_7d)}>
              {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)}{" "}
              {fmtSigned(row.market_value_change_7d)}
            </span>
          </Row>
          <Row label="Auktion">
            <AuctionValue row={row} now={now} />
          </Row>
          <Row label="3-Monats-Tief">{fmtNum(row.market_value_low_92d)}</Row>
          <Row label="3-Monats-Hoch">{fmtNum(row.market_value_high_92d)}</Row>
        </dl>
      </div>
    </div>
  );
}

function CardHeader({ row }: { row: SpekulationRow }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <TeamCrest teamId={row.team_id} teamName={row.team_name} />
      <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
      <span className="text-xs text-slate-400 dark:text-slate-500">
        {POSITION_ABBR[row.position] ?? row.position}
      </span>
    </div>
  );
}

function AuctionValue({ row, now }: { row: SpekulationRow; now: number }) {
  if (row.auction_urgent) return <Badge tone="crit">{auctionLabel(row, now)}</Badge>;
  if (!row.auction_status && !row.auction_expires_at) {
    return <span className="text-slate-400 dark:text-slate-500">unbekannt</span>;
  }
  return <>{auctionLabel(row, now)}</>;
}

// Kickbase liefert selbst keine Logo-URL - Wappen liegen self-hosted unter
// public/crests/{team_id}.svg (vom User zu besorgen). Fehlt eine Datei
// (noch), faellt die Kachel auf einen Initialen-Badge zurueck statt ein
// kaputtes Bild-Icon zu zeigen - Wappen koennen nach und nach ergaenzt werden.
function TeamCrest({ teamId, teamName }: { teamId: string | null; teamName: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!teamId || failed) {
    return (
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-600 dark:bg-slate-700 dark:text-slate-300">
        {(teamName ?? "?").slice(0, 2).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      src={`${import.meta.env.BASE_URL}crests/${teamId}.svg`}
      alt={teamName ?? ""}
      onError={() => setFailed(true)}
      className="h-6 w-6 shrink-0 rounded-full object-contain"
    />
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right font-medium tabular-nums text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}

function Badge({ tone, children }: { tone: "good" | "crit"; children: ReactNode }) {
  const toneClass =
    tone === "good"
      ? "bg-brand-100 text-brand-800 dark:bg-brand-950 dark:text-brand-300"
      : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>
  );
}
