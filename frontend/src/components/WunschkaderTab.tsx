import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import { useDebouncedCallback } from "../lib/useDebouncedCallback";
import { staggerContainerVariants, staggerItemVariants } from "../lib/motionVariants";
import type { DashboardSnapshot, RawWunschkaderTarget } from "../types";
import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, normalizeSearchText, plannedPriceFor, type AlleSpielerRow, type BudgetPlan, type PlannedPrice } from "../lib/derive";
import { resolveTarget, type ResolvedTarget } from "../lib/wunschkaderResolve";
import { canAddStarter, matchedFormation, POSITIONS, type Position, type PositionCounts } from "../lib/formations";
import { Badge, CARD_TONE_CLASSES, PositionBadge, Row, SignalBadge, TeamCrest, cardTone } from "./ui";
import { budgetTone, fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { useModalOpenTracking } from "../lib/modalOpenTracker";
import PlayerCompareModal from "./PlayerCompareModal";
import { IconActionBank, IconActionField, IconActionSwap, IconActionTrash } from "./icons";

const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const MAX_SQUAD_SIZE = 17;
// Wie lange die kurze "Gespeichert"-Anzeige nach einem erfolgreichen
// Auto-Save sichtbar bleibt, bevor sie automatisch verschwindet. Fehler
// nutzen diesen Timer NICHT - die bleiben stehen, bis der Nutzer etwas
// tut (User-Feedback f462d415: "ausser es gibt beim Schreiben einen
// Fehler der sollte angezeigt werden").
const SAVE_INDICATOR_DISMISS_MS = 2500;
// Wie lange nach dem letzten Tastendruck in der Notiz gewartet wird, bevor
// automatisch gespeichert wird - verhindert einen Firestore-Write pro
// Zeichen (User-Feedback f462d415, "wirkliches Auto-Save").
const NOTE_SAVE_DEBOUNCE_MS = 800;

type SaveStatus = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };

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
  const q = normalizeSearchText(query);
  return scoreReplacementPool(alleSpieler, target)
    .filter((p) => normalizeSearchText(p.name).includes(q))
    .slice(0, 20);
}

// Positionsuebergreifende Namenssuche fuer den generischen Add-Dialog
// (kein presetPosition) - die Position kommt beim Hinzufuegen vom gewaehlten
// Spieler selbst, nicht von einer vorher getroffenen Auswahl. Behaelt den
// Frei/Eigener-Kader-Owner-Filter aus scoreReplacementPool() bei.
function searchAnyPosition(alleSpieler: AlleSpielerRow[], excludePlayerId: string | undefined, query: string) {
  const q = normalizeSearchText(query);
  return alleSpieler
    .filter((p) => p.player_id !== excludePlayerId && (p.owner === "Frei" || p.owner === "Eigener Kader"))
    .filter((p) => normalizeSearchText(p.name).includes(q))
    .slice(0, 20);
}

