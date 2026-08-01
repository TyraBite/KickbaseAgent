# Eigenes Team liest Wunschkader live statt aus eingefrorenem Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bug fixen, bei dem eine Wunschkader-Änderung im "Eigenes Team"-Tab erst nach einem Reload (bzw. nie, ohne Reload) sichtbar wird — `EigenesTeamTab` soll die aktuelle Wunschkader-Zielliste live lesen statt aus der beim App-Mount eingefrorenen Snapshot-Kopie.

**Architecture:** `App.tsx` bekommt einen zweiten, unabhängigen Firestore-Read (`wunschkader/current`, live) neben dem bestehenden `dashboard_snapshot/latest`-Read, gehalten in eigenem State. `EigenesTeamTab`/`WunschkaderTab` lesen diesen neuen State statt `data.wunschkader_targets`/`data.wunschkader_formation`. `WunschkaderTab.handleSave()` aktualisiert diesen State per Callback sofort nach dem Firestore-Write — kein Reload, kein Realtime-Listener nötig.

**Tech Stack:** React + TypeScript (Vite), Firebase JS SDK (`firebase/firestore`), kein Test-Framework im Frontend — Verifikation über `tsc --noEmit` + manuelle Browser-Reproduktion des gemeldeten Bugs.

## Global Constraints

- **Kein `npm install` im Haupt-Checkout** (Windows-DrvFs-Mount) — `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` ist der einzige Verifikationsbefehl fürs Frontend.
- **Kein Test-Framework im Frontend** — kein Jest/Vitest, keine `.test.ts(x)`-Dateien. Verifikation ausschließlich per `tsc --noEmit` + der letzte Task zusätzlich per manueller Browser-Reproduktion des exakten User-gemeldeten Bugs.
- **Backend-Tests unberührt, aber vor jedem Commit laufen lassen**: `python3 -m unittest discover -s tests`.
- **Push auf `main` erlaubt, aber nur wenn direkt vorher alle Tests grün sind** (Backend-Suite + `tsc --noEmit`).
- **Kein `onSnapshot`/Realtime-Listener** — bewusst nicht Teil dieses Vorhabens (siehe Spec), bleibt beim etablierten einmaligen `getDoc()`-Muster dieses Repos.
- **Kein Backend-/Firestore-Rules-/Workflow-Code ändern** — reine Frontend-Änderung, `wunschkader`-Collection-Rechte existieren bereits.
- **Basis ist der aktuelle, unveränderte Code** — ein anderer, bereits geschriebener aber noch NICHT ausgeführter Plan (`docs/superpowers/plans/2026-08-01-ml-horizonte-frontend-anzeige.md`) ändert `EigenesTeamTab.tsx`/`App.tsx` ebenfalls, ist aber zum Zeitpunkt dieses Plans noch nicht umgesetzt — alle Code-Zitate unten sind gegen den tatsächlich aktuell auf der Platte liegenden Stand verifiziert, nicht gegen den hypothetischen Zielzustand jenes anderen Plans.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/App.tsx` | Neuer `wunschkader`-State + eigener Firestore-Read im bestehenden Lade-Effect, an `WunschkaderTab`/`EigenesTeamTab` durchgereicht |
| `frontend/src/components/EigenesTeamTab.tsx` | Liest `wunschkader.targets` (neue Prop) statt `data.wunschkader_targets` |
| `frontend/src/components/WunschkaderTab.tsx` | Liest `wunschkader.targets`/`wunschkader.formation` (neue Props) statt `data.wunschkader_targets`/`data.wunschkader_formation`, `handleSave()` ruft neuen `onSaved`-Callback + korrigierter Bestätigungstext |

---

## Task 1: App.tsx — Live-Wunschkader-State + Fallback

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: nichts Neues (bestehende `getDoc`/`doc`/`db`-Imports, `DashboardSnapshot`-Typ).
- Produces: neuer App-Level-State `wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null } | null`, durchgereicht an `WunschkaderTab`/`EigenesTeamTab` als Prop `wunschkader`. Neuer Callback `onSaved: (targets: RawWunschkaderTarget[], formation: FormationKey) => void`, durchgereicht an `WunschkaderTab`. **Task 2/3 müssen diese exakten Prop-Namen/Typen in ihren Komponentensignaturen übernehmen.**

- [ ] **Step 1: Imports ergänzen**

Alt: `import type { DashboardSnapshot } from "./types";`

Neu: `import type { DashboardSnapshot, RawWunschkaderTarget } from "./types";`

Neue Zeile direkt danach ergänzen: `import type { FormationKey } from "./lib/formations";`

- [ ] **Step 2: Neuer State**

Alt:
```typescript
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState(readStoredActiveTab);
```

Neu:
```typescript
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [wunschkader, setWunschkader] = useState<{ targets: RawWunschkaderTarget[]; formation: string | null } | null>(null);
  const [activeTab, setActiveTab] = useState(readStoredActiveTab);
