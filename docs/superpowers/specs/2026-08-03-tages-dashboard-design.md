# Tages-Dashboard — Design

## Kontext

User-Feedback (`feedback/current`, Item `bef54eff`, erstellt 2026-07-31T19:26:26.926Z, `type: "feature"`, mit Abstand
am ausführlichsten beschriebener Wunsch): ein Dashboard, das täglichen Handlungsbedarf bündelt — Verkaufskandidaten
(Prognose fällt), Kaufkandidaten (Wunschkader-Ziele gerade auf dem Markt), letzte Transfers anderer Manager. Ziel:
"sich täglich nur wenige Male in Kickbase einloggen müssen". Aufstellungsplanung explizit erst zum Saisonstart
("aktuell gehts nur um Kader planen, Kapital steigern, Kader aufbauen") — **nicht** Teil dieser Spec.

War bereits einmal in Brainstorming, User hat nach der ersten Frage selbst gestoppt ("bedarf größerer Planung").
Jetzt (2026-08-03) im Chat vollständig durchgesprochen.

Im Brainstorming zusätzlich entschieden (nicht im ursprünglichen Feedback-Text): eine **Investment-Sektion**
(Positions-unabhängiger Kapitalanlage-Vergleich, konkrete Swap-Vorschläge) und ein **Kaderlimit-Hinweis** (Kickbase
löscht laut User alle offenen Gebote, sobald der Kader 17 Spieler erreicht — verifiziert nur als User-Aussage, nicht
gegen die Kickbase-API/-Doku gegengecheckt, siehe Nicht-Ziele/Risiken).

Bestehende Bausteine, die diese Spec wiederverwendet (verifiziert gegen aktuellen Code):

- `sellSignal(mlPrediction, mae)` (derive.ts:250) — 1T-Prognose vs. MAE, `"verkaufen"` wenn Prognose negativ UND
  außerhalb der Modell-Ungenauigkeit. Bereits die App-weite Quelle für "Jetzt verkaufen"-Badges.
- `ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 }` (WunschkaderTab.tsx/TransfermarktTab.tsx,
  perzentil-basiert kalibriert) — bereits etablierte Schwelle für "starker" 3T-Trend, wiederverwendet als
  Mindestabstand für Investment-Swap-Paare statt eines neu erfundenen Schwellenwerts.
- `data.own_squad_ids` (bereits vorhandenes Snapshot-Feld) — echte Kadergröße für den Kaderlimit-Hinweis. **Wichtig:
  eigener, unabhängiger Wert von `MAX_SQUAD_SIZE = 17` in `WunschkaderTab.tsx`** — jener zählt geplante
  Wunschkader-**Ziele**, nicht den echten Kader. Beide Konzepte teilen zufällig die Zahl 17, bleiben aber getrennt.
- `TransfermarktCard` (TransfermarktTab.tsx:388, aktuell nicht exportiert) — Kartendarstellung mit Preis/Prognose
  1T+3T, wird für die Kauf-Kandidaten-Sektion wiederverwendet (Export nötig).
- `get_activities_feed(token, league_id)` (kickbase_client.py:209) — wird bereits im Heavy-Cron gezogen (aktuell nur
  für `manager_budgets.py`s Budget-Schätzung anderer Manager genutzt), enthält Typ-15-Trade-Einträge
  (`data.pi`=Spieler-ID, `data.byr`/`data.slr`=Käufer/Verkäufer-User-Id, `data.trp`=Preis). Keine neue
  Kickbase-API-Anbindung nötig für den Transfer-Feed.
- `ranking_rows` (dashboard_export.py, bereits an `_build_ligaanalyse()` übergeben) — enthält `user_id`→Name-Mapping,
  wiederverwendet zur Auflösung von Käufer/Verkäufer-Namen im Transfer-Feed.

## Nicht-Ziele

- Keine Aufstellungsplanung/Formation-Vorschläge (explizit auf Saisonstart vertagt, eigenes künftiges Feature).
- Kein automatisches Handeln (kein Auto-Verkauf/-Kauf/-Gebot) — alle Sektionen sind reine Entscheidungshilfe, jede
  Aktion bleibt manuell in der echten Kickbase-App (konsistent mit der bisherigen "Autopilot"-Idee im HANDOFF, die
  ebenfalls bewusst nicht umgesetzt ist: bewusst kein schreibender API-Zugriff).
