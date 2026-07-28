# Phase 6: Frontend-Rearchitektur — Sub-Projekt 2 (Wunschkader-Migration)

## Context

Sub-Projekt 1 (Spekulation-Pilot, siehe
`docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md`)
ist umgesetzt und live getestet. Laut Roadmap dort ist Sub-Projekt 2 der
Wunschkader-Tab: der interaktivste Tab der alten `index.html` (Anzeige +
Hinzufuegen/Entfernen + "Wechsel"-Ersatzspieler-Suche + Speichern per
`setDoc`, Budget-Planungs-Kachel). Datenschicht bleibt unveraendert
(direktes Client-seitiges Firestore-Read/Write, kein Cloud-Function-
Umweg) - gleiches Prinzip wie Sub-Projekt 1.

**Wichtige Randbedingung**: `index.html` bleibt waehrend des gesamten
Parallelbetriebs live und unveraendert nutzbar (Cutover erst in
Sub-Projekt 4, nach expliziter Freigabe). Die alte Seite hat sowohl einen
eigenen Wunschkader-Tab als auch eine Watchlist-Ansicht im Eigenes-Team-Tab,
die BEIDE dieselbe Python-Funktion `_build_wunschkader()`
(`src/dashboard_export.py`) und dasselbe Firestore-Dokument
(`wunschkader/current`) nutzen wie das neue Frontend. Jede Aenderung muss
also entweder rueckwaerts-kompatibel sein oder bewusst eine globale
Verhaltensaenderung sein (siehe "Backend-Aenderungen" unten fuer die
Abgrenzung).

## Daten-Audit + Feld-Reihenfolge (Dialog-Ergebnis)

Bisherige 11 Spalten (`wunschkaderColumns` in `index.html`): Position,
Spieler, Rolle, Status, Marktwert, Geplant, Schnitt, Signal, ML-Prognose,
Startelf-Rang, Notiz.

**Komplett raus** (nur in der neuen Ansicht - Begruendung jeweils
User-Aussage):
- **Geplant** (Preis-Spalte pro Ziel) - Budget-Planung wird stattdessen
  pauschal ueberschlagen (10% Aufschlag, "schnell im Kopf gerechnet"),
  kein Bedarf mehr fuer den Wert pro Zeile.
- **Status** ("Eigener Kader"/"Markt (...)"/"Bei X"/"Frei"/"Nicht
  gefunden") - kein Begruendungs-Nachfrage-Bedarf, User wollte es explizit
  raus.
- **Rolle** (Starter/Bank/Backup als Text) - "ergibt sich von selbst",
  ersetzt durch eine reine Bank/Startelf-Gruppierung im Layout (siehe
  unten), kein Text-Wert mehr sichtbar.
- **Notiz** - komplett raus.
- **ML-Prognose** - redundant, ist bereits Teil des noch zu migrierenden
  Eigenes-Team-Tabs (Sub-Projekt 3).

**Bleiben, neue Reihenfolge nach Entscheidungsrelevanz** (User-Vorgabe,
weicht bewusst von meinem Erst-Vorschlag "Signal/Rang zuerst" ab):

1. Position (nur Kuerzel: TW/ABW/MF/ST, wie Spekulation-Tab)
2. Spieler
3. Marktwert
4. Startelf-Rang
5. Schnitt
6. Signal

## Layout: Formation-Gruppierung (per Mockup-Dialog entschieden)

Anfrage des Users waehrend des Feld-Audits: Karten nach Aufstellung
gruppieren (Startelf pro Position + Bank), Kadergroesse max. 17 (11
Startelf + 6 Bank). Drei Layout-Varianten als Wireframes vorgestellt
(visueller Begleiter war technisch nicht erreichbar in dieser Sandbox-
Umgebung, daher rein textuell entschieden):

- A) Spielfeld-Grafik (Pitch-Formation als visuelle Reihen) - verworfen,
  zu aufwendiges CSS fuer den Nutzen.
- **B) Gewaehlt: Gruppen nach Position, Listen-Stil.** Vier Abschnitte
  (Torwart/Abwehr/Mittelfeld/Sturm), Header zeigt "Position · X/Y belegt"
  (Y = Formations-Sollzahl fuer diese Position), Karten im gleichen Stil
  wie Spekulation. Leerer Slot zeigt eine gestrichelte "+ Ziel"-Karte.
- C) Flaches Grid ohne Gruppierung - verworfen, verliert das
  "Luecken pro Position sofort sehen"-Feature.

**Formation**: Dropdown mit gängigen Formationen (3-4-3, 4-3-3, 3-5-2,
4-4-2 - erste Zahl Abwehr, zweite Mittelfeld, dritte Sturm, Torwart immer
1), aenderbar, wird mit gespeichert (`wunschkader_formation`-Feld bleibt
bestehen). Slot-Sollzahl pro Position ergibt sich direkt aus der
gewaehlten Formation.

**Bank-Bereich**: eigener Abschnitt unterhalb der 4 Positions-Gruppen,
zeigt alle Ziele mit Bank-Flag gesetzt (siehe Datenmodell), unabhaengig
von Position (Positions-Kuerzel bleibt auf der Karte sichtbar, da hier
nicht gruppiert wird). Bis zu 6 Bank-Plaetze.

