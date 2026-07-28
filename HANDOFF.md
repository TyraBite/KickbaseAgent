# Handoff: KickbaseAgent Dashboard — Phase 6, Sub-Projekt 1 "Nacharbeit Runde 2" IMPLEMENTIERT, NICHT verifiziert/gepusht

**Generated**: 2026-07-28 (Ende der Session, 4. Update)
**Branch**: main
**Status**: In Progress — Phase 1-5 fertig & live (Details: `git log -p --
HANDOFF.md` fuer die volle Vorgeschichte, oder frueherer Commit
`233fd4d^:HANDOFF.md` fuer den letzten Phase-5-Stand). Phase 6 begonnen —
Frontend-Rearchitektur-Entscheidung getroffen, Sub-Projekt 1 (React/Vite/
Tailwind-Pilot fuer den Spekulation-Tab) implementiert (`0ef19f0`), nach
erstem User-Feedback ueberarbeitet (Kickbase-angelehntes Theme, Detail-
Modal statt Tab-weitem Umschalter, 3-Monats-Hoch/Tief, deutsche Umlaute,
`e3e1a9c`, **committed**). User hat danach echt mit `npm run dev`
getestet und eine ZWEITE Runde Feedback gegeben (7 Punkte, spaeter auf 8
verfeinert: Kachel-Header inkl. Vereinswappen, Badges entfernen,
Auktions-Zeit live statt eingefroren, 3-Monats-Daten fehlen im UI,
Farbindikatoren fehlen, 5-stufige Pfeile, Grid-Breakpoints,
Label/Wert-Abstand) — dafuer wurde recherchiert (Explore-Agent, echte
Code-Zitate, echte Schwellenwerte aus `data/kickbase.db`/
`data/ml_prediction_log.jsonl`) und vollstaendig geplant. **In DIESER
Session (neuer Kontext, per `/handoff:resume`) wurde der komplette Plan
implementiert und committed (`d888431`, lokal, NICHT gepusht)** — siehe
Abschnitt "Nacharbeit Runde 2" unten fuer den genauen Stand pro Punkt.
**Wichtiges Signal aus einer fruehen Session**: `frontend/node_modules` +
`package-lock.json` sind real aufgetaucht (User hat vermutlich selbst
`npm install` auf seinem Windows-Rechner laufen lassen, geteilter
DrvFs-Mount, dann auch `npm run dev`) — `package.json`/`package-lock.json`
stimmen exakt ueberein, Dependency-Aufloesung war erfolgreich.

## Goal

Phase 5 war reines CSS/JS-Polish der bestehenden `index.html`. User hat
danach 4 groessere Themen aufgeworfen: (1) wachsende Komplexitaet macht
die Vanilla-JS/CSS-Architektur unhandlich, (2) Frontend soll "schoener"
werden (Karten/Dashboard-Stil statt Tabellen-Optik), (3) "Datenmuell"
(ueberfluessige Spalten/Felder) soll raus, (4) ein Quick/Detail-View-
Konzept pro Tabelle. Nach ausfuehrlichem Interview (siehe Konversation):
kompletter Umbau auf React + Vite + Tailwind CSS, in Sub-Projekte
zerlegt. Voller Kontext + Roadmap:
`docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md`.

## Completed (diese Session)

- [x] **Architektur-Interview** (mehrere Runden, siehe Konversation):
  - React + Vite + Tailwind CSS (User-Entscheidung, gegen meine initiale
    "Vanilla aufraeumen"-Empfehlung).
  - **Kein** Cloud-Functions-/Backend-API-Umbau — User hat das nach
    kurzer Ueberlegung WIEDER verworfen: 2h-Cron-Batch-Job + direktes
    Client-seitiges Firestore-Read/Write bleiben unveraendert, nur die
    Rendering-Schicht wird ersetzt.
  - Hosting bleibt GitHub Pages (nicht auf Firebase Hosting umgezogen).
  - Rollout: Parallelbetrieb — alte `index.html` bleibt live, neues
    Frontend erscheint separat unter `.../KickbaseAgent/preview/`, bis
    ein bewusster Cutover erfolgt.
  - Quick/Detail-View: EIN globaler Umschalter PRO Tabelle/Tab (nicht pro
    Zeile), aber nicht jeder Tab braucht ihn zwingend (siehe Spekulation).
  - **Neues generelles Prinzip fuer alle kuenftigen Tab-Migrationen**:
    Feld-REIHENFOLGE wird nicht von der alten Tabelle uebernommen, sondern
    per kurzem Dialog nach Entscheidungsrelevanz neu festgelegt.
- [x] **Daten-Audit + Reihenfolge fuer Spekulation-Tab** (live im Dialog):
  Position, Verein, Schnitt komplett gestrichen (9 -> 5 Felder + Name).
  Finale Reihenfolge: Spieler-Name, ML-Prognose, Rendite%, Preis,
  Trend 7T, Auktion-Status (Auktion-Status bewusst ganz hinten, weil die
  Karten-Liste ohnehin standardmaessig danach sortiert ist). Alle 5 Felder
  immer sichtbar, kein Quick/Detail-Umschalter fuer diesen Tab noetig.