- Investment-Sektion berücksichtigt **bewusst keine Position** — reine Kapitalanlage-Betrachtung, entkoppelt von
  Kaderaufstellung (User-Entscheidung im Brainstorming, passt zur aktuellen Saisonphase).
- Investment-Swaps berücksichtigen **kein Kapital/Leistbarkeit** — wie die Kauf-Kandidaten-Sektion rein
  Prognose-basiert, keine Budget-Filterung.
- Kaderlimit-Hinweis zeigt nur den nackten Status ("Kader voll 17/17"), **keine** Erklärung der
  Konsequenz (Gebote-Löschung) — auf ausdrücklichen User-Wunsch gekürzt.
- Kein neuer Kickbase-API-Call — Transfer-Feed nutzt ausschließlich den bereits im Heavy-Cron gezogenen
  Activity-Feed.

## Architektur

### A) Tab & Navigation

Neuer Tab, Key `"dashboard"`, Label `"Dashboard"`, als **erster** Eintrag in `TABS`/`ACTIVE_TABS` (`App.tsx`).
`readStoredActiveTab()`s Fallback (aktuell `"team"` für neue Sessions ohne `localStorage`-Wert) wird auf
`"dashboard"` geändert — betrifft nur Sessions ohne gespeicherte Präferenz, bestehende Nutzer mit gespeichertem
`activeTab` sind unbetroffen.

### B) Reihenfolge der Sektionen — abhängig vom Kaderlimit

```
wenn own_squad_ids.length < 17:  Kaufen → Verkaufen → Investment → Transfer-Feed
wenn own_squad_ids.length >= 17: Verkaufen → Kaufen → Investment → Transfer-Feed
```

Kaderlimit-Banner ("Kader voll 17/17") erscheint zusätzlich ganz oben, nur wenn `>= 17`.

### C) Verkaufen-Sektion

Alle Spieler aus `data.own_squad_ids` mit `sellSignal(player.ml_prediction, mae) === "verkaufen"` (gleiche `mae`
wie überall sonst, `liveModelMae(data.ml_metrics)`). Kompakte Karte pro Treffer: Name, Position, Marktwert, Prognose
1T (Grund fürs Signal) + 3T als Kontext (gleiche `trendClass`/`trendArrow`-Darstellung wie im Rest der App). Leer:
"Aktuell keine Verkaufskandidaten."

### D) Kaufen-Sektion

Wunschkader-Ziele (`wunschkader.targets`), deren `player_id` aktuell in `data.transfermarkt_listings` auftaucht.
Zeigt die **volle** `TransfermarktCard` (dafür `export function TransfermarktCard` statt lokal in
`TransfermarktTab.tsx`) — kein eigenes, reduziertes Kartenformat. Kein Leistbarkeits-Filter. Leer: "Aktuell keine
Wunschkader-Ziele auf dem Markt."

### E) Investment-Sektion (neu, Position irrelevant)

1. Alle `own_squad_ids`-Spieler nach `ml_prediction_3d` **aufsteigend** sortiert (schlechteste zuerst) → Top 3 als
   "Verkaufen-Kandidaten (Kapitalanlage)".
2. Alle `transfermarkt_listings` nach `ml_prediction_3d` **absteigend** sortiert (beste zuerst) → Top 3 als
   "Kauf-Kandidaten (Kapitalanlage)".
3. Paarung 1:1 (schlechtester eigener ↔ bester Markt, zweitschlechtester ↔ zweitbester, ...) — ein Paar wird nur
   angezeigt, wenn `marktSpieler.ml_prediction_3d - eigenerSpieler.ml_prediction_3d >= ML_PREDICTION_3D_THRESHOLDS.strong`
   (420 000, bestehende Konstante). Reicht der Abstand nicht, wird dieses Paar übersprungen (keine
   Lückenauffüllung mit dem nächsten Kandidaten — maximal 3 Paare, potenziell weniger oder keins).
4. Darstellung je Paar: "Verkaufen: {Name} (Prognose 3T: {Wert}) → Kaufen: {Name} (Prognose 3T: {Wert})". Leer (kein
   Paar erreicht die Schwelle): "Aktuell keine Kapitalanlage-Swaps mit ausreichendem Abstand."

### F) Transfer-Feed-Sektion