**Kadergroessen-Warnung**: kein hartes Limit, nur eine Anzeige/Warnung
wenn Startelf+Bank zusammen 17 uebersteigt (reines Planungswerkzeug, kein
harter Stopp noetig). Ebenso kein hartes Limit pro Positions-Gruppe: hat
eine Position mehr Ziele als die Formation vorsieht (z.B. 4 Sturm-Ziele bei
einer 3-Sturm-Formation), zeigt der Header schlicht "4/3 belegt" und alle
4 Karten bleiben sichtbar - kein Erzwingen/Aussortieren. Ein
Formation-Wechsel aendert nur die angezeigte Soll-Zahl je Gruppe, weist
aber keine bestehenden Ziele automatisch zwischen Startelf und Bank um.

## Datenmodell: Bank/Startelf-Unterscheidung (Kompatibilitaets-Fix)

Erste Idee war ein neues `is_bench`-Boolean-Feld im Backend. **Verworfen**
nach genauerem Hinsehen: das haette die alte `index.html` (Wunschkader-Tab
+ Eigenes-Team-Watchlist, die `role`/`status`/`note`/`planned_price` aus
`_build_wunschkader()` weiter erwartet) kaputt gemacht.

**Finale Loesung**: Backend-Datenmodell fuer `role`/`status`/`note`
bleibt **komplett unveraendert** (`_build_wunschkader()` reicht weiterhin
alle bisherigen Felder durch, exakt wie heute). Die neue React-Ansicht:
- Liest **nur**, ob `role === "Bank/Backup-Option"` (bestehende Konvention
  aus `MDs/kaderplan.md`, Tella/Scherhant) - daraus ergibt sich clientseitig
  ein reines UI-Flag "ist Bank", ohne dass das Backend etwas Neues liefern
  muss.
- Zeigt dieses Flag NICHT als Text/Dropdown, sondern als Toggle-Button
  im Detail-Modal ("Auf Bank verschieben" / "In Startelf verschieben").
- Beim Speichern schreibt der Toggle direkt den String
  `"Bank/Backup-Option"` in `role` (oder entfernt das Feld fuer
  Startelf-Ziele) - alte `index.html` liest weiterhin denselben Wert,
  keine Verhaltensaenderung fuer sie.
- Neue Ziele ueber ein Positions-Slot ("+ Ziel" in einer Positions-Gruppe)
  werden ohne `role` angelegt (= Startelf). Neue Ziele ueber den generischen
  Bank-"+ Ziel"-Button bekommen sofort `role: "Bank/Backup-Option"` gesetzt
  und fragen zusaetzlich nach der Position (Pflichtfeld in
  `_build_wunschkader()`, siehe bestehender Code).
- `note` und `status` werden von der neuen Ansicht schlicht nicht
  angezeigt/editiert (aber unveraendert weiter berechnet/gespeichert,
  damit die alte Seite nichts verliert).

**Damit sind KEINE Backend-Datenmodell-Aenderungen fuer Rolle/Status/
Notiz noetig** - nur die zwei folgenden echten Formel-Aenderungen, die
User explizit als globale Vereinfachung wollte (wirkt sich bewusst auf
BEIDE Seiten aus):

1. **`_estimate_price()`**: bisheriges 2-Stufen-Aufschlagsystem
   (`topspieler_threshold`/`topspieler_markup`/`normal_markup` aus
   `wunschkader.json`s `markup_rules`) wird ersetzt durch einen pauschalen
   Aufschlag: `market_value * 1.10`. Ein gesetzter `actual_bid` (echtes,
   bereits platziertes Gebot, z.B. Stage 16,2 Mio.) hat weiterhin Vorrang
   vor der Schaetzung - unveraendert. Bereits im Kader befindliche Ziele
   (`is_own`) bekommen weiterhin `planned_price = 0` (ist schon im
   aktuellen Kontostand abgezogen) - unveraendert, User hat das im Dialog
   bestaetigt. `markup_rules`-Config in `wunschkader.json` wird dadurch
   ungenutzt (kann spaeter aufgeraeumt werden, kein Teil dieser Aenderung).
2. **`_build_budget_plan()`**: Login-Praemien-Projektion komplett raus,
   sowohl aus der Anzeige als auch aus der Rechnung. `_project_login_bonus()`
   wird nicht mehr aufgerufen (Funktion kann entfernt werden), `pool =
   cash + sell_proceeds` (vorher `+ login_bonus_projection`). Die
   Ausgabefelder `login_bonus_projection`/`season_start` entfallen aus dem
   `budget_plan`-Dict. `wunschkader.json`s `login_bonus`/`season_start`-
   Config wird dadurch ungenutzt (kann spaeter aufgeraeumt werden, kein
   Teil dieser Aenderung).

**Zukuenftige Idee, nicht Teil dieser Runde**: Liga-Bietverhalten live
beobachten, um eine dynamische statt pauschale Aufschlag-Prognose zu
bauen - waere auch fuer den Spekulation-Tab nuetzlich. User will vorerst
nur die pauschale 10%-Schaetzung.

