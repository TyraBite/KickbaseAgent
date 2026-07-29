import type { ReactNode } from "react";
import type { DashboardSnapshot, EigenesTeamRow, WunschkaderRow } from "../types";
import { Badge, POSITION_ABBR, Row, SignalBadge, TeamCrest } from "./ui";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";

// Felder gekuerzt ggue. der alten index.html: cost_per_point weggelassen
// (redundant zu Signal, beide leiten sich aus Marktwert/Punkte-Schnitt ab),
// 92-Tage-Tief/Hoch weggelassen (Spekulations-Konzept "guenstig einsteigen",
// nicht "eigenen Spieler halten/verkaufen") - schneller Port, echter
// Feld-Audit folgt spaeter (siehe Plan).
const TREND_7D_THRESHOLDS = { flat: 200_000, strong: 1_500_000 };

export default function EigenesTeamTab({ data }: { data: DashboardSnapshot }) {
  const split = data.eigenes_team_split ?? { verkaufen: [], bleibt: [] };
  const watchlist = data.wunschkader_watchlist ?? [];
  const thresholds = data.signal_thresholds;

  return (
    <div>
      <Section title={`Verkaufskandidaten (${split.verkaufen.length})`}>
        {split.verkaufen.length ? (
          <CardGrid>
            {split.verkaufen.map((row) => (
              <PlayerCard key={row.player_id} row={row} thresholds={thresholds} />
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
              <WunschkaderWatchlistCard key={row.name} row={row} thresholds={thresholds} />
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
              <PlayerCard key={row.player_id} row={row} thresholds={thresholds} />
            ))}
          </CardGrid>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Spieler in dieser Gruppe.</p>
        )}
      </Section>
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

function CardShell({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {header}
      <dl className="space-y-1.5 text-sm">{children}</dl>
    </div>
  );
}

function PlayerCard({
  row,
  thresholds,
}: {
  row: EigenesTeamRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
}) {
  return (
    <CardShell
      header={
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          {row.sell_signal && (
            <Badge tone={row.sell_signal === "halten" ? "good" : "warn"}>
              {row.sell_signal === "halten" ? "Noch halten" : "Jetzt verkaufen"}
            </Badge>
          )}
        </div>
      }
    >
      <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      <Row label="Trend 7T">
        <span className={trendClass(row.market_value_change_7d)}>
          {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
        </span>
      </Row>
      <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
      <Row label="Signal">
        <SignalBadge signal={row.signal} thresholds={thresholds} />
      </Row>
      <Row label="ML-Prognose">{fmtSigned(row.ml_prediction)}</Row>
      <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
      <Row label="Status">{row.status_label ?? "—"}</Row>
    </CardShell>
  );
}

function WunschkaderWatchlistCard({
  row,
  thresholds,
}: {
  row: WunschkaderRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
}) {
  return (
    <CardShell
      header={
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
        </div>
      }
    >
      <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      <Row label="Schnitt">{fmtNum(row.points_avg)}</Row>
      <Row label="Signal">
        <SignalBadge signal={row.signal} thresholds={thresholds} />
      </Row>
      <Row label="ML-Prognose">{fmtSigned(row.ml_prediction)}</Row>
      <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
      <Row label="Status">{row.status ?? "—"}</Row>
    </CardShell>
  );
}
