import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { DashboardSnapshot } from "../types";
import { buildEigenesTeamSplit, liveModelMae, type EigenesTeamRow } from "../lib/derive";
import { resolveTarget, type ResolvedTarget } from "../lib/wunschkaderResolve";
import { useModalOpenTracking } from "../lib/modalOpenTracker";
import { Badge, CARD_TONE_CLASSES, FitnessBadge, PositionBadge, Row, SignalBadge, TeamCrest, cardTone } from "./ui";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import PlayerNamePicker from "./PlayerNamePicker";
import PlayerCompareModal from "./PlayerCompareModal";

// Felder gekuerzt ggue. der alten index.html: cost_per_point weggelassen
// (redundant zu Signal, beide leiten sich aus Marktwert/Punkte-Schnitt ab),
// 92-Tage-Tief/Hoch weggelassen (Spekulations-Konzept "guenstig einsteigen",
// nicht "eigenen Spieler halten/verkaufen"). Trend 7T/Signal/Status-Text
// zusaetzlich aus der Kachel raus in die Detailansicht verschoben (User-
// Feedback nach erstem Feld-Audit 2026-07-29) - Kachel zeigt nur noch
// Marktwert/Schnitt/ML-Prognose/Startelf-Rang, Status als kompaktes Badge
// statt Text-Zeile.
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

// ResolvedTarget (Task 14) hat kein ml_prediction-Feld - das bleibt bewusst so
// (wunschkaderResolve.ts ist bereits reviewt/approved), daher hier lokal um das
// Feld erweitert, damit MlPredictionRow (unveraendert) weiter funktioniert.
type WatchlistRow = ResolvedTarget & { ml_prediction: number | null };

type Selected = { kind: "player"; row: EigenesTeamRow } | { kind: "watchlist"; row: WatchlistRow } | null;

