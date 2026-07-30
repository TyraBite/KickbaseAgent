import { useEffect, useMemo, useRef, useState } from "react";
import type { DashboardSnapshot } from "../types";
import { buildAlleSpielerRows, type AlleSpielerRow } from "../lib/derive";
import { Badge, POSITION_ABBR, Row, SignalBadge, TeamCrest } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import PlayerNamePicker from "./PlayerNamePicker";
import PlayerCompareModal from "./PlayerCompareModal";
import { useModalOpenTracking } from "../lib/modalOpenTracker";

const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
type Verfuegbarkeit = "all" | "frei" | "eigen" | "andere";

function ownerTone(owner: string): "good" | "warn" | "crit" {
  if (owner === "Frei") return "good";
  if (owner === "Eigener Kader") return "warn";
  return "crit";
}

export default function AlleSpielerTab({ data }: { data: DashboardSnapshot }) {
  const allRows = useMemo(
    () => buildAlleSpielerRows(data.players, data.own_squad_ids, data.owned_by, data.calibration),
    [data.players, data.own_squad_ids, data.owned_by, data.calibration]
  );
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
  const [selected, setSelected] = useState<AlleSpielerRow | null>(null);

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
      sortValue: (r) => r.name,
      render: (r) => (
        <div className="flex flex-wrap items-center gap-2">
          <TeamCrest teamName={r.team_name} />
          <span className="font-medium text-slate-900 dark:text-slate-50">{r.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[r.position] ?? r.position}</span>
        </div>
      ),
    },
    { key: "owner", label: "Verfügbarkeit", sortValue: (r) => r.owner, render: (r) => <Badge tone={ownerTone(r.owner)}>{r.owner}</Badge> },
    {
      key: "starting_rank",
      label: "Startelf-Rang",
      align: "right",
      sortValue: (r) => r.starting_rank,
      render: (r) => r.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>,
    },
    { key: "status_label", label: "Fitness", sortValue: (r) => r.status_label, render: (r) => (r.status_label ? <Badge tone="warn">{r.status_label}</Badge> : "") },
    { key: "average_points", label: "Schnitt", align: "right", sortValue: (r) => r.average_points, render: (r) => fmtNum(r.average_points) },
    { key: "signal", label: "Signal", align: "right", sortValue: (r) => r.signal, render: (r) => <SignalBadge signal={r.signal} thresholds={thresholds} /> },
    { key: "market_value", label: "Marktwert", align: "right", sortValue: (r) => r.market_value, render: (r) => fmtNum(r.market_value) },
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
      <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
      {selected && (
        <AlleSpielerDetailModal
          row={selected}
          thresholds={thresholds}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
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

const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

function AlleSpielerDetailModal({
  row,
  thresholds,
  players,
  calibration,
  onClose,
}: {
  row: AlleSpielerRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  useModalOpenTracking();

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <>
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
              className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              ✕
            </button>
          </div>
          <dl className="space-y-2 text-sm">
            <Row label="Verfügbarkeit">
              <Badge tone={ownerTone(row.owner)}>{row.owner}</Badge>
            </Row>
            <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
            <Row label="Fitness">
              <Badge tone={row.status_label ? "crit" : "good"}>{row.status_label ?? "Fit"}</Badge>
            </Row>
            <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
            <Row label="Signal">
              <SignalBadge signal={row.signal} thresholds={thresholds} />
            </Row>
            <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
            <Row label="ML-Prognose">
              <span className={trendClass(row.ml_prediction)}>
                {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
              </span>
            </Row>
          </dl>
          <button
            type="button"
            onClick={() => setComparing((v) => !v)}
            className="mt-3 text-xs text-brand-600 hover:underline dark:text-brand-400"
          >
            Vergleichen mit…
          </button>
          {comparing && (
            <div className="mt-2">
              <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
            </div>
          )}
        </div>
      </div>
      {compareWith && (
        <PlayerCompareModal
          playerIdA={row.player_id}
          playerIdB={compareWith}
          players={players}
          calibration={calibration}
          thresholds={thresholds}
          onClose={() => setCompareWith(null)}
        />
      )}
    </>
  );
}
