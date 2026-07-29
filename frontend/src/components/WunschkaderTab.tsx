import { useEffect, useMemo, useState, type FormEvent } from "react";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import type { AlleSpielerRow, DashboardSnapshot, RawWunschkaderTarget, WunschkaderRow } from "../types";
import { DEFAULT_FORMATION, FORMATION_KEYS, type FormationKey, POSITIONS, type Position, isFormationKey, slotsFor } from "../lib/formations";
import { Badge, CARD_TONE_CLASSES, POSITION_ABBR, Row, SignalBadge, TeamCrest, cardTone } from "./ui";
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
  team_name: string | null;
  status: string | null;
}

// 1:1 Logik aus computedFor() in der bestehenden index.html: zuerst die
// serverseitig berechnete Wunschkader-Zeile nehmen (hat Fairwert-Signal
// gegen die eigene Position berechnet), sonst auf die allgemeine
// Alle-Spieler-Liste zurueckfallen (frisch hinzugefuegte Ziele haben noch
// keine Wunschkader-Zeile, bis der naechste Pipeline-Lauf durch ist) -
// UND pro einzelnem Feld, nicht pro Quelle: eine wunschkader-Zeile kann ein
// Feld mit null haben, das in alleSpieler trotzdem bekannt ist (z.B. ein
// Snapshot von vor einem Schema-Update, siehe team_name-Nachzieh-Bug
// 2026-07-29) - ohne Per-Feld-Fallback bliebe das Feld dann dauerhaft leer.
// `status` (Ownership/Marktlage-Text) gibt es nur serverseitig als echten
// Text mit dem "Markt (...)"-Sonderfall - der Fallback ueber owner
// ("Eigener Kader"/"Frei"/Manager-Name, auf AlleSpielerRow immer vorhanden)
// bildet denselben Text nach, nur ohne den market_by_name-Kontext, den der
// Client nicht hat.
function computedFor(name: string, wunschkader: WunschkaderRow[], alleSpieler: AlleSpielerRow[]): Computed {
  const fromWunschkader = wunschkader.find((r) => r.name === name);
  const live = alleSpieler.find((p) => p.name === name);
  const liveStatus = live ? (live.owner === "Frei" || live.owner === "Eigener Kader" ? live.owner : `Bei ${live.owner}`) : null;
  return {
    market_value: fromWunschkader?.market_value ?? live?.market_value ?? null,
    points_avg: fromWunschkader?.points_avg ?? live?.points_avg ?? null,
    starting_rank: fromWunschkader?.starting_rank ?? live?.starting_rank ?? null,
    signal: fromWunschkader?.signal ?? live?.signal ?? null,
    team_name: fromWunschkader?.team_name ?? live?.team_name ?? null,
    status: fromWunschkader?.status ?? liveStatus,
  };
}

// 1:1 Portierung von _estimate_price() aus src/dashboard_export.py.
function estimatePrice(marketValue: number | null): number | null {
  if (!marketValue) return null;
  return Math.round(marketValue * 1.1);
}

// Spiegelt die planned_price-Prioritaet aus _build_wunschkader() (dashboard_export.py):
// actual_bid > 0 bei eigenem Kader > geschaetzter Preis.
function plannedPriceFor(target: RawWunschkaderTarget, marketValue: number | null, isOwn: boolean): number | null {
  if (target.actual_bid !== undefined) return target.actual_bid;
  if (isOwn) return 0;
  return estimatePrice(marketValue);
}

// Zaehlt Nicht-Bank-Ziele pro Verein - Basis fuer die Max-3-pro-Verein-Warnung
// (Kickbase-Regel: max. 3 Startelf-Spieler desselben Vereins).
function countByClub(targets: EditTarget[], teamNameFor: (name: string) => string | null): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const t of targets) {
    if (isBench(t)) continue;
    const club = teamNameFor(t.name);
    if (!club) continue;
    counts[club] = (counts[club] ?? 0) + 1;
  }
  return counts;
}

