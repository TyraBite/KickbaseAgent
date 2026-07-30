import { useEffect, useMemo, useState, type FormEvent } from "react";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import type { DashboardSnapshot, RawWunschkaderTarget } from "../types";
import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, plannedPriceFor, type AlleSpielerRow, type BudgetPlan } from "../lib/derive";
import { resolveTarget, type ResolvedTarget } from "../lib/wunschkaderResolve";
import { DEFAULT_FORMATION, FORMATION_KEYS, type FormationKey, POSITIONS, type Position, isFormationKey, slotsFor } from "../lib/formations";
import { Badge, CARD_TONE_CLASSES, POSITION_ABBR, Row, SignalBadge, TeamCrest, cardTone } from "./ui";
import { fmtNum } from "../format";
import { useModalOpenTracking } from "../lib/modalOpenTracker";

const MAX_SQUAD_SIZE = 17;

export type EditTarget = RawWunschkaderTarget & { _uid: number };

function isBench(target: RawWunschkaderTarget): boolean {
  return target.role === "Bank/Backup-Option";
}

// Zaehlt Nicht-Bank-Ziele pro Verein - Basis fuer die Max-3-pro-Verein-Warnung
// (Kickbase-Regel: max. 3 Startelf-Spieler desselben Vereins). teamNameFor
// bekommt jetzt die player_id statt des Namens (player_id ist der
// verlaessliche Join-Key seit der players-Map-Umstellung).
function countByClub(targets: EditTarget[], teamNameFor: (playerId: string) => string | null): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const t of targets) {
    if (isBench(t)) continue;
    const club = teamNameFor(t.player_id);
    if (!club) continue;
    counts[club] = (counts[club] ?? 0) + 1;
  }
  return counts;
}

// 1:1 portiert aus scoreReplacementPool()/suggestReplacements()/
// searchReplacementPool() der bestehenden index.html - jetzt gegen player_id
// statt Name selbst-exkludierend und mit average_points (AlleSpielerRow aus
// derive.ts) statt des alten points_avg-Feldnamens.
function scoreReplacementPool(
  alleSpieler: AlleSpielerRow[],
  target: { player_id?: string; position: string; market_value: number | null; average_points: number | null }
) {
  const pool = alleSpieler.filter(
    (p) => p.position === target.position && p.player_id !== target.player_id && (p.owner === "Frei" || p.owner === "Eigener Kader")
  );
  const mv = target.market_value || 0;
  const pts = target.average_points || 0;
  return pool
    .map((p) => {
      const mvDist = mv ? Math.abs((p.market_value || 0) - mv) / mv : 0;
      const ptsDist = pts ? Math.abs((p.average_points || 0) - pts) / pts : 0;
      return { ...p, distance: mvDist + ptsDist };
    })
    .sort((a, b) => a.distance - b.distance);
}

function suggestReplacements(
  alleSpieler: AlleSpielerRow[],
  target: { player_id?: string; position: string; market_value: number | null; average_points: number | null },
  count = 3
) {
  return scoreReplacementPool(alleSpieler, target).slice(0, count);
}