Neues Backend: `_build_recent_transfers()` (`dashboard_export.py`, läuft im Heavy-Cron, gleicher Ort wie die
bestehende `activities`-Nutzung für `bid_premium.update_and_load()`). Filtert Typ-15-Einträge, löst
`data.pi`→Spielername (`players_map`), `data.byr`/`data.slr`→Manager-Name (`ranking_rows`); fehlt `byr` oder `slr`,
wird das als `"Kickbase"` (Systemkauf/-verkauf) markiert, analog zur bestehenden Trade-Interpretation in
`manager_budgets.py::_parse_trades()`. **Eigene** Trades (`byr`/`slr` == eigene User-Id) werden rausgefiltert
(stehen bereits in Verkaufen/Kaufen). Schreibt eine großzügige Historie (letzte 72h ab `fetched_at`, nicht nur 24h)
in ein neues Snapshot-Feld `recent_transfers: [{player_id, buyer, seller, price, date}]` — die eigentliche
24h-Grenze wird **client-seitig live** angewendet (`Date.now()` vs. `date`, gleiches Live-Countdown-Prinzip wie beim
Auktions-Status), damit ein Trade nicht allein durch einen leicht daneben liegenden Server-Cutoff vorzeitig aus der
Liste fällt. Darstellung je Eintrag: Spielername, Käufer, Verkäufer (oder "Kickbase"), Preis, relative Zeit
(`formatRelativeTime()`, bereits vorhanden). Leer: "Keine Transfers in den letzten 24 Stunden."

**Neues Snapshot-Feld** → muss in `_assemble_snapshot()` UND `AssembleSnapshotContractTests.EXPECTED_KEYS` ergänzt
werden (bestehender Contract-Test-Mechanismus, verhindert die Fehlerklasse des früheren Weißer-Bildschirm-Vorfalls).

### G) Kaderlimit-Banner

`data.own_squad_ids.length >= 17` → Banner ganz oben: "Kader voll (17/17)". Reiner Read, kein neues Backend-Feld.

## Risiken/offene Verifikation

- **"17 Spieler → alle Gebote werden gelöscht"** ist eine User-Aussage, nicht gegen Kickbase-API/-Dokumentation oder
  einen echten In-App-Beleg verifiziert (anders als z.B. die `status_label`-Codes, die per echtem In-App-Test
  bestätigt wurden). Da der Hinweistext auf User-Wunsch ohnehin auf die nackte Zahl gekürzt wurde ("Kader voll
  17/17", keine Konsequenz-Erklärung mehr), ist das Risiko eines falschen Behauptungstexts entschärft — die reine
  Zählung (`own_squad_ids.length`) ist in jedem Fall korrekt, unabhängig davon, was bei Erreichen tatsächlich passiert.
- `TransfermarktCard`-Export könnte weitere, noch nicht betrachtete lokale Abhängigkeiten aus
  `TransfermarktTab.tsx` mitziehen (z.B. `suggestBid`/`bidHistory`-Prop) — vom Implementierungsplan beim tatsächlichen
  Lesen der Datei zu prüfen, nicht hier im Spec vorweggenommen.

## Verification

- Neue reine Funktionen (`buildDashboardSellCandidates`, `buildDashboardBuyCandidates`, `buildInvestmentSwaps`,
  Transfer-Feed-24h-Filter) unit-testbar wie der Rest von `derive.ts` — TDD, analog zu bestehenden
  `derive.test.ts`-Fällen.
- Backend: neuer Test für `_build_recent_transfers()` (Trade-Filterung, Eigene-Trades-Ausschluss,
  System-Markierung), analog zu bestehenden `dashboard_export.py`-Tests.
- `AssembleSnapshotContractTests` um `recent_transfers` erweitert.
- `npm run typecheck`, `npm run build`, volle Vitest-Suite grün. Backend-Suite (aktuell 226 Tests) weiterhin grün.
- Manuell: Dashboard-Tab mit echten Produktionsdaten öffnen, alle 4 Sektionen + Kaderlimit-Banner-Bedingung
  (aktuellen `own_squad_ids`-Stand gegen 17 prüfen) sichtprüfen.

## Out of Scope (bewusst)

- Aufstellungsplanung (siehe Nicht-Ziele).
- Automatisches Handeln/Bieten.
- Investment-Sektion mit Positions-/Kapital-Filterung.
- Verifikation der "Gebote werden gelöscht"-Behauptung gegen echte Kickbase-Doku/API (siehe Risiken).
