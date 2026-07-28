# Mobile/UX-Ueberarbeitung von index.html (Phase 5)

## Warum

Das Dashboard wird laut User schon regelmaessig auf dem Handy genutzt,
nervt dort aber im Alltag. Brainstorming-Interview ergab drei Pain
Points: Tabellen zu breit (horizontales Scrollen), Buttons/Filter zu
klein zum Antippen, Tab-Navigation/Layout allgemein unhandlich. "Eigenes
Team"/Wunschkader- und Spekulation-Tab sind auf dem Handy meistgenutzt
und bekommen zusaetzliche Politur; alle Tabs bekommen ein responsives
Basis-Layout.

`index.html` hatte vor dieser Aenderung NULL responsive Breakpoints
ausser `prefers-color-scheme: dark`.

## Scope-Entscheidung (User-Feedback aus Brainstorming)

Erste Design-Idee war ein globaler Mechanismus fuer die 6 Tabs, die
bereits `buildTable()` nutzten, PLUS ein manueller Sonderfall fuer den
Wunschkader-Tab (der sein Table-HTML komplett handgerollt baute).
User-Feedback: lieber EIN einheitlicher Rendering-Mechanismus fuer alle
Tabs, Tabs unterscheiden sich nur in Funktion und Datenbeschaffung. Der
Wunschkader-Tab wurde deshalb ebenfalls auf `buildTable()` umgebaut,
inklusive Sortierbarkeit (zweite Nachfrage: volle Konsistenz inkl.
Sortier-Feature statt Sonderfall ohne Sortierung).

## Architektur (ein Mechanismus fuer alle Tabs)

Alle 7 Tabs nutzen durchgaengig `buildTable()`/`makeSortable()`
(`index.html`, Funktionen `annotateCardRows`/`makeSortable`/`buildTable`).
Erweiterungen dort sind generisch, kein Tab-Sonderfall im JS:

1. **`data-label`-Injection** (`annotateCardRows()`): nach jedem
   `tbody`-Render wird jede `<tr>` durchgegangen; nur wenn
   `tr.children.length === columns.length` (generische Absicherung gegen
   Sonderzeilen wie die Wunschkader-Vorschlagszeile mit `colspan`),
   bekommt jedes `<td>` `data-label="${columns[i].label}"`.
2. **Card-Layout per CSS-Breakpoint** (`@media (max-width: 640px)`, neben
   dem Dark-Mode-Query): `table/thead/tbody/tr/td` auf `display:block`,
   `thead` versteckt, `td[data-label]::before { content: attr(data-label)
   }` zeigt das Label ueber dem Wert, `tr` wird visuell zur Karte
   (Rand+Radius+Abstand). Kein JS-Unterschied zwischen Tabs.
3. **Optionales `secondary:true`-Flag pro Spalte**: wird im selben
   generischen Schritt zu `data-secondary="1"` markiert, im Breakpoint
   per CSS ausgeblendet. Existiert mindestens eine `secondary`-Spalte,
   haengt `annotateCardRows()` pro Zeile eine "Details"-Toggle-Zelle an
   (`tr.classList.toggle('expanded')` zeigt sie wieder). `buildTable()`
   ergaenzt dafuer einen leeren `<th></th>` im Kopf, damit Spalten- und
   Kopfzahl auch im Desktop-Tabellen-Layout zusammenpassen. Welche
   Spalten `secondary` sind, entscheidet jeder Tab ueber sein eigenes
   `columns[]`-Array.
4. **Tap-Targets generisch groesser**: im Breakpoint `button,
   input:not([type=checkbox]):not([type=radio]), select { min-height:
   44px }` projektweit (Checkboxen/Radios bewusst ausgenommen, sonst
   wirken die Rang-Filter-Checkboxen im Alle-Spieler-Tab riesig).
5. **Tab-Navigation** (`nav.tabs`): im Breakpoint horizontal scrollbar
   (`overflow-x:auto; flex-wrap:nowrap`) statt Umbruch/Ueberlauf.
6. **`.filter-bar`**: im Breakpoint gestapelt statt Flex-Row.

## Wunschkader-Migration (`renderWunschkader()`)

Vorher: handgerolltes `<table>`-HTML, `data-idx` (Array-Index) zur
Identifikation, Event-Listener wurden nach JEDEM State-Wechsel (Add/
Remove/Wechsel-Pick) komplett neu gebunden, weil die ganze Funktion sich
selbst neu aufrief (voller Container-Rebuild).

