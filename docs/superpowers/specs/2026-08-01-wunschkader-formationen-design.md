# Wunschkader: alle erlaubten Formationen + live abgeleitete Positions-Buttons — Design

## Kontext

User-Feedback (`feedback/current` in Firestore, Item vom 2026-08-01T10:34:27.589Z, `type: "feature"`): "Wunschkader: es
sind mehr Formationen möglich als die die wir bislang konfiguriert haben, hier ist einen Recherche notwendig was
möglich ist und das müssen wir einbauen. Ggf wird sie nicht starr über die Combobox ausgewählt sondern live geschaut.
3-5-2 ist zum Beispiel möglich. Wenn der Spieler also bislang 3-4-2 aufgestellt hat, dann kann er sowohl bei
Abwehr,mittelfeld, oder Sturm einen Spieler hinzufügen. Sobald aber 10 Feldspieler konform mit den erlaubten
Aufstellungen aufgestellt sind, verschwinden die buttons zum hinzufügen der Position, sie sollen sich verschwinden,
wenn das Maximum pro Position erreicht ist, das könnte zB 5 sein, das muss aber auch geprüft werden."

**Aktueller Zustand** (`frontend/src/lib/formations.ts`): nur 4 Formationen konfiguriert (3-4-3, 4-3-3, 3-5-2, 4-4-2).
`WunschkaderTab.tsx` lässt den User EINE davon per Combobox auswählen (`formation`-State, initial aus
`data.wunschkader_formation`), `slotsFor(formation, position)` liefert dafür eine FESTE Slot-Zahl pro Position —
gerendert werden `slots - targets.length` leere "+Ziel"-Karten. Wählt der User z.B. "3-4-3", sieht er in Abwehr immer
genau 3 Slots, unabhängig davon, ob er tatsächlich vorhat, 3, 4 oder 5 Verteidiger aufzustellen.

**Recherche (2026-08-01, WebSearch/WebFetch)**: Kickbases eigene Hilfe-Seite (help.kickbase.com) listet keine
konkreten Formationen, bestätigt nur "11 Spieler frei per Drag&Drop". Ein DAZN-Artikel (Drittquelle, siehe Quellen
unten) nennt konkret **10 erlaubte Formationen**, alle mit exakt 10 Feldspielern + 1 Torwart:

`3-4-3`, `3-5-2`, `3-6-1`, `4-2-4`, `4-3-3`, `4-4-2`, `4-5-1`, `5-2-3`, `5-3-2`, `5-4-1`

Daraus abgeleitete Positions-Bandbreite: Abwehr 3–5, Mittelfeld 2–6, Sturm 1–4 (Torwart immer exakt 1). Bestätigtes
Minimum aus derselben Quelle: "mindestens ein Torwart, drei Verteidiger, zwei Mittelfeldspieler und ein Stürmer".
**Hinweis für die Implementierung**: Dies ist eine Drittquelle, keine offizielle Kickbase-Dokumentation — die Zahlen
sind intern konsistent (alle Formationen summieren exakt auf 10, passen zum bestätigten Minimum), aber sollten bei
Gelegenheit gegen den echten In-App-Aufstellungs-Dialog gegengecheckt werden. Alle bisher konfigurierten 4
Formationen sind in der 10er-Liste enthalten (keine bestehende Formation entfällt, es kommen nur 6 dazu).

Entschieden im Brainstorming (siehe Chat, 2026-08-01):

- Formation wird nicht mehr per Combobox vorausgewählt, sondern **live aus den tatsächlich zugewiesenen Zielen pro
  Position abgeleitet** — pro Position wird ein "+Ziel"-Button nur angezeigt, wenn noch mindestens eine der 10
  Formationen mit der aktuellen Belegung + 1 in dieser Position erreichbar ist.
- Ein rein informatives, read-only Feld zeigt die aktuell erreichte Formation (sobald exakt 10 Feldspieler stehen)
  bzw. einen "noch nicht komplett"-Hinweis.
- `wunschkader_formation` (gespeichertes Feld, User-Auswahl) wird **komplett aus dem Stack entfernt** — Backend
  (`dashboard_export.py`), Contract-Test, `types.ts`. Kein Ersatz-Feld — die Formation ist ab jetzt eine reine
  Frontend-Ableitung aus den bereits vorhandenen Zielen, nie mehr in Firestore gespeichert.

**Wichtig — Abgrenzung zu einem anderen, parallel geplanten Vorhaben**: Der Live-Sync-Bugfix-Plan
(`docs/superpowers/specs/2026-08-01-eigenes-team-wunschkader-live-sync-design.md` +
`docs/superpowers/plans/2026-08-01-eigenes-team-wunschkader-live-sync.md`, ebenfalls committed, noch nicht
umgesetzt) hebt `wunschkader/current`s **Ziel-Liste** (`targets`) in einen live App-Level-State — wurde extra
angepasst, `formation` NICHT mit anzufassen, genau um Kollision mit diesem Vorhaben hier zu vermeiden. Dieses
Vorhaben hier baut auf dem AKTUELLEN, unveränderten Code auf (keiner der beiden Pläne ist umgesetzt) und geht davon
aus, dass `WunschkaderTab`s `data`/`wunschkader`-Props zum Implementierungszeitpunkt exakt so aussehen wie auf der
Platte — falls der Live-Sync-Plan zuerst umgesetzt wird, muss der Implementierungsplan dieses Vorhabens die dann
bereits vorhandene `wunschkader`-Prop für `targets` mitverwenden statt sie neu zu erfinden (siehe Global Constraints
im zugehörigen Implementierungsplan).

