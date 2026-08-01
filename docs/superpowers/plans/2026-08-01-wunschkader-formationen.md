# Wunschkader alle 10 Formationen + live abgeleitete Positions-Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die starre 4-Formationen-Combobox in Wunschkader durch alle 10 recherchierten, tatsächlich in Kickbase erlaubten Formationen ersetzen — Positions-Add-Buttons werden live aus der tatsächlichen Ziel-Belegung abgeleitet statt aus einer vorab gewählten Formation, `wunschkader_formation` wird komplett aus dem Stack entfernt (Backend, Contract-Test, `types.ts`).

**Architecture:** `formations.ts` bekommt alle 10 Formationen + zwei neue reine Funktionen (`canAddStarter`/`matchedFormation`) statt der bisherigen `slotsFor()`/festen Formation-Auswahl. `WunschkaderTab.tsx` verliert die Combobox, zeigt stattdessen live pro Position höchstens einen Add-Button (feasibility-geprüft) und eine read-only Formations-Anzeige. Backend/Contract-Test/`types.ts` verlieren `wunschkader_formation` vollständig — die Formation ist ab jetzt eine reine Frontend-Ableitung, nie mehr gespeichert.

**Tech Stack:** React + TypeScript (Vite) fürs Frontend, Python 3.11 fürs Backend, kein Test-Framework im Frontend (nur `tsc` + manuelle Browser-Verifikation), `unittest` für Backend-Tests.

## Global Constraints

- **Kein `npm install` im Haupt-Checkout** (Windows-DrvFs-Mount) — `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` ist der einzige Frontend-Verifikationsbefehl.
- **Kein Test-Framework im Frontend** — Verifikation per `tsc --noEmit` + der letzte Task zusätzlich per manueller Browser-Prüfung.
- **Backend-Tests müssen nach Task 3 weiterhin grün sein**: `python3 -m unittest discover -s tests` — Task 3 ändert selbst zwei bestehende Backend-Tests (Contract-Test-Assertions), das ist beabsichtigt, kein neuer Fehler.
- **Push auf `main` erlaubt, aber nur wenn direkt vorher alle Tests grün sind** (Backend-Suite + `tsc --noEmit`).
- **Keine Migration bestehender Firestore-Daten nötig** — die neuen 10 Formationen sind in jeder Position großzügiger als die alten 4 (siehe Spec, Korrektheits-Argument), jede bisher gespeicherte Ziel-Belegung bleibt automatisch gültig. Ein eventuell noch in `wunschkader/current` gespeicherter `formation`-Schlüssel wird einfach nie mehr gelesen — keine Löschung des Firestore-Feldes nötig.
- **Zwei andere, bereits geschriebene aber NOCH NICHT umgesetzte Pläne berühren dieselben Dateien**:
  - `docs/superpowers/plans/2026-07-31-ml-horizonte-frontend-anzeige.md`-Nachfolger `2026-08-01-ml-horizonte-frontend-anzeige.md` ändert `WunschkaderTab.tsx`s Detail-Modal (Prognose-1T/3T-Zeilen) — andere Zeilen als dieser Plan, kein Konflikt erwartet, aber vor Ausführung gegenchecken, falls beide zwischenzeitlich umgesetzt wurden.
  - `docs/superpowers/plans/2026-08-01-eigenes-team-wunschkader-live-sync.md` ändert `WunschkaderTab.tsx`s Props (`data`/`wunschkader`/`onSaved` für `targets`) UND `App.tsx`. Dieser Plan hier geht vom AKTUELLEN, unveränderten Code aus (keiner der beiden Pläne ist zum Zeitpunkt dieses Plans umgesetzt). **Falls der Live-Sync-Plan ZUERST ausgeführt wird**: `WunschkaderTab`s Signatur hat dann bereits `wunschkader`/`onSaved`-Props für `targets` (nicht `formation`, das wurde in jenem Plan bewusst rausgehalten, siehe dessen Spec) — Task 2 dieses Plans muss dann `wunschkader.targets`/den bereits vorhandenen `onSaved`-Aufruf respektieren statt die in Task 2 unten gezeigten "Alt:"-Codeblöcke 1:1 zu erwarten. Vor Ausführung immer den tatsächlichen Ist-Stand von `WunschkaderTab.tsx` lesen, nicht blind die "Alt:"-Blöcke unten annehmen.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/lib/formations.ts` | Alle 10 Formationen, `canAddStarter()`/`matchedFormation()` statt `slotsFor()`/`isFormationKey()`/`DEFAULT_FORMATION` |
| `frontend/src/components/WunschkaderTab.tsx` | Combobox raus, live Add-Button-Logik pro Position, read-only Formations-Anzeige, `formation` nicht mehr Teil des Firestore-Writes |
| `src/dashboard_export.py` | `wunschkader_formation` aus `export()`/`_assemble_snapshot()` entfernt |
| `tests/test_dashboard_export.py` | Contract-Test (`EXPECTED_KEYS` + Testaufruf) an das neue Key-Set angepasst |
| `frontend/src/types.ts` | `wunschkader_formation`-Feld aus `DashboardSnapshot` entfernt |

---

## Task 1: formations.ts — alle 10 Formationen + Live-Algorithmus

**Files:**
- Modify: `frontend/src/lib/formations.ts`

**Interfaces:**
- Consumes: nichts.
- Produces: `FORMATIONS` (10 Einträge), `FormationKey`, `FORMATION_KEYS` (unverändert exportiert, nur mehr Einträge), neuer Typ `PositionCounts = Record<Position, number>`, neue Funktionen `canAddStarter(counts: PositionCounts, position: Position): boolean` und `matchedFormation(counts: PositionCounts): FormationKey | null`. **Entfernt**: `slotsFor()`, `isFormationKey()`, `DEFAULT_FORMATION` — Task 2 darf diese NICHT mehr importieren.

- [ ] **Step 1: Datei komplett ersetzen**

Alt (komplette aktuelle Datei):
```typescript
// Formations-Notation Verteidigung-Mittelfeld-Sturm (Torwart immer 1,
// nicht Teil der Notation) - Standardkonvention im deutschen Fussball.
export const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"] as const;
export type Position = (typeof POSITIONS)[number];

