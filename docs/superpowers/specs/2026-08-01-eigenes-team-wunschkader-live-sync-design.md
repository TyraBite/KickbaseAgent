# Eigenes Team liest Wunschkader live statt aus eingefrorenem Snapshot — Design

## Kontext

User-Feedback (`feedback/current` in Firestore, Item vom 2026-08-01T10:12:37.394Z, `type: "bug"`): "Wenn ich den
Wunschkader anpasse, dann ist das Eigene Team nicht der live Stand des Wunschkaders. Habe Hader gerade aus dem
Wunschkader entfernt, bei Eigenes Team ist er nicht bei Verkaufskandidaten sondern noch bei Bleibt im Team."

Root Cause (gegen den aktuellen Code verifiziert):

- `App.tsx` lädt `dashboard_snapshot/latest` **einmalig** per `getDoc()` in einem `useEffect` beim Mount (kein
  `onSnapshot`, kein Polling, kein Reload-Trigger danach).
- Alle Tabs bleiben durchgehend gemountet (nur per CSS-Klasse `hidden` versteckt, kein Unmount beim Tab-Wechsel).
- `EigenesTeamTab.tsx` berechnet den Verkaufskandidaten/Bleibt-Split ausschließlich aus `data.wunschkader_targets`
  (`buildEigenesTeamSplit()`, derive.ts) — das ist die beim App-Mount einmalig geladene, seitdem eingefrorene Kopie
  aus dem Snapshot.
- `WunschkaderTab.tsx` initialisiert sein lokales `editState` ebenfalls aus `data.wunschkader_targets`, hält danach
  aber alle Änderungen nur in lokalem React-State. `handleSave()` schreibt direkt nach Firestore
  (`setDoc(doc(db,"wunschkader","current"), {...}, {merge:true})`), aktualisiert aber **nie** das App-Level
  `data`-Objekt. Die bestehende Speicher-Bestätigung sagt das sogar selbst: "hier sofort sichtbar. In anderen
  Ansichten/nach einem Reload erst nach dem nächsten Pipeline-Lauf."
- `grep` bestätigt: `wunschkader_targets` (`DashboardSnapshot`-Feld) wird im gesamten Frontend nur von genau diesen
  2 Dateien gelesen — keine weiteren Konsumenten.
- Das Backend (`dashboard_export.py::_build_wunschkader_targets()`) liest `wunschkader/current` ebenfalls (während
  des Pipeline-Laufs) und schreibt eine Kopie in den Snapshot — bleibt unangetastet, dieses Vorhaben ist rein
  Frontend-seitig.
- Precedent im selben Repo: `FeedbackTab.tsx` liest/schreibt bereits frontend-only direkt gegen eine eigene
  Firestore-Collection (`feedback/current`), unabhängig vom Backend-Pipeline-Workflow — auch dort nur ein einmaliges
  `getDoc()` beim Mount, kein Realtime-Listener. Dieses Vorhaben folgt demselben Muster für `wunschkader/current`.
- **Bewusst NICHT Teil dieser Spec**: `wunschkader_formation` (Snapshot-Feld) — ein separates, ebenfalls geplantes
  Vorhaben (Formations-Recherche/-Umbau, eigene Spec) macht dieses Feld komplett überflüssig (Formation wird dort
  rein client-seitig aus den Zielen abgeleitet statt gespeichert). Um doppelte Arbeit zu vermeiden, hebt dieses
  Vorhaben deshalb NUR die Ziel-Liste (`targets`) live, nicht `formation` mit.

Entschieden im Brainstorming (siehe Chat, 2026-08-01):

- `wunschkader/current`s Ziel-Liste wird als eigenes, von `data: DashboardSnapshot` unabhängiges
  App-Level-State-Stück geführt, live per eigenem `getDoc()` geladen — nicht mehr aus der Snapshot-Kopie gelesen.
- `WunschkaderTab.handleSave()` aktualisiert nach erfolgreichem Firestore-Write zusätzlich dieses App-Level-State
  über einen neuen Callback-Prop, damit `EigenesTeamTab` (durchgehend gemountet) sofort den korrekten Split zeigt,
  ohne Reload.
- Kein `onSnapshot`/Realtime-Listener — neues Architekturmuster für dieses Repo, nicht nötig für den gemeldeten Bug
  (Single-User-Hobby-Projekt, ein Browser-Tab zur Zeit), Precedent (`FeedbackTab.tsx`) macht es genauso einfach.
- Schlägt der Live-Read fehl oder existiert das Dokument noch nicht (Cold-Start): Fallback auf die Snapshot-Kopie
  (`data.wunschkader_targets`) — kein eigener Error-Zustand.
- Die jetzt veraltete Speicher-Bestätigung in `WunschkaderTab.tsx` wird korrigiert (verspricht nicht mehr fälschlich
  Verzögerung für andere Ansichten).

## Nicht-Ziele

- Kein `onSnapshot`/Realtime-Listener (siehe oben).
- Keine Backend-/Workflow-/Cron-Änderung, keine Änderung an `_build_wunschkader_targets()` (`dashboard_export.py`).
- Keine Änderung an `firestore.rules` — die Read/Write-Berechtigung für `wunschkader` existiert bereits (nötig war
  sie schon für `WunschkaderTab.tsx`s bestehendes `setDoc()`).
- Kein neuer Cold-Start-/Error-UI-Zustand für `EigenesTeamTab`/`WunschkaderTab` — der Fallback auf die Snapshot-Kopie
  deckt den seltenen Fehlerfall ab, ohne zusätzliche UI-Zweige.

## Architektur

**`App.tsx`**: neuer State