export default function EigenesTeamTab({ data }: { data: DashboardSnapshot }) {
  const liveMae = liveModelMae(data.ml_metrics);
  const split = useMemo(
    () => buildEigenesTeamSplit(data.players, data.own_squad_ids, data.wunschkader_targets, data.calibration, liveMae),
    [data.players, data.own_squad_ids, data.wunschkader_targets, data.calibration, liveMae]
  );

  const ownSquadIdSet = useMemo(() => new Set(data.own_squad_ids), [data.own_squad_ids]);
  const listingsByPlayerId = useMemo(
    () => new Map(data.transfermarkt_listings.map((l) => [l.player_id, l])),
    [data.transfermarkt_listings]
  );
  const watchlist: WatchlistRow[] = useMemo(
    () =>
      data.wunschkader_targets
        .filter((t) => !ownSquadIdSet.has(t.player_id))
        .map((t) => ({
          ...resolveTarget(t.player_id, data.players, ownSquadIdSet, listingsByPlayerId, data.owned_by, data.calibration),
          ml_prediction: data.players[t.player_id]?.ml_prediction ?? null,
        })),
    [data.wunschkader_targets, ownSquadIdSet, data.players, listingsByPlayerId, data.owned_by, data.calibration]
  );
  const thresholds = data.signal_thresholds;
  const [selected, setSelected] = useState<Selected>(null);

  return (
    <div>
      <Section title={`Verkaufskandidaten (${split.verkaufen.length})`}>
        {split.verkaufen.length ? (
          <CardGrid>
            {split.verkaufen.map((row) => (
              <PlayerCard key={row.player_id} row={row} onSelect={() => setSelected({ kind: "player", row })} />
            ))}
          </CardGrid>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Verkaufskandidaten.</p>
        )}
      </Section>

      <Section title={`Watchlist (${watchlist.length})`}>
        {watchlist.length ? (
          <CardGrid>
            {watchlist.map((row) => (
              <WunschkaderWatchlistCard key={row.player_id} row={row} onSelect={() => setSelected({ kind: "watchlist", row })} />
            ))}
          </CardGrid>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Wunschkader-Ziele außerhalb des eigenen Kaders.</p>
        )}
      </Section>

      <Section title={`Bleibt im Kader (${split.bleibt.length})`}>
        {split.bleibt.length ? (
          <CardGrid>
            {split.bleibt.map((row) => (
              <PlayerCard key={row.player_id} row={row} onSelect={() => setSelected({ kind: "player", row })} />
            ))}
          </CardGrid>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Spieler in dieser Gruppe.</p>
        )}
      </Section>

      {selected?.kind === "player" && (
        <PlayerDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
      {selected?.kind === "watchlist" && (
        <WatchlistDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</div>
      {children}
    </div>
  );
}

function CardGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">{children}</div>;
}

function CardShell({
  header,
  children,
  onSelect,
  toneClass,
}: {
  header: ReactNode;
  children: ReactNode;
  onSelect: () => void;
  toneClass?: string;
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
      className={`cursor-pointer rounded-2xl border p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:hover:border-brand-600 ${
        toneClass ?? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      {header}
      <dl className="space-y-1.5 text-sm">{children}</dl>
    </div>
  );
}

function MlPredictionRow({ value, mae }: { value: number | null; mae?: number | null }) {
  return (
    <Row label="ML-Prognose">
      <span className={trendClass(value)}>
        {trendArrow(value, ML_PREDICTION_THRESHOLDS)} {fmtSigned(value)}
      </span>
      {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
    </Row>
  );
}

// Echter Verletzt/Angeschlagen/Im-Aufbau-Text statt Rohwert, "Fit" als
// expliziter Normalzustand statt einer leeren Zeile (User-Wunsch
// 2026-07-30: direkt sichtbar auf der Karte, nicht nur als Badge im Header).
function StatusLabelRow({ value }: { value: string | null }) {
  return (
    <Row label="Fitness">
      <FitnessBadge label={value} />
    </Row>
  );
}

function PlayerCard({
  row,
  onSelect,
}: {
  row: EigenesTeamRow;
  onSelect: () => void;
}) {
  return (
    <CardShell
      onSelect={onSelect}
      header={
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
          <PositionBadge position={row.position} />
          {row.sell_signal && (
            <Badge tone={row.sell_signal === "halten" ? "good" : row.sell_signal === "unklar" ? "warn" : "crit"}>
              {row.sell_signal === "halten" ? "Noch halten" : row.sell_signal === "unklar" ? "Unklar" : "Jetzt verkaufen"}
            </Badge>
          )}
        </div>
      }
    >
      <MlPredictionRow value={row.ml_prediction} />
      <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
      <StatusLabelRow value={row.status_label} />
      <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
      <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
    </CardShell>
  );
}

function WunschkaderWatchlistCard({
  row,
  onSelect,
}: {
  row: WatchlistRow;
  onSelect: () => void;
}) {
  const tone = cardTone(row.status);
  return (
    <CardShell
      onSelect={onSelect}
      toneClass={CARD_TONE_CLASSES[tone]}
      header={
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
          <PositionBadge position={row.position} />
          {tone === "market" && <Badge tone="good">🛒 Markt</Badge>}
        </div>
      }
    >
      <MlPredictionRow value={row.ml_prediction} />
      <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
      <StatusLabelRow value={row.status_label} />
      <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
    </CardShell>
  );
}

function useEscapeClose(onClose: () => void) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);
}

function DetailModalShell({
  header,
  footer,
  onClose,
  children,
}: {
  header: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  useEscapeClose(onClose);
  useModalOpenTracking();
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          {header}
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">{children}</dl>
        {footer}
      </div>
    </div>
  );
}

function PlayerDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: EigenesTeamRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  return (
    <>
      <DetailModalShell
        onClose={onClose}
        header={
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <PositionBadge position={row.position} />
          </div>
        }
        footer={
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setComparing((v) => !v)}
              className="text-xs text-brand-600 hover:underline dark:text-brand-400"
            >
              Vergleichen mit…
            </button>
            {comparing && (
              <div className="mt-2">
                <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
              </div>
            )}
          </div>
        }
      >
        {row.sell_signal && (
          <Row label="Empfehlung">
            <Badge tone={row.sell_signal === "halten" ? "good" : row.sell_signal === "unklar" ? "warn" : "crit"}>
              {row.sell_signal === "halten" ? "Noch halten" : row.sell_signal === "unklar" ? "Unklar" : "Jetzt verkaufen"}
            </Badge>
          </Row>
        )}
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <StatusLabelRow value={row.status_label} />
        <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      </DetailModalShell>
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

function WatchlistDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: WatchlistRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  return (
    <>
      <DetailModalShell
        onClose={onClose}
        header={
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <PositionBadge position={row.position} />
          </div>
        }
        footer={
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setComparing((v) => !v)}
              className="text-xs text-brand-600 hover:underline dark:text-brand-400"
            >
              Vergleichen mit…
            </button>
            {comparing && (
              <div className="mt-2">
                <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
              </div>
            )}
          </div>
        }
      >
        <Row label="Verfügbarkeit">{row.status ?? "—"}</Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
        <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
      </DetailModalShell>
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