export interface FormationSlots {
  Torwart: number;
  Abwehr: number;
  Mittelfeld: number;
  Sturm: number;
}

export const FORMATIONS = {
  "3-4-3": { Torwart: 1, Abwehr: 3, Mittelfeld: 4, Sturm: 3 },
  "4-3-3": { Torwart: 1, Abwehr: 4, Mittelfeld: 3, Sturm: 3 },
  "3-5-2": { Torwart: 1, Abwehr: 3, Mittelfeld: 5, Sturm: 2 },
  "4-4-2": { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 },
} as const satisfies Record<string, FormationSlots>;

export type FormationKey = keyof typeof FORMATIONS;

export const FORMATION_KEYS = Object.keys(FORMATIONS) as FormationKey[];

export const DEFAULT_FORMATION: FormationKey = "3-4-3";

export function isFormationKey(value: string | null | undefined): value is FormationKey {
  return !!value && value in FORMATIONS;
}

export function slotsFor(formation: string | null | undefined, position: Position): number {
  const key = isFormationKey(formation) ? formation : DEFAULT_FORMATION;
  return FORMATIONS[key][position];
}
```

Neu (komplette neue Datei):
```typescript
// Formations-Notation Verteidigung-Mittelfeld-Sturm (Torwart immer 1,
// nicht Teil der Notation) - Standardkonvention im deutschen Fussball.
export const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"] as const;
export type Position = (typeof POSITIONS)[number];

export interface FormationSlots {
  Torwart: number;
  Abwehr: number;
  Mittelfeld: number;
  Sturm: number;
}