```typescript
const [wunschkader, setWunschkader] = useState<{ targets: RawWunschkaderTarget[] } | null>(null);
```

Im bestehenden Lade-`useEffect` (der aktuell nur `dashboard_snapshot/latest` holt) wird zusätzlich
`getDoc(doc(db, "wunschkader", "current"))` geholt — **beide Fetches im selben Effect, bevor `setLoadState("ready")`
gesetzt wird**, damit nie ein Zwischenzustand entsteht, in dem `data` schon bereit ist, `wunschkader` aber noch
`null`. Auflösung:

- Snapshot-Fetch schlägt fehl / Dokument fehlt → wie bisher (`loadState = "error"`), `wunschkader` bleibt `null`,
  spielt keine Rolle (Tabs werden ohnehin nicht gerendert).
- Snapshot-Fetch erfolgreich, `wunschkader`-Fetch erfolgreich UND Dokument existiert → `wunschkader = { targets:
  raw.targets ?? [] }` (aus dem `wunschkader/current`-Dokument).
- Snapshot-Fetch erfolgreich, `wunschkader`-Fetch schlägt fehl ODER Dokument existiert nicht (Cold-Start — noch nie
  gespeichert) → Fallback: `wunschkader = { targets: snapshotData.wunschkader_targets ?? [] }` (die Snapshot-Kopie,
  wie bisher).

Danach `setWunschkader(...)` und `setLoadState("ready")` gemeinsam — `wunschkader` ist ab dem Moment, in dem die
Tabs gerendert werden, garantiert nicht mehr `null` (kein neuer Optional-Guard in den Kindkomponenten nötig).

**`EigenesTeamTab`**: bekommt `wunschkader: { targets: RawWunschkaderTarget[] }` als neue Prop (statt
`data.wunschkader_targets` direkt zu lesen) — `buildEigenesTeamSplit()`- und `watchlist`-Berechnung nutzen
`wunschkader.targets` statt `data.wunschkader_targets`.

**`WunschkaderTab`**: bekommt ebenfalls `wunschkader` als Prop (statt `data.wunschkader_targets` für die
Initialisierung) sowie einen neuen Callback-Prop `onSaved: (targets: RawWunschkaderTarget[]) => void`.
`handleSave()` ruft nach dem erfolgreichen `setDoc()` zusätzlich `onSaved(targets)` auf — App.tsx reicht dafür
`(targets) => setWunschkader({ targets })` durch. Das aktualisiert den App-Level-State sofort, `EigenesTeamTab`
(durchgehend gemountet, `hidden` statt unmounted) rendert direkt danach mit dem korrekten Split neu.

Die bisherige, lokal in `WunschkaderTab` verwaltete `formation`-Auswahl (Combobox + `data.wunschkader_formation`)
ist NICHT Teil dieser Spec — bleibt vorerst unverändert bestehen (das separate Formations-Vorhaben ersetzt sie
komplett durch eine live abgeleitete, read-only Anzeige und entfernt `wunschkader_formation` aus dem gesamten
Stack).

**Speicher-Bestätigungstext** (`WunschkaderTab.tsx::handleSave()`): der Teil "in anderen Ansichten/nach einem Reload
erst nach dem nächsten Pipeline-Lauf (kann verzögert sein)" wird entfernt/umformuliert, da er nach diesem Fix nicht
mehr zutrifft — die Ziel-Liste selbst ist jetzt sofort überall sichtbar. Was weiterhin stimmt und im Text bleibt:
andere, aus dem Pipeline-Snapshot stammende Daten (Marktwerte, ML-Prognosen für neu hinzugefügte Spieler etc.)
aktualisieren sich weiterhin nur mit dem nächsten Pipeline-Lauf — das bleibt im Text als Einschränkung stehen, nur
eben nicht mehr für die Wunschkader-Liste selbst formuliert.

## Verification

- `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` (Standard-Verifikationsschritt, kein `npm
  install` im Haupt-Checkout).
- Backend-Testsuite (`python3 -m unittest discover -s tests`) bleibt unberührt, trotzdem vor Commit laufen lassen.
- Manuelle Live-Verifikation im Browser (genau der gemeldete Bug-Reproduktionsfall): einen Spieler im
  Wunschkader-Tab entfernen (oder hinzufügen/tauschen) → Speichern → OHNE Reload zum Eigenes-Team-Tab wechseln →
  Spieler erscheint sofort korrekt bei Verkaufskandidaten (bzw. bei Bleibt/Watchlist, je nach Aktion).
- Zusätzlich: frischer Seitenaufbau (Reload) zeigt weiterhin den korrekten, zuletzt gespeicherten Stand (bestätigt,
  dass der initiale Live-`getDoc()` funktioniert, nicht nur der Save-Callback-Pfad).
- `feedback/current`-Item (Firestore, erstellt `2026-08-01T10:12:37.394Z`) nach Live-Verifikation auf
  `status: "done"` setzen (Read-Modify-Write gegen den frischen Serverstand, etabliertes Muster).
- HANDOFF.md nach Abschluss aktualisieren (Completed-Eintrag).

## Out of Scope (bewusst)

- Realtime-Sync über mehrere gleichzeitig offene Browser-Tabs/Geräte hinweg (kein `onSnapshot`, siehe Nicht-Ziele).
- `wunschkader_formation`/die Formation-Combobox — eigenes, separates Vorhaben (siehe oben).
- Die anderen offenen Feedback-Items aus derselben Session (Tages-Dashboard, Transfermarkt/AlleSpieler-Kartenansicht,
  Wunschkader-Icon-Buttons) — unabhängige Vorhaben, nicht Teil dieser Spec.