// 1:1 portiert aus scoreReplacementPool()/suggestReplacements()/
// searchReplacementPool() der bestehenden index.html.
function scoreReplacementPool(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }) {
  const pool = alleSpieler.filter(
    (p) => p.position === target.position && p.name !== target.name && (p.owner === "Frei" || p.owner === "Eigener Kader")
  );
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
  const [addDialog, setAddDialog] = useState<{ presetPosition: Position | null } | null>(null);

  const wunschkader = data.wunschkader ?? [];
  const alleSpieler = data.alle_spieler ?? [];
  const thresholds = data.signal_thresholds;

  const ownSquadNames = useMemo(
    () => new Set(alleSpieler.filter((p) => p.owner === "Eigener Kader").map((p) => p.name)),
    [alleSpieler]
  );

  const clubCounts = useMemo(
    () => countByClub(editState, (name) => computedFor(name, wunschkader, alleSpieler).team_name),
    [editState, wunschkader, alleSpieler]
  );

  // Rechnet _build_budget_plan() (dashboard_export.py) 1:1 clientseitig nach,
  // damit die Budget-Zahlen sofort auf jede Wunschkader-Aenderung reagieren
  // statt erst nach Speichern + naechstem 2h-Cron-Lauf.
  const liveBudgetPlan = useMemo(() => {
    const sellList = data.wunschkader_raw?.sell_list ?? [];
    const ownByName = new Map(alleSpieler.filter((p) => p.owner === "Eigener Kader").map((p) => [p.name, p]));
    const sellRows = sellList
      .filter((name) => ownByName.has(name))
      .map((name) => ({ name, market_value: ownByName.get(name)!.market_value }));
    const sellProceeds = sellRows.reduce((sum, r) => sum + (r.market_value || 0), 0);

    const cash = data.own_budget_exact || 0;
    const pool = cash + sellProceeds;

    const committed = editState.reduce((sum, t) => {
      if (isBench(t)) return sum;
      const isOwn = ownSquadNames.has(t.name);
      if (isOwn) return sum;
      const marketValue = computedFor(t.name, wunschkader, alleSpieler).market_value;
      return sum + (plannedPriceFor(t, marketValue, isOwn) || 0);
    }, 0);

    return { cash, sell_rows: sellRows, sell_proceeds: sellProceeds, pool, committed, remaining: pool - committed };
  }, [alleSpieler, data.wunschkader_raw, data.own_budget_exact, editState, ownSquadNames, wunschkader]);

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
      prev.map((t) => {
        if (t._uid !== uid) return t;
        const { note: _note, actual_bid: _bid, ...keep } = t;
        return { ...keep, name: replacement.name, position: replacement.position };
      })
    );
    setSelected(null);
  }

  function updateNote(uid: number, note: string) {
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }

  function addTarget(target: { name: string; position: Position; role: string }) {
    setEditState((prev) => [...prev, { ...target, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 }]);
  }

  const [saveStatus, setSaveStatus] = useState("");

  async function handleSave() {
    setSaveStatus("Speichere…");
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
      setSaveStatus("Gespeichert. Änderungen erscheinen im nächsten Pipeline-Lauf (~2h).");
    } catch (err) {
      setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
    }
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

      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Speichern
        </button>
        {saveStatus && <span className="text-sm text-slate-500 dark:text-slate-400">{saveStatus}</span>}
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
              {targets.map((t) => {
                const computed = computedFor(t.name, wunschkader, alleSpieler);
                return (
                  <TargetCard
                    key={t._uid}
                    target={t}
                    computed={computed}
                    thresholds={thresholds}
                    clubCount={computed.team_name ? clubCounts[computed.team_name] ?? 0 : 0}
                    onSelect={() => setSelected(t)}
                  />
                );
              })}
              {Array.from({ length: Math.max(slots - targets.length, 0) }).map((_, i) => (
                <EmptySlotCard key={`empty-${position}-${i}`} onClick={() => setAddDialog({ presetPosition: position })} />
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
          {bench.map((t) => {
            const computed = computedFor(t.name, wunschkader, alleSpieler);
            return (
              <TargetCard
                key={t._uid}
                target={t}
                computed={computed}
                thresholds={thresholds}
                clubCount={0}
                onSelect={() => setSelected(t)}
              />
            );
          })}
          <EmptySlotCard onClick={() => setAddDialog({ presetPosition: null })} />
        </div>
      </div>

      <BudgetPlanCard plan={liveBudgetPlan} />

      {selected && (
        <DetailModal
          target={selected}
          computed={computedFor(selected.name, wunschkader, alleSpieler)}
          plannedPrice={plannedPriceFor(selected, computedFor(selected.name, wunschkader, alleSpieler).market_value, ownSquadNames.has(selected.name))}
          thresholds={thresholds}
          alleSpieler={alleSpieler}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(replacement) => replaceTarget(selected._uid, replacement)}
          onNoteChange={(note) => updateNote(selected._uid, note)}
        />
      )}

      {addDialog && (
        <AddTargetModal
          presetPosition={addDialog.presetPosition}
          onAdd={addTarget}
          onClose={() => setAddDialog(null)}
        />
      )}
    </div>
  );
}

