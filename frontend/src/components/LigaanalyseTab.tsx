import { useMemo, useState } from "react";
import type { DashboardSnapshot, LigaanalyseRow } from "../types";
import { Badge, Row } from "./ui";
import { fmtNum } from "../format";

const HINT =
  "Budgets außer der eigenen Zeile sind Schätzungen aus dem Activity-Feed (siehe MDs/methodik.md). " +
  "Stammspieler = starting_rank 1 oder 2 (wahrscheinlichster/zweitwahrscheinlichster Stammplatz je Position) im gesamten Kader.";

export default function LigaanalyseTab({ data }: { data: DashboardSnapshot }) {
  const allRows = data.ligaanalyse ?? [];
  const [search, setSearch] = useState("");

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? allRows.filter((r) => r.name.toLowerCase().includes(q)) : allRows;
  }, [allRows, search]);

  return (
    <div>
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Manager suchen…"
          className="min-w-[200px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
        {visible.map((r) => (
          <LigaanalyseCard key={r.name} row={r} />
        ))}
      </div>
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
    </div>
  );
}

function LigaanalyseCard({ row }: { row: LigaanalyseRow }) {
  return (
    <div
      className={`rounded-2xl border p-4 shadow-sm dark:bg-slate-900 ${
        row.is_self ? "border-brand-400 bg-brand-50 dark:border-brand-600 dark:bg-brand-950/30" : "border-slate-200 bg-white dark:border-slate-800"
      }`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        {row.is_self && <Badge tone="good">ich</Badge>}
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Platz">{fmtNum(row.season_placement)}</Row>
        <Row label="Punkte">{fmtNum(row.season_points)}</Row>
        <Row label="Kadergröße">{fmtNum(row.squad_size)}</Row>
        <Row label="Stammspieler">{fmtNum(row.regular_count)}</Row>
        <Row label="Verkaufsangebote">{fmtNum(row.sell_count)}</Row>
        <Row label="Teamwert">{fmtNum(row.team_value)}</Row>
        <Row label="Kaderwert">{fmtNum(row.squad_value)}</Row>
        <Row label={row.is_self ? "Budget" : "Budget (geschätzt)"}>{fmtNum(row.estimated_budget)}</Row>
        <Row label="Verfügbar (inkl. Kredit)">{fmtNum(row.available_budget)}</Row>
      </dl>
    </div>
  );
}
