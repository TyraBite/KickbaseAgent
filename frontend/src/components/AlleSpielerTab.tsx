import { useEffect, useMemo, useRef, useState } from "react";
import type { AlleSpielerRow, DashboardSnapshot } from "../types";
import { Badge, POSITION_ABBR, SignalBadge, TeamCrest } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { fmtNum } from "../format";

const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
type Verfuegbarkeit = "all" | "frei" | "eigen" | "andere";

function ownerTone(owner: string): "good" | "warn" | "crit" {
  if (owner === "Frei") return "good";
  if (owner === "Eigener Kader") return "warn";
  return "crit";
}

export default function AlleSpielerTab({ data }: { data: DashboardSnapshot }) {
  const allRows = data.alle_spieler ?? [];
  const thresholds = data.signal_thresholds;

  const maxMarketValue = useMemo(
    () => Math.max(500_000, ...allRows.map((r) => r.market_value ?? 0)),
    [allRows]
  );
  const availableRanks = useMemo(
    () =>
      [...new Set(allRows.map((r) => r.starting_rank).filter((r): r is number => r != null))].sort((a, b) => a - b),
    [allRows]
  );

  const [position, setPosition] = useState("all");
  const [verfuegbarkeit, setVerfuegbarkeit] = useState<Verfuegbarkeit>("all");
  const [ranks, setRanks] = useState<Set<number>>(new Set());
  const [marketValueMin, setMarketValueMin] = useState(500_000);
  const [marketValueMax, setMarketValueMax] = useState(maxMarketValue);
  const [search, setSearch] = useState("");

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRows.filter((r) => {
      if (position !== "all" && r.position !== position) return false;
      if (verfuegbarkeit === "frei" && r.owner !== "Frei") return false;
      if (verfuegbarkeit === "eigen" && r.owner !== "Eigener Kader") return false;
      if (verfuegbarkeit === "andere" && (r.owner === "Frei" || r.owner === "Eigener Kader")) return false;
      if (ranks.size && (r.starting_rank === null || !ranks.has(r.starting_rank))) return false;
      if ((r.market_value ?? 0) < marketValueMin || (r.market_value ?? 0) > marketValueMax) return false;
      if (q && !`${r.name} ${r.team_name ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allRows, position, verfuegbarkeit, ranks, marketValueMin, marketValueMax, search]);

  const columns: TableColumn<AlleSpielerRow>[] = [
    {
      key: "name",
      label: "Spieler",
      render: (r) => (
        <div className="flex flex-wrap items-center gap-2">
          <TeamCrest teamName={r.team_name} />
          <span className="font-medium text-slate-900 dark:text-slate-50">{r.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[r.position] ?? r.position}</span>
        </div>
      ),
    },
    { key: "market_value", label: "Marktwert", align: "right", render: (r) => fmtNum(r.market_value) },
    { key: "points_avg", label: "Schnitt", align: "right", render: (r) => fmtNum(r.points_avg) },
    { key: "signal", label: "Signal", align: "right", render: (r) => <SignalBadge signal={r.signal} thresholds={thresholds} /> },
    {
      key: "starting_rank",
      label: "Startelf-Rang",
      align: "right",
      render: (r) => r.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>,
    },
    { key: "owner", label: "Status", render: (r) => <Badge tone={ownerTone(r.owner)}>{r.owner}</Badge> },
    { key: "status_label", label: "Fitness", render: (r) => (r.status_label ? <Badge tone="warn">{r.status_label}</Badge> : "") },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Position
          <select value={position} onChange={(e) => setPosition(e.target.value)} className={selectClass}>
            <option value="all">Alle Positionen</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Verfügbarkeit
          <select value={verfuegbarkeit} onChange={(e) => setVerfuegbarkeit(e.target.value as Verfuegbarkeit)} className={selectClass}>
            <option value="all">Alle</option>
            <option value="frei">Nur freie</option>
            <option value="eigen">Nur eigene</option>
            <option value="andere">Nur bei anderen Managern</option>
          </select>
        </label>
        <RankFilter available={availableRanks} selected={ranks} onChange={setRanks} />
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Marktwert min
          <input
            type="number"
            min={500_000}
            step={100_000}
            value={marketValueMin}
            onChange={(e) => setMarketValueMin(Number(e.target.value) || 500_000)}
            className="w-32 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Marktwert max
          <input
            type="number"
            min={500_000}
            step={100_000}
            value={marketValueMax}
            onChange={(e) => setMarketValueMax(Number(e.target.value) || maxMarketValue)}
            className="w-32 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Spieler/Verein suchen…"
          className="min-w-[200px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {visible.length} von {allRows.length} Spielern sichtbar
        </span>
      </div>
      <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} />
    </div>
  );
}

const selectClass =
  "rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

function RankFilter({
  available,
  selected,
  onChange,
}: {
  available: number[];
  selected: Set<number>;
  onChange: (ranks: Set<number>) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  function toggle(rank: number) {
    const next = new Set(selected);
    if (next.has(rank)) next.delete(rank);
    else next.add(rank);
    onChange(next);
  }

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        Startelf-Rang {selected.size ? `(${selected.size})` : ""} ▾
      </button>
      {open && (
        <div className="absolute z-10 mt-1 max-h-60 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-800 dark:bg-slate-900">
          {available.map((rank) => (
            <label key={rank} className="flex items-center gap-2 whitespace-nowrap px-2 py-1 text-sm text-slate-700 dark:text-slate-200">
              <input type="checkbox" checked={selected.has(rank)} onChange={() => toggle(rank)} />
              Rang {rank}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
