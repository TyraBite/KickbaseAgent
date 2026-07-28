import { useMemo, useState } from "react";
import type { AlleSpielerRow, DashboardSnapshot, RawWunschkaderTarget, WunschkaderRow } from "../types";
import { DEFAULT_FORMATION, FORMATION_KEYS, type FormationKey, POSITIONS, type Position, isFormationKey, slotsFor } from "../lib/formations";
import { Badge, POSITION_ABBR, Row, SignalBadge } from "./ui";
import { fmtNum } from "../format";

const MAX_SQUAD_SIZE = 17;

export type EditTarget = RawWunschkaderTarget & { _uid: number };

function isBench(target: RawWunschkaderTarget): boolean {
  return target.role === "Bank/Backup-Option";
}

interface Computed {
  market_value: number | null;
  points_avg: number | null;
  starting_rank: number | null;
  signal: number | null;
}

// 1:1 Logik aus computedFor() in der bestehenden index.html: zuerst die
// serverseitig berechnete Wunschkader-Zeile nehmen (hat Fairwert-Signal
// gegen die eigene Position berechnet), sonst auf die allgemeine
// Alle-Spieler-Liste zurueckfallen (frisch hinzugefuegte Ziele haben noch
// keine Wunschkader-Zeile, bis der naechste Pipeline-Lauf durch ist).
function computedFor(name: string, wunschkader: WunschkaderRow[], alleSpieler: AlleSpielerRow[]): Computed {
  const fromWunschkader = wunschkader.find((r) => r.name === name);
  if (fromWunschkader) {
    return {
      market_value: fromWunschkader.market_value,
      points_avg: fromWunschkader.points_avg,
      starting_rank: fromWunschkader.starting_rank,
      signal: fromWunschkader.signal,
    };
  }
  const live = alleSpieler.find((p) => p.name === name);
  if (!live) return { market_value: null, points_avg: null, starting_rank: null, signal: null };
  return {
    market_value: live.market_value,
    points_avg: live.points_avg,
    starting_rank: live.starting_rank,
    signal: live.signal,
  };
}

// 1:1 portiert aus scoreReplacementPool()/suggestReplacements()/
// searchReplacementPool() der bestehenden index.html.
function scoreReplacementPool(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }) {
  const pool = alleSpieler.filter((p) => p.position === target.position && p.name !== target.name && p.owner === "Frei");
  const mv = target.market_value || 0;
  const pts = target.points_avg || 0;
  return pool
    .map((p) => {
      const mvDist = mv ? Math.abs((p.market_value || 0) - mv) / mv : 0;
      const ptsDist = pts ? Math.abs((p.points_avg || 0) - pts) / pts : 0;
      return { ...p, distance: mvDist + ptsDist };
    })
    .sort((a, b) => a.distance - b.distance);
}

function suggestReplacements(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }, count = 3) {
  return scoreReplacementPool(alleSpieler, target).slice(0, count);
}

function searchReplacementPool(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }, query: string) {
  const q = query.toLowerCase();
  return scoreReplacementPool(alleSpieler, target)
    .filter((p) => p.name.toLowerCase().includes(q))
    .slice(0, 20);
}

