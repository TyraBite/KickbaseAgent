# ML-Horizonte (3-Tage-Prognose + Konfidenz-Signal) — Design

## Kontext

`market_predictor.py` prognostiziert aktuell ausschließlich die Marktwertänderung für den NÄCHSTEN Tag (`FEATURES`/`TARGET = mv_target_clipped`). Für Verkaufszeitpunkt-Entscheidungen (eigener Kader/Wunschkader) und Kaufzeitpunkt-Entscheidungen (Spekulation/Transfermarkt) reicht ein reiner 1-Tages-Blick oft nicht: eine kurzfristig fallende Prognose kann sich innerhalb weniger Tage wieder umkehren, und eine kleine Prognose kann innerhalb der ohnehin vorhandenen Modell-Ungenauigkeit (MAE) untergehen — die Richtung selbst ist dann nicht verlässlich.

**Ziel:** einen zusätzlichen 3-Tage-Horizont einbauen (primärer Indikator bleibt der 1-Tages-Wert) und eine kombinierte Konfidenz-Einschätzung, die sowohl den bestehenden binären "Jetzt verkaufen"/"Noch halten"-Trigger als auch neue Detail-Texte in vier Tabs beeinflusst.

## Scope

- Neuer 3-Tage-Prognose-Horizont im Backend (`market_predictor.py`), inkl. eigenem Walk-Forward-Backtest und eigenem Live-Genauigkeits-Tracking (Horizont-Dimension in bestehender Infrastruktur, nicht dupliziert).
- Neue kombinierte Konfidenz-/Momentum-Einschätzung im Frontend (`derive.ts`), die 1-Tages-Prognose (primär), 3-Tages-Prognose (Relativierer) und Modell-MAE (Unsicherheit) zusammenführt.
- Bestehendes `sellSignal()` wird von binär auf 3-wertig erweitert (`"halten" | "verkaufen" | "unklar"`), Trigger ändert sich (nicht nur der Anzeigetext).
- **Out of Scope**: keine Änderung an Spekulations-Sortierung/-Filterung (bleibt ROI-basiert); keine Erweiterung des "Modell-Tracking"-Tabs um eine 3-Tage-Ansicht (die neue `ml_metrics_3d`/Tracking-Infrastruktur wird nur intern für Live-Modellauswahl gebraucht, UI-Anzeige dafür ist ein möglicher späterer Task); keine 7-Tage- oder weitere Horizonte (bewusst nur 1+3).

## Backend-Architektur

**Neues Trainings-Ziel**: `_engineer_features()` bekommt eine zweite Zielspalte `mv_target_3d_clipped` — identische Berechnung wie das bestehende `mv_target`/`mv_target_clipped` (`df.groupby("player_id")["mv"].shift(-1)` → Delta → IQR-Clipping), nur mit `.shift(-3)` statt `.shift(-1)`. Gleiche `FEATURES`-Liste für beide Ziele (inkl. der heute frisch eingebauten Fitness-Features) — kein neuer Datenbedarf, der Corpus liefert die 3-Tage-später-Werte bereits mit.

**Zweiter Modell-Fit**: `predict_market_value_changes()` ruft `_build_candidates()`/`_train_and_evaluate()` ein zweites Mal auf, trainiert auf `mv_target_3d_clipped` statt `mv_target_clipped`. Eigene Live-Modellauswahl (`_select_live_model()`, generalisiert um einen `horizon_days`-Parameter statt dupliziert) — das 3-Tage-Ziel kann ein anderes Modell "gewinnen" als das 1-Tage-Ziel.

**Zweiter Backtest**: `_walk_forward_backtest()` läuft zusätzlich für `mv_target_3d_clipped`, bevor die 3-Tage-Prognose als vertrauenswürdig gilt — Regression: 1-Tage-Backtest bleibt unverändert, das ist ein zusätzlicher, kein ersetzender Lauf.

**players-Map**: neues Feld `ml_prediction_3d` (analog `ml_prediction`), nur gesetzt wenn das 3-Tage-Modell für diesen Spieler eine Prognose liefert.

## Genauigkeits-Tracking-Erweiterung

`ml_prediction_log`/`ml_accuracy_daily` bekommen ein neues Feld `horizon_days` (`1` oder `3`) als Teil des Doc-Keys (z.B. `{date}_{player_id}_{model_type}_{horizon_days}` bzw. `{date}_{model_type}_{horizon_days}`) — verhindert Kollisionen zwischen den beiden Horizonten in derselben Collection. Bestehende Auswertungsfunktionen (`_build_daily_accuracy_updates`, `_realized_by_model_from_daily`, `_trend_from_daily`, `_select_live_model`) werden um einen `horizon_days`-Parameter generalisiert statt dupliziert — für Horizont 3 vergleicht die Auswertung eine vor 3 Tagen geloggte Prognose mit dem heutigen Ist-Wert (statt vor 1 Tag), sonst identische Logik.

**Snapshot**: neues Top-Level-Feld `ml_metrics_3d` (gleiche `MlMetrics`-Struktur wie das bestehende `ml_metrics`, nur für Horizont 3) — rein additiv, bestehendes `ml_metrics` bleibt unverändert. Dient primär der internen Live-Modellauswahl für den 3-Tage-Horizont; eine UI-Anzeige im Modell-Tracking-Tab ist bewusst nicht Teil dieser Spec (siehe Out of Scope).

## Frontend: Konfidenz-/Momentum-Einschätzung

