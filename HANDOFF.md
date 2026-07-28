# Handoff: KickbaseAgent Dashboard — Phase 5 (Mobile/UX) + Wechsel-Suche committed

**Generated**: 2026-07-28 (Ende der Session, 2. Update)
**Branch**: main
**Status**: In Progress — Phase 1-4 fertig & live (unveraendert seit letztem
Handoff). Phase 5 (Mobile/UX) implementiert (`c458b35`), User hat danach
ECHT im Browser getestet und 3 Probleme gefunden — alle behoben und
committed (`dbac469`). Danach Feature-Wunsch: Freitext-Suche fuer den
Wunschkader-"Wechsel"-Dialog (nicht nur die 3 Auto-Vorschlaege) —
umgesetzt und committed (`342d29f`). WEDER die 3 Fixes NOCH die Suche
sind bisher im echten Browser verifiziert (Sandbox hat weiterhin keinen
Browser/Login) — das ist der naechste Schritt.

## Goal

Dashboard (`index.html`) mobile-tauglich machen: Tabellen waren zu breit
(horizontales Scrollen), Buttons/Filter zu klein zum Antippen,
Tab-Navigation unhandlich. Vollstaendige 5-Phasen-Architektur in
`docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md`.
Phase 1-4 (Firestore-Migration, Live-Read, Hosting, ML-Genauigkeit) sind
laenger fertig — siehe vorherige Handoff-Versionen in der Git-Historie
(`git log -p -- HANDOFF.md`) fuer die volle Vorgeschichte. Dieser Handoff
fokussiert auf Phase 5 + die zwei noch offenen Punkte aus Phase 4.

## Completed (diese Session)

- [x] **Brainstorming abgeschlossen**: Ansatz-Frage beantwortet (globaler
  CSS/JS-Mechanismus), User-Feedback eingearbeitet (EIN einheitlicher
  Rendering-Mechanismus fuer ALLE Tabs statt Sonderfall fuer Wunschkader;
  danach: volle Sortierbarkeit auch fuer Wunschkader statt
  `sortable:false`-Ausnahme). Design-Doc:
  `docs/superpowers/specs/2026-07-28-mobile-ux-design.md`.
- [x] **Implementierungsplan** erstellt und genehmigt (Plan Mode):
  `/home/node/.claude/plans/ich-bin-kein-frontendler-async-koala.md`.
- [x] **CSS-Mobile-Breakpoint** (`@media (max-width: 640px)`, neben dem
  bestehenden Dark-Mode-Query): Tabellen werden zu gestapelten Karten,
  Tab-Leiste scrollt horizontal statt zu brechen, `.filter-bar` stapelt
  sich, Tap-Targets (`button`, `input` ausser Checkbox/Radio, `select`)
  auf `min-height: 44px`.
- [x] **Genereischer JS-Mechanismus** (`annotateCardRows()`, erweiterte
  `makeSortable()`/`buildTable()`): nach jedem `tbody`-Render bekommt
  jedes `<td>` automatisch `data-label` (fuer die CSS-Karten-Darstellung)
  und optional `data-secondary="1"` (fuer ausblendbare Detail-Felder,
  siehe `columns[].secondary`). Absicherung: nur Zeilen mit
  `tr.children.length === columns.length` werden annotiert — schuetzt
  Sonderzeilen wie die Wunschkader-Vorschlagszeile (`colspan`).
- [x] **Wunschkader-Tab komplett auf `buildTable()` migriert**
  (`renderWunschkader()`, vorher komplett handgerolltes Table-HTML):
  stabile `_uid` pro Ziel (ueberlebt Sortierung, wird NIE mitgespeichert),
  Event-Delegation (ein `click`/`change`-Listener auf dem Sub-Container
  statt Re-Binding nach jedem State-Wechsel), State-Aenderungen (Add/
  Remove/Wechsel-Pick) rufen jetzt die von `buildTable()` zurueckgegebene
  `redraw()`-Closure statt die ganze Funktion neu aufzurufen.
- [x] **Feld-Prioritaet** (`secondary:true`) fuer Wunschkader- und
  Spekulation-Tab: Kernfelder vorne, Rest hinter "Details"-Toggle im
  Card-Modus (siehe Spec-Doc fuer die genaue Spaltenaufteilung).
- [x] **Commit** `c458b35` (lokal, NICHT gepusht) — `index.html` +
  neues Spec-Doc.