## Nicht-Ziele

- Keine Änderung an `sellSignal()`/Budget-Logik/anderen Wunschkader-Features (Bank/Backup, Notiz, Wechsel-Dialog,
  Ersatzspieler-Suche) — nur die Formations-/Positions-Slot-Logik ändert sich.
- Kein Backend-Validierungs-Aufwand für "ist die aktuelle Ziel-Belegung eine gültige Formation" — reine
  Frontend-Anzeige-/UX-Logik, das Backend speichert `targets` unverändert als reine `player_id`-Referenzliste.
- Keine Migration bestehender gespeicherter Daten nötig — die neuen 10 Formationen sind in jeder Position
  großzügiger als die alten 4, jede bisher gültige Belegung bleibt automatisch gültig (siehe Architektur).
- Kein Ersatz-Feld für `wunschkader_formation` — ersatzlos entfernt, keine Rückwärtskompatibilität nötig (einziger
  Konsument war `WunschkaderTab.tsx` selbst).

## Architektur

### `frontend/src/lib/formations.ts` — vollständige 10-Formationen-Liste + Live-Algorithmus

`POSITIONS`/`Position`-Export bleibt unverändert (wird auch von `MlGenauigkeitTab.tsx` genutzt). `FORMATIONS` wird
auf alle 10 recherchierten Formationen erweitert:

```typescript
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
```

`slotsFor()`, `isFormationKey()`, `DEFAULT_FORMATION` werden gelöscht (per `grep` bestätigt: ausschließlich in
`WunschkaderTab.tsx` genutzt, sonst keine Konsumenten) — ersetzt durch zwei neue Funktionen:

```typescript
export type PositionCounts = Record<Position, number>;

// True, wenn mindestens eine der 10 Formationen mit den aktuellen
// Zaehlungen PLUS einem weiteren Starter in `position` noch erreichbar
// ist (in jeder anderen Position muss die Formation mindestens die
// aktuelle Zaehlung zulassen, in `position` mindestens Zaehlung+1).
export function canAddStarter(counts: PositionCounts, position: Position): boolean {
  return FORMATION_KEYS.some((key) => {
    const f = FORMATIONS[key];
    return POSITIONS.every((p) => f[p] >= counts[p] + (p === position ? 1 : 0));
  });
}

// Liefert den Namen der exakt passenden Formation, falls die Zaehlungen
// GENAU einer der 10 entsprechen - sonst null (Belegung noch nicht
// komplett). Torwart ist in jeder Formation fix 1, faellt also automatisch
// mit rein.
export function matchedFormation(counts: PositionCounts): FormationKey | null {
  return FORMATION_KEYS.find((key) => POSITIONS.every((p) => FORMATIONS[key][p] === counts[p])) ?? null;
}
```

**Korrektheits-Argument** (warum kein Sonderfall für "ungültige Zwischenbelegung" nötig ist): jeder Klick auf einen
Add-Button ist durch `canAddStarter()` gegen alle 10 Formationen abgesichert — die Belegung bleibt dadurch
induktiv immer eine Teilmenge mindestens einer Formation. Erreicht die Summe aller Positionen (inkl. Torwart) genau
11, MUSS die Belegung exakt einer Formation entsprechen (eine Teilmenge einer 11er-Formation, die selbst auf 11
summiert, ist zwangsläufig die Formation selbst) — `matchedFormation()` findet in diesem Fall garantiert einen
Treffer, nie `null`. Entfernen von Zielen verringert Zählungen nur, verletzt diese Eigenschaft nie.

**Bestehende Daten bleiben gültig**: die alten 4 Formationen hatten maximal Abwehr 4, Mittelfeld 5, Sturm 3 — die
neue 10er-Liste erlaubt in jeder Position mindestens so viel (Abwehr bis 5, Mittelfeld bis 6, Sturm bis 4). Jede
unter dem alten System gespeicherte Ziel-Belegung ist also automatisch auch unter dem neuen System gültig, keine
Migration nötig.

### `WunschkaderTab.tsx` — Combobox raus, live Add-Buttons, read-only Formations-Anzeige

- Lokales `formation`-`useState` + das `<select>`-Dropdown (Formation-Auswahl) werden komplett entfernt.
- Neuer `useMemo`: `startingCounts: PositionCounts` — zählt `editState`-Einträge, die NICHT Bank sind
  (`!isBench(t)`), gruppiert nach der über `resolvedByPlayerId` aufgelösten Position (identisches Muster zu
  `byPosition`, das schon existiert).