- [x] **Sub-Projekt 1 implementiert** (Commit `0ef19f0`, lokal, NICHT
  gepusht): neues `frontend/`-Verzeichnis (React 18 + Vite + Tailwind,
  eigenes `package.json`, komplett getrennt vom Python-Root), EIN Tab
  migriert (`SpekulationTab.tsx` — Card-Grid, Sortier-Dropdown, Suchfeld,
  Signal-Badges), Firebase-Auth+Firestore-Read 1:1 uebernommen (kein
  Cloud-Function-Layer). Neuer CI-Workflow
  (`.github/workflows/frontend-pilot.yml`) baut `frontend/` und deployt
  es NEBEN der unveraenderten `index.html` unter einem `/preview/`-
  Unterpfad. Trivialer Nebenpunkt erledigt: Zeilen-Zaehler neben den
  Tab-Namen (`updateTabBadges()`) aus der alten `index.html` entfernt.
- [x] **Nacharbeit nach erstem Feedback** (Commit `e3e1a9c`, lokal, NICHT
  gepusht): Kickbase-angelehntes Theme (neue `brand`-Gruenskala in
  `tailwind.config.js`, `slate` statt `neutral`, kein offizieller Marken-
  Hex verifizierbar — `brand.kickbase.com` blockiert automatisierte
  Abrufe, bewusst als Annaeherung markiert). Sortier-Dropdown deckt jetzt
  alle 6 Datenfelder ab (vorher 3). Klick auf eine Kachel oeffnet ein
  Detail-Modal (ersetzt den urspruenglich geplanten globalen Quick/
  Detail-Umschalter fuer diesen Tab — User-Entscheidung nach dem ersten
  Blick auf den Piloten). Modal zeigt zusaetzlich 3-Monats-Tief/-Hoch
  (`market_value_low_92d`/`_high_92d`) — dafuer `_build_spekulation()` in
  `src/dashboard_export.py` erweitert (Felder existierten serverseitig
  schon, wurden nur nicht durchgereicht), neuer Unit-Test dafuer gruen
  (`python3 -m unittest tests.test_dashboard_export`). Verein-Suche
  entfernt (Verein/Position werden gar nicht mehr angezeigt). Deutsche
  Umlaute durchgaengig in allen `frontend/`-Dateien (UI-Texte + Kommentare).

## Nacharbeit Runde 2 — IMPLEMENTIERT (Commits `d888431`+`7058daa`, lokal, NICHT gepusht), User hat live getestet, 2 Nachbesserungen

Alle 8 Punkte sind umgesetzt. Stand pro Punkt (Original-Plan darunter
weiterhin als Referenz, u.a. fuer die verwendeten Schwellenwerte):