```

- [ ] **Step 3: Lade-Effect — zweiter, unabhängig fehlschlagbarer Live-Read**

Alt:
```typescript
  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then((snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte später erneut versuchen.");
          setLoadState("error");
          return;
        }
        setData(snap.data() as DashboardSnapshot);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, [user]);
```

Neu:
```typescript
  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then(async (snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte später erneut versuchen.");
          setLoadState("error");
          return;
        }
        const snapshotData = snap.data() as DashboardSnapshot;
        setData(snapshotData);

        // Live-Stand bevorzugt (wird von WunschkaderTab.handleSave() sofort
        // beschrieben, ohne auf den naechsten Pipeline-Lauf zu warten) -
        // eigenstaendig abgefangen: ein Wunschkader-Lesefehler darf NICHT den
        // gesamten Dashboard-Ladevorgang scheitern lassen, deshalb kein
        // gemeinsames Promise.all() mit dem Snapshot-Read oben. Fallback auf
        // die Snapshot-Kopie, wenn das Dokument noch nie gespeichert wurde
        // oder der Read fehlschlaegt.
        try {
          const wunschkaderSnap = await getDoc(doc(db, "wunschkader", "current"));
          if (wunschkaderSnap.exists()) {
            const raw = wunschkaderSnap.data() as { targets?: RawWunschkaderTarget[]; formation?: string };
            setWunschkader({ targets: raw.targets ?? [], formation: raw.formation ?? null });
          } else {
            setWunschkader({
              targets: snapshotData.wunschkader_targets ?? [],
              formation: snapshotData.wunschkader_formation ?? null,
            });
          }
        } catch {
          setWunschkader({
            targets: snapshotData.wunschkader_targets ?? [],
            formation: snapshotData.wunschkader_formation ?? null,
          });
        }

        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, [user]);
```

- [ ] **Step 4: Render-Aufrufe — `wunschkader`/`onSaved` durchreichen**

Alt:
```typescript
        {loadState === "ready" && data && data.players && (
          <div className={activeTab === "wunschkader" ? "" : "hidden"}>
            <WunschkaderTab data={data} />
          </div>
        )}
        {loadState === "ready" && data && data.players && (
          <div className={activeTab === "team" ? "" : "hidden"}>
            <EigenesTeamTab data={data} />
          </div>
        )}
```

Neu:
```typescript
        {loadState === "ready" && data && data.players && wunschkader && (
          <div className={activeTab === "wunschkader" ? "" : "hidden"}>
            <WunschkaderTab
              data={data}
              wunschkader={wunschkader}
              onSaved={(targets, formation) => setWunschkader({ targets, formation })}
            />
          </div>
        )}
        {loadState === "ready" && data && data.players && wunschkader && (
          <div className={activeTab === "team" ? "" : "hidden"}>
            <EigenesTeamTab data={data} wunschkader={wunschkader} />
          </div>
        )}