- Pro Position-Sektion: bisher `Array.from({ length: Math.max(slots - targets.length, 0) })` leere Karten — neu
  **höchstens eine** `EmptySlotCard`, nur gerendert wenn `canAddStarter(startingCounts, position)` true ist. Das ist
  eine zwangsläufige Vereinfachung ggü. dem alten "zeigt genau X fehlende Slots"-Verhalten, da es keine einzelne
  Ziel-Formation mehr gibt, gegen die "X fehlende" definiert wäre — nur noch ein binäres "geht noch einer mehr?".
- Neue read-only Anzeige (ersetzt die alte Combobox-Stelle): `matchedFormation(startingCounts)` — zeigt den
  Formations-Namen (z.B. "3-5-2"), sobald 11 Feldspieler (inkl. Torwart) stehen, sonst einen Hinweistext mit
  Fortschritt (z.B. "Noch nicht komplett (`Summe`/11 Feldspieler)").
- Bank/Backup-Ziele bleiben unverändert außerhalb dieser Zählung (bereits heute per `isBench()` gefiltert,
  unbegrenzt hinzufügbar).

### Backend + Contract-Test + `types.ts` — `wunschkader_formation` komplett entfernt

- `src/dashboard_export.py::export()`: die Zeile `wunschkader_formation=wunschkader_config.get("formation") if
  wunschkader_config else None,` im `_assemble_snapshot(...)`-Aufruf entfällt. `wunschkader_config` bleibt bestehen
  (wird weiterhin für `wunschkader_targets` gebraucht).
- `src/dashboard_export.py::_assemble_snapshot()`: Parameter `wunschkader_formation` und der zugehörige
  `"wunschkader_formation": wunschkader_formation`-Eintrag im zurückgegebenen Dict entfallen.
- `tests/test_dashboard_export.py::AssembleSnapshotContractTests`: `"wunschkader_formation"` aus `EXPECTED_KEYS`
  entfernt, `wunschkader_formation=None,` aus dem Testaufruf entfernt.
- `frontend/src/types.ts`: `wunschkader_formation: string | null;` aus `DashboardSnapshot` entfernt.
- **Nicht angefasst**: `_load_wunschkader()`/`firestore_db.py::get_wunschkader()` (generische Passthrough-Reads des
  kompletten `wunschkader/current`-Dokuments, unabhängig davon, ob darin noch ein `formation`-Schlüssel steht — ein
  eventuell noch vorhandener alter `formation`-Wert im Firestore-Dokument selbst wird schlicht nie mehr gelesen,
  keine Löschung des Firestore-Feldes nötig). `tests/test_dashboard_export.py::LoadWunschkaderTests` bleibt
  unverändert (testet die generische Passthrough-Funktion, nicht das jetzt entfernte Snapshot-Feld).

## Verification

- `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` (Standard-Verifikationsschritt).
- `python3 -m unittest discover -s tests` (Backend-Suite, inkl. der angepassten Contract-Test-Assertions).
- Manuelle Live-Verifikation im Browser:
  - Wunschkader-Tab: ein Ziel pro Position hinzufügen bis 11 stehen — Add-Buttons müssen verschwinden, sobald keine
    der 10 Formationen mehr Raum lässt (z.B. Sturm nach 4 Zielen, da `5-2-3`/`4-2-4` die höchsten Sturm-Werte
    haben). Read-only Anzeige zeigt die exakt erreichte Formation.
  - Ein Ziel wieder entfernen — Add-Button für die betroffene Position muss wieder erscheinen, Anzeige wechselt
    zurück auf "noch nicht komplett".
  - Bank-Ziele hinzufügen — bleiben unbegrenzt möglich, beeinflussen die Positions-Zählung/Anzeige nicht.
- `feedback/current`-Item (Firestore, erstellt `2026-08-01T10:34:27.589Z`) nach Live-Verifikation auf
  `status: "done"` setzen (Read-Modify-Write gegen den frischen Serverstand).
- HANDOFF.md nach Abschluss aktualisieren (Completed-Eintrag), inkl. Hinweis auf die Drittquelle für die
  10-Formationen-Liste (siehe Kontext).

## Out of Scope (bewusst)

- Formale In-App-Bestätigung der 10-Formationen-Liste gegen Kickbase selbst (Drittquellen-Hinweis bleibt im Code/
  HANDOFF dokumentiert, kein Blocker für die Umsetzung).
- Die anderen offenen Feedback-Items derselben Session (Tages-Dashboard, Transfermarkt/AlleSpieler-Kartenansicht,
  Wunschkader-Icon-Buttons) — unabhängige Vorhaben.

## Quellen (Recherche 2026-08-01)

- [Alles rund um deine Aufstellung – Kickbase Hilfe](https://help.kickbase.com/help/alles-rund-um-deine-aufstellung)
  (keine konkrete Formations-Liste, bestätigt nur "11 Spieler frei per Drag&Drop")
- [Wie funktioniert Kickbase? – DAZN News](https://www.dazn.com/de-DE/news/fu%C3%9Fball/tipps-empfehlungen-bundesliga-managerspiel-kickbase-formationen-transfermarkt-trading-saisonstart/1amhezlfcbypy1dcml5428scwz)
  (nennt die 10 konkreten Formationen + Minimum-Angaben, Drittquelle)