- [x] **1. Nacharbeitsrunde nach echtem Mobile-Test** (User-Feedback, per
  Plan Mode neu geplant und umgesetzt, Commit `dbac469`, lokal, NICHT
  gepusht):
  1. Card-Modus-Sortierung: `thead` bleibt sichtbar (statt komplett
     versteckt), wird im Breakpoint zu einer horizontal scrollbaren
     Pill-Leiste (`display:flex`, jedes `th` eine Pille). Reine
     CSS-Aenderung, bestehende Sortier-Logik greift unveraendert.
     Sinnlose Pills (Wunschkader-Button-Spalten `key:""`, leere
     Details-Toggle-`th`) werden ausgeblendet.
  2. Wunschkader-Name ist kein `<input>` mehr, sondern reiner Text
     (`.wk-name-input`-CSS + zugehoeriger `change`-Listener entfernt) —
     Umbenennen nur noch ueber "Wechsel"+Vorschlag.
  3. Neue `computedFor(name)`-Hilfsfunktion in `renderWunschkader()`:
     faellt bei fehlendem Treffer in `DATA.wunschkader` auf
     `DATA.alle_spieler` zurueck (Marktwert/Schnitt/Signal/Rang/Status),
     damit ein frisch per "Wechsel" gewaehlter Spieler sofort Werte
     zeigt statt komplett leer zu sein. `planned_price`/`ml_prediction`/
     `note` bleiben bewusst "n/v" bis zum naechsten Pipeline-Lauf (echte
     serverseitige Logik, nicht dupliziert).
- [x] **Freitext-Suche im Wunschkader-"Wechsel"-Dialog** (Commit
  `342d29f`, lokal, NICHT gepusht): User wollte nicht nur aus den 3
  Auto-Vorschlaegen waehlen koennen. Geklaert: Suche bleibt auf gleiche
  Position + freie Spieler (`owner==="Frei"`) beschraenkt, wie die 3
  Auto-Vorschlaege selbst. `suggestReplacements()`s Pool-/Scoring-Logik
  ausgelagert nach `scoreReplacementPool()`, neue `searchReplacementPool
  (target, query)` filtert zusaetzlich per Name-Substring (max. 20
  Treffer). `pickBtnHtml()` als gemeinsamer Button-Baustein fuer Auto-
  Vorschlaege UND Suchergebnisse (beide nutzen dieselbe `.wk-pick-btn`-
  Klasse/Event-Delegation). Neues Suchfeld (`.wk-wechsel-search`) +
  Ergebnis-Container (`.wk-search-results`) erscheinen neben den 3
  Auto-Vorschlaegen im "Wechsel"-Aufklapper, per neuem delegierten
  `input`-Listener auf `#tab-wunschkader-table`.

## Not Yet Done

- [ ] **Echter Browser-Check der 3 Nacharbeit-Fixes** (naechster Schritt,
  siehe Resume Instructions) — User hatte die erste Phase-5-Version schon
  echt getestet und 3 Probleme gefunden (Card-Modus ohne Sortierung,
  editierbarer Wunschkader-Name, Wechsel-Vorschlag ohne Werte, siehe
  Completed unten fuer die Fixes). Die Fixes selbst (`dbac469`) sind
  bisher nur per `node --check` + manuellem Diff-Review geprueft, noch
  NICHT im echten Browser nachverifiziert.
- [ ] **Quota-Fix (Read-Seite) sauber isoliert live verifizieren** (aus
  Phase 4, unveraendert offen): der einzige reale Versuch war durch
  Write-Quota-Erschoepfung vom selben Tag ueberlagert. An einem Tag OHNE
  vorheriges Backfill-Testen: `FIRESTORE_ENABLED=1
  GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3
  -m src.dashboard_export`, dann `firestore_db
  .get_accuracy_daily(firestore_db.connect())` gegenchecken, in der
  Firebase-Console (Firestore → Nutzung/Quota) die echte Read-Zahl
  pruefen (sollte niedriger Tausenderbereich sein, nicht 30-40k).
- [ ] **ML-Backfill-Fortsetzung** (aus Phase 4, unveraendert offen): nur
  46 von 90 Tagen sind in `ml_accuracy_daily`. In kleinen Haeppchen
  nachziehen (z.B. `python3 -m src.market_predictor --backfill 15`
  mehrfach), ERST nachdem Quota-Fix isoliert verifiziert ist.

## Failed Approaches (Don't Repeat These)

