import type {
  DashboardSnapshot,
  MlAccuracyTrendEntry,
  MlMetrics,
  PlayerRecord,
} from "../types";

function player(
  overrides: Partial<PlayerRecord> & Pick<PlayerRecord, "player_id" | "name" | "position">
): PlayerRecord {
  return {
    team_name: null,
    status_code: null,
    starting_rank: null,
    market_value: null,
    average_points: null,
    ...overrides,
  };
}

// Marktwert/Punkte der drei "close"-Spieler liegen absichtlich nah am Ziel
// (werden dadurch automatisch die 3 Vorschlaege - suggestReplacements()
// nimmt immer die 3 naechsten). "searchOnly" liegt absichtlich weit weg,
// damit er NICHT unter den 3 Vorschlaegen landet und nur ueber die
// Freitextsuche auffindbar ist.
export const FIXTURE_PLAYERS = {
  target: player({
    player_id: "p-target-abwehr", name: "Kai Zielspieler", position: "Abwehr",
    market_value: 5_000_000, average_points: 180,
  }),
  suggestion1: player({
    player_id: "p-abwehr-close-1", name: "Lukas Nahstand", position: "Abwehr",
    market_value: 5_100_000, average_points: 175,
  }),
  suggestion2: player({
    player_id: "p-abwehr-close-2", name: "Jonas Nahstand", position: "Abwehr",
    market_value: 4_800_000, average_points: 190,
  }),
  suggestion3: player({
    player_id: "p-abwehr-close-3", name: "Peter Mittelnah", position: "Abwehr",
    market_value: 5_500_000, average_points: 165,
  }),
  searchOnly: player({
    player_id: "p-abwehr-weitweg", name: "Werner Weitweg", position: "Abwehr",
    market_value: 500_000, average_points: 20,
  }),
  // Kartenkopf-Wrap-Regression (2026-08-06): bewusst ein deutlich laengerer
  // Name als die uebrigen Fixtures, um bei knapper Kartenbreite (Drag-Handle
  // reserviert Platz rechts oben) sicher ueber die verfuegbare Zeilenbreite
  // hinauszulaufen.
  longName: player({
    player_id: "p-abwehr-langername", name: "Maximilian Langername", position: "Abwehr",
    market_value: 5_050_000, average_points: 178,
  }),
  // Bug-1-Regression (Task 3) braucht bewusst einen NICHT-Sturm-Spieler als
  // Haupt-Testsubjekt: der entfernte Code hatte "Sturm" als Default-Position -
  // ein Test, der nur nach einem Sturm-Spieler sucht, waere auch mit dem
  // alten, kaputten Code zufaellig gruen gewesen.
  torwart: player({
    player_id: "p-tw-frei", name: "Torsten Torwart", position: "Torwart",
    market_value: 2_000_000, average_points: 90,
  }),
  sturm: player({
    player_id: "p-sturm-frei", name: "Stefan Stürmer", position: "Sturm",
    market_value: 8_000_000, average_points: 220,
  }),
  mittelfeld: player({
    player_id: "p-mf-frei", name: "Micha Mittelfeld", position: "Mittelfeld",
    market_value: 3_000_000, average_points: 140,
  }),
};

// Minimal, aber vollstaendig typkorrekt gegen MlMetrics/MlAccuracyTrendEntry -
// NUR fuer Tests, die MlGenauigkeitTab mit sichtbarem Chart-Inhalt brauchen
// (Task 8/9: die E2E-Touch-vs-Swipe-Regression). Bewusst NICHT Default in
// buildFixtureSnapshot() (die bleibt ml_metrics:null) - explizit per
// overrides anfordern.
export const FIXTURE_ML_METRICS: MlMetrics = {
  model_type: "RandomForest",
  rmse: 500_000, mae: 300_000, r2: 0.6, sign_accuracy: 62.5,
  train_rows: 1000, test_rows: 200,
  per_model: {
    RandomForest: {
      rmse: 500_000, mae: 300_000, r2: 0.6, sign_accuracy: 62.5,
      mae_given_correct_sign: 250_000, baseline_sign_accuracy: 55.0, baseline_mae: 340_000,
      reversal_sign_accuracy: 48.0, reversal_n: 12,
    },
    HistGradientBoosting: {
      rmse: 520_000, mae: 310_000, r2: 0.58, sign_accuracy: 60.1,
      mae_given_correct_sign: 260_000, baseline_sign_accuracy: 55.0, baseline_mae: 340_000,
      reversal_sign_accuracy: 46.0, reversal_n: 12,
    },
  },
};
export const FIXTURE_ML_TREND: MlAccuracyTrendEntry[] = [
  { date: "2026-07-20", RandomForest: 58.2, HistGradientBoosting: 55.0 },
  { date: "2026-07-27", RandomForest: 61.4, HistGradientBoosting: 59.8 },
  { date: "2026-08-02", RandomForest: 62.5, HistGradientBoosting: 60.1 },
];

export function buildFixtureSnapshot(overrides?: Partial<DashboardSnapshot>): DashboardSnapshot {
  const players = Object.fromEntries(Object.values(FIXTURE_PLAYERS).map((p) => [p.player_id, p]));
  return {
    fetched_at: "2026-08-02T06:00:00.000Z",
    generated_at: "2026-08-02T06:05:00.000Z",
    players,
    calibration: null,
    transfermarkt_listings: [],
    // suggestion2 ist "Eigener Kader" (beweist, dass scoreReplacementPool()
    // sowohl Frei- als auch Eigener-Kader-Spieler als Kandidaten zulaesst).
    own_squad_ids: [FIXTURE_PLAYERS.suggestion2.player_id],
    owned_by: {},
    wunschkader_targets: [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }],
    ligaanalyse: [],
    ml_metrics: null,
    ml_accuracy_trend: null,
    signal_thresholds: { good: 1.1, critical: 0.9 },
    own_budget_exact: 10_000_000,
    own_available_budget: null,
    ...overrides,
  };
}