```

(Die zusätzliche `wunschkader &&`-Bedingung ist in der Praxis nie lange `false`, während `data`/`data.players` bereits `true` sind — beide States werden im selben Lade-Effect-Durchlauf gesetzt, bevor `loadState` auf `"ready"` wechselt, siehe Step 3. Sie ist trotzdem nötig, damit TypeScript `wunschkader` innerhalb des Blocks als nicht-`null` erkennt.)

- [ ] **Step 5: `tsc` — Fehler in ANDEREN Dateien sind hier erwartet**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: Fehler der Form `Property 'wunschkader' does not exist on type ...`/`Property 'onSaved' does not exist on type ...` bezogen auf die JSX-Aufrufe von `WunschkaderTab`/`EigenesTeamTab` in `App.tsx` selbst (weil deren Komponenten-Props diese Felder noch nicht kennen). **Das ist erwartet** — behoben in Task 2 (EigenesTeamTab) und Task 3 (WunschkaderTab).

- [ ] **Step 6: Commit**

```bash
cd /workspace/work
python3 -m unittest discover -s tests
git add frontend/src/App.tsx
git commit -m "App.tsx: wunschkader/current live per eigenem getDoc gelesen statt nur aus dem eingefrorenen Snapshot (Grundlage fuer Eigenes-Team-Live-Sync-Fix)"
```

---

## Task 2: EigenesTeamTab.tsx — `wunschkader`-Prop statt Snapshot-Feld

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Consumes: `wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null }` (Task 1).
- Produces: nichts, das Task 3 braucht (eigenständiger Tab).

- [ ] **Step 1: Import ergänzen**

Alt: `import type { DashboardSnapshot } from "../types";`

Neu: `import type { DashboardSnapshot, RawWunschkaderTarget } from "../types";`

- [ ] **Step 2: Komponentensignatur — neue Prop `wunschkader`**

Alt: `export default function EigenesTeamTab({ data }: { data: DashboardSnapshot }) {`

Neu:
```typescript
export default function EigenesTeamTab({
  data,
  wunschkader,
}: {
  data: DashboardSnapshot;
  wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null };
}) {
```

- [ ] **Step 3: `split`-Berechnung — `wunschkader.targets` statt `data.wunschkader_targets`**

Alt:
```typescript
  const split = useMemo(
    () => buildEigenesTeamSplit(data.players, data.own_squad_ids, data.wunschkader_targets, data.calibration, liveMae),
    [data.players, data.own_squad_ids, data.wunschkader_targets, data.calibration, liveMae]
  );
```

Neu:
```typescript
  const split = useMemo(
    () => buildEigenesTeamSplit(data.players, data.own_squad_ids, wunschkader.targets, data.calibration, liveMae),
    [data.players, data.own_squad_ids, wunschkader.targets, data.calibration, liveMae]
  );
```

- [ ] **Step 4: `watchlist`-Berechnung — `wunschkader.targets` statt `data.wunschkader_targets`**

Alt:
```typescript
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
```

Neu:
```typescript
  const watchlist: WatchlistRow[] = useMemo(
    () =>
      wunschkader.targets
        .filter((t) => !ownSquadIdSet.has(t.player_id))
        .map((t) => ({
          ...resolveTarget(t.player_id, data.players, ownSquadIdSet, listingsByPlayerId, data.owned_by, data.calibration),
          ml_prediction: data.players[t.player_id]?.ml_prediction ?? null,
        })),
    [wunschkader.targets, ownSquadIdSet, data.players, listingsByPlayerId, data.owned_by, data.calibration]
  );
```

- [ ] **Step 5: `tsc` — diese Datei muss jetzt 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: keine Fehler mehr, die `EigenesTeamTab.tsx` betreffen. `App.tsx` zeigt an diesem Punkt noch EINEN Fehler zum `WunschkaderTab`-Aufruf (aus Task 1) — normal, behoben in Task 3.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EigenesTeamTab.tsx
git commit -m "EigenesTeamTab: liest Wunschkader-Ziele jetzt aus der live wunschkader-Prop statt der eingefrorenen Snapshot-Kopie"
```

---

## Task 3: WunschkaderTab.tsx — `wunschkader`/`onSaved`-Props, Save-Callback, korrigierter Text

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null }`, `onSaved: (targets: RawWunschkaderTarget[], formation: FormationKey) => void` (beide Task 1).
- Produces: nichts, das andere Tasks brauchen.

- [ ] **Step 1: Komponentensignatur — neue Props `wunschkader`/`onSaved`**

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
export default function WunschkaderTab({
  data,
  wunschkader,
  onSaved,
}: {
  data: DashboardSnapshot;
  wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null };
  onSaved: (targets: RawWunschkaderTarget[], formation: FormationKey) => void;
}) {
  const [formation, setFormation] = useState<FormationKey>(
    isFormationKey(wunschkader.formation) ? wunschkader.formation : DEFAULT_FORMATION
  );
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (wunschkader.targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
```

- [ ] **Step 2: `handleSave()` — Callback aufrufen + Bestätigungstext korrigieren**

Alt:
```typescript
    setSaveStatus("Speichere…");
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
      setSaveStatus("Gespeichert - hier sofort sichtbar. In anderen Ansichten/nach einem Reload erst nach dem nächsten Pipeline-Lauf (kann verzögert sein, siehe HANDOFF.md).");
    } catch (err) {
      setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
    }
  }
```