export default function WunschkaderTab({ data }: { data: DashboardSnapshot }) {
  const [formation, setFormation] = useState<FormationKey>(
    isFormationKey(data.wunschkader_formation) ? data.wunschkader_formation : DEFAULT_FORMATION
  );
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (data.wunschkader_raw?.targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
  const [selected, setSelected] = useState<EditTarget | null>(null);

  const wunschkader = data.wunschkader ?? [];
  const alleSpieler = data.alle_spieler ?? [];
  const budgetPlan = data.budget_plan;
  const thresholds = data.signal_thresholds;

  const byPosition = useMemo(() => {
    const groups: Record<Position, EditTarget[]> = { Torwart: [], Abwehr: [], Mittelfeld: [], Sturm: [] };
    for (const t of editState) {
      if (isBench(t)) continue;
      const pos = (t.position as Position) in groups ? (t.position as Position) : "Sturm";
      groups[pos].push(t);
    }
    return groups;
  }, [editState]);

  const bench = useMemo(() => editState.filter(isBench), [editState]);

  function toggleBench(uid: number) {
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }

  function removeTarget(uid: number) {
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }

  function replaceTarget(uid: number, replacement: AlleSpielerRow) {
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { name: replacement.name, position: replacement.position, role: t.role } : t))
    );
    setSelected(null);
  }

  const totalCount = editState.length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Formation
          <select
            value={formation}
            onChange={(e) => setFormation(e.target.value as FormationKey)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {FORMATION_KEYS.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>
        {totalCount > MAX_SQUAD_SIZE && (
          <Badge tone="warn">
            {totalCount}/{MAX_SQUAD_SIZE} Kadergröße überschritten
          </Badge>
        )}
      </div>

      {POSITIONS.map((position) => {
        const targets = byPosition[position];
        const slots = slotsFor(formation, position);
        return (
          <div key={position} className="mb-6">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {position} · {targets.length}/{slots} belegt
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
              {targets.map((t) => (
                <TargetCard
                  key={t._uid}
                  target={t}
                  computed={computedFor(t.name, wunschkader, alleSpieler)}
                  thresholds={thresholds}
                  onSelect={() => setSelected(t)}
                />
              ))}
              {Array.from({ length: Math.max(slots - targets.length, 0) }).map((_, i) => (
                <EmptySlotCard key={`empty-${position}-${i}`} />
              ))}
            </div>
          </div>
        );
      })}

      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Bank ({bench.length})
        </div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          {bench.map((t) => (
            <TargetCard
              key={t._uid}
              target={t}
              computed={computedFor(t.name, wunschkader, alleSpieler)}
              thresholds={thresholds}
              onSelect={() => setSelected(t)}
            />
          ))}
          <EmptySlotCard />
        </div>
      </div>

      {budgetPlan && <BudgetPlanCard plan={budgetPlan} />}

      {selected && (
        <DetailModal
          target={selected}
          computed={computedFor(selected.name, wunschkader, alleSpieler)}
          thresholds={thresholds}
          alleSpieler={alleSpieler}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(replacement) => replaceTarget(selected._uid, replacement)}
        />
      )}
    </div>
  );
}

function TargetCard({
  target,
  computed,
  thresholds,
  onSelect,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  onSelect: () => void;
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
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-600"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
        <span className="font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
        <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <Row label="Schnitt">{fmtNum(computed.points_avg)}</Row>
        <Row label="Signal">
          <SignalBadge signal={computed.signal} thresholds={thresholds} />
        </Row>
      </dl>
    </div>
  );
}

function EmptySlotCard() {
  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
      + Ziel
    </div>
  );
}

function DetailModal({
  target,
  computed,
  thresholds,
  alleSpieler,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  alleSpieler: AlleSpielerRow[];
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (replacement: AlleSpielerRow) => void;
}) {
  const [wechselOpen, setWechselOpen] = useState(false);
  const [search, setSearch] = useState("");

  const targetForSearch = { name: target.name, position: target.position, market_value: computed.market_value, points_avg: computed.points_avg };
  const suggestions = suggestReplacements(alleSpieler, targetForSearch);
  const searchResults = search.trim() ? searchReplacementPool(alleSpieler, targetForSearch, search.trim()) : [];

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
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
        <dl className="mb-4 space-y-2 text-sm">
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
          <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Schnitt">{fmtNum(computed.points_avg)}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
        </dl>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onToggleBench}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isBench(target) ? "In Startelf verschieben" : "Auf Bank verschieben"}
          </button>
          <button
            type="button"
            onClick={() => setWechselOpen((v) => !v)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Wechsel
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
          >
            Entfernen
          </button>
        </div>
        {wechselOpen && (
          <div className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-800">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Vorschläge</div>
            {suggestions.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s.player_id}
                    type="button"
                    onClick={() => onReplace(s)}
                    className="rounded-full border border-brand-300 bg-brand-50 px-3 py-1 text-xs text-brand-800 hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300"
                  >
                    {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.points_avg)})
                  </button>
                ))}
              </div>
            ) : (
              <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">Keine freien Alternativen gleicher Position gefunden.</p>
            )}
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Anderen freien Spieler gleicher Position suchen…"
              className="mb-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
            {search.trim() && (
              <div className="flex flex-wrap gap-2">
                {searchResults.length ? (
                  searchResults.map((s) => (
                    <button
                      key={s.player_id}
                      type="button"
                      onClick={() => onReplace(s)}
                      className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.points_avg)})
                    </button>
                  ))
                ) : (
                  <span className="text-xs text-slate-400 dark:text-slate-500">Keine Treffer.</span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function BudgetPlanCard({ plan }: { plan: NonNullable<DashboardSnapshot["budget_plan"]> }) {
  const remainingTone = plan.remaining >= 0 ? "text-brand-600 dark:text-brand-400" : "text-red-600 dark:text-red-400";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-50">Budget-Planung</h3>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Cash</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.cash)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">+ Verkaufserlöse</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.sell_proceeds)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">= Pool</div>
          <div className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.pool)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">- Eingeplant</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.committed)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">= Rest</div>
          <div className={`font-semibold tabular-nums ${remainingTone}`}>{fmtNum(plan.remaining)}</div>
        </div>
      </div>
    </div>
  );
}
