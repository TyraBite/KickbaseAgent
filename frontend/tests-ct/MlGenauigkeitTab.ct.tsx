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
  });

  test("zeigt Traegheits-Baseline-Erklaertext am Ende der Sektion", async ({ mount }) => {
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
  });
});