Neu:
```typescript
    setSaveStatus("Speichere…");
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
      onSaved(targets, formation);
      setSaveStatus("Gespeichert - überall sofort sichtbar (auch Eigenes Team), kein Reload nötig. Andere Werte wie Marktwerte/ML-Prognosen für ggf. neu hinzugefügte Spieler folgen weiterhin erst mit dem nächsten Pipeline-Lauf.");
    } catch (err) {
      setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
    }
  }
```

- [ ] **Step 3: `tsc` — Projekt muss jetzt komplett 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: **0 Fehler im gesamten Projekt** (Task 1–3 sind jetzt konsistent — `App.tsx` übergibt exakt die Props, die beide Komponenten jetzt erwarten).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: liest wunschkader-Prop statt Snapshot-Kopie, meldet Aenderungen per onSaved-Callback sofort an App.tsx zurueck, Speichern-Text korrigiert"
```

---

## Task 4: Abschluss — Verifikation, Feedback-Item, HANDOFF.md, Push

**Files:**
- Modify: `HANDOFF.md` (neuer Completed-Eintrag)
- Keine Code-Änderung sonst.

**Interfaces:**
- Consumes: alle vorherigen Tasks (letzter, zusammenfassender Task).

- [ ] **Step 1: Volle Verifikation**

```bash
cd /workspace/work
node frontend/node_modules/typescript/bin/tsc -p frontend/tsconfig.json --noEmit
python3 -m unittest discover -s tests
```

Expected: beides ohne Fehler (`tsc`: 0 Ausgabe; Backend-Suite: `OK`).

- [ ] **Step 2: Manuelle Live-Reproduktion des exakten gemeldeten Bugs**

`cd frontend && npm run dev` (KEIN `npm install` davor — `node_modules` existiert bereits) und im Browser:

1. Wunschkader-Tab öffnen, einen Spieler aus dem eigenen Kader aus dem Wunschkader **entfernen** ("Entfernen"-Button im Detail-Modal).
2. "Speichern" klicken, Bestätigungstext prüfen (neuer Wortlaut, kein "erst nach dem nächsten Pipeline-Lauf" mehr für die Liste selbst).
3. **Ohne Reload** zum "Eigenes Team"-Tab wechseln.
4. Erwartet: der entfernte Spieler erscheint jetzt sofort bei **Verkaufskandidaten**, nicht mehr bei "Bleibt im Kader" — genau der im Feedback-Item beschriebene Fall (dort mit dem Spieler "Hader").
5. Zusätzlich: einen Spieler zum Wunschkader **hinzufügen**, speichern, ohne Reload prüfen, dass er in "Eigenes Team" jetzt aus den Verkaufskandidaten verschwindet (bzw. bei der Watchlist auftaucht, falls er nicht im eigenen Kader ist).
6. Danach die Seite neu laden (F5) — der zuletzt gespeicherte Stand muss weiterhin korrekt angezeigt werden (bestätigt, dass der initiale Live-`getDoc()` beim Mount ebenfalls funktioniert, nicht nur der `onSaved`-Callback-Pfad).

- [ ] **Step 3: `feedback/current`-Item auf `status: "done"` setzen**

Read-Modify-Write gegen den frischen Serverstand — Item identifiziert über `created_at` (`"2026-08-01T10:12:37.394Z"`, Text beginnt mit "Wenn ich den Wunschkader anpasse"):

```bash
GOOGLE_APPLICATION_CREDENTIALS=firebase-service-account.json python3 -c "
from google.cloud import firestore
c = firestore.Client()
ref = c.collection('feedback').document('current')
doc = ref.get()
data = doc.to_dict()
items = data['items']
target_created_at = '2026-08-01T10:12:37.394Z'
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

Expected: `OK, status=done gesetzt fuer: 2026-08-01T10:12:37.394Z`. Falls `RuntimeError` — Item frisch aus `feedback/current` lesen und Diskrepanz dem User melden statt blind zu erzwingen.

- [ ] **Step 4: HANDOFF.md ergänzen**

Neuen Bullet unter `## Completed` einfügen (ans Ende der Liste). Commit-Hashes durch die echten kurzen Hashes aus `git log --oneline` für die 3 Code-Commits dieses Plans (Task 1–3) ersetzen:

