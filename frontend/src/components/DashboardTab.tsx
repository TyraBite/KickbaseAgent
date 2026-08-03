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
  sellSignal,
  type EigenesTeamRow,
  type TransfermarktRow,
} from "../lib/derive";
import { TransfermarktCard, TransfermarktDetailModal } from "./TransfermarktTab";
import { PlayerCard, PlayerDetailModal } from "./EigenesTeamTab";
import { fmtNum } from "../format";

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
  const [selectedOwned, setSelectedOwned] = useState<EigenesTeamRow | null>(null);

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
  // Investment schliesst Wunschkader-Ziele aus - das sind Spieler, die fest im
  // Kader eingeplant sind, keine reinen Kapitalanlagen-Verkaufskandidaten
  // (User-Feedback 2026-08-03, nach dem initialen Dashboard-Merge).
  const wunschkaderTargetIds = new Set(wunschkader.targets.map((t) => t.player_id));
  const investmentOwnRows = ownPlayerRows.filter((r) => !wunschkaderTargetIds.has(r.player_id));
  // Nur Auktionen, die vor dem naechsten 22-Uhr-Marktwert-Update enden, sind
  // heute noch handlungsrelevant - laeuft eine Auktion erst danach aus, gibt
  // es keinen Zeitdruck fuer heute (User-Feedback 2026-08-03). auction_urgent
  // ist exakt dieses bestehende Signal (siehe buildTransfermarktRows()).
  const investmentMarketRows = transfermarktRows.filter((r) => r.auction_urgent);
  const investmentSwaps = buildInvestmentSwaps(investmentOwnRows, investmentMarketRows, ML_PREDICTION_3D_THRESHOLDS.strong);

  const recentTransfers = recentTransfersWithin24h(data.recent_transfers ?? [], new Date(now));

  const SellSection = (
    <Section key="verkaufen" title="Verkaufen" emptyText="Aktuell keine Verkaufskandidaten." isEmpty={sellCandidates.length === 0}>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        {sellCandidates.map((r) => (
          <PlayerCard key={r.player_id} row={r} onSelect={() => setSelectedOwned(r)} />
        ))}
      </div>
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
      <div className="space-y-4">
        {investmentSwaps.map((pair) => {
          const sellRow: EigenesTeamRow = { ...pair.sell, sell_signal: sellSignal(pair.sell.ml_prediction, mae) };
          return (
            <div key={pair.sell.player_id + pair.buy.player_id} className="flex flex-wrap items-center gap-3">
              <div className="w-56 shrink-0">
                <PlayerCard row={sellRow} onSelect={() => setSelectedOwned(sellRow)} />
              </div>
              <span className="text-2xl text-slate-400 dark:text-slate-500" aria-hidden="true">→</span>
              <div className="w-56 shrink-0">
                <TransfermarktCard row={pair.buy} bidHistory={data.bid_premium_history ?? []} thresholds={data.signal_thresholds} onSelect={() => setSelected(pair.buy)} />
              </div>
            </div>
          );
        })}
      </div>
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
      {selectedOwned && (
        <PlayerDetailModal
          row={selectedOwned}
          thresholds={data.signal_thresholds}
          mae={mae}
          mae3d={liveModelMae(data.ml_metrics_3d ?? null)}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelectedOwned(null)}
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
