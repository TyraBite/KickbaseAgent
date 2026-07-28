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

**Noch offen (braucht echten Login, kann im Sandbox nicht ausgefuehrt
werden)**: manueller Browser-Check mit echtem Firebase-Login — DevTools-
Mobile-Emulation auf allen 7 Tabs (keine horizontalen Scrollbalken mehr,
Tab-Leiste scrollt statt zu brechen), Wunschkader-Flow (Sortieren, Name
aendern, Wechsel-Vorschlaege, Entfernen, Hinzufuegen, Speichern —
inklusive Pruefung, dass `_uid` NICHT im gespeicherten Firestore-Dokument
landet), Desktop-Breite als Regressionscheck, Dark Mode im Card-Layout.