```markdown
- [x] **Bug: Wunschkader-Änderung nicht live in Eigenes Team sichtbar** (2026-08-01, Spec `docs/superpowers/specs/2026-08-01-eigenes-team-wunschkader-live-sync-design.md` + 4-Task-Plan `docs/superpowers/plans/2026-08-01-eigenes-team-wunschkader-live-sync.md`, User-Fund aus `feedback/current`): `EigenesTeamTab` berechnete den Verkaufskandidaten/Bleibt-Split aus `data.wunschkader_targets` — einer beim App-Mount einmalig geladenen, danach eingefrorenen Snapshot-Kopie. `WunschkaderTab.handleSave()` schrieb Änderungen zwar sofort nach Firestore (`wunschkader/current`), aktualisierte aber nie das App-Level-State, das alle Tabs teilen (alle Tabs bleiben durchgehend gemountet, nur per CSS `hidden` versteckt). Fix: `App.tsx` liest `wunschkader/current` jetzt per eigenem, unabhängig fehlschlagbarem `getDoc()` (Fallback auf die Snapshot-Kopie bei Cold-Start/Lesefehler), `EigenesTeamTab`/`WunschkaderTab` lesen diesen State statt der Snapshot-Felder, `WunschkaderTab` meldet erfolgreiche Saves per neuem `onSaved`-Callback sofort zurück — kein Reload, kein neuer `onSnapshot`/Realtime-Listener nötig (bleibt beim etablierten Einmal-`getDoc()`-Muster dieses Repos, analog `FeedbackTab.tsx`). Speichern-Bestätigungstext korrigiert (versprach vorher fälschlich Verzögerung für die Wunschkader-Liste selbst). Commits `COMMIT_TASK1`–`COMMIT_TASK3`. Reine Frontend-Änderung, Backend/Pipeline/Cron unangetastet.
```

- [ ] **Step 5: HANDOFF.md committen**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Eigenes-Team-Wunschkader-Live-Sync-Fix (Task 1-3 dieses Plans) als abgeschlossen dokumentiert"
```

- [ ] **Step 6: Push**

Nur ausführen, wenn Step 1 (tsc + Backend-Suite) tatsächlich fehlerfrei war.

```bash
git push origin main
```

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle Abschnitte der Spec (neuer App-Level-State, gemeinsam mit dem Snapshot-Fetch aufgelöst, Fallback auf Snapshot-Kopie bei Cold-Start/Fehler, `EigenesTeamTab`/`WunschkaderTab`-Prop-Umstellung, `onSaved`-Callback, korrigierter Speichertext, Verification inkl. Feedback-Item+HANDOFF) sind auf Task 1–4 abgebildet.
- **Platzhalter-Scan**: keine TBD gefunden. Die einzigen bewusst offenen Werte (`COMMIT_TASK1`–`COMMIT_TASK3` in Task 4/Step 4) sind Commit-Hashes, die erst beim tatsächlichen Committen entstehen — exakter Einfügeort vorgegeben, kein Implementierungs-Placeholder.
- **Typ-Konsistenz geprüft**: `wunschkader: { targets: RawWunschkaderTarget[]; formation: string | null }` heißt in App.tsx (State-Typ), `EigenesTeamTab` (Prop-Typ) und `WunschkaderTab` (Prop-Typ) exakt gleich benannt und gleich typisiert. `onSaved(targets: RawWunschkaderTarget[], formation: FormationKey)` — Task 1 (Callback-Aufruf `onSaved={(targets, formation) => setWunschkader({ targets, formation })}`) und Task 3 (`onSaved(targets, formation)`-Aufruf in `handleSave()`) nutzen exakt dieselbe Signatur; `formation` ist überall `FormationKey`, nicht generisches `string` (wichtig, da `wunschkader.formation` selbst `string | null` ist — die beiden Typen NICHT verwechseln, siehe `isFormationKey()`-Aufruf in Task 3/Step 1, der genau diese Umwandlung leistet).
- **Gegen den echten Code verifiziert**: `App.tsx` (kompletter Lade-Effect + beide Tab-Render-Aufrufe, Zeilen 1–30 und 108–240), `EigenesTeamTab.tsx`, `WunschkaderTab.tsx` wurden für diesen Plan frisch gelesen — insbesondere bestätigt, dass `SpekulationTab`/`TransfermarktTab`-Aufrufe in `App.tsx` NOCH im alten, unveränderten Zustand sind (der andere, noch nicht umgesetzte 3T-Anzeige-Plan hat dort noch nichts verändert) — dieser Plan zitiert deshalb bewusst nur die tatsächlich betroffenen Zeilen, nicht spekulativ den Zielzustand eines anderen Plans. `formations.ts` (`FormationKey`/`isFormationKey`/`DEFAULT_FORMATION`) wurde gelesen, um die exakte Callback-Signatur (`FormationKey`, nicht `string`) korrekt zu setzen.