## Budget-Plan-Kachel (Anzeige-Aenderung, kein Backend-Impact)

Die 6 Kennzahlen (Cash, + Verkaufserloese, = Pool, - Eingeplant, = Rest;
Login-Praemien-Zeile entfaellt komplett, siehe oben) bleiben. Der
erklaerende Hinweistext darunter (Verkaufsliste mit Einzelwerten,
Login-Praemien-Anmerkung, "Eingeplant zaehlt nur Starter/Backup") entfaellt
in der neuen Ansicht komplett - reine Darstellungsentscheidung, `sell_rows`
etc. werden weiterhin berechnet (nur nicht mehr gerendert).

## Karten-Interaktion

- Klick auf eine gefuellte Karte → Detail-Modal (wie Spekulation-Tab):
  zeigt die 6 Kernfelder, zusaetzlich zwei Aktionen: **Wechsel**
  (Ersatzspieler-Suche - Quick-Vorschlaege nach Distanz in Marktwert+Schnitt
  unter freien Spielern gleicher Position, plus Freitextsuche, 1:1 aus
  `scoreReplacementPool()`/`suggestReplacements()`/`searchReplacementPool()`
  in `index.html` uebernommene Logik) und **Bank/Startelf-Toggle** (siehe
  oben). Zusaetzlich **Entfernen**.
- Klick auf einen leeren Positions-Slot ("+ Ziel" in einer Positions-
  Gruppe) → Hinzufuegen-Dialog mit vorbelegter Position (kein
  Positions-Dropdown mehr noetig), nur Name-Eingabe.
- Klick auf "+ Ziel" im Bank-Bereich → Hinzufuegen-Dialog mit Name UND
  Position-Dropdown (Position ist Pflichtfeld in `_build_wunschkader()`,
  wird aber hier nicht durch einen Slot vorgegeben).
- **Speichern**: ein Button wie bisher, sammelt alle Aenderungen
  (Hinzufuegen/Entfernen/Wechsel/Bank-Toggle/Formation-Wechsel) im lokalen
  React-State, schreibt erst beim Klick per `setDoc(doc(db, "wunschkader",
  "current"), { targets, formation, updated_at }, { merge: true })` - wie
  die bestehende `index.html`-Logik.

## Dateien (voraussichtlich)

- `src/dashboard_export.py`: `_estimate_price()` vereinfachen,
  `_build_budget_plan()` Login-Praemie entfernen, `_project_login_bonus()`
  entfernen (totes Code).
- `tests/test_dashboard_export.py`: bestehende Tests fuer
  `_estimate_price`/`_build_budget_plan` (falls vorhanden) anpassen,
  neue Tests fuer die 10%-Formel und die fehlende Login-Praemie.
- `frontend/src/components/WunschkaderTab.tsx` (neu): Formation-Dropdown,
  4 Positions-Gruppen + Bank-Sektion, Detail-Modal mit Wechsel-Suche,
  Hinzufuegen/Entfernen, Speichern-Button, Budget-Plan-Kachel (ohne
  Hinweistext).
- `frontend/src/types.ts`: `WunschkaderRow`/`BudgetPlan`-Typen ergaenzen.
- `frontend/src/App.tsx`: Wunschkader-Tab aktivieren (zweiter aktiver Tab
  neben Spekulation).

## Verifikation

- `python3 -m unittest tests.test_dashboard_export` gruen nach den
  Formel-Aenderungen.
- Manueller Code-Review + Klammer-Balance-Check fuer alle neuen/
  geaenderten `.tsx`/`.ts`-Dateien (kein `tsc`/`npm run build` in dieser
  Sandbox moeglich, siehe bekanntes Windows-DrvFs-Mount-Problem).
- User testet lokal (`npm run dev`): Formation waehlen, Positions-Gruppen
  zeigen korrekte Soll/Ist-Zahlen, Hinzufuegen/Entfernen/Wechsel/
  Bank-Toggle funktionieren, Speichern schreibt nach Firestore, alte
  `index.html`-Wunschkader-Tab UND Eigenes-Team-Watchlist zeigen nach dem
  Speichern weiterhin korrekt an (Kompatibilitaets-Check).

## Out of Scope (bewusst nicht in diesem Sub-Projekt)

- Sub-Projekt 3 (restliche 5 Tabs) und Sub-Projekt 4 (Cutover) - unveraendert
  spaetere Schritte.
- Dynamische, live-beobachtete Aufschlag-Prognose statt pauschaler 10%
  (siehe oben) - eigene, spaetere Idee.
- Aufraeumen der jetzt ungenutzten `markup_rules`/`login_bonus`/
  `season_start`-Config in `wunschkader.json` - kann bleiben, ist nur
  totes Datenfeld, kein Aufwand hier.
- Drag-and-drop-Neusortierung innerhalb einer Positions-Gruppe - Reihenfolge
  ergibt sich aus der Speicher-Reihenfolge im `targets`-Array, kein
  manuelles Umsortieren in dieser Runde.