function TargetCard({
  target,
  computed,
  thresholds,
  clubCount,
  onSelect,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  clubCount: number;
  onSelect: () => void;
}) {
  const tone = cardTone(computed.status);
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
      className={`cursor-pointer rounded-2xl border p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:hover:border-brand-600 ${CARD_TONE_CLASSES[tone]}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TeamCrest teamName={computed.team_name} />
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
        <span className="font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
        {tone === "market" && <Badge tone="good">🛒 Markt</Badge>}
        {clubCount >= 4 && (
          <Badge tone="warn">
            {clubCount}× {computed.team_name}
          </Badge>
        )}
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

function EmptySlotCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-center rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 hover:border-brand-400 hover:text-brand-600 dark:border-slate-700 dark:text-slate-500 dark:hover:border-brand-600 dark:hover:text-brand-400"
    >
      + Ziel
    </button>
  );
}

function DetailModal({
  target,
  computed,
  plannedPrice,
  thresholds,
  alleSpieler,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
  onNoteChange,
}: {
  target: EditTarget;
  computed: Computed;
  plannedPrice: number | null;
  thresholds: DashboardSnapshot["signal_thresholds"];
  alleSpieler: AlleSpielerRow[];
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (replacement: AlleSpielerRow) => void;
  onNoteChange: (note: string) => void;
}) {
  const [wechselOpen, setWechselOpen] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

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
            <TeamCrest teamName={computed.team_name} />
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
          <Row label="Status">{computed.status ?? "—"}</Row>
          <Row label="Verein">{computed.team_name ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Geplanter Preis">{fmtNum(plannedPrice)}</Row>
        </dl>
        <label className="mb-4 block text-sm">
          <span className="mb-1 block text-slate-500 dark:text-slate-400">Notiz</span>
          <textarea
            value={target.note ?? ""}
            onChange={(e) => onNoteChange(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
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

function AddTargetModal({
  presetPosition,
  onAdd,
  onClose,
}: {
  presetPosition: Position | null;
  onAdd: (target: { name: string; position: Position; role: string }) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [position, setPosition] = useState<Position>(presetPosition ?? "Sturm");

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd({
      name: trimmed,
      position: presetPosition ?? position,
      role: presetPosition ? "Starter" : "Bank/Backup-Option",
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-50">
          Ziel hinzufügen{presetPosition ? ` (${presetPosition})` : ""}
        </h3>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name"
          autoFocus
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {!presetPosition && (
          <select
            value={position}
            onChange={(e) => setPosition(e.target.value as Position)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Hinzufügen
          </button>
        </div>
      </form>
    </div>
  );
}
