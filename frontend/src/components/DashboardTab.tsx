import { useState } from "react";
import type { DashboardSnapshot, RawWunschkaderTarget } from "../types";
import {
  buildDashboardBuyCandidates,
  buildDashboardSellCandidates,
  buildInvestmentSwaps,
  buildPlayerRow,
  formatRelativeTime,
  liveModelMae,
  recentTransfersWithin24h,
  type TransfermarktRow,
} from "../lib/derive";
import { TransfermarktCard, TransfermarktDetailModal } from "./TransfermarktTab";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { PositionBadge, TeamCrest } from "./ui";

const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const MAX_OWNED_SQUAD_SIZE = 17;

export default function DashboardTab({
  data,
  wunschkader,
  transfermarktRows,
  now,
}: {
  data: DashboardSnapshot;
  wunschkader: { targets: RawWunschkaderTarget[] };
  transfermarktRows: TransfermarktRow[];
  now: number;
}) {
  const mae = liveModelMae(data.ml_metrics);
  const [selected, setSelected] = useState<TransfermarktRow | null>(null);

  const squadFull = data.own_squad_ids.length >= MAX_OWNED_SQUAD_SIZE;

  const sellCandidates = buildDashboardSellCandidates(data.players, data.own_squad_ids, data.calibration, mae);
  const buyCandidates = buildDashboardBuyCandidates(transfermarktRows, wunschkader.targets);

  // Investment betrachtet ALLE eigenen Spieler (nicht nur die sellSignal-
  // gefilterten sellCandidates) - Position/Verkaufssignal spielen hier bewusst
  // keine Rolle, siehe Spec Abschnitt E.
  const ownPlayerRows = data.own_squad_ids
    .map((pid) => data.players[pid])
    .filter((p): p is (typeof data.players)[string] => !!p)
    .map((p) => buildPlayerRow(p, data.calibration));
  const investmentSwaps = buildInvestmentSwaps(ownPlayerRows, transfermarktRows, ML_PREDICTION_3D_THRESHOLDS.strong);

  const recentTransfers = recentTransfersWithin24h(data.recent_transfers ?? [], new Date(now));

  const SellSection = (
    <Section key="verkaufen" title="Verkaufen" emptyText="Aktuell keine Verkaufskandidaten." isEmpty={sellCandidates.length === 0}>
      {sellCandidates.map((r) => (
        <PlayerRowCard key={r.player_id} name={r.name} position={r.position} teamName={r.team_name} marketValue={r.market_value} ml1d={r.ml_prediction} ml3d={r.ml_prediction_3d} />
      ))}
    </Section>
  );

  const BuySection = (
    <Section key="kaufen" title="Kaufen" emptyText="Aktuell keine Wunschkader-Ziele auf dem Markt." isEmpty={buyCandidates.length === 0}>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        {buyCandidates.map((r) => (
          <TransfermarktCard key={r.player_id} row={r} bidHistory={data.bid_premium_history ?? []} thresholds={data.signal_thresholds} onSelect={() => setSelected(r)} />
        ))}
      </div>
    </Section>
  );

  const InvestmentSection = (
    <Section key="investment" title="Investment" emptyText="Aktuell keine Kapitalanlage-Swaps mit ausreichendem Abstand." isEmpty={investmentSwaps.length === 0}>
      {investmentSwaps.map((pair) => (
        <p key={pair.sell.player_id + pair.buy.player_id} className="text-sm text-slate-700 dark:text-slate-200">
          Verkaufen: {pair.sell.name} (
          <span className={trendClass(pair.sell.ml_prediction_3d)}>{fmtSigned(pair.sell.ml_prediction_3d)}</span>
          ) → Kaufen: {pair.buy.name} (
          <span className={trendClass(pair.buy.ml_prediction_3d)}>{fmtSigned(pair.buy.ml_prediction_3d)}</span>
          )
        </p>
      ))}
    </Section>
  );

  const FeedSection = (
    <Section key="feed" title="Letzte Transfers" emptyText="Keine Transfers in den letzten 24 Stunden." isEmpty={recentTransfers.length === 0}>
      {recentTransfers.map((t) => (
        <p key={t.player_id + t.date} className="text-sm text-slate-700 dark:text-slate-200">
          {t.player_name}: {t.seller} → {t.buyer}, {fmtNum(t.price)} ({formatRelativeTime(t.date, new Date(now))})
        </p>
      ))}
    </Section>
  );

  const sections = squadFull ? [SellSection, BuySection, InvestmentSection, FeedSection] : [BuySection, SellSection, InvestmentSection, FeedSection];

  return (
    <div>
      {squadFull && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          Kader voll (17/17)
        </div>
      )}
      {sections}
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          mae={mae}
          mae3d={liveModelMae(data.ml_metrics_3d ?? null)}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function Section({
  title, emptyText, isEmpty, children,
}: { title: string; emptyText: string; isEmpty: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h3>
      {isEmpty ? <p className="text-sm text-slate-500 dark:text-slate-400">{emptyText}</p> : <div className="space-y-2">{children}</div>}
    </div>
  );
}

function PlayerRowCard({
  name, position, teamName, marketValue, ml1d, ml3d,
}: { name: string; position: string; teamName: string | null; marketValue: number | null; ml1d: number | null; ml3d: number | null }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900">
      <TeamCrest teamName={teamName} />
      <span className="font-medium text-slate-900 dark:text-slate-50">{name}</span>
      <PositionBadge position={position} />
      <span className="text-slate-500 dark:text-slate-400">{fmtNum(marketValue)}</span>
      <span className={trendClass(ml1d)}>{trendArrow(ml1d, { flat: 20_000, strong: 100_000 })} {fmtSigned(ml1d)}</span>
      <span className={trendClass(ml3d)}>{trendArrow(ml3d, ML_PREDICTION_3D_THRESHOLDS)} {fmtSigned(ml3d)}</span>
    </div>
  );
}