- **Automatisierten Browser-/DOM-Test fuer Phase 5 versucht** (jsdom via
  `node -e "require('jsdom')"`): nicht installiert, kein `npm`/kein
  `package.json` in diesem Python-Projekt — Installation haette eine
  Node-Abhaengigkeit in ein reines Python+Vanilla-JS-Projekt gezogen, nur
  fuer einen einmaligen Check. Bewusst NICHT gemacht (Projekt-Ethos:
  0€/YAGNI, kein Build-Schritt fuer `index.html`). Stattdessen: `node
  --check` auf die extrahierten `<script>`-Inhalte (reiner
  Syntax-Check, kein DOM/Firebase noetig) + manueller Diff-Review.
- Weitere fruehere Failed Approaches (Baumann/Hein/Backhaus-Verwechslungen,
  Plan-Mode-Subagent-Problem, `gh api -X POST`-Sandbox-Block) sind
  weiterhin gueltig — siehe vorherige Handoff-Version
  (`git show 5f6a96f:HANDOFF.md`) fuer den vollen Wortlaut.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| EIN Rendering-Mechanismus (`buildTable()`) fuer ALLE 7 Tabs, kein Tab-Sonderfall | User-Feedback: "vielleicht waere ein einheitliches rendering pro Tab sinnvoll, Tabs sollten sich nur in Funktion und Datenbeschaffung unterscheiden" — Wunschkader-Tab war der einzige Ausreisser (handgerollt), jetzt migriert |
| Wunschkader-Tabelle voll sortierbar (nicht `sortable:false`-Ausnahme) | Zweite Nachfrage explizit beantwortet: User wollte volle Konsistenz inkl. Sortier-Feature, trotz Mehraufwand (stabile IDs + Event-Delegation noetig) |
| `secondary:true`-Spalten-Flag generisch in `columns[]` statt Tab-spezifischem Karten-Layout | Haelt "ein Mechanismus, Tabs unterscheiden sich nur in Daten" durch — jeder Tab entscheidet nur ueber sein eigenes `columns[]`-Array |
| Kein automatisierter Browser-Test fuer diese Aenderung | Kein Test-Harness/Build-Tooling in diesem Ein-Datei-Projekt, Sandbox hat keinen Browser/Login — Nachziehen von jsdom/puppeteer waere unverhaeltnismaessig fuer ein Hobby-Projekt |
| Commit lokal, nicht gepusht | Weiterhin gueltiger Standing-Auftrag seit dem Public-Umstieg (Ruleset `NeverPushOnMain`) — User pusht selbst |

## Current State

**Working**: Phase 1-4 unveraendert live (Dashboard unter
https://tyrabite.github.io/KickbaseAgent/, Login+Live-Read, Firestore-
Write alle 2h). Phase 5 ist implementiert und committed, aber
UNGETESTET im echten Browser.

**Nicht verifiziert (nicht "broken", nur ungeprueft)**: ob das Karten-
Layout auf einem echten Handy/DevTools-Mobile-Emulation tatsaechlich gut
aussieht, ob der Wunschkader-Flow (Sortieren/Umbenennen/Wechsel/
Entfernen/Hinzufuegen/Speichern) im echten Browser fehlerfrei laeuft, ob
`_uid` wirklich nie im gespeicherten Firestore-Dokument landet.

**Uncommitted Changes**: keine — `git status` ist clean, alles in
`c458b35`.

## Files to Know

| File | Why It Matters |
|------|----------------|
| `index.html` | Einzige geaenderte Datei, Ein-Datei-Projekt, handgepflegt |
| `docs/superpowers/specs/2026-07-28-mobile-ux-design.md` | Volle Architektur-Doku dieser Session (Mechanismus, Wunschkader-Migration, Spalten-Prioritaet) |
| `/home/node/.claude/plans/ich-bin-kein-frontendler-async-koala.md` | Der genehmigte Implementierungsplan (Referenz falls Details zur Herleitung fehlen) |
| `docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md` | Die volle 5-Phasen-Architektur (Ursprungsspec) |

## Code Context

**Neuer genereischer Mechanismus** (`index.html`, in `makeSortable()`s
`draw()`):
```js
tbody.innerHTML = data.map(renderRow).join("");
if (columns) annotateCardRows(tbody, columns);
```
`annotateCardRows(tbody, columns)` setzt `data-label`/`data-secondary`
pro `<td>` und haengt bei Bedarf eine `.row-toggle`-Zelle an — siehe
Spec-Doc Abschnitt "Architektur" fuer den vollen Code.

**Wunschkader-Identifikation** (statt Array-Index):
```js
let wkNextUid = 0; // clientseitige stabile Zeilen-Id, ueberlebt Sortierung - nie mitspeichern
// ...
wunschkaderEditState = (DATA.wunschkader_raw ? DATA.wunschkader_raw.targets : [])
  .map((t) => ({ ...t, _uid: wkNextUid++ }));
// Speichern:
const targets = wunschkaderEditState.map(({ _uid, ...rest }) => rest);
```