// Alle 10 in Kickbase erlaubten Formationen (Recherche 2026-08-01, siehe
// docs/superpowers/specs/2026-08-01-wunschkader-formationen-design.md fuer
// Quellen - Drittquelle, keine offizielle Kickbase-Dokumentation, aber
// intern konsistent: jede Formation summiert exakt auf 10 Feldspieler +
// 1 Torwart, passt zum bestaetigten Minimum "mind. 3 Abwehr/2 Mittelfeld/
// 1 Sturm").
export const FORMATIONS = {
  "3-4-3": { Torwart: 1, Abwehr: 3, Mittelfeld: 4, Sturm: 3 },
  "3-5-2": { Torwart: 1, Abwehr: 3, Mittelfeld: 5, Sturm: 2 },
  "3-6-1": { Torwart: 1, Abwehr: 3, Mittelfeld: 6, Sturm: 1 },
  "4-2-4": { Torwart: 1, Abwehr: 4, Mittelfeld: 2, Sturm: 4 },
  "4-3-3": { Torwart: 1, Abwehr: 4, Mittelfeld: 3, Sturm: 3 },
  "4-4-2": { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 },
  "4-5-1": { Torwart: 1, Abwehr: 4, Mittelfeld: 5, Sturm: 1 },
  "5-2-3": { Torwart: 1, Abwehr: 5, Mittelfeld: 2, Sturm: 3 },
  "5-3-2": { Torwart: 1, Abwehr: 5, Mittelfeld: 3, Sturm: 2 },
  "5-4-1": { Torwart: 1, Abwehr: 5, Mittelfeld: 4, Sturm: 1 },
} as const satisfies Record<string, FormationSlots>;

export type FormationKey = keyof typeof FORMATIONS;

export const FORMATION_KEYS = Object.keys(FORMATIONS) as FormationKey[];

export type PositionCounts = Record<Position, number>;

// True, wenn mindestens eine der 10 Formationen mit den aktuellen
// Zaehlungen PLUS einem weiteren Starter in `position` noch erreichbar
// ist (in jeder anderen Position muss die Formation mindestens die
// aktuelle Zaehlung zulassen, in `position` mindestens Zaehlung+1) -
// ersetzt die alte starre Combobox-Auswahl (ehemals slotsFor()).
export function canAddStarter(counts: PositionCounts, position: Position): boolean {
  return FORMATION_KEYS.some((key) => {
    const f = FORMATIONS[key];
    return POSITIONS.every((p) => f[p] >= counts[p] + (p === position ? 1 : 0));
  });
}