- **Stabile IDs**: jedes Ziel bekommt beim Laden eine clientseitige
  `_uid` (`wkNextUid`-Zaehler). Noetig, weil die Tabelle jetzt sortierbar
  ist — Anzeige-Reihenfolge stimmt dann nicht mehr mit dem Array-Index
  ueberein. `_uid` wird nie mitgespeichert (`wk-save-btn`-Handler baut
  das Payload per Destructuring ohne `_uid`).
- **`buildTable()`-Aufruf**: `renderWunschkader()` baut die aeussere
  Huelle (Hint, Sub-Container `#tab-wunschkader-table`, Add-Formular,
  Speichern-Button, Budget-Plan) einmalig, ruft dann `buildTable()` fuer
  den Sub-Container auf und haelt die zurueckgegebene `redraw`-Funktion
  in einer Closure fest.
- **Event-Delegation statt Re-Binding**: ein `click`- und ein
  `change`-Listener auf `#tab-wunschkader-table` (wird von `draw()`
  NICHT ersetzt, nur `tbody`s Inhalt aendert sich). Delegation ueber
  `e.target.closest(...)`/`e.target.matches(...)` — ueberlebt jeden
  Redraw (Sortier-Klick oder eigene State-Aenderung), muss nur einmal
  registriert werden.
- **State-Aenderungen rufen `redraw()` statt `renderWunschkader()`**:
  Add/Remove/Wechsel-Pick mutieren `wunschkaderEditState` und rufen die
  gemerkte `redraw()`-Closure auf statt die ganze Funktion neu — erhaelt
  aktuelle Sortierung, guenstiger als voller Rebuild.
- **Sortier-Wermutstropfen**: die zwei Button-Spalten (Wechsel/Entfernen)
  haben `key: ""` (kein sinnvoller Sortier-Wert) — ein Klick auf ihre
  Kopfzeile markiert sie optisch als "sortiert", `draw()` ueberspringt den
  eigentlichen Sortier-Schritt aber, da ein leerer String als Sortier-
  Schluessel falsy ist. Rein kosmetischer Nebeneffekt der vollen
  Vereinheitlichung, keine funktionale Auswirkung.

## Priorisierte Tabs: Feld-Reihenfolge + Details-Toggle

Reine `columns[]`-Konfigurationsaenderung, kein neuer Mechanismus:

- **Wunschkader**: Kernspalten vorne (Position, Name, Wechsel/Entfernen-
  Buttons — bleiben an ihrer bisherigen Stelle direkt nach dem Namen,
  Status, Marktwert, Geplant); Rolle/Schnitt/Signal/ML-Prognose/Rang/
  Notiz sind `secondary:true` (hinter "Details" im Card-Modus).
- **Spekulation**: Kernspalten vorne (Name, Position, Preis, Rendite%,
  Auktion-Status); Verein/Trend/ML-Prognose/Schnitt sind `secondary:true`.
- Alle anderen Tabs bekommen nur die generische Karten-Darstellung, keine
  manuelle Feld-Priorisierung — kein Bedarf laut Interview.

## Verifikation

Kein Test-Harness fuer `index.html` in diesem Projekt (reines
Client-JS). Durchgefuehrt:

- Beide `<script type="module">`-Bloecke per `node --check` auf
  Syntaxfehler geprueft (gruen).
- Vollstaendiger Code-Review des Diffs (Spalten-/Zellen-Anzahl je Zeile
  gegengecheckt, keine `data-idx`-Altlasten mehr im Code).

**Update**: der User hat den echten Browser-Check durchgefuehrt (Sandbox
selbst kann das mangels Login/Browser nicht) und dabei 3 Probleme
gefunden — siehe "Nacharbeit nach echtem Mobile-Test" unten.

## Nacharbeit nach echtem Mobile-Test

Drei vom User im echten Browser gefundene Probleme, alle in `index.html`
behoben:

1. **Card-Modus hatte keine Sortier-Moeglichkeit mehr**: `thead` wurde
   komplett versteckt (`position: absolute; top: -9999px`). Fix: `thead`
   bleibt sichtbar, wird aber im Breakpoint zu einer horizontal
   scrollbaren Pill-Leiste (`display:flex`, jedes `th` eine Pille). Reine
   CSS-Aenderung — die bestehende Klick-zum-Sortieren-Logik in
   `makeSortable()` (inkl. `th.sorted::after`-Pfeil) greift unveraendert.
   Spalten ohne sinnvollen Sortier-Key (`th[data-key=""]`, die generisch
   angehaengte leere Details-Toggle-`th` ohne `data-key`) werden in der
   Pill-Leiste ausgeblendet.