function searchReplacementPool(
  alleSpieler: AlleSpielerRow[],
  target: { player_id?: string; position: string; market_value: number | null; average_points: number | null },
  query: string
) {
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
    (data.wunschkader_targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
  const [selected, setSelected] = useState<EditTarget | null>(null);
  const [addDialog, setAddDialog] = useState<{ presetPosition: Position | null } | null>(null);

  const alleSpieler = useMemo(
    () => buildAlleSpielerRows(data.players, data.own_squad_ids, data.owned_by, data.calibration),
    [data.players, data.own_squad_ids, data.owned_by, data.calibration]
  );
  const thresholds = data.signal_thresholds;

  const ownSquadIds = useMemo(() => new Set(data.own_squad_ids), [data.own_squad_ids]);
  const listingsByPlayerId = useMemo(
    () => new Map(data.transfermarkt_listings.map((l) => [l.player_id, l])),
    [data.transfermarkt_listings]
  );

  // Ein Ziel kennt nur noch seine player_id - Name/Position/Marktwert/etc.
  // sind rein abgeleitet ueber resolveTarget(). Einmal pro eindeutiger
  // player_id in editState aufgeloest statt bei jedem Render-Ort erneut, damit
  // jede Kachel/Detailansicht garantiert denselben Wert sieht.
  const resolvedByPlayerId = useMemo(() => {
    const map = new Map<string, ResolvedTarget>();
    for (const t of editState) {
      if (!map.has(t.player_id)) {
        map.set(t.player_id, resolveTarget(t.player_id, data.players, ownSquadIds, listingsByPlayerId, data.owned_by, data.calibration));
      }
    }
    return map;
  }, [editState, data.players, ownSquadIds, listingsByPlayerId, data.owned_by, data.calibration]);

  const clubCounts = useMemo(
    () => countByClub(editState, (playerId) => resolvedByPlayerId.get(playerId)?.team_name ?? null),
    [editState, resolvedByPlayerId]
  );

  // Verkaufserloese/Cash/Pool/Eingeplant kommen jetzt komplett aus
  // buildBudgetPlan() (derive.ts) - dieselbe Logik, die auch EigenesTeamTab
  // fuer die Verkaufskandidaten-Ableitung nutzt (Bug, gefunden 2026-07-29:
  // die alte wunschkader_raw.sell_list war eine separate, manuell gepflegte
  // Liste, unabhaengig vom aktuellen Wunschkader-Stand).
  const liveBudgetPlan: BudgetPlan = useMemo(
    () =>
      buildBudgetPlan({
        players: data.players,
        ownSquadIds,
        targets: editState,
        ownBudgetExact: data.own_budget_exact,
        listingsByPlayerId,
      }),
    [data.players, ownSquadIds, editState, data.own_budget_exact, listingsByPlayerId]
  );

  const byPosition = useMemo(() => {
    const groups: Record<Position, EditTarget[]> = { Torwart: [], Abwehr: [], Mittelfeld: [], Sturm: [] };
    for (const t of editState) {
      if (isBench(t)) continue;
      const resolvedPosition = resolvedByPlayerId.get(t.player_id)?.position;
      const pos = resolvedPosition && (resolvedPosition as Position) in groups ? (resolvedPosition as Position) : "Sturm";
      groups[pos].push(t);
    }
    return groups;
  }, [editState, resolvedByPlayerId]);

  const bench = useMemo(() => editState.filter(isBench), [editState]);

  // Geplanter Preis fuer die aktuell geoeffnete Detailansicht - ausserhalb von
  // buildBudgetPlan() (das summiert nur ueber alle Ziele), daher hier per
  // liveBidFor()/plannedPriceFor() (derive.ts) - dieselben Funktionen, die
  // buildBudgetPlan() intern nutzt, damit Kachel-Einzelpreis und Budget-Summe
  // garantiert nie divergieren (Review-Fund 2026-07-29: vorher war der
  // Live-Gebots-Ausdruck hier separat dupliziert).
  const selectedPlannedPrice = useMemo(() => {
    if (!selected) return null;
    const computed = resolvedByPlayerId.get(selected.player_id);
    if (!computed) return null;
    const liveBid = liveBidFor(selected.player_id, listingsByPlayerId);
    return plannedPriceFor(computed.market_value, ownSquadIds.has(selected.player_id), liveBid);
  }, [selected, resolvedByPlayerId, listingsByPlayerId, ownSquadIds]);

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
        const { note: _note, ...keep } = t;
        return { ...keep, player_id: replacement.player_id };
      })
    );
    setSelected(null);
  }

  function updateNote(uid: number, note: string) {
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }

  function addTarget(target: { player_id: string; position: Position; role: string }) {
    setEditState((prev) => [
      ...prev,
      { player_id: target.player_id, role: target.role, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 },
    ]);
  }

  const [saveStatus, setSaveStatus] = useState("");

  async function handleSave() {
    // Absicherung gegen die einmalige Migration (migrate_wunschkader_player_ids.py):
    // solange die noch nicht gegen den aktuellen Firestore-Wunschkader-Doc
    // gelaufen ist, kann _build_wunschkader_targets() (dashboard_export.py)
    // Ziele ohne player_id durchreichen (nur stderr-Warnung, kein Datenverlust
    // serverseitig). Ein Save von hier aus wuerde mit merge:true das gesamte
    // targets-Array ersetzen und damit die name-Felder unwiderruflich
    // wegwerfen, die das Migrationsskript zum Aufloesen braucht - deshalb
    // lieber hart blockieren als stillschweigend Daten verlieren.
    if (editState.some((t) => !t.player_id)) {
      setSaveStatus(
        "Speichern blockiert: mindestens ein Ziel hat keine player_id (Migration noch nicht gelaufen?) — Firestore-Konsole pruefen."
      );
      return;
    }
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
                const computed = resolvedByPlayerId.get(t.player_id)!;
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
            const computed = resolvedByPlayerId.get(t.player_id)!;
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
          computed={resolvedByPlayerId.get(selected.player_id)!}
          plannedPrice={selectedPlannedPrice}
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
          alleSpieler={alleSpieler}
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
  computed: ResolvedTarget;
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
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[computed.position] ?? computed.position}</span>
        <span className="font-semibold text-slate-900 dark:text-slate-50">{computed.name}</span>
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
        <Row label="Schnitt">{fmtNum(computed.average_points)}</Row>
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
  computed: ResolvedTarget;
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

  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const targetForSearch = {
    player_id: target.player_id,
    position: computed.position,
    market_value: computed.market_value,
    average_points: computed.average_points,
  };
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
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[computed.position] ?? computed.position}</span>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{computed.name}</span>
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
        <dl className="mb-4 space-y-2 text-sm">
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
          <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Schnitt">{fmtNum(computed.average_points)}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
          <Row label="Verfügbarkeit">{computed.status}</Row>
          <Row label="Verein">{computed.team_name ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Geplanter Preis">{fmtNum(plannedPrice)}</Row>
        </dl>
        <label className="mb-4 block text-sm">
          <span className="mb-1 block text-slate-500 dark:text-slate-400">Notiz</span>
          <textarea
            value={target.note ?? ""}
            onChange={(e) => onNoteChange(e.target.value)}
            rows={2}
            maxLength={500}
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
                    {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.average_points)})
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
                      {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.average_points)})
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