// Liefert den Namen der exakt passenden Formation, falls die Zaehlungen
// GENAU einer der 10 entsprechen - sonst null (Belegung noch nicht
// komplett). Torwart ist in jeder Formation fix 1, faellt automatisch mit
// rein. Jede ueber canAddStarter() erreichte 11er-Belegung (inkl.
// Torwart) entspricht zwangslaeufig genau einer Formation (Teilmenge +
// gleiche Summe = Gleichheit) - kein Fall, in dem hier unerwartet null
// zurueckkaeme, sobald die Summe 11 erreicht.
export function matchedFormation(counts: PositionCounts): FormationKey | null {
  return FORMATION_KEYS.find((key) => POSITIONS.every((p) => FORMATIONS[key][p] === counts[p])) ?? null;
}
```

- [ ] **Step 2: `tsc` — Fehler in `WunschkaderTab.tsx` sind hier erwartet**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: Fehler der Form `Module '"../lib/formations"' has no exported member 'slotsFor'/'isFormationKey'/'DEFAULT_FORMATION'.` in `WunschkaderTab.tsx`. **Das ist erwartet** — behoben in Task 2. `formations.ts` selbst und `MlGenauigkeitTab.tsx` (nutzt nur `POSITIONS`, unverändert) dürfen KEINEN Fehler zeigen.

- [ ] **Step 3: Commit**

```bash
cd /workspace/work
python3 -m unittest discover -s tests
git add frontend/src/lib/formations.ts
git commit -m "formations.ts: alle 10 in Kickbase erlaubten Formationen + canAddStarter()/matchedFormation() statt starrer slotsFor()-Auswahl"
```

---

## Task 2: WunschkaderTab.tsx — Combobox raus, live Add-Buttons, read-only Anzeige

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `canAddStarter`, `matchedFormation`, `PositionCounts` (Task 1).
- Produces: nichts, das andere Tasks brauchen.

**Wichtig**: vor Ausführung den tatsächlichen Ist-Stand von `WunschkaderTab.tsx` lesen (siehe Global Constraints — falls der Live-Sync-Plan bereits umgesetzt wurde, existieren dort schon `wunschkader`/`onSaved`-Props für `targets`, die "Alt:"-Blöcke unten passen dann nicht mehr 1:1 auf `data.wunschkader_targets`).

- [ ] **Step 1: Import ersetzen**

Alt: `import { DEFAULT_FORMATION, FORMATION_KEYS, type FormationKey, POSITIONS, type Position, isFormationKey, slotsFor } from "../lib/formations";`

Neu: `import { canAddStarter, matchedFormation, POSITIONS, type Position, type PositionCounts } from "../lib/formations";`

- [ ] **Step 2: `formation`-State entfernen**

Alt:
```typescript
export default function WunschkaderTab({ data }: { data: DashboardSnapshot }) {
  const [formation, setFormation] = useState<FormationKey>(
    isFormationKey(data.wunschkader_formation) ? data.wunschkader_formation : DEFAULT_FORMATION
  );
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (data.wunschkader_targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
```

Neu:
```typescript
export default function WunschkaderTab({ data }: { data: DashboardSnapshot }) {
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (data.wunschkader_targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
```

- [ ] **Step 3: `startingCounts` aus dem bestehenden `byPosition` ableiten**

Alt:
```typescript
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
```

Neu:
```typescript
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
```

- [ ] **Step 4: `handleSave()` — `formation` nicht mehr Teil des Firestore-Writes**

Alt:
```typescript
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
```

Neu:
```typescript
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, updated_at: updatedAt }, { merge: true });
```

(Der restliche `handleSave()`-Text/Bestätigungsmeldung bleibt unverändert — das ist Sache des separaten Live-Sync-Plans, nicht dieses Tasks.)

- [ ] **Step 5: Combobox durch read-only Formations-Anzeige ersetzen**

Alt:
```typescript
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
```

Neu:
```typescript
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-600 dark:text-slate-300">
          Formation:{" "}
          <span className="font-medium text-slate-900 dark:text-slate-100">
            {matchedFormation(startingCounts) ??
              `noch nicht komplett (${POSITIONS.reduce((sum, p) => sum + startingCounts[p], 0)}/11 Feldspieler)`}
          </span>
        </span>
        {totalCount > MAX_SQUAD_SIZE && (
          <Badge tone="warn">
            {totalCount}/{MAX_SQUAD_SIZE} Kadergröße überschritten
          </Badge>
        )}
      </div>
```

- [ ] **Step 6: Positions-Rendering — höchstens ein Add-Button statt N fester Slots**

Alt:
```typescript
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
```

Neu:
```typescript
      {POSITIONS.map((position) => {
        const targets = byPosition[position];
        const canAdd = canAddStarter(startingCounts, position);
        return (
          <div key={position} className="mb-6">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {position} · {targets.length} belegt
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
              {canAdd && <EmptySlotCard onClick={() => setAddDialog({ presetPosition: position })} />}
            </div>
          </div>
        );
      })}
```

- [ ] **Step 7: `tsc` — diese Datei muss jetzt 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: 0 Fehler im gesamten Projekt (kein anderer Task hängt von `formations.ts`s alten Exporten ab — `WunschkaderTab.tsx` war die einzige betroffene Datei).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: Formation-Combobox durch live abgeleitete Positions-Buttons + read-only Formations-Anzeige ersetzt"
```

---

## Task 3: Backend + Contract-Test + types.ts — `wunschkader_formation` entfernen

**Files:**
- Modify: `src/dashboard_export.py`
- Modify: `tests/test_dashboard_export.py`
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Consumes: nichts aus Task 1/2 (unabhängige Backend-/Typ-Änderung).
- Produces: nichts, das andere Tasks brauchen.

- [ ] **Step 1: `export()`s `_assemble_snapshot(...)`-Aufruf**

Alt (`src/dashboard_export.py`):
```python
        transfermarkt_listings=_build_transfermarkt_listings(market_listings),
        own_squad_ids=[r["player_id"] for r in own_squad],
        owned_by=heavy["owned_by"],
        wunschkader_targets=wunschkader_targets,
        wunschkader_formation=wunschkader_config.get("formation") if wunschkader_config else None,
        ligaanalyse_rows=ligaanalyse_result["rows"],
        position_need=ligaanalyse_result["position_need"],
    )
```

Neu:
```python
        transfermarkt_listings=_build_transfermarkt_listings(market_listings),
        own_squad_ids=[r["player_id"] for r in own_squad],
        owned_by=heavy["owned_by"],
        wunschkader_targets=wunschkader_targets,
        ligaanalyse_rows=ligaanalyse_result["rows"],
        position_need=ligaanalyse_result["position_need"],
    )
```

(`wunschkader_config` bleibt bestehen — wird weiterhin für `wunschkader_targets` gebraucht, siehe `_build_wunschkader_targets(wunschkader_config, players_map)` direkt darüber.)

- [ ] **Step 2: `_assemble_snapshot()`-Signatur**

Alt:
```python
def _assemble_snapshot(
    fetched_at,
    generated_at,
    own_available_budget,
    own_budget_exact,
    calibration,
    ml_metrics,
    ml_accuracy_trend,
    ml_metrics_3d,
    ml_accuracy_trend_3d,
    players_map,
    bid_premium_history,
    bid_premium_outcome_counts,
    transfermarkt_listings,
    own_squad_ids,
    owned_by,
    wunschkader_targets,
    wunschkader_formation,
    ligaanalyse_rows,
    position_need,
) -> dict:
```

Neu:
```python
def _assemble_snapshot(
    fetched_at,
    generated_at,
    own_available_budget,
    own_budget_exact,
    calibration,
    ml_metrics,
    ml_accuracy_trend,
    ml_metrics_3d,
    ml_accuracy_trend_3d,
    players_map,
    bid_premium_history,
    bid_premium_outcome_counts,
    transfermarkt_listings,
    own_squad_ids,
    owned_by,
    wunschkader_targets,
    ligaanalyse_rows,
    position_need,
) -> dict:
```

- [ ] **Step 3: `_assemble_snapshot()`s zurückgegebenes Dict**

Alt:
```python
        "own_squad_ids": own_squad_ids,
        "owned_by": owned_by,
        "wunschkader_targets": wunschkader_targets,
        "wunschkader_formation": wunschkader_formation,
        "ligaanalyse": ligaanalyse_rows,
        "position_need": position_need,
    }
```

Neu:
```python
        "own_squad_ids": own_squad_ids,
        "owned_by": owned_by,
        "wunschkader_targets": wunschkader_targets,
        "ligaanalyse": ligaanalyse_rows,
        "position_need": position_need,
    }
```

- [ ] **Step 4: Contract-Test `EXPECTED_KEYS` + Testaufruf**

Alt (`tests/test_dashboard_export.py`):
```python
    EXPECTED_KEYS = {
        "fetched_at", "generated_at", "own_available_budget", "own_budget_exact", "calibration",
        "ml_metrics", "ml_accuracy_trend", "ml_metrics_3d", "ml_accuracy_trend_3d", "signal_thresholds", "players",
        "bid_premium_history", "bid_premium_outcome_counts", "transfermarkt_listings",
        "own_squad_ids", "owned_by", "wunschkader_targets", "wunschkader_formation",
        "ligaanalyse", "position_need",
    }

    def test_returns_exactly_the_expected_top_level_keys(self):
        result = _assemble_snapshot(
            fetched_at="2026-07-30T00:00:00Z",
            generated_at="2026-07-30T21:07:00Z",
            own_available_budget=1,
            own_budget_exact=1,
            calibration=None,
            ml_metrics=None,
            ml_accuracy_trend=None,
            ml_metrics_3d=None,
            ml_accuracy_trend_3d=None,
            players_map={},
            bid_premium_history=[],
            bid_premium_outcome_counts={},
            transfermarkt_listings=[],
            own_squad_ids=[],
            owned_by={},
            wunschkader_targets=[],
            wunschkader_formation=None,
            ligaanalyse_rows=[],
            position_need={},
        )

        self.assertEqual(set(result.keys()), self.EXPECTED_KEYS)
```

Neu:
```python
    EXPECTED_KEYS = {
        "fetched_at", "generated_at", "own_available_budget", "own_budget_exact", "calibration",
        "ml_metrics", "ml_accuracy_trend", "ml_metrics_3d", "ml_accuracy_trend_3d", "signal_thresholds", "players",
        "bid_premium_history", "bid_premium_outcome_counts", "transfermarkt_listings",
        "own_squad_ids", "owned_by", "wunschkader_targets",
        "ligaanalyse", "position_need",
    }

    def test_returns_exactly_the_expected_top_level_keys(self):
        result = _assemble_snapshot(
            fetched_at="2026-07-30T00:00:00Z",
            generated_at="2026-07-30T21:07:00Z",
            own_available_budget=1,
            own_budget_exact=1,
            calibration=None,
            ml_metrics=None,
            ml_accuracy_trend=None,
            ml_metrics_3d=None,
            ml_accuracy_trend_3d=None,
            players_map={},
            bid_premium_history=[],
            bid_premium_outcome_counts={},
            transfermarkt_listings=[],
            own_squad_ids=[],
            owned_by={},
            wunschkader_targets=[],
            ligaanalyse_rows=[],
            position_need={},
        )

        self.assertEqual(set(result.keys()), self.EXPECTED_KEYS)
```

- [ ] **Step 5: `types.ts`**

Alt (`frontend/src/types.ts`):
```typescript
  wunschkader_targets: RawWunschkaderTarget[];
  wunschkader_formation: string | null;
  ligaanalyse: LigaanalyseRow[];
```

Neu:
```typescript
  wunschkader_targets: RawWunschkaderTarget[];
  ligaanalyse: LigaanalyseRow[];
```

- [ ] **Step 6: Backend-Tests + `tsc` — beide müssen 0 Fehler/Failures zeigen**

Run:
```bash
python3 -m unittest discover -s tests
node frontend/node_modules/typescript/bin/tsc -p frontend/tsconfig.json --noEmit
```

Expected: Backend-Suite komplett grün (inkl. der angepassten `AssembleSnapshotContractTests`), `tsc` 0 Ausgabe.

- [ ] **Step 7: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py frontend/src/types.ts
git commit -m "wunschkader_formation komplett aus dem Stack entfernt (Backend, Contract-Test, types.ts) - Formation ist jetzt reine Frontend-Ableitung"
```

---

## Task 4: Abschluss — Verifikation, Feedback-Item, HANDOFF.md, Push

**Files:**
- Modify: `HANDOFF.md` (neuer Completed-Eintrag)
- Keine Code-Änderung sonst.

**Interfaces:**
- Consumes: alle vorherigen Tasks.

- [ ] **Step 1: Volle Verifikation**

```bash
cd /workspace/work
node frontend/node_modules/typescript/bin/tsc -p frontend/tsconfig.json --noEmit
python3 -m unittest discover -s tests
```

Expected: beides ohne Fehler.

- [ ] **Step 2: Manuelle Live-Verifikation im Browser**

`cd frontend && npm run dev` (KEIN `npm install` davor) und im Wunschkader-Tab:

1. Ausgehend von einem leeren/kleinen Wunschkader: pro Position Ziele hinzufügen. Formations-Anzeige zeigt "noch nicht komplett (X/11 Feldspieler)".
2. Sturm auf 4 Ziele auffüllen (Maximum über alle 10 Formationen, z.B. via 4-2-4/5-2-3) — Add-Button bei Sturm muss danach verschwinden, Add-Buttons bei Abwehr/Mittelfeld/Torwart bleiben (falls noch nicht bei ihrem jeweiligen Maximum) sichtbar, solange insgesamt noch keine 11 Feldspieler stehen.
3. Insgesamt 11 Starter erreichen (1 Torwart + 10 Feldspieler in einer der 10 gültigen Kombinationen) — ALLE Add-Buttons verschwinden, Formations-Anzeige zeigt den exakten Formations-Namen (z.B. "4-2-4").
4. Ein Ziel wieder entfernen — der zugehörige Add-Button erscheint wieder, Anzeige wechselt zurück auf "noch nicht komplett".
5. Bank-Ziele hinzufügen — bleibt unbegrenzt möglich, beeinflusst weder Zählung noch Anzeige.
6. "Speichern" klicken — kein Fehler, Firestore-Dokument enthält keinen `formation`-Schlüssel mehr (per Firebase-Konsole oder `GOOGLE_APPLICATION_CREDENTIALS=firebase-service-account.json python3 -c "from google.cloud import firestore; print(firestore.Client().collection('wunschkader').document('current').get().to_dict().keys())"` prüfbar).

- [ ] **Step 3: `feedback/current`-Item auf `status: "done"` setzen**

Read-Modify-Write gegen den frischen Serverstand — Item identifiziert über `created_at` (`"2026-08-01T10:34:27.589Z"`, Text beginnt mit "Wunschkader: es sind mehr Formationen möglich"):

```bash
GOOGLE_APPLICATION_CREDENTIALS=firebase-service-account.json python3 -c "
from google.cloud import firestore
c = firestore.Client()
ref = c.collection('feedback').document('current')
doc = ref.get()
data = doc.to_dict()
items = data['items']
target_created_at = '2026-08-01T10:34:27.589Z'
updated = False
for item in items:
    if item.get('created_at') == target_created_at:
        item['status'] = 'done'
        updated = True
if not updated:
    raise RuntimeError('Item nicht gefunden - created_at in feedback/current pruefen, evtl. hat sich das Array seit Session-Start veraendert')
ref.set({'items': items}, merge=True)
print('OK, status=done gesetzt fuer:', target_created_at)
"
```

Expected: `OK, status=done gesetzt fuer: 2026-08-01T10:34:27.589Z`. Falls `RuntimeError` — Item frisch aus `feedback/current` lesen und Diskrepanz dem User melden statt blind zu erzwingen.

- [ ] **Step 4: HANDOFF.md ergänzen**

Neuen Bullet unter `## Completed` einfügen (ans Ende der Liste). Commit-Hashes durch die echten kurzen Hashes aus `git log --oneline` für die 3 Code-Commits dieses Plans (Task 1–3) ersetzen:

```markdown
- [x] **Wunschkader: alle 10 erlaubten Formationen + live abgeleitete Positions-Buttons statt starrer Combobox** (2026-08-01, Spec `docs/superpowers/specs/2026-08-01-wunschkader-formationen-design.md` + 4-Task-Plan `docs/superpowers/plans/2026-08-01-wunschkader-formationen.md`, User-Fund aus `feedback/current`): vorher nur 4 von tatsächlich 10 in Kickbase erlaubten Formationen konfiguriert (Recherche per WebSearch/WebFetch, Drittquelle DAZN — Kickbases eigene Hilfe-Seite listet keine Details, siehe Spec). Formation wird nicht mehr per Combobox vorausgewählt, sondern live aus der tatsächlichen Ziel-Belegung abgeleitet (`canAddStarter()`/`matchedFormation()`, `formations.ts`) — Add-Button pro Position nur sichtbar, solange mindestens eine der 10 Formationen noch erreichbar ist, read-only Anzeige zeigt die exakt erreichte Formation sobald 11 Feldspieler stehen. `wunschkader_formation` komplett aus dem Stack entfernt (Backend `dashboard_export.py`, Contract-Test, `types.ts`) — keine Migration nötig, da die neuen 10 Formationen jede bisher gespeicherte Ziel-Belegung weiterhin zulassen. Commits `COMMIT_TASK1`–`COMMIT_TASK3`.
```

- [ ] **Step 5: HANDOFF.md committen**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Wunschkader-Formationen-Feature (Task 1-3 dieses Plans) als abgeschlossen dokumentiert"
```

- [ ] **Step 6: Push**

Nur ausführen, wenn Step 1 (tsc + Backend-Suite) tatsächlich fehlerfrei war.

```bash
git push origin main
```

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle Abschnitte der Spec (10-Formationen-Liste, `canAddStarter()`/`matchedFormation()`-Algorithmus + Korrektheits-Argument, Combobox-Entfernung, read-only Anzeige, Add-Button-Vereinfachung auf höchstens einen pro Position, Backend/Contract-Test/types.ts-Entfernung, Verification inkl. Feedback-Item+HANDOFF) sind auf Task 1–4 abgebildet.
- **Platzhalter-Scan**: keine TBD gefunden. Die einzigen bewusst offenen Werte (`COMMIT_TASK1`–`COMMIT_TASK3` in Task 4/Step 4) sind Commit-Hashes, die erst beim tatsächlichen Committen entstehen.
- **Typ-Konsistenz geprüft**: `PositionCounts = Record<Position, number>` (Task 1) wird in Task 2 identisch für `startingCounts` verwendet. `canAddStarter(counts: PositionCounts, position: Position)`/`matchedFormation(counts: PositionCounts)` — Task 2 ruft beide exakt mit dieser Signatur auf (`canAddStarter(startingCounts, position)`, `matchedFormation(startingCounts)`). Keine Datei importiert nach Task 2 noch `slotsFor`/`isFormationKey`/`DEFAULT_FORMATION` (per Task 1 gelöscht) — einziger Konsument war `WunschkaderTab.tsx`, per `grep` vor Spec-Erstellung bestätigt.
- **Gegen den echten Code verifiziert**: `formations.ts` (komplette Datei), `WunschkaderTab.tsx` (Imports, Component-Signatur, `byPosition`/`bench`-Berechnung, `handleSave()`, JSX-Combobox-Block, Positions-Rendering-Loop), `dashboard_export.py` (`export()`s `_assemble_snapshot(...)`-Aufruf inkl. `wunschkader_config`-Abhängigkeit, `_assemble_snapshot()`-Signatur+Dict), `tests/test_dashboard_export.py` (`AssembleSnapshotContractTests` + bestätigt, dass `LoadWunschkaderTests` NICHT angepasst werden muss — testet die generische `_load_wunschkader()`-Passthrough-Funktion, nicht das jetzt entfernte Snapshot-Feld), `frontend/src/types.ts` wurden für diesen Plan frisch gelesen. `git log --oneline -3 -- <betroffene Dateien>` bestätigt: keine Änderung seit den frühesten Reads dieser Session, alle Code-Zitate sind aktuell.
