import { useMemo, useState, type ReactNode } from "react";
import type { SpekulationRow } from "../types";
import { fmtNum, fmtSigned, trendClass } from "../format";

type SortKey = "auction" | "roi" | "price";

// Methodik-Hinweis 1:1 aus der bestehenden index.html uebernommen.
const HINT =
  "Kauf-und-Wiederverkauf-Kandidaten, nur Systemangebote (Festpreis = Marktwert, kein Mitspieler-Aufschlag), positive ML-Prognose. " +
  '"Hype-Gipfel" (rot) = Warnung: starker 7-Tage-Sprung + 92-Tage-Hoch + kein Punkteschnitt, meist Nachrichten-Hype statt echtes Signal - NICHT zum Kauf geeignet. ' +
  '"Boden-Schutz" (gruen) = Preis unter 1 Mio., nahe am 500k-Mindestwert, begrenztes Abwaertsrisiko. ' +
  "ML-Prognose ist nur eine 1-Tages-Vorhersage - Spekulation stuetzt sich auf den laufenden Trend, nicht allein aufs Modell. Rot markierte Auktionen laufen vor dem naechsten 22-Uhr-Update ab.";

function sortRows(rows: SpekulationRow[], key: SortKey): SpekulationRow[] {
  const sorted = [...rows];
  if (key === "auction") {
    sorted.sort(
      (a, b) => (a.auction_remaining_seconds ?? Infinity) - (b.auction_remaining_seconds ?? Infinity)
    );
  } else if (key === "roi") {
    sorted.sort((a, b) => b.roi_pct - a.roi_pct);
  } else {
    sorted.sort((a, b) => a.price - b.price);
  }
  return sorted;
}

export default function SpekulationTab({ rows }: { rows: SpekulationRow[] }) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("auction");

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q
      ? rows.filter((r) => `${r.name} ${r.team_name ?? ""}`.toLowerCase().includes(q))
      : rows;
    return sortRows(filtered, sortKey);
  }, [rows, search, sortKey]);

  if (!rows.length) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Aktuell keine Spekulations-Kandidaten mit positiver ML-Prognose auf dem Markt.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-4 max-w-3xl text-xs text-neutral-500 dark:text-neutral-400">{HINT}</p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Spieler/Verein suchen..."
          className="min-w-[220px] rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        <label className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-300">
          Sortieren nach
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded-lg border border-neutral-300 bg-white px-2 py-2 text-sm text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          >
            <option value="auction">Auktion (Standard)</option>
            <option value="roi">Rendite%</option>
            <option value="price">Preis</option>
          </select>
        </label>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((r) => (
          <SpekulationCard key={r.name} row={r} />
        ))}
      </div>
    </div>
  );
}

function SpekulationCard({ row }: { row: SpekulationRow }) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-semibold text-neutral-900 dark:text-neutral-100">{row.name}</span>
        {row.is_hype_gipfel && <Badge tone="crit">Hype-Gipfel</Badge>}
        {row.near_floor && <Badge tone="good">Boden-Schutz</Badge>}
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="ML-Prognose">
          <span className={trendClass(row.ml_prediction)}>{fmtSigned(row.ml_prediction)}</span>
        </Row>
        <Row label="Rendite%">{row.roi_pct.toFixed(1)}%</Row>
        <Row label="Preis">{fmtNum(row.price)}</Row>
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Auktion">
          {row.auction_urgent ? (
            <Badge tone="crit">{row.auction_status}</Badge>
          ) : (
            row.auction_status ?? <span className="text-neutral-400 dark:text-neutral-500">unbekannt</span>
          )}
        </Row>
      </dl>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-neutral-500 dark:text-neutral-400">{label}</dt>
      <dd className="font-medium tabular-nums text-neutral-900 dark:text-neutral-100">{children}</dd>
    </div>
  );
}

function Badge({ tone, children }: { tone: "good" | "crit"; children: ReactNode }) {
  const toneClass =
    tone === "good"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>
  );
}