## Resume Instructions

1. **Sofort: die 3 Nacharbeit-Fixes + die neue Freitext-Suche im echten
   Browser verifizieren** (braucht User oder eine Session mit echtem
   Firebase-Login):
   - Lokal oeffnen (`index.html` direkt oder `python -m http.server` im
     Repo-Root), einloggen.
   - DevTools-Mobile-Emulation (~375px, z.B. iPhone-Preset), irgendeinen
     Tab mit Tabelle oeffnen:
     - Erwartet: Kopfzeile ist jetzt eine horizontal scrollbare Pill-
       Leiste (statt komplett unsichtbar), Antippen einer Pille sortiert
       wie gehabt (Pfeil erscheint auf der Pille). Wunschkader-Button-
       Spalten und die leere Details-Toggle-Spalte tauchen NICHT als
       leere Pills auf.
   - Wunschkader-Tab, Desktop-Breite: Name ist jetzt Klartext (kein
     Eingabefeld mehr), komplett lesbar.
   - Wunschkader-Tab: "Wechsel" → einen Vorschlag waehlen.
     - Erwartet: die Zeile zeigt SOFORT Marktwert/Schnitt/Signal/
       Startelf-Rang/Status des neuen Spielers (nicht mehr komplett
       leer). "Geplant"/"ML-Prognose"/"Notiz" bleiben erwartungsgemaess
       "n/v" bis zum naechsten 2h-Pipeline-Lauf.
     - Falls trotzdem leer: `computedFor()` in `renderWunschkader()`
       gegenchecken (Namens-Abgleich ist exakter String-Vergleich —
       bei abweichender Schreibweise zwischen Wunschkader-Target-Namen
       und `DATA.alle_spieler`-Namen bleibt der Fallback leer).
   - Im selben "Wechsel"-Aufklapper: ins neue Suchfeld tippen (Name
     eines freien Spielers gleicher Position).
     - Erwartet: Treffer erscheinen live unter dem Feld als klickbare
       Buttons (max. 20), Auswahl funktioniert genau wie ein Klick auf
       einen der 3 Auto-Vorschlaege. Leeres Suchfeld zeigt keine
       Ergebnisse. Tippen eines Namens ohne Treffer zeigt "Keine Treffer.".
     - Falls nichts erscheint: `searchReplacementPool()`/den neuen
       `input`-Listener auf `#tab-wunschkader-table` in `index.html`
       gegenchecken.
   - Weiter wie gehabt: "Entfernen", neuen Eintrag hinzufuegen,
     "Speichern" (kein Fehler, `wk-save-status` zeigt Erfolg, danach im
     gespeicherten Firestore-Dokument pruefen: KEINE `_uid`-Felder in den
     `targets`).
   - Desktop-Breite (>640px) und Dark Mode: kurzer Regressionscheck ueber
     alle 7 Tabs.
2. **Danach, bei Gelegenheit: Quota-Fix isoliert live nachverifizieren**
   und **Backfill-Fortsetzung** (aus Phase 4, siehe Not Yet Done oben für
   die genauen Befehle).

## Setup Required

Nichts Neues gegenueber vorheriger Session — Firebase-Projekt/Service-
Account/Firestore/Pages/CI-Secret alle vollstaendig eingerichtet.

## Warnings

- **Commits bleiben lokal, NICHT pushen** — Ruleset `NeverPushOnMain`
  aktiv, User pusht selbst (siehe `project_kickbaseagent_git_workflow`-
  Memory).
- **`firebase-service-account.json` niemals committen** — weiterhin
  gitignored.
- **Kein Test-Harness fuer `index.html`** — jede Aenderung an diesem
  File muss manuell im Browser verifiziert werden, es gibt keinen
  automatisierten Ersatz dafuer in diesem Projekt.
- Kosmetischer Nebeneffekt in Kauf genommen: Klick auf die Kopfzeile der
  Wechsel-/Entfernen-Spalten im Wunschkader-Tab markiert sie optisch als
  "sortiert", sortiert aber nichts (leerer String als Sortier-Schluessel
  ist falsy) — kein Bug, bewusste Konsequenz der vollen Vereinheitlichung.
- `MDs/*.md` und `data/kickbase.db` koennen als "modified" auftauchen —
  bekannte CRLF-Sache vom Windows-Tool auf dem geteilten DrvFs-Mount,
  kein inhaltlicher Unterschied.