function BudgetPlanCard({ plan }: { plan: BudgetPlan }) {
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
          <div className="text-xs text-slate-500 dark:text-slate-400">= Spielraum</div>
          <div className={`font-semibold tabular-nums ${remainingTone}`}>{fmtNum(plan.remaining)}</div>
        </div>
      </div>
    </div>
  );
}

function AddTargetModal({
  presetPosition,
  alleSpieler,
  onAdd,
  onClose,
}: {
  presetPosition: Position | null;
  alleSpieler: AlleSpielerRow[];
  onAdd: (target: { player_id: string; position: Position; role: string }) => void;
  onClose: () => void;
}) {
  const [position, setPosition] = useState<Position>(presetPosition ?? "Sturm");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AlleSpielerRow | null>(null);

  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const effectivePosition = presetPosition ?? position;
  const searchTarget = { position: effectivePosition, market_value: 0, average_points: 0 };
  const results = search.trim() ? searchReplacementPool(alleSpieler, searchTarget, search.trim()) : [];

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    onAdd({
      player_id: selected.player_id,
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
        {!presetPosition && (
          <select
            value={position}
            onChange={(e) => {
              setPosition(e.target.value as Position);
              setSelected(null);
            }}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
        <input
          type="text"
          value={selected ? selected.name : search}
          onChange={(e) => {
            setSelected(null);
            setSearch(e.target.value);
          }}
          placeholder="Spieler suchen…"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {!selected && search.trim() && (
          <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
            {results.length ? (
              results.map((p) => (
                <button
                  key={p.player_id}
                  type="button"
                  onClick={() => {
                    setSelected(p);
                    setSearch("");
                  }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  {p.name} ({fmtNum(p.market_value)}, Ø{fmtNum(p.average_points)})
                </button>
              ))
            ) : (
              <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                Keine Treffer (freie Spieler/eigener Kader, Position {effectivePosition}).
              </p>
            )}
          </div>
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
            disabled={!selected}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Hinzufügen
          </button>
        </div>
      </form>
    </div>
  );
}
