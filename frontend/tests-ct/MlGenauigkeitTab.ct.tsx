import { test, expect } from "@playwright/experimental-ct-react";
import MlGenauigkeitTab from "../src/components/MlGenauigkeitTab";
import { buildFixtureSnapshot, FIXTURE_ML_METRICS, FIXTURE_ML_TREND } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("MlGenauigkeitTab - Baseline-/Trendwende-Anzeige", () => {
  test("zeigt Baseline-Delta, Trendwende-Trefferquote mit n, und MAE-bei-richtiger-Richtung", async ({ mount }) => {
    const metrics = {
      ...FIXTURE_ML_METRICS,
      realized_by_model: {
        RandomForest: {
          realized_30d: {
            n: 120, sign_accuracy: 72.5, mae: 25000,
            mae_given_correct_sign: 18000,
            baseline_sign_accuracy: 60.0, baseline_mae: 30000,
            reversal_sign_accuracy: 55.0, reversal_n: 18,
          },
          realized_7d: null,
        },
        HistGradientBoosting: {
          realized_30d: {
            n: 120, sign_accuracy: 70.0, mae: 26000,
            mae_given_correct_sign: 19000,
            baseline_sign_accuracy: 60.0, baseline_mae: 30000,
            reversal_sign_accuracy: 50.0, reversal_n: 18,
          },
          realized_7d: null,
        },
      },
    };
    const snapshot = buildFixtureSnapshot({ ml_metrics: metrics, ml_accuracy_trend: FIXTURE_ML_TREND });

    const component = await mount(<MlGenauigkeitTab data={snapshot} />);

    // Baseline-Delta: 72.5 - 60.0 = +12.5pp
    await expect(component.getByText(/\+12\.5%/)).toBeVisible();
    // Trendwende mit Stichprobengroesse (beide Modell-Karten haben hier
    // absichtlich denselben reversal_n=18 - .first() vermeidet die
    // Playwright-Strict-Mode-Ambiguitaet, die 55.0%-Assertion daneben bleibt
    // eindeutig einem einzelnen Modell zugeordnet).
    await expect(component.getByText(/n=18/).first()).toBeVisible();
    await expect(component.getByText(/55\.0%/)).toBeVisible();
    // MAE bei richtiger Richtung
    await expect(component.getByText(/18000|18\.000|18,000/)).toBeVisible();
    // ggue. Traegheits-MAE (Finding 2, finaler Review) - beide Modell-Karten
    // haben hier absichtlich denselben baseline_mae=30000, .first() vermeidet
    // dieselbe Strict-Mode-Ambiguitaet wie bei n=18 oben.
    await expect(component.getByText(/30000|30\.000|30,000/).first()).toBeVisible();
  });

  test("zeigt '– (noch keine Baseline-Daten)' statt eines erfundenen n=0, wenn fuer das Fenster noch nie eine Baseline berechnet wurde", async ({
    mount,
  }) => {
    // Finding 1 (finaler Review): baseline_sign_accuracy: null bedeutet "fuer
    // dieses Fenster wurde noch NIE eine Baseline berechnet" (z.B. jeder
    // Tages-Doc vor dem Backfill faellt ueber _summarize_from_daily()s
    // `.get(..., None)` hierauf zurueck) - NICHT "die Baseline lag im Fenster
    // nie falsch". Die alte Anzeige "noch keine Faelle im Fenster (n=0)" war
    // in diesem Fall eine erfundene Tatsache (n=0 bedeutet hier "unbekannt",
    // nicht "null beobachtete Trendwenden").
    const metrics = {
      ...FIXTURE_ML_METRICS,
      realized_by_model: {
        RandomForest: {
          realized_30d: {
            n: 5, sign_accuracy: 60.0, mae: 25000, mae_given_correct_sign: null,
            baseline_sign_accuracy: null, baseline_mae: null, reversal_sign_accuracy: null, reversal_n: 0,
          },
          realized_7d: null,
        },
        HistGradientBoosting: { realized_30d: null, realized_7d: null },
      },
    };
    const snapshot = buildFixtureSnapshot({ ml_metrics: metrics, ml_accuracy_trend: FIXTURE_ML_TREND });
    const component = await mount(<MlGenauigkeitTab data={snapshot} />);
    await expect(component.getByText(/Trägheits-Annahme/)).toBeVisible();
    await expect(component.getByText(/– \(noch keine Baseline-Daten\)/)).toBeVisible();
    await expect(component.getByText(/noch keine Fälle im Fenster/)).toHaveCount(0);
  });

  test("zeigt weiterhin 'noch keine Faelle im Fenster (n=0)' wenn die Baseline berechnet wurde, aber im Fenster nie falsch lag", async ({
    mount,
  }) => {
    // Schliesst die im finalen Review geparkte Luecke: der vorherige Test
    // testete baseline_sign_accuracy===null UND reversal_n===0 gemeinsam -
    // nie isoliert, dass der reine "0 Trendwenden, aber Baseline WURDE
    // berechnet"-Fall weiterhin die alte, gueltige Meldung zeigt. reversal_n
    // ist hier bewusst 0 (nicht >0): laut _finalize_score_counts() in
    // market_predictor.py ist reversal_sign_accuracy IMMER gesetzt, sobald
    // reversal_n (n_baseline_wrong) > 0 ist - die einzige reale Kombination
    // mit reversal_sign_accuracy===null ist reversal_n===0 (Baseline war im
    // Fenster kein einziges Mal falsch).
    const metrics = {
      ...FIXTURE_ML_METRICS,
      realized_by_model: {
        RandomForest: {
          realized_30d: {
            n: 40, sign_accuracy: 80.0, mae: 25000, mae_given_correct_sign: 18000,
            baseline_sign_accuracy: 95.0, baseline_mae: 30000, reversal_sign_accuracy: null, reversal_n: 0,
          },
          realized_7d: null,
        },
        HistGradientBoosting: { realized_30d: null, realized_7d: null },
      },
    };
    const snapshot = buildFixtureSnapshot({ ml_metrics: metrics, ml_accuracy_trend: FIXTURE_ML_TREND });
    const component = await mount(<MlGenauigkeitTab data={snapshot} />);
    await expect(component.getByText(/noch keine Fälle im Fenster \(n=0\)/)).toBeVisible();
    await expect(component.getByText(/– \(noch keine Baseline-Daten\)/)).toHaveCount(0);
  });
});