Neue Funktion in `derive.ts`:

```ts
export type MomentumConfidence = "sicher" | "wahrscheinlich" | "unsicher";

export interface MomentumAssessment {
  confidence: MomentumConfidence;
  direction: "steigend" | "fallend";
  agreesWith3d: boolean | null; // null wenn keine 3-Tage-Prognose vorhanden
  label: string; // fertiger deutscher Text fuer die Detail-Anzeige
}

export function momentumAssessment(
  prediction1d: number | null,
  prediction3d: number | null,
  mae: number | null
): MomentumAssessment | null
```

**Konfidenz-Stufen** (bezogen auf die 1-Tages-Prognose, primärer Indikator):
- `|prediction1d| > 2 × mae` → `"sicher"`
- `mae < |prediction1d| ≤ 2 × mae` → `"wahrscheinlich"`
- `|prediction1d| ≤ mae` → `"unsicher"` — die Richtung selbst ist nicht verlässlich

**3-Tage als Relativierer** (nur Text, kein Trigger): stimmt das Vorzeichen von `prediction3d` mit `prediction1d` überein → Text bestätigt ("3-Tage-Trend bestätigt das"); stimmt es nicht überein → Warnhinweis ("3-Tage-Trend zeigt allerdings [X] — evtl. nur kurzfristiges Rauschen").

Beispiel-Ausgabe (`prediction1d=+15000, mae=25000, prediction3d=+40000`):
> "Unsicher steigend (+15.000, Modell-Ungenauigkeit ±25.000) — 3-Tage-Trend bestätigt (+40.000)"

`mae` kommt aus dem bereits vorhandenen `liveModelMae(data.ml_metrics)` (1-Tages-Modell-MAE — die Unsicherheit bezieht sich auf das Modell, das die primäre 1-Tages-Prognose erzeugt hat, nicht auf das 3-Tage-Modell).

**Anzeige**: `momentumAssessment()`s `label` wird als neue Zeile in allen vier bestehenden Detail-Modals ergänzt (EigenesTeamTab, WunschkaderTab, SpekulationTab, TransfermarktTab) — keine Änderung an Listen-/Kachel-Ansichten außer der `sellSignal()`-Badge (siehe unten). Keine Änderung an Spekulations-Sortierung/-Filterung.

## `sellSignal()`-Umbau (einziger betroffener Trigger)

Aktuell (`derive.ts`, einzige Nutzung: `buildEigenesTeamSplit()` → `EigenesTeamRow.sell_signal` → Badge in `EigenesTeamTab.tsx`, 2 Render-Stellen: Kachel + Detail):

```ts
export function sellSignal(mlPrediction: number | null | undefined): "halten" | "verkaufen" {
  return (mlPrediction ?? 0) > 0 ? "halten" : "verkaufen";
}
```

**Neu:**

```ts
export function sellSignal(
  mlPrediction: number | null | undefined,
  mae: number | null
): "halten" | "verkaufen" | "unklar" {
  const pred = mlPrediction ?? 0;
  if (mae !== null && Math.abs(pred) <= mae) return "unklar";
  return pred > 0 ? "halten" : "verkaufen";
}
```

`buildEigenesTeamSplit()` bekommt einen neuen Parameter `mae: number | null`, durchgereicht von `liveModelMae(data.ml_metrics)` (bereits an anderer Stelle in `EigenesTeamTab.tsx` berechnet — nur die Aufruf-Reihenfolge muss angepasst werden, kein neuer Berechnungsweg).

**Badge-Farben neu verteilt** (bewusste, im Vorfeld abgestimmte Verhaltensänderung): `halten` = grün (`tone="good"`, unverändert), `unklar` = gelb (`tone="warn"`, übernimmt die bisherige "verkaufen"-Farbe), `verkaufen` = jetzt rot (`tone="crit"`, vorher gelb) — semantisch stimmiger: Rot ist jetzt reserviert für die tatsächlich konfidente Verkaufsempfehlung, Gelb für "nicht eindeutig".

## Testing

- Backend: TDD wie gewohnt (`python3 -m unittest discover -s tests`). Neue/generalisierte Funktionen brauchen Tests für beide Horizonte (1 und 3), insbesondere die Doc-Key-Kollisionsfreiheit zwischen den Horizonten in `ml_prediction_log`/`ml_accuracy_daily`.
- Frontend: `tsc --noEmit` (kein Test-Runner vorhanden, wie im Rest des Projekts). `momentumAssessment()`/neues `sellSignal()` sind reine Funktionen — falls ein Test-Setup zu diesem Zeitpunkt existiert, wären sie die naheliegendsten Kandidaten für Unit-Tests; aktuell nicht vorhanden, daher manuelle Verifikation gegen konkrete Beispiel-Werte im Plan.

## Self-Review

- Platzhalter-Scan: keine TBD/TODO.
- Konsistenz: `sellSignal()`s neuer Trigger-Schwellwert (`|pred| ≤ mae` → "unklar") ist identisch zur "unsicher"-Schwelle in `momentumAssessment()` — beide Stellen nutzen dieselbe Definition von "Konfidenz", keine widersprüchliche zweite Definition eingeführt.
- Scope-Check: fokussiert auf EIN zusammenhängendes Feature (3-Tage-Horizont + darauf aufbauende Konfidenz-Signale), keine Aufteilung in mehrere Specs nötig — analog zum heutigen Fitness-Historie-Vorgehen (Pipeline+Read+ML-Integration in einem Zug).
