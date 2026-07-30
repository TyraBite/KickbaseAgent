import { useEffect, useMemo, useState } from "react";
import type { DashboardSnapshot, LigaanalyseRow } from "../types";
import { groupSquadByPosition } from "../lib/derive";
import { Badge, POSITION_ABBR, Row } from "./ui";
import { fmtNum } from "../format";

const HINT =
  "Budgets außer der eigenen Zeile sind Schätzungen aus dem Activity-Feed (siehe MDs/methodik.md). " +
  "Stammspieler = starting_rank 1 oder 2 (wahrscheinlichster/zweitwahrscheinlichster Stammplatz je Position) im gesamten Kader.";

export default function LigaanalyseTab({ data }: { data: DashboardSnapshot }) {
  const allRows = data.ligaanalyse ?? [];
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LigaanalyseRow | null>(null);

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
          <LigaanalyseCard key={r.name} row={r} onClick={() => setSelected(r)} />
        ))}
      </div>
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
      {selected && (
        <LigaanalyseDetailModal row={selected} players={data.players} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function LigaanalyseCard({ row, onClick }: { row: LigaanalyseRow; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className={`cursor-pointer rounded-2xl border p-4 shadow-sm transition hover:shadow-md dark:bg-slate-900 ${
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

function LigaanalyseDetailModal({
  row,
  players,
  onClose,
}: {
  row: LigaanalyseRow;
  players: DashboardSnapshot["players"];
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const groups = groupSquadByPosition(row.squad_player_ids ?? [], players);

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            {row.is_self && <Badge tone="good">ich</Badge>}
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
        <dl className="mb-4 space-y-1.5 text-sm">
          <Row label="Platz">{fmtNum(row.season_placement)}</Row>
          <Row label="Punkte">{fmtNum(row.season_points)}</Row>
          <Row label={row.is_self ? "Budget" : "Budget (geschätzt)"}>{fmtNum(row.estimated_budget)}</Row>
        </dl>
        {groups.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Kaderdaten verfügbar.</p>
        ) : (
          <div className="space-y-3">
            {groups.map((group) => (
              <div key={group.position}>
                <p className="mb-1 text-xs font-semibold uppercase text-slate-400 dark:text-slate-500">
                  {POSITION_ABBR[group.position] ?? group.position}
                </p>
                <ul className="space-y-1">
                  {group.entries.map((entry) => (
                    <li key={entry.player_id} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
                        {entry.name}
                        {entry.is_regular && <Badge tone="good">Stamm</Badge>}
                      </span>
                      <span className="text-slate-500 dark:text-slate-400">{fmtNum(entry.market_value)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