**User hat danach ECHT im Browser getestet** (`npm run dev`) und 2
kleine Nachbesserungen direkt im Chat gegeben (beide committed, lokal,
NICHT gepusht):
- **Pfeil-Farbe** (`frontend/src/format.ts`, `trendArrow()`): User sah
  `▲`/`▼` (Geometric-Shapes-Dreiecke) immer gruen dargestellt, unabhaengig
  von Richtung — Font-Rendering-Problem (Dreiecke folgen auf manchen
  Systemfonts nicht `currentColor`). Fix 1 (Commit `65e2993`): auf reine
  Pfeil-Glyphen `↑`/`↓` gewechselt. **User-Folge-Feedback**: dann sahen
  NUR die 45°-Pfeile (`↗`/`↘`) farbig aus ("weisser Pfeil im blauen
  Quadrat", offizielle Emoji-Darstellung), der Rest blieb einfarbiger
  Text. Fix 2 (Commit `f48246a`, **finaler Stand**): alle 5 Stufen auf
  offizielle Pfeil-Emoji MIT explizitem Variation-Selector `️`
  umgestellt (`⬆️`/`↗️`/`➡️`/`↘️`/`⬇️`) — User hat das bestaetigt ("sieht
  besser aus").
- **Vereinswappen-Fallback-Badge** (Commit, siehe naechster Push — Session
  noch offen beim Schreiben dieses Updates): User wollte statt der ersten
  2 Buchstaben des Vereinsnamens die ECHTEN 3-Buchstaben-TV-Kuerzel
  (Sky/Kicker-Uebertragungsstil, z.B. "BVB", "FCB"). `TEAM_ABBR`-Mapping
  in `SpekulationTab.tsx` ergaenzt, `team_id`-Liste dafuer per Live-DB-
  Abfrage (`own_squad`+`market_listings`, alle `fetched_at`) auf 18
  Vereine erweitert (Bayern/`team_id=2` fehlte im urspruenglichen
  17er-Snapshot). Unbekannte `team_id` fallen weiterhin auf die ersten 3
  Buchstaben des Vereinsnamens zurueck (kein Hard-Fail bei neuen Vereinen).

- **Punkt 1 (Wappen+Position im Header)**: `TeamCrest`-Komponente in
  `frontend/src/components/SpekulationTab.tsx` — laedt
  `${BASE_URL}crests/{team_id}.svg`, faellt per `onError` auf
  Initialen-Badge zurueck. `team_id` wird jetzt serverseitig durchgereicht
  (`_player_row`/`_build_spekulation` in `src/dashboard_export.py`,
  Unit-Test ergaenzt). **Offen**: Die eigentlichen SVG-Dateien fehlen noch
  (`frontend/public/crests/` existiert nur mit einer `README.md` als
  Mapping-Doku) — User muss die ~17 Wappen besorgen und dort ablegen,
  siehe Resume Instructions.
- **Punkt 2 (Badges entfernen)**: Hype-Gipfel/Boden-Schutz-Pills raus aus
  Card+Modal, Hinweistext (`HINT`-Konstante) entsprechend gekuerzt.
  Felder bleiben im Datenmodell (`types.ts`), nur nicht mehr gerendert.
- **Punkt 3 (Live-Auktionszeit)**: `auction_expires_at` serverseitig
  durchgereicht (`_build_transfermarkt`/`_build_spekulation`,
  `src/dashboard_export.py`, Unit-Test ergaenzt). Frontend: `useNow(60_000)`-
  Hook + `auctionLabel()`/`formatDurationMs()` (`format.ts`) berechnen die
  Restzeit bei jedem Render + alle 60s neu. `auction_urgent` bleibt
  server-berechnet (nicht dupliziert).
- **Punkt 4 (3-Monats-Hoch/Tief)**: kein Code noetig (war schon korrekt),
  nur Push + Pipeline-Lauf noetig — siehe Resume Instructions.
- **Punkt 5 (Farbindikatoren + Schatten-Haertung)**: `trendClass()` war
  schon korrekt (Tailwind-Cache-Verdacht) — User muss `npm run dev` NEU
  STARTEN, um das zu verifizieren. Zusaetzlich gehaertet:
  `shadow-[0_0_12px_theme(colors.brand.400)]` in `App.tsx`/`Login.tsx`
  durch `shadow-md shadow-brand-500/50` ersetzt (native Tailwind-Utility
  statt Arbitrary-Value mit verschachteltem `theme()`-Call).
- **Punkt 6 (5-stufige Pfeile)**: `trendArrow(value, {flat, strong})` in
  `format.ts`, mit den recherchierten echten Schwellen (Trend 7T:
  200k/1,5M; ML-Prognose: 20k/100k) in `SpekulationTab.tsx` aufgerufen.
- **Punkt 7 (Grid)**: `grid-cols-[repeat(auto-fill,minmax(260px,1fr))]`.
- **Punkt 8 (Label/Wert-Abstand)**: `Row`-Komponente auf
  `grid grid-cols-[auto_1fr] gap-x-3` umgestellt.

**Verifikation in dieser Session**: `python3 -m unittest
tests.test_dashboard_export` gruen (8 Tests, 2 neue fuer `team_id`/
`auction_expires_at`). Klammer-Balance-Check (`(){}`[]`) fuer alle
geaenderten `.tsx`/`.ts`-Dateien manuell gegengezaehlt (kein `tsc` ohne
`node_modules` moeglich, siehe Warnings) — alle balanciert. **Kein echter
Browser-Test, kein `tsc`/`npm run build` in dieser Sandbox.**

**Volltext-Plan liegt auch in
`/home/node/.claude/plans/ich-bin-kein-frontendler-async-koala.md` dieser
Sandbox-Session, der aber in einer NEUEN Session/Sandbox evtl. nicht mehr
existiert - deshalb hier weiterhin als Referenz dupliziert:**

**1. Kachel-Header: Position-Abkuerzung + ECHTES Vereinswappen (Update
nach Rueckfrage - nicht mehr Initialen-Badge).** Kickbase-API liefert
selbst keine Logo-URL (bestaetigt), aber User wollte trotzdem echte
Wappen statt Initialen - Vereine sind bekannt, Wappen oeffentlich
auffindbar (z.B. Wikimedia Commons):
- **Self-hosted** unter `frontend/public/crests/{team_id}.svg` (o.ae.),
  NICHT von einer Drittanbieter-URL live eingebunden (bricht sonst
  irgendwann, Repo ist ausserdem public).
- **Bildrechte-Hinweis**: Vereinswappen sind markenrechtlich geschuetzt -
  fuer privates Hobby-Dashboard geringes Risiko, aber Repo ist OEFFENTLICH,
  Wappen liegen dann fuer jeden sichtbar im Code. User wurde darauf
  hingewiesen und hat sich bewusst dafuer entschieden.
- **Mapping-Key: `team_id`** (nicht `team_name`-String - robuster gegen
  Sonderzeichen wie "M'gladbach"). `team_id` liegt in `market_listings`
  schon vor, aber `_player_row()` (`dashboard_export.py:142-166`) reicht
  es bisher NICHT durch (nur `team_name`) - kleine Python-Ergaenzung:
  `"team_id": row["team_id"]` zum Dict, `_build_spekulation()` reicht
  `r.get("team_id")` durch.
- **Echte team_id/team_name-Paare** (live aus `data/kickbase.db`,
  `market_listings`, 17 Vereine mit aktuell gelisteten Spielern, nicht
  geraten): `13 Augsburg, 10 Bremen, 3 Dortmund, 77 Elversberg,
  4 Frankfurt, 5 Freiburg, 6 Hamburg, 14 Hoffenheim, 28 Köln, 43 Leipzig,
  7 Leverkusen, 15 M'gladbach, 18 Mainz, 29 Paderborn, 8 Schalke,
  9 Stuttgart, 40 Union Berlin` - weitere Liga-Teams ggf. gegen
  `league_ranking`/`get_teams()` vervollstaendigen.
- **Graceful Fallback**: fehlt fuer ein `team_id` (noch) eine Wappen-
  Datei, faellt die Kachel auf einen Initialen-Badge zurueck (`onError`
  am `<img>`) statt kaputtes Bild-Icon - Wappen koennen nach und nach
  ergaenzt werden, kein Big-Bang.
- **Wichtige Einschraenkung**: die Bilddateien selbst kann ich in dieser
  Sandbox NICHT herunterladen (kein Binaer-Download-Tool, `WebFetch`
  liefert nur Text/Markdown) - die ~17 Wappen muessen vom User besorgt
  werden (z.B. Wikimedia Commons) und nach `frontend/public/crests/`
  gelegt werden, oder eine kuenftige Session mit Bild-Download-Zugriff
  uebernimmt das. Code (Mapping/Fallback) wird trotzdem vollstaendig
  vorbereitet.

Position weiterhin ueber Abkuerzungs-Map: Torwart→TW, Abwehr→ABW,
Mittelfeld→MF, Sturm→ST. `position` ist in `SpekulationRow`
(`frontend/src/types.ts`) bereits vorhanden.

**2. Boden-Schutz/Hype-Gipfel-Badges entfernen** aus Card UND Detail-Modal
(`SpekulationCard`/`SpekulationDetailModal` in
`frontend/src/components/SpekulationTab.tsx`). **Geklaert per Rueckfrage**:
Hype-Gipfel-Kandidaten bleiben OHNE Filter in der Liste (User verlaesst
sich jetzt bewusst auf ML-Prognose/Trend statt auf die bisherige Warn-
Badge) - KEIN serverseitiger Filter in `_build_spekulation()` noetig.
`is_hype_gipfel`/`near_floor` bleiben im Datenmodell, nur nicht mehr
angezeigt.

**3. Auktionszeit war eingefroren zum Export-Zeitpunkt (User-Frage,
bestaetigt durch Recherche).** `_auction_status()`
(`src/dashboard_export.py:106-133`) berechnet `auction_remaining_seconds`
relativ zu einem `now`, das EINMAL beim Export-Lauf gesetzt wird
(`dashboard_export.py:600`, spaeter als der eigentliche Markt-Fetch in
`fetcher.py`). Der absolute Ablaufzeitpunkt (`expires_at`, ISO-String)
wird schon bei `fetcher._compute_expiry()` berechnet und in der SQLite-
Tabelle `market_listings` gespeichert - er wird nur bisher NICHT ins
exportierte Snapshot-Dict durchgereicht.
- **Fix Python**: `_build_transfermarkt()` (`dashboard_export.py:169-200`)
  ergaenzt sein `row.update({...})` um `"auction_expires_at": r["expires_at"]`
  (roh, direkt aus `r` - trivialer Ein-Zeilen-Zusatz, keine neue Berechnung).
  `_build_spekulation()` reicht `r.get("auction_expires_at")` genauso durch
  wie die anderen Auktionsfelder. Fuer den Spekulation-Tab (nur
  Systemangebote) ist `expires_at` IMMER exakt (nie die `mpst`-Tage-
  Schaetzung) - keine "geschaetzt"-Sonderbehandlung im Client noetig.
  Test ergaenzen in `tests/test_dashboard_export.py` (gleiches Muster wie
  der bestehende 92d-Test).
- **Fix Frontend**: `SpekulationRow` (`frontend/src/types.ts`) bekommt
  `auction_expires_at: string | null`. `SpekulationTab.tsx` berechnet die
  Restzeit-Anzeige aus `auction_expires_at` (`new Date(...).getTime() -
  Date.now()`) bei jedem Render/Reload, PLUS `setInterval` (alle 60s neu
  berechnen - kein sekundengenauer Live-Ticker, unnoetiger Aufwand) fuer
  "laufend aktuell" ohne auf den naechsten 2h-Fetch warten zu muessen.
  `auction_urgent` bleibt server-berechnet (haengt an Europe/Berlin-22-Uhr-
  Cutoff-Logik, nicht in JS duplizieren).

**4. 3-Monats-Hoch/Tief zeigt keine Daten - KEIN Bug, nur noch nicht
deployed.** Bestaetigt durch Recherche: die Felder werden serverseitig
ECHT berechnet (`fetcher._apply_market_value_history()`, echter Kickbase-
API-Call `/v4/leagues/{id}/players/{id}/marketValue/92`) und liegen fuer
JEDE Markt-/Spekulation-Zeile vor. Der vorherige Fix (Commit `e3e1a9c`,
`_build_spekulation()` reicht die Felder durch) war korrekt und
vollstaendig. **Grund fuer "keine Daten"**: alle Commits sind bisher nur
lokal (nicht gepusht), der 2h-Cron (`dashboard.yml`) lief seitdem nicht
mit dem neuen Code - der aktuelle Firestore-Snapshot ist schlicht aelter
als der Fix. **Keine weitere Code-Aenderung noetig** - nach dem Pushen
einmal `gh workflow run dashboard.yml` (oder auf den naechsten regulaeren
2h-Lauf warten), dann sollten die Werte im Modal erscheinen.

**5. Farbindikatoren fehlen (Betraege/Prognosen erscheinen weiss statt
rot/gruen) - vermutlich Tailwind-Cache, kein Logik-Bug.** Code-Review von
`trendClass()` (`frontend/src/format.ts`) zeigt keinen Fehler. Auffaellig:
`ml_prediction` ist per Filter in `_build_spekulation()` IMMER positiv -
jede "ML-Prognose"-Zelle haengt zu 100% von der custom `brand`-Farbklasse
ab. Boden-Schutz/Hype-Gipfel-Badges hat der User vermutlich am TEXT
erkannt, nicht zwingend an der Farbe. Wahrscheinlichste Erklaerung: der
Dev-Server lief schon, BEVOR die `brand`-Farbskala in `tailwind.config.js`
ergaenzt wurde (vorherige Nacharbeit-Runde) - **erster Diagnoseschritt:
`npm run dev` NEU STARTEN**. Zusaetzlich als Haertung: die bisher
ungetestete `shadow-[...theme(colors.brand.400)...]`-Arbitrary-Value-
Syntax im Header-Dot (`App.tsx`/`Login.tsx`) durch eine einfachere,
sicher funktionierende Alternative ersetzen (z.B. feste Schatten-Klasse
oder ganz ohne Glow).

**6. Pfeil-Indikator, 5-stufig (▲/↗/→/↘/▼) statt nur hoch/runter.** User
wollte explizit KEINEN simplen ▲/▼, sondern bei kleiner Aenderung
horizontal, bei mittlerer 45° - Schwellenwerte auf ECHTEN Daten dieser
Sandbox ermittelt (`data/kickbase.db`, `data/ml_prediction_log.jsonl`),
nicht geraten:
- **Trend 7T** (`market_value_change_7d`, absoluter €-Betrag): Verteilung
  aus `market_listings`, 161 aktuelle Zeilen, `abs(...)`: Median 845k,
  P75 1,28M, P90 1,58M. Bestehende Konstante `HYPE_CHANGE_THRESHOLD =
  1_500_000` (`dashboard_export.py:226`) ist schon die im Projekt
  etablierte "starke 7-Tage-Bewegung"-Schwelle - wiederverwendet statt
  einer zweiten Zahl fuers selbe Feld:
  - `< 200.000€` → horizontal (→)
  - `200.000€–1.500.000€` → 45° (↗/↘)
  - `> 1.500.000€` (= `HYPE_CHANGE_THRESHOLD`) → steil (▲/▼)
- **ML-Prognose** (`ml_prediction`, auf diesem Tab IMMER positiv):
  Verteilung aus `ml_prediction_log.jsonl`, Feld `predicted_delta`, nur
  positive Werte (12.850 echte historische Datenpunkte): Median 29k, P75
  88k, P90 145k, P95 186k:
  - `< 20.000€` → horizontal (→)
  - `20.000€–100.000€` → 45° (↗/↘)
  - `> 100.000€` → steil (▲/▼)

  `frontend/src/format.ts` bekommt eine generische `trendArrow(value,
  { flat, strong })`-Funktion (Vorzeichen = Richtung, Betrag ueber die
  zwei Schwellen = Stufe) - Aufrufer uebergeben ihre feldspezifischen
  Schwellen, keine hartkodierte Zahlendopplung in der Komponente.

**7. Grid-Breakpoints/Kachel-Maximalbreite.** Bisher `grid-cols-1
sm:grid-cols-2 lg:grid-cols-3` (Tailwind-Fixbreakpoints) - fuehlt sich
beim Umspringen abrupt an, Kacheln werden bei wenigen Treffern/mittleren
Breiten zu breit. Fix: `grid-cols-[repeat(auto-fill,minmax(260px,1fr))]`
(reine `grid-template-columns`-Arbitrary-Value, KEIN verschachtelter
Funktionsaufruf wie `theme()` - risikoaermer als Punkt 5s bisherige
Schatten-Syntax). Bewusst `auto-fill`, NICHT `auto-fit` - Letzteres
wuerde leere Spalten kollabieren und die Kacheln bei wenigen Treffern
doch wieder aufblaehen.

**8. Abstand zwischen Feldbezeichnung und Wert.** Bisheriges `Row`
(`flex items-center justify-between` in `SpekulationTab.tsx`) zieht Label
und Wert an gegenueberliegende Raender - bei breiteren Kacheln wirkt die
Luecke unverhaeltnismaessig gross. Fix: `Row` auf 2-Spalten-Grid umstellen
(`grid grid-cols-[auto_1fr] gap-x-3`, Label `auto`-breit, Wert-Spalte
`1fr` mit `text-right`) statt Flex-Space-Between - Werte richten sich
sauber an einer gemeinsamen rechten Kante aus. Profitiert zusaetzlich von
Punkt 7 (Kacheln werden grundsaetzlich schmaler/gleichmaessiger).

**Dateien fuer diese Runde**: `src/dashboard_export.py` (`_player_row`
neues Feld `team_id`, `_build_transfermarkt`, `_build_spekulation`),
`tests/test_dashboard_export.py`, `frontend/src/types.ts`,
`frontend/src/format.ts`, `frontend/public/crests/` (neue Wappen-
Bilddateien, vom User zu besorgen), `frontend/src/components/SpekulationTab.tsx`,
`frontend/src/App.tsx`/`Login.tsx` (Schatten-Syntax haerten).

**Verifikation danach**: Python-Unit-Test gruen
(`python3 -m unittest tests.test_dashboard_export`), Code-Review/Klammer-
Balance-Check fuer TS (kein `tsc` ohne `node_modules` in dieser Sandbox
moeglich). User-seitig: `npm run dev` NEU STARTEN, dann Browser-Check
(Farbindikatoren, 5-stufige Pfeile plausibel, Header-Badges, keine
Boden-Schutz/Hype-Gipfel-Pills mehr, Auktions-Countdown zaehlt bei
Reload/nach 60s aktuell weiter, Kacheln bleiben schmal, Label/Wert-
Abstand aufgeraeumt). 3-Monats-Hoch/Tief bleibt "–" bis Push+Pipeline-Lauf.

## Not Yet Done

- [ ] **Nacharbeit Runde 2 ist implementiert + committed, aber NOCH NICHT
  im Browser verifiziert** — naechster Schritt ist User-seitiges Testen
  (Dev-Server neu starten), nicht mehr Implementierung.
- [ ] **Vereinswappen-Bilddateien fehlen — MUSS DER USER HAENDISCH
  BESORGEN, kein KI-Todo** (bestaetigt im Chat, 2026-07-28): diese
  Sandbox hat kein Binaer-Download-Tool (`WebFetch` liefert nur Text/
  Markdown), Bilddateien koennen hier grundsaetzlich NICHT heruntergeladen
  werden — auch eine kuenftige Session mit demselben Tool-Zugriff kann das
  nicht automatisch nachholen, ausser die Sandbox bekommt ein
  Bild-Download-Tool. `frontend/public/crests/` hat nur eine `README.md`,
  die 18 SVGs (siehe dortige Liste, jetzt inkl. `2.svg` fuer Bayern) muss
  der User selbst besorgen (z.B. Wikimedia Commons) und dort ablegen
  (Dateiname = `{team_id}.svg`). Fallback bis dahin: TV-Kuerzel-Badge
  (`TEAM_ABBR` in `SpekulationTab.tsx`, z.B. "BVB", "FCB") statt Initialen -
  funktioniert unveraendert, kein Blocker fuer alles andere.
- [ ] **GitHub-Pages-Source umstellen**: Repo-Settings -> Pages -> Source
  von "Deploy from a branch" auf "GitHub Actions" — einmaliger manueller
  Schritt, macht der User selbst im Browser (wie bei frueherem Pages-Setup
  ueblich).
- [ ] **Sub-Projekt 2** (Wunschkader-Migration) und **Sub-Projekt 3**
  (restliche 5 Tabs, je mit eigenem Daten-Audit-Dialog) stehen noch aus —
  jeweils eigener Plan/Spec, siehe Roadmap-Tabelle im Spec-Doc.
- [ ] **Sub-Projekt 4** (Cutover, alte `index.html` entfernen) — ganz am
  Ende, erst nach expliziter User-Freigabe.
- [ ] Aus Phase 4 weiterhin offen (unveraendert diese Session):
  Firestore-Read-Quota-Fix isoliert live nachverifizieren, ML-Accuracy-
  Backfill-Fortsetzung (~44 fehlende Tage). Siehe `git show
  233fd4d^:HANDOFF.md` fuer die vollen Befehle/Details.

## Failed Approaches (Don't Repeat These)

- **Automatisierter Build/Test von `frontend/` in dieser Sandbox
  versucht** (`npm --version`, `node -e "require('jsdom')"` etc. in
  frueheren Sessions bereits gescheitert/bewusst unterlassen): kein
  `npm install` hier ausgefuehrt (Windows-DrvFs-Mount-Problem, siehe
  Warnings) — stattdessen nur Code-Review + `python3 -c "import yaml"`
  fuer den Workflow + Klammer-Balance-Check als Ersatz-Verifikation.
- Weitere fruehere Failed Approaches (Baumann/Hein/Backhaus-Verwechslungen,
  Plan-Mode-Subagent-Problem, `gh api -X POST`-Sandbox-Block) weiterhin
  gueltig — siehe `git show 233fd4d^:HANDOFF.md`.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| React + Vite + Tailwind statt "Vanilla aufraeumen" | Explizite User-Entscheidung gegen meine Empfehlung — User will jetzt einen echten Komponenten-/Design-System-Ansatz fuer den Karten-Stil |
| Kein Cloud-Functions-/Backend-Umbau | User hat das nach kurzer Ueberlegung selbst wieder verworfen — 2h-Cron + direktes Firestore-Read/Write funktioniert gut, kein Grund es anzufassen |
| Parallelbetrieb (altes Dashboard bleibt live) statt Big-Bang-Ersatz | User nutzt das Dashboard taeglich, soll waehrend des Umbaus nicht kaputt sein |
| GitHub Pages bleibt (nicht Firebase Hosting) | User-Entscheidung — ein System (GH Pages) statt zwei parallelen Hosting-Systemen zu pflegen war NICHT der Wunsch, aber Firebase Hosting haette Cloud-Functions-Naehe gebraucht, die inzwischen entfaellt |
| Sub-Projekt-Zerlegung (Pilot -> Wunschkader -> Rest -> Cutover) statt ein grosser Plan | Kompletter Umbau ist zu gross fuer einen Plan/eine PR (siehe `superpowers:brainstorming`-Dekompositions-Regel) |
| Feld-Reihenfolge neu nach Entscheidungsrelevanz statt alte Spaltenordnung | User-Wunsch, explizit als generelles Prinzip fuer ALLE kuenftigen Tab-Migrationen festgehalten, nicht nur Spekulation |
| Kein `npm install` in dieser Sandbox | Bekanntes Problem aus einem anderen Projekt auf demselben Windows-DrvFs-Mount (Unix-Bin-Shims statt `.cmd`, bricht dann auf Windows/Rider) — CI baut, User testet lokal selbst |

## Current State

**Working**: Phase 1-5 unveraendert live (`index.html` unter
https://tyrabite.github.io/KickbaseAgent/, inkl. aller Phase-5-Mobile-Fixes
+ Wechsel-Freitextsuche). NEU: `frontend/`-Verzeichnis mit komplettem
React/Vite/Tailwind-Setup fuer den Spekulation-Piloten existiert im Repo,
Runde-2-Nacharbeit ist mit implementiert, aber noch NIE gebaut/deployt
worden.

**Ungetestet/Unverifiziert**:
- Ob `frontend/` ueberhaupt fehlerfrei baut (`npm install && npm run
  build`) — nur Code-Review + Klammer-Balance-Check, kein echter
  TypeScript-Compile passiert.
- Ob der neue CI-Workflow nach Pages-Source-Umstellung tatsaechlich
  erfolgreich deployt.
- Ob der Spekulation-Pilot MIT den Runde-2-Aenderungen im Browser wie
  gedacht aussieht/funktioniert (Wappen-Fallback, Live-Countdown,
  Pfeil-Stufen, Grid/Abstand).

**Commits**: alle Commits dieser Session sind lokal, NICHT gepusht
(Standing-Rule seit Phase 3, siehe Warnings). Neuester: `d888431`
(Nacharbeit Runde 2).

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md` | Volle Architektur-Doku + Roadmap fuer Phase 6, inkl. aller Interview-Entscheidungen |
| `/home/node/.claude/plans/ich-bin-kein-frontendler-async-koala.md` | Der in Plan Mode genehmigte Plan fuer Sub-Projekt 1 (Referenz, gleicher Inhalt wie das Spec-Doc) |
| `frontend/` (neu) | Komplettes neues React/Vite/Tailwind-Projekt, eigenes `package.json` — NICHT `npm install` in dieser Sandbox ausfuehren |
| `frontend/src/components/SpekulationTab.tsx` | Die eigentliche Piloten-Komponente — Card-Grid, Sortierung, Suche, Feld-Reihenfolge |
| `frontend/vite.config.ts` | `base: "/KickbaseAgent/preview/"` — muss zum GH-Pages-Unterpfad passen |
| `.github/workflows/frontend-pilot.yml` (neu) | Baut `frontend/`, kombiniert mit `index.html` zu einem Pages-Artefakt |
| `index.html` (Repo-Root) | Bleibt die produktive Seite waehrend des gesamten Parallelbetriebs — NICHT anfassen ausser fuer triviale Sachen wie den entfernten Tab-Zaehler |

## Resume Instructions

1. **User besorgt Vereinswappen** (~17 SVG/PNG-Dateien, z.B. Wikimedia
   Commons) und legt sie unter `frontend/public/crests/{team_id}.svg` ab
   (siehe `frontend/public/crests/README.md` fuer die bekannten
   `team_id`/Verein-Paare). Ohne das laeuft die Kachel auf den
   Initialen-Fallback, ist also nicht blockierend fuer den restlichen Test.
2. **User testet lokal** (`npm run dev` NEU STARTEN, wichtig fuer Punkt 5
   der Nacharbeit - Tailwind-Cache/Farbindikatoren): Spekulation-Tab im
   Card-Layout pruefen, Reihenfolge Name/ML-Prognose/Rendite%/Preis/
   Trend-7T/Auktion-Status, Header zeigt Position+Vereinswappen (oder
   Initialen-Fallback), keine Boden-Schutz/Hype-Gipfel-Pills mehr,
   Farbindikatoren + 5-stufige Pfeile da, Auktions-Countdown zaehlt bei
   Reload/nach 60s aktuell weiter, Kacheln angemessen schmal (auto-fill-
   Grid), Label/Wert-Abstand aufgeraeumt, Sortier-Dropdown + Suchfeld
   funktionieren, Daten stimmen mit dem alten Dashboard
   (`.../KickbaseAgent/`, weiterhin unveraendert erreichbar) ueberein.
3. **Falls Test gruen: Commits pushen** (User macht das selbst, Standing-
   Rule `NeverPushOnMain`, siehe Warnings).
4. **Danach: GitHub-Pages-Source umstellen** (User macht das selbst im
   Browser): Repo-Settings -> Pages -> Source von "Deploy from a branch"
   auf "GitHub Actions".
5. **Danach: `frontend-pilot.yml` einmal laufen lassen** (automatisch bei
   Push auf `main` mit Aenderungen in `frontend/`/`index.html`, oder
   manuell per `workflow_dispatch`/`gh workflow run frontend-pilot.yml`
   nach dem Push).
   - Erwartet: Workflow gruen, `.../KickbaseAgent/preview/` zeigt die neue
     React-App.
   - Falls `npm ci`/`npm run build` in CI fehlschlaegt: Fehler im CI-Log
     gegenlesen, sehr wahrscheinlich kleine Konfigurationsfehler in
     `frontend/package.json`/`vite.config.ts`/`tsconfig.json`.
6. **Danach: `dashboard.yml` einmal laufen lassen** (oder auf den
   naechsten regulaeren 2h-Lauf warten) — damit Punkt 4 der Nacharbeit
   (3-Monats-Hoch/Tief) im Modal tatsaechlich Werte zeigt statt "–".
7. **Danach**: Sub-Projekt 2 (Wunschkader-Migration) planen — eigener
   `superpowers:brainstorming`-Zyklus mit Daten-Audit-Dialog fuer diesen
   Tab, wie bei Spekulation.

## Setup Required

- GitHub-Pages-Source-Umstellung (siehe Resume Instructions Punkt 1) —
  noch nicht gemacht.
- Sonst nichts Neues — Firebase-Projekt/Service-Account/Firestore/CI-
  Secrets alle unveraendert vom Vorher-Stand.

## Warnings

- **`npm install`/`npm run` NIE in dieser Sandbox ausfuehren** fuer
  `frontend/` — bekanntes Problem auf dem Windows-DrvFs-Mount (erzeugt
  Unix-Bin-Shims statt `.cmd`, bricht dann auf echtem Windows/Rider, siehe
  `feedback_no_npm_install_in_sandbox_for_windows_projects`-Memory). CI
  (GitHub Actions, sauberer Linux-Runner) baut, User testet lokal auf
  seinem echten Windows-Rechner.
- **Commits bleiben lokal, NICHT pushen** — Ruleset `NeverPushOnMain`
  aktiv, User pusht selbst (siehe `project_kickbaseagent_git_workflow`-
  Memory).
- **`frontend/` ist komplett ungetestet** — erster echter Build passiert
  entweder in CI oder beim User lokal, nicht in dieser Sandbox. Kleinere
  Config-Fehler (Vite/Tailwind/TS-Versionen) sind moeglich, siehe Resume
  Instructions Punkt 2 fuer den Umgang damit.
- `MDs/*.md` und `data/kickbase.db` koennen als "modified" auftauchen —
  bekannte CRLF-Sache vom Windows-Tool auf dem geteilten DrvFs-Mount,
  kein inhaltlicher Unterschied.