2. **Wunschkader-Name war ein editierbares `<input>`**, dadurch oft nicht
   komplett lesbar — und laut User ohnehin ueberfluessig, weil der
   "Wechsel"-Button das Ersetzen schon abdeckt. Fix: Name-Zelle ist jetzt
   reiner (escapeter) Text, `.wk-name-input`-CSS-Regel und der zugehoerige
   delegierte `change`-Listener sind entfernt. Umbenennen geht nur noch
   ueber "Wechsel" + Vorschlag.
3. **Frisch per "Wechsel" gewaehlter Ersatzspieler zeigte keine Werte**:
   `wkRenderRow()` suchte "computed"-Werte nur in `DATA.wunschkader` (dem
   Snapshot vom letzten 2h-Pipeline-Lauf) — ein gerade erst client-seitig
   gewaehlter Spieler stand dort naturgemaess noch nicht drin. Fix: neue
   `computedFor(name)`-Hilfsfunktion in `renderWunschkader()` faellt bei
   fehlendem Treffer auf `DATA.alle_spieler` zurueck (Marktwert, Schnitt,
   Signal, Startelf-Rang, Status ueber `owner` — dieselbe Signal-Formel
   wie serverseitig, siehe `_build_alle_spieler` vs. `_build_wunschkader`
   in `src/dashboard_export.py`). Wird auch im "Wechsel"-Klick-Handler
   selbst genutzt (fuer die Vorschlags-Distanzberechnung), nicht nur beim
   Rendern. `planned_price`/`ml_prediction`/`note` bleiben bis zum
   naechsten Pipeline-Lauf "n/v" — echte serverseitige Logik (Fairwert-
   Gebotsschaetzung, ML-Modell), bewusst nicht client-seitig dupliziert.

## Freitext-Suche fuer Wunschkader-Wechsel

User-Feedback nach den 3 Fixes: die 3 automatischen Vorschlaege reichen
nicht immer - man soll auch selbst nach einem Ersatzspieler suchen
koennen, nicht nur aus den drei Top-Treffern waehlen muessen. Geklaerte
Scope-Fragen (beide "Recommended"-Optionen bestaetigt): Suche bleibt auf
dieselbe Position wie das Ziel UND auf freie Spieler (`owner === "Frei"`)
beschraenkt - identisch zum Pool der 3 Auto-Vorschlaege, nur ohne
Top-3-Limit.

- `suggestReplacements()`s bisherige Pool-Filter- und Distanz-Scoring-
  Logik ist in `scoreReplacementPool(target)` ausgelagert (gibt die volle
  sortierte Liste zurueck, kein Slicing). `suggestReplacements(target,
  count=3)` ist jetzt nur noch `scoreReplacementPool(target).slice(0,
  count)` - unveraendertes Verhalten fuer die 3 Auto-Vorschlaege.
- Neu: `searchReplacementPool(target, query)` - dieselbe Pool-Basis,
  zusaetzlich per Name-Substring gefiltert (case-insensitive), auf 20
  Treffer gedeckelt.
- Neu: `pickBtnHtml(id, s)` - der Vorschlags-Button-HTML-Baustein war
  vorher inline dupliziert (Auto-Vorschlaege), jetzt eine gemeinsame
  Funktion fuer Auto-Vorschlaege UND Suchergebnisse (beide nutzen
  dieselbe `.wk-pick-btn`-Klasse/Event-Delegation - kein neuer Klick-Pfad
  noetig).
- `renderWunschkader()`: der "Wechsel"-Klick baut die Vorschlagszeile jetzt
  aus zwei Teilen - `.wk-suggestions-quick` (die bestehenden 3 Auto-
  Vorschlaege) + `.wk-search-wrap` (Text-Input + `.wk-search-results`-
  Container, anfangs leer). Ein neuer delegierter `input`-Listener auf
  `#tab-wunschkader-table` (Suffix zum bestehenden `click`-Listener)
  reagiert auf Tippen in `.wk-wechsel-search`, ruft `searchReplacementPool()`
  auf und rendert Treffer als `.wk-pick-btn`-Buttons in `.wk-search-results`
  - leeres Suchfeld zeigt keine Ergebnisse (vermeidet Redundanz mit den
  3 Auto-Vorschlaegen direkt darueber).
