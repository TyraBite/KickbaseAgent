# ML-Horizonte im Frontend sichtbar machen (Prognose 1T/3T) — Design

## Kontext

Das "ML-Horizonte"-Feature (2026-07-31, `docs/superpowers/specs/2026-07-31-ml-horizonte-design.md`) hat eine zweite,
3-Tage-ML-Prognose (`ml_prediction_3d` pro Spieler, `ml_metrics_3d`/`ml_accuracy_trend_3d` im Snapshot) hinzugefügt.
Im Frontend ist sie bisher NICHT direkt sichtbar: `momentumAssessment()` (`frontend/src/lib/derive.ts`) verrechnet
1-Tages-Prognose, 3-Tages-Prognose und MAE zu einer qualitativen Text-Zeile ("Einschätzung": z.B. "Sicher steigend
(+45.230, Modell-Ungenauigkeit ±25.147) — 3-Tage-Trend bestätigt (+112.400)"), verdrahtet in 4 Detail-Modals
(EigenesTeam, Wunschkader, Spekulation, Transfermarkt). Der rohe 3-Tages-Wert erscheint sonst nirgends — weder auf
Kartenfronten noch in Tabellen. `ml_metrics_3d`/`ml_accuracy_trend_3d` werden zwar in Firestore geschrieben, haben
aber keine eigene UI-Anzeige (Modell-Tracking-Tab zeigt nur 1-Tages-Genauigkeit).

User-Feedback (`feedback/current` in Firestore, Item vom 2026-08-01): die 3-Tages-Prognose soll direkt als Zahl
sichtbar sein statt nur über die "Einschätzung" relativiert zu werden, beide Felder umbenannt in "Prognose 1T"/
"Prognose 3T", 3T mindestens auf der Spekulation-Kartenfront, und Modell-Tracking soll die 3T-Genauigkeit ebenfalls
zeigen.

Entschieden im Brainstorming (siehe Chat, 2026-08-01):

- "Einschätzung" wird ersatzlos durch die zwei rohen Zahlen ersetzt, keine Konfidenz-Text-Variante bleibt erhalten.
- 3T wird konsequent überall ergänzt, wo heute schon 1T sichtbar ist (nicht nur Detail-Modals) — inkl.
  EigenesTeam-Kartenfront und einer neuen Transfermarkt-Tabellenspalte.
- WunschkaderTab bekommt neu Prognose-1T/3T-Zeilen im Detail-Modal (hatte vorher gar keine rohe ML-Prognose-Anzeige,
  nur die jetzt wegfallende Einschätzung).
- Modell-Tracking bekommt einen zur 1T-Ansicht strukturgleichen zweiten Block (Kopf-an-Kopf-Kacheln + Trend-Chart)
  für 3T.

## Nicht-Ziele

- Keine Änderung an `sellSignal()` (Kauf/Verkauf-Empfehlung in EigenesTeam) — eigene, unabhängige Logik von
  `momentumAssessment()`, nutzt weiterhin nur die 1-Tages-Prognose + MAE.
- Keine neuen Backend-/Firestore-Felder — `ml_prediction_3d`/`ml_metrics_3d`/`ml_accuracy_trend_3d` existieren
  bereits (seit dem ML-Horizonte-Feature), dieses Vorhaben ist rein Frontend-Anzeige.
- Keine eigene 3T-Kalibrierung der Trend-Pfeil-Schwellen (`ML_PREDICTION_THRESHOLDS`) in diesem Vorhaben — siehe
  Abschnitt "Trend-Pfeil für Prognose 3T" unten.

## Datenmodell: `PlayerRow` um `ml_prediction_3d` erweitern

`frontend/src/lib/derive.ts`: `PlayerRow`-Interface bekommt ein neues Feld `ml_prediction_3d: number | null`,
gefüllt in `buildPlayerRow()` aus `player.ml_prediction_3d ?? null` (identisches Muster zum bestehenden
`ml_prediction`-Feld direkt darüber). Da `TransfermarktRow`, `SpekulationRow`, `EigenesTeamRow`, `AlleSpielerRow`
alle von `PlayerRow` erben bzw. darauf aufbauen, steht das Feld danach überall automatisch zur Verfügung — die
bisherigen Ad-hoc-Lookups `players[row.player_id]?.ml_prediction_3d` (aktuell 4 Stellen, ausschließlich als
Argument für `momentumAssessment()`) entfallen ersatzlos.

`liveModelMae()` bleibt unverändert (ist bereits generisch auf `MlMetrics | null` typisiert) — für die 3T-MAE wird
es einfach zusätzlich mit `data.ml_metrics_3d` statt `data.ml_metrics` aufgerufen.

**Entfernt**: `momentumAssessment()`, `MomentumAssessment`-Interface, `MomentumConfidence`-Type — nach Umbau aller 4
Aufrufstellen ungenutzt (letzte verbliebene Referenz). Der Kommentar in `sellSignal()`, der auf die geteilte
"unsicher"/"unklar"-Schwelle mit `momentumAssessment()` verweist, wird angepasst (kein Cross-Reference mehr auf eine
gelöschte Funktion).

## Trend-Pfeil für Prognose 3T

`trendArrow()`/`trendClass()` (bestehende Helper, `format.ts`) brauchen zur Einfärbung Schwellenwerte
(`ML_PREDICTION_THRESHOLDS`, aktuell `{flat: 20_000, strong: 100_000}` pro Tab-Datei dupliziert) — diese sind aus
der 1-Tages-Verteilung kalibriert. Eine 3-Tage-Prognose ist strukturell größer (kumulierte Bewegung über 3 Tage),
dieselben Schwellen würden sie zu oft als "stark" markieren. Da das 3-Tage-Signal erst seit 2026-07-31 läuft, gibt
es noch keine belastbare eigene Verteilung. Prognose 3T wird deshalb vorerst **ohne** `trendArrow`/`trendClass`
dargestellt — reine Zahl mit Vorzeichen (`fmtSigned`), optional MAE in Klammern, kein Pfeil/keine Farbe. Sobald
genug 3T-Historie vorliegt, kann eine eigene `ML_PREDICTION_3D_THRESHOLDS`-Konstante nachgezogen werden (nicht Teil
dieses Vorhabens).

## Pro-Tab-Änderungen

### EigenesTeamTab.tsx

`MlPredictionRow` (aktuell `{value, mae}` → eine `<Row label="ML-Prognose">`) wird erweitert auf
`{value1d, mae1d, value3d, mae3d}` und rendert zwei `<Row>`-Elemente: "Prognose 1T" (mit Pfeil/Farbe, wie bisher)
und "Prognose 3T" (reine Zahl, siehe oben). Die Komponente wird unverändert an 4 Stellen weiterverwendet:
`PlayerCard`, `WunschkaderWatchlistCard` (Kartenfronten — `mae1d`/`mae3d` dort `undefined`, wie bisher schon bei
`mae`) und `PlayerDetailModal`, `WatchlistDetailModal` (mit MAE). In beiden Detail-Modals entfällt der
`momentumAssessment(...)`-Aufruf + die `Einschätzung`-Zeile ersatzlos.

### TransfermarktTab.tsx

Tabellenspalte `{key: "ml_prediction", label: "ML-Prognose", ...}` wird umbenannt zu "Prognose 1T". Direkt danach
eine neue Spalte `{key: "ml_prediction_3d", label: "Prognose 3T", ...}` (reine Zahl, kein Pfeil). Sort-Dropdown-
Option `{value: "ml", label: "ML-Prognose"}` wird zu "Prognose 1T" umbenannt (Sortierschlüssel unverändert, sortiert
weiterhin nach `ml_prediction`). Im Detail-Modal: bestehende Zeile umbenannt + neue "Prognose 3T"-Zeile (mit MAE),
`momentumAssessment(...)`-Aufruf + `Einschätzung`-Zeile entfallen.

### SpekulationTab.tsx

Kartenfront (`SpekulationCard`) bekommt eine neue "Prognose 3T"-Zeile direkt unter der bestehenden (jetzt "Prognose
1T" benannten) ML-Prognose-Zeile. Tabelle (`SpekulationTable`) bekommt analog eine neue Spalte. Detail-Modal:
bestehende Zeile umbenannt + neue Zeile mit MAE, `momentumAssessment(...)`-Aufruf + `Einschätzung`-Zeile entfallen.

### WunschkaderTab.tsx

Hatte bisher gar keine rohe ML-Prognose-Anzeige (weder Karte noch Modal), nur die jetzt wegfallende
`Einschätzung`-Zeile im `DetailModal`. Neu: zwei `<Row>`-Zeilen "Prognose 1T"/"Prognose 3T" (mit MAE) an derselben
Stelle, wo bisher die `momentumAssessment(...)`-Zeile stand, direkt aus `target.player_id`s `PlayerRow`-Werten (die
seit der `PlayerRow`-Erweiterung oben bereits `ml_prediction`/`ml_prediction_3d` mitführen).

## Modell-Tracking (`MlGenauigkeitTab.tsx`)

Der bestehende "Kopf-an-Kopf"-Kachelblock (Zeilen ~79–119) und die `TrendChart`-Komponente (Zeilen ~145–319) werden
auf ihre Eingabedaten parametrisiert (`metrics: MlMetrics`, `trend: MlAccuracyTrendEntry[]`, plus ein `heading`-Text)
statt fest auf `data.ml_metrics`/`data.ml_accuracy_trend` zuzugreifen. Beide werden danach zweimal gerendert:

1. "Kopf-an-Kopf (1-Tages-Horizont)" mit `data.ml_metrics`/`data.ml_accuracy_trend` (unverändertes Verhalten).
2. "Kopf-an-Kopf (3-Tages-Horizont)" mit `data.ml_metrics_3d`/`data.ml_accuracy_trend_3d` (neu) — nur gerendert,
   wenn `data.ml_metrics_3d` vorhanden ist (Cold-Start-Guard analog zum bestehenden `if (!metrics)`-Check).

Das vermeidet ~150 Zeilen Copy-Paste (JSX + Chart-Berechnungslogik) und hält beide Horizonte konsistent, falls
später ein drittes Feld dazukommt. Keine Änderung an `bidPremiumSection` (unabhängig von ML-Metriken, siehe
bestehender Kommentar im Code, warum das nicht hinter dem `!metrics`-Guard hängen darf).

## Verification

- `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` (Standard-Verifikationsschritt dieses Repos,
  kein `npm install` im Haupt-Checkout, siehe HANDOFF.md/Warnings).
- Backend-Testsuite (`python3 -m unittest discover -s tests`) bleibt unberührt (reine Frontend-Änderung), trotzdem
  vor Commit laufen lassen (Standard-Vorgehen dieses Repos vor jedem Push).
- Manuelle Live-Verifikation im Browser: alle 4 Tabs (Karten + Tabellen wo zutreffend) zeigen "Prognose 1T"/
  "Prognose 3T" statt "ML-Prognose"/"Einschätzung"; Modell-Tracking zeigt zwei Kopf-an-Kopf-Blöcke.
- `feedback/current`-Item (Firestore, 2026-08-01, "3T Prediction anzeigen …") nach Live-Verifikation auf
  `status: "done"` setzen (Read-Modify-Write gegen den frischen Serverstand, etabliertes Muster aus
  `FeedbackTab.tsx`).
- HANDOFF.md nach Abschluss aktualisieren (Completed-Eintrag).

## Out of Scope (bewusst)

- Eigene 3T-Trend-Pfeil-Schwellen (siehe oben).
- Änderung an `sellSignal()`/Kauf-Verkauf-Logik.
- Die separate, bereits als eigene Spec existierende 3-Tage-Hyperparameter-Suche
  (`docs/superpowers/specs/2026-08-01-ml-3d-tuning-design.md`, unabhängiges Vorhaben, nicht Teil dieser Session).