export default function WunschkaderTab({
  data,
  wunschkader,
  onSaved,
}: {
  data: DashboardSnapshot;
  wunschkader: { targets: RawWunschkaderTarget[] };
  onSaved: (targets: RawWunschkaderTarget[]) => void;
}) {
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (wunschkader.targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
  // Immer der aktuellste editState-Stand, synchron waehrend des Renders
  // gepflegt (kein useEffect) - Grundlage fuer den debounced Notiz-Save
  // unten, der bei Feuern NICHT den zum Aufrufzeitpunkt eingefangenen
  // (potenziell veralteten) Stand schreiben darf, sondern immer den
  // neuesten (Review-Fund: ein spaeterer Sofort-Save (Bank-Toggle/Entfernen/
  // Tauschen) innerhalb der 800ms-Debounce-Zeit wurde durch den verspaetet
  // feuernden Notiz-Save wieder ueberschrieben - stale write).
  const latestEditStateRef = useRef(editState);
  latestEditStateRef.current = editState;
  const [selected, setSelected] = useState<EditTarget | null>(null);
  const [addDialog, setAddDialog] = useState<{ presetPosition: Position | null } | null>(null);

  // Planungsmodus: Auto-Save wird fuer die Dauer der Session ausgesetzt,
  // Aenderungen werden erst per commitSimulation()/discardSimulation() am
  // Ende gespeichert oder verworfen. simulationModeRef ist noetig, weil ein
  // bereits laufender Notiz-Debounce-Timer (debouncedSaveTargets) beim
  // Fristablauf den AKTUELLEN Modus sehen muss, nicht den zum Zeitpunkt des
  // Timer-Starts eingefangenen - gleiches Muster wie latestEditStateRef oben.
  const [simulationMode, setSimulationMode] = useState(false);
  const simulationModeRef = useRef(false);
  simulationModeRef.current = simulationMode;
  const [baseline, setBaseline] = useState<EditTarget[] | null>(null);
  const [pendingChangeCount, setPendingChangeCount] = useState(0);

  const alleSpieler = useMemo(
    () => buildAlleSpielerRows(data.players, data.own_squad_ids, data.owned_by, data.calibration),
    [data.players, data.own_squad_ids, data.owned_by, data.calibration]
  );
  const thresholds = data.signal_thresholds;
  const liveMae = liveModelMae(data.ml_metrics);
  const liveMae3d = liveModelMae(data.ml_metrics_3d ?? null);

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
        bidHistory: data.bid_premium_history ?? [],
      }),
    [data.players, ownSquadIds, editState, data.own_budget_exact, listingsByPlayerId, data.bid_premium_history]
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

  // Live-Zaehlung pro Position (nur Starter, kein Bank/Backup) - Basis
  // fuer canAddStarter()/matchedFormation() statt einer vorab gewaehlten
  // Formation. Direkt aus byPosition abgeleitet statt eigenstaendig neu
  // ueber editState zu iterieren - eine einzige Quelle fuer "wie viele
  // Starter stehen pro Position".
  const startingCounts: PositionCounts = useMemo(
    () => ({
      Torwart: byPosition.Torwart.length,
      Abwehr: byPosition.Abwehr.length,
      Mittelfeld: byPosition.Mittelfeld.length,
      Sturm: byPosition.Sturm.length,
    }),
    [byPosition]
  );

  const bench = useMemo(() => editState.filter(isBench), [editState]);

  // Geplanter Preis fuer die aktuell geoeffnete Detailansicht - ausserhalb von
  // buildBudgetPlan() (das summiert nur ueber alle Ziele), daher hier per
  // liveBidFor()/plannedPriceFor() (derive.ts) - dieselben Funktionen, die
  // buildBudgetPlan() intern nutzt, damit Kachel-Einzelpreis und Budget-Summe
  // garantiert nie divergieren (Review-Fund 2026-07-29: vorher war der
  // Live-Gebots-Ausdruck hier separat dupliziert). plannedPriceFor() liefert
  // seit dem Final-Review (2026-08-02/03, Minor #3) direkt Preis + Quelle +
  // Stichprobengroesse in einem Objekt zurueck - diese Stelle ruft
  // suggestBid()/isOwn/liveBid NICHT mehr selbst ein zweites Mal auf, um die
  // "(Schätzung)"-Beschriftung abzuleiten (das war das Duplikations-Risiko,
  // das den fehlenden p75>0-Guard erst unbemerkt durchrutschen liess).
  const selectedPlannedPrice = useMemo(() => {
    if (!selected) return { price: null, source: "marketValue" as const, suggestionN: null };
    const computed = resolvedByPlayerId.get(selected.player_id);
    if (!computed) return { price: null, source: "marketValue" as const, suggestionN: null };
    const isOwn = ownSquadIds.has(selected.player_id);
    const liveBid = liveBidFor(selected.player_id, listingsByPlayerId);
    const bidHistory = data.bid_premium_history ?? [];
    return plannedPriceFor(computed, isOwn, liveBid, bidHistory);
  }, [selected, resolvedByPlayerId, listingsByPlayerId, ownSquadIds, data.bid_premium_history]);

  function toggleBench(uid: number) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }

  function removeTarget(uid: number) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }

  function replaceTarget(uid: number, playerId: string) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) =>
      prev.map((t) => {
        if (t._uid !== uid) return t;
        const { note: _note, ...keep } = t;
        return { ...keep, player_id: playerId };
      })
    );
    setSelected(null);
  }

  function updateNote(uid: number, note: string) {
    pendingSaveKind.current = "debounced";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }

  function addTarget(target: { player_id: string; position: Position; role: string }) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => [
      ...prev,
      { player_id: target.player_id, role: target.role, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 },
    ]);
  }

  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ kind: "idle" });

  // Auto-Save macht den expliziten "Speichern"-Moment ueberfluessig - die
  // Erfolgsmeldung darf deshalb nur noch ein kurzer, sich selbst
  // wegraeumender Hinweis sein ("gespeichert reicht", User-Feedback
  // f462d415), keine dauerhafte Statuszeile mehr. Fehler bleiben bewusst
  // stehen (kein Timer in diesem Zweig).
  useEffect(() => {
    if (saveStatus.kind !== "saved") return;
    const timer = setTimeout(() => setSaveStatus({ kind: "idle" }), SAVE_INDICATOR_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [saveStatus]);

  // Monoton steigende Sequenznummer fuer in-flight saveTargets()-Aufrufe -
  // siehe Kommentar in saveTargets() unten.
  const saveSeqRef = useRef(0);

  async function saveTargets(next: EditTarget[]) {
    // Waehrend des Planungsmodus schreibt nichts nach Firestore - weder der
    // Sofort-Pfad (direkter Aufruf aus dem editState-Effect) noch der
    // debounced Notiz-Pfad (debouncedSaveTargets() ruft ebenfalls saveTargets()
    // auf). Ref statt State, damit ein spaet feuernder Debounce-Timer den
    // aktuellen Modus sieht.
    if (simulationModeRef.current) return;
    // Absicherung gegen die einmalige Migration (migrate_wunschkader_player_ids.py):
    // solange die noch nicht gegen den aktuellen Firestore-Wunschkader-Doc
    // gelaufen ist, kann _build_wunschkader_targets() (dashboard_export.py)
    // Ziele ohne player_id durchreichen (nur stderr-Warnung, kein Datenverlust
    // serverseitig). Ein Save von hier aus wuerde mit merge:true das gesamte
    // targets-Array ersetzen und damit die name-Felder unwiderruflich
    // wegwerfen, die das Migrationsskript zum Aufloesen braucht - deshalb
    // lieber hart blockieren als stillschweigend Daten verlieren.
    if (next.some((t) => !t.player_id)) {
      setSaveStatus({
        kind: "error",
        message:
          "Speichern blockiert: mindestens ein Ziel hat keine player_id (Migration noch nicht gelaufen?) — Firestore-Konsole pruefen.",
      });
      return;
    }
    // Sequenznummer VOR dem await einfangen - falls waehrend dieses Writes
    // (Netzwerk-Latenz) bereits ein neuerer saveTargets()-Aufruf gestartet
    // wurde, darf dieser hier bei Abschluss NICHT mehr onSaved()/setSaveStatus()
    // aufrufen: ein langsamerer, aelterer Write, der nach einem schnelleren,
    // neueren Write ankommt, wuerde sonst veraltete Daten an den Parent
    // durchreichen (Review-Fund, Important #3) bzw. eine erfolgreiche neuere
    // Meldung mit dem Fehler/Erfolg des aelteren Writes uebermalen.
    const seq = ++saveSeqRef.current;
    setSaveStatus({ kind: "saving" });
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = next.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, updated_at: updatedAt }, { merge: true });
      if (seq !== saveSeqRef.current) return;
      onSaved(targets);
      setSaveStatus({ kind: "saved" });
    } catch (err) {
      if (seq !== saveSeqRef.current) return;
      setSaveStatus({ kind: "error", message: "Fehler beim Speichern: " + (err as Error).message });
    }
  }

  // Merkt sich, WELCHE Art Save nach der naechsten editState-Aenderung
  // faellig ist: "immediate" fuer diskrete Aktionen (Ziel hinzufuegen/
  // entfernen/tauschen, Bank-Toggle - kein Freitext, darf sofort schreiben),
  // "debounced" fuer die Notiz (Freitext, siehe Task 4). Ein Ref statt
  // State, weil das Setzen synchron VOR dem setEditState()-Aufruf passieren
  // muss und selbst keinen Re-Render braucht. null bedeutet "editState hat
  // sich aus einem anderen Grund geaendert (z.B. initiales Mount) - nicht
  // speichern", verhindert also einen Auto-Save direkt beim Laden der Seite.
  const pendingSaveKind = useRef<"immediate" | "debounced" | null>(null);
  // Liest bei Fristablauf latestEditStateRef.current statt den editState-Stand
  // vom Aufrufzeitpunkt als Argument einzufangen - siehe Kommentar bei
  // latestEditStateRef oben (Review-Fund, Critical #1). Faellt der Timer erst
  // NACH einem inzwischen passierten Sofort-Save, ist das dann nur noch ein
  // harmloser, idempotenter Re-Save desselben (bereits korrekten) Stands statt
  // eines ueberschreibenden Writes mit veralteten Daten.
  const debouncedSaveTargets = useDebouncedCallback(() => {
    saveTargets(latestEditStateRef.current);
  }, NOTE_SAVE_DEBOUNCE_MS);

  useEffect(() => {
    const kind = pendingSaveKind.current;
    if (kind === null) return;
    pendingSaveKind.current = null;
    if (kind === "immediate") {
      saveTargets(editState);
    } else {
      debouncedSaveTargets();
    }
  }, [editState, debouncedSaveTargets]);

  function enterSimulationMode() {
    setBaseline(editState);
    setPendingChangeCount(0);
    simulationModeRef.current = true;
    setSimulationMode(true);
  }

  async function commitSimulation() {
    // Ref MUSS synchron gesetzt werden, nicht nur ueber setSimulationMode(false) -
    // die Ref-Zuweisung "simulationModeRef.current = simulationMode" oben im
    // Funktionskoerper passiert erst beim naechsten Render, saveTargets() wird
    // aber noch VOR diesem Render aufgerufen und wuerde den Guard sonst
    // faelschlich noch aktiv sehen.
    simulationModeRef.current = false;
    setSimulationMode(false);
    await saveTargets(editState);
    setBaseline(null);
  }

  function discardSimulation() {
    // Verhindert, dass der editState-Effect das gleich folgende Zuruecksetzen
    // auf die Baseline als faelligen Save interpretiert (waere durch den
    // saveTargets()-Guard ohnehin harmlos, macht die Absicht aber explizit
    // statt sich auf die Guard-Reihenfolge zu verlassen).
    pendingSaveKind.current = null;
    simulationModeRef.current = false;
    setSimulationMode(false);
    if (baseline) setEditState(baseline);
    setBaseline(null);
  }

  useEffect(() => {
    if (!simulationMode || pendingChangeCount === 0) return;
    function handler(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [simulationMode, pendingChangeCount]);

  const totalCount = editState.length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-600 dark:text-slate-300">
          Formation:{" "}
          <span className="font-medium text-slate-900 dark:text-slate-100">
            {(() => {
              const matched = matchedFormation(startingCounts);
              if (matched) return matched;
              const filled = POSITIONS.reduce((sum, p) => sum + startingCounts[p], 0);
              // "In Startelf verschieben" (toggleBench) prueft die Formations-Machbarkeit
              // nicht - eine ungueltige Kombination (z.B. 2 Torwaerter) kann daher trotz
              // filled>=11 keine Formation matchen. Ohne diese Unterscheidung wuerde
              // "noch nicht komplett" hier faelschlich weitere Ziele nahelegen.
              return filled >= 11
                ? `ungültige Aufstellung (${filled}/11 Spieler inkl. Torwart)`
                : `noch nicht komplett (${filled}/11 Spieler inkl. Torwart)`;
            })()}
          </span>
        </span>
        {totalCount > MAX_SQUAD_SIZE && (
          <Badge tone="warn">
            {totalCount}/{MAX_SQUAD_SIZE} Kadergröße überschritten
          </Badge>
        )}
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        {!simulationMode && (
          <button
            type="button"
            onClick={enterSimulationMode}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Planungsmodus starten
          </button>
        )}
        {simulationMode && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40">
            <span className="font-medium text-amber-800 dark:text-amber-300">
              Planungsmodus aktiv — Änderungen werden erst beim Speichern übernommen
            </span>
            <span className="text-amber-700 dark:text-amber-400">
              {pendingChangeCount} ungespeicherte {pendingChangeCount === 1 ? "Änderung" : "Änderungen"}
            </span>
            <button
              type="button"
              onClick={discardSimulation}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Verwerfen
            </button>
            <button
              type="button"
              onClick={commitSimulation}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
            >
              Speichern
            </button>
          </div>
        )}
        {!simulationMode && saveStatus.kind === "saving" && (
          <span className="text-sm text-slate-500 dark:text-slate-400">Speichere…</span>
        )}
        {!simulationMode && saveStatus.kind === "saved" && (
          <span className="text-sm text-emerald-600 dark:text-emerald-400">✓ Gespeichert</span>
        )}
        {!simulationMode && saveStatus.kind === "error" && (
          <span className="text-sm text-red-600 dark:text-red-400">
            {saveStatus.message}{" "}
            <button type="button" onClick={() => saveTargets(editState)} className="underline hover:no-underline">
              Erneut versuchen
            </button>
          </span>
        )}
      </div>

      {POSITIONS.map((position) => {
        const targets = byPosition[position];
        const canAdd = canAddStarter(startingCounts, position);
        return (
          <div key={position} className="mb-6">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {position} · {targets.length} belegt
            </div>
            <motion.div
              className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
              variants={staggerContainerVariants}
              initial="initial"
              animate="animate"
            >
              <AnimatePresence>
                {targets.map((t) => {
                  const computed = resolvedByPlayerId.get(t.player_id)!;
                  return (
                    <motion.div
                      key={t._uid}
                      layoutId={`wunschkader-${t._uid}`}
                      variants={staggerItemVariants}
                      initial="initial"
                      animate="animate"
                      exit="exit"
                    >
                      <TargetCard
                        target={t}
                        computed={computed}
                        thresholds={thresholds}
                        clubCount={computed.team_name ? clubCounts[computed.team_name] ?? 0 : 0}
                        onSelect={() => setSelected(t)}
                      />
                    </motion.div>
                  );
                })}
              </AnimatePresence>
              {canAdd && <EmptySlotCard onClick={() => setAddDialog({ presetPosition: position })} />}
            </motion.div>
          </div>
        );
      })}

      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Bank ({bench.length})
        </div>
        <motion.div
          className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
          variants={staggerContainerVariants}
          initial="initial"
          animate="animate"
        >
          <AnimatePresence>
            {bench.map((t) => {
              const computed = resolvedByPlayerId.get(t.player_id)!;
              return (
                <motion.div
                  key={t._uid}
                  layoutId={`wunschkader-${t._uid}`}
                  variants={staggerItemVariants}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                >
                  <TargetCard target={t} computed={computed} thresholds={thresholds} clubCount={0} onSelect={() => setSelected(t)} />
                </motion.div>
              );
            })}
          </AnimatePresence>
          <EmptySlotCard onClick={() => setAddDialog({ presetPosition: null })} />
        </motion.div>
      </div>

      <BudgetPlanCard plan={liveBudgetPlan} />

      {selected && (
        <DetailModal
          target={selected}
          computed={resolvedByPlayerId.get(selected.player_id)!}
          plannedPrice={selectedPlannedPrice}
          thresholds={thresholds}
          mae={liveMae}
          mae3d={liveMae3d}
          alleSpieler={alleSpieler}
          players={data.players}
          calibration={data.calibration}
          ownSquadIds={ownSquadIds}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(playerId) => replaceTarget(selected._uid, playerId)}
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
        <PositionBadge position={computed.position} />
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
  mae,
  mae3d,
  alleSpieler,
  players,
  calibration,
  ownSquadIds,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
  onNoteChange,
}: {
  target: EditTarget;
  computed: ResolvedTarget;
  plannedPrice: PlannedPrice;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  mae3d: number | null;
  alleSpieler: AlleSpielerRow[];
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  ownSquadIds: Set<string>;
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (playerId: string) => void;
  onNoteChange: (note: string) => void;
}) {
  const [wechselOpen, setWechselOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [compareWith, setCompareWith] = useState<AlleSpielerRow | null>(null);

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
    <>
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={computed.team_name} />
            <PositionBadge position={computed.position} />
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
          <Row label="Verfügbarkeit">{computed.status}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
          <Row label="Prognose 1T">
            <span className={trendClass(players[target.player_id]?.ml_prediction ?? null)}>
              {trendArrow(players[target.player_id]?.ml_prediction ?? null, ML_PREDICTION_THRESHOLDS)}{" "}
              {fmtSigned(players[target.player_id]?.ml_prediction ?? null)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          <Row label="Prognose 3T">
            <span className={trendClass(players[target.player_id]?.ml_prediction_3d ?? null)}>
              {trendArrow(players[target.player_id]?.ml_prediction_3d ?? null, ML_PREDICTION_3D_THRESHOLDS)}{" "}
              {fmtSigned(players[target.player_id]?.ml_prediction_3d ?? null)}
            </span>
            {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
          </Row>
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
          {ownSquadIds.has(target.player_id) ? (
            <Row label="Tatsächlicher Kaufpreis">
              {players[target.player_id]?.purchase_price != null
                ? fmtNum(players[target.player_id].purchase_price)
                : <span className="text-slate-400 dark:text-slate-500">n/v</span>}
            </Row>
          ) : (
            <Row label="Geplanter Preis">
              {fmtNum(plannedPrice.price)}
              {plannedPrice.source === "estimate" && plannedPrice.suggestionN !== null && plannedPrice.suggestionN < MIN_N_FOR_PERCENTILE_SPREAD ? (
                <span className="text-slate-400 dark:text-slate-500"> (geringe Datenbasis, n={plannedPrice.suggestionN})</span>
              ) : plannedPrice.source === "estimate" ? (
                <span className="text-slate-400 dark:text-slate-500"> (Schätzung)</span>
              ) : null}
            </Row>
          )}
          <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Verein">{computed.team_name ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Schnitt">{fmtNum(computed.average_points)}</Row>
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
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isBench(target) ? (
              <>
                <IconActionField className="h-4 w-4" />
                Startelf
              </>
            ) : (
              <>
                <IconActionBank className="h-4 w-4" />
                Bank
              </>
            )}
          </button>
          <button
            type="button"
            onClick={() => setWechselOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <IconActionSwap className="h-4 w-4" />
            Wechsel
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="flex items-center gap-1.5 rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
          >
            <IconActionTrash className="h-4 w-4" />
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
                    onClick={() => setCompareWith(s)}
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
                    <div
                      key={s.player_id}
                      className="flex items-center overflow-hidden rounded-full border border-slate-300 dark:border-slate-700"
                    >
                      <button
                        type="button"
                        onClick={() => onReplace(s.player_id)}
                        className="px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.average_points)})
                      </button>
                      <button
                        type="button"
                        onClick={() => setCompareWith(s)}
                        title="Vergleichen"
                        className="border-l border-slate-300 px-2 py-1 text-xs text-brand-600 hover:bg-slate-100 dark:border-slate-700 dark:text-brand-400 dark:hover:bg-slate-800"
                      >
                        Vergleichen
                      </button>
                    </div>
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
    <AnimatePresence>
      {compareWith && (
        <PlayerCompareModal
          playerIdA={target.player_id}
          playerIdB={compareWith.player_id}
          players={players}
          calibration={calibration}
          thresholds={thresholds}
          onSelectSide={(playerId) => {
            if (playerId !== target.player_id) onReplace(playerId);
            setCompareWith(null);
          }}
          onClose={() => setCompareWith(null)}
        />
      )}
    </AnimatePresence>
    </>
  );
}

function BudgetPlanCard({ plan }: { plan: BudgetPlan }) {
  const remainingTone = plan.remaining >= 0 ? "text-brand-600 dark:text-brand-400" : "text-red-600 dark:text-red-400";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-50">Budget-Planung</h3>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Kapital</div>
          <div className={`font-medium tabular-nums ${budgetTone(plan.cash)}`}>{fmtNum(plan.cash)}</div>
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
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Eingeplant enthält für Ziele ohne eigenes Live-Gebot eine p75-Aufschlagsschätzung aus ähnlichen historischen
        Käufen (siehe Detailansicht).
      </p>
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

  const results = search.trim()
    ? presetPosition
      ? searchReplacementPool(alleSpieler, { position: presetPosition, market_value: 0, average_points: 0 }, search.trim())
      : searchAnyPosition(alleSpieler, undefined, search.trim())
    : [];

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    onAdd({
      player_id: selected.player_id,
      position: presetPosition ?? (selected.position as Position),
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
          value={selected ? selected.name : search}
          onChange={(e) => {
            setSelected(null);
            setSearch(e.target.value);
          }}
          placeholder="Spieler suchen…"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {selected && (
          <p className="text-sm text-brand-700 dark:text-brand-400">
            ✓ Ausgewählt: {selected.name} ({fmtNum(selected.market_value)})
          </p>
        )}
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
                  className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {p.name} ({fmtNum(p.market_value)}, Ø{fmtNum(p.average_points)})
                </button>
              ))
            ) : (
              <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                Keine Treffer (freie Spieler/eigener Kader{presetPosition ? `, Position ${presetPosition}` : ""}).
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
