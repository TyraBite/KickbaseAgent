import { useEffect, useState, type ReactNode } from "react";
import type { Calibration, PlayerRecord } from "../types";
import { buildPlayerRow, type PlayerRow } from "../lib/derive";
import { Badge, POSITION_ABBR, SignalBadge, TeamCrest } from "./ui";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { useModalOpenTracking } from "../lib/modalOpenTracker";
import PlayerNamePicker from "./PlayerNamePicker";

const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

type Side = "a" | "b";
type Winner = Side | null;

function better(a: number | null, b: number | null, lowerIsBetter = false): Winner {
  if (a === null || b === null || a === b) return null;
  const aWins = lowerIsBetter ? a < b : a > b;
  return aWins ? "a" : "b";
}

function betterFitness(a: string | null, b: string | null): Winner {
  const aFit = !a;
  const bFit = !b;
  if (aFit === bFit) return null;
  return aFit ? "a" : "b";
}

function CompareRow({ label, valueA, valueB, winner }: { label: string; valueA: ReactNode; valueB: ReactNode; winner: Winner }) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0 dark:border-slate-800/60">
      <div className={`text-right ${winner === "a" ? "font-semibold text-brand-600 dark:text-brand-400" : "text-slate-700 dark:text-slate-200"}`}>
        {valueA}
      </div>
      <div className="whitespace-nowrap text-center text-xs text-slate-400 dark:text-slate-500">{label}</div>
      <div className={`text-left ${winner === "b" ? "font-semibold text-brand-600 dark:text-brand-400" : "text-slate-700 dark:text-slate-200"}`}>
        {valueB}
      </div>
    </div>
  );
}

export default function PlayerCompareModal({
  playerIdA,
  playerIdB,
  players,
  calibration,
  thresholds,
  onSelectSide,
  onClose,
}: {
  playerIdA: string;
  playerIdB: string;
  players: Record<string, PlayerRecord>;
  calibration: Calibration | null;
  thresholds: { good: number; critical: number };
  onSelectSide?: (playerId: string) => void;
  onClose: () => void;
}) {
  const [idA, setIdA] = useState(playerIdA);
  const [idB, setIdB] = useState(playerIdB);
  const [switching, setSwitching] = useState<Side | null>(null);

  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const playerA = players[idA];
  const playerB = players[idB];
  if (!playerA || !playerB) {
    // Sollte praktisch nie vorkommen (IDs kommen immer aus data.players),
    // aber ohne diesen Guard wuerde buildPlayerRow() auf undefined crashen.
    return (
      <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
        <div onClick={(e) => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
          <p className="text-sm text-slate-500 dark:text-slate-400">Spieler nicht gefunden.</p>
        </div>
      </div>
    );
  }

  const rowA: PlayerRow = buildPlayerRow(playerA, calibration);
  const rowB: PlayerRow = buildPlayerRow(playerB, calibration);

  function renderName(row: PlayerRow, side: Side) {
    return (
      <div className="flex flex-col items-center gap-1 text-center">
        <div className="flex items-center gap-1.5">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        </div>
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
        <button
          type="button"
          onClick={() => setSwitching(side)}
          className="text-xs text-brand-600 hover:underline dark:text-brand-400"
        >
          Wechseln
        </button>
        {onSelectSide && (
          <button
            type="button"
            onClick={() => onSelectSide(side === "a" ? idA : idB)}
            className="mt-1 rounded-full border border-brand-300 bg-brand-50 px-3 py-1 text-xs text-brand-800 hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300"
          >
            Diesen als Ersatz wählen
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="grid flex-1 grid-cols-2 gap-4">
            {renderName(rowA, "a")}
            {renderName(rowB, "b")}
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

        {switching && (
          <div className="mb-4 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
              Ersetze Seite {switching === "a" ? "links" : "rechts"} durch…
            </p>
            <PlayerNamePicker
              players={players}
              excludePlayerId={switching === "a" ? idB : idA}
              onSelect={(id) => {
                if (switching === "a") setIdA(id);
                else setIdB(id);
                setSwitching(null);
              }}
            />
          </div>
        )}

        <div>
          <CompareRow
            label="ML-Prognose"
            valueA={<span className={trendClass(rowA.ml_prediction)}>{trendArrow(rowA.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(rowA.ml_prediction)}</span>}
            valueB={<span className={trendClass(rowB.ml_prediction)}>{trendArrow(rowB.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(rowB.ml_prediction)}</span>}
            winner={better(rowA.ml_prediction, rowB.ml_prediction)}
          />
          <CompareRow
            label="Signal"
            valueA={<SignalBadge signal={rowA.signal} thresholds={thresholds} />}
            valueB={<SignalBadge signal={rowB.signal} thresholds={thresholds} />}
            winner={better(rowA.signal, rowB.signal)}
          />
          <CompareRow
            label="Marktwert"
            valueA={fmtNum(rowA.market_value)}
            valueB={fmtNum(rowB.market_value)}
            winner={better(rowA.market_value, rowB.market_value, true)}
          />
          <CompareRow
            label="Startelf-Rang"
            valueA={rowA.starting_rank ?? "n/v"}
            valueB={rowB.starting_rank ?? "n/v"}
            winner={better(rowA.starting_rank, rowB.starting_rank, true)}
          />
          <CompareRow
            label="Fitness"
            valueA={<Badge tone={rowA.status_label ? "crit" : "good"}>{rowA.status_label ?? "Fit"}</Badge>}
            valueB={<Badge tone={rowB.status_label ? "crit" : "good"}>{rowB.status_label ?? "Fit"}</Badge>}
            winner={betterFitness(rowA.status_label, rowB.status_label)}
          />
          <CompareRow
            label="Schnitt"
            valueA={fmtNum(rowA.average_points)}
            valueB={fmtNum(rowB.average_points)}
            winner={better(rowA.average_points, rowB.average_points)}
          />
        </div>
      </div>
    </div>
  );
}
