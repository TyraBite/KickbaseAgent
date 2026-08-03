import { test, expect, type ComponentFixtures } from "@playwright/experimental-ct-react";
import PlayerCompareModal from "../src/components/PlayerCompareModal";
import type { Calibration, PlayerRecord } from "../src/types";

// Zwei Fixture-Spieler mit bewusst unterschiedlichen Werten in allen 7
// Vergleichsdimensionen. Die Gewinner sind absichtlich zwischen A und B
// gemischt (nicht "A gewinnt immer alles") - sonst wuerde ein Test bei
// vertauschter Seiten-Logik in CompareRow trotzdem gruen bleiben.
const playerA: PlayerRecord = {
  player_id: "compare-a",
  name: "Anton Alpha",
  position: "Sturm",
  team_name: "SC Beispiel",
  status_code: 1, // -> "Verletzt": A verliert die Fitness-Zeile.
  starting_rank: 1, // niedriger = besser -> A gewinnt Startelf-Rang.
  market_value: 6_000_000, // niedriger = besser -> A verliert Marktwert.
  average_points: 400, // hoeher = besser -> A gewinnt Schnitt.
  ml_prediction: 50_000, // hoeher = besser -> A verliert Prognose 1T.
  // ml_prediction_3d bewusst auf beiden Seiten weggelassen -> null bei
  // beiden -> Tie-Fall fuer die Prognose-3T-Zeile.
};

const playerB: PlayerRecord = {
  player_id: "compare-b",
  name: "Bruno Beta",
  position: "Mittelfeld",
  team_name: "FC Musterstadt",
  status_code: null, // -> "Fit": gewinnt gegen jeden gesetzten Status.
  starting_rank: 5,
  market_value: 3_000_000,
  average_points: 100,
  ml_prediction: 200_000,
};

const players: Record<string, PlayerRecord> = {
  [playerA.player_id]: playerA,
  [playerB.player_id]: playerB,
};

// Eigene, direkt konstruierte Calibration statt ueber buildFixtureSnapshot()
// (deren Default calibration: null waere) - sonst liefert valuation() fuer
// beide Spieler signal: null und die Signal-Zeile koennte NIE einen echten
// Gewinner haben (siehe Task-Brief-Gotcha zu kForPosition()/valuation()).
// global_k=1000, position_k leer -> beide Positionen fallen auf global_k
// zurueck.
const calibration: Calibration = { n: 10, global_k: 1000, position_k: {} };
const thresholds = { good: 1.05, critical: 0.85 };

// Nur zur Doku, nicht Teil der Assertion - Signal-Werte aus valuation():
//   A: round(1000 / (6_000_000 / 400)   * 100) / 100 = 0.07
//   B: round(1000 / (3_000_000 / 100)   * 100) / 100 = 0.03
// -> A gewinnt Signal (hoeher = besser).

function renderModal(mount: ComponentFixtures["mount"]) {
  return mount(
    <PlayerCompareModal
      playerIdA={playerA.player_id}
      playerIdB={playerB.player_id}
      players={players}
      calibration={calibration}
      thresholds={thresholds}
      onClose={() => {}}
    />
  );
}

// DOM-Scoping fuer eine Vergleichszeile: CompareRow rendert
// [valueA-div, label-div, valueB-div] als exakt 3 direkte Kinder desselben
// Grid-Row-divs. Ausgehend vom (eindeutigen) Label finden wir das
// Eltern-Grid und darin die Value-Wrapper an Index 0 und 2.
async function assertWinner(
  component: Awaited<ReturnType<ComponentFixtures["mount"]>>,
  label: string,
  winner: "a" | "b" | null
) {
  const labelDiv = component.getByText(label, { exact: true });
  const row = labelDiv.locator("xpath=..");
  const valueA = row.locator(":scope > div").nth(0);
  const valueB = row.locator(":scope > div").nth(2);

  if (winner === "a") {
    await expect(valueA).toHaveClass(/font-semibold/);
    await expect(valueA).toHaveClass(/text-brand-600/);
    await expect(valueB).not.toHaveClass(/font-semibold/);
    await expect(valueB).not.toHaveClass(/text-brand/);
  } else if (winner === "b") {
    await expect(valueB).toHaveClass(/font-semibold/);
    await expect(valueB).toHaveClass(/text-brand-600/);
    await expect(valueA).not.toHaveClass(/font-semibold/);
    await expect(valueA).not.toHaveClass(/text-brand/);
  } else {
    await expect(valueA).not.toHaveClass(/font-semibold/);
    await expect(valueA).not.toHaveClass(/text-brand/);
    await expect(valueB).not.toHaveClass(/font-semibold/);
    await expect(valueB).not.toHaveClass(/text-brand/);
  }
}

test.describe("PlayerCompareModal - Gewinner-Hervorhebung je Vergleichszeile", () => {
  test("Prognose 1T: hoeherer ml_prediction-Wert gewinnt (Spieler B)", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Prognose 1T", "b");
  });

  test("Prognose 3T: beide Werte fehlen (null) -> keiner gewinnt", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Prognose 3T", null);
  });

  test("Signal: hoeherer Signal-Wert gewinnt (Spieler A)", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Signal", "a");
  });

  test("Marktwert: niedrigerer Wert gewinnt (Spieler B)", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Marktwert", "b");
  });

  test("Startelf-Rang: niedrigerer Rang gewinnt (Spieler A)", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Startelf-Rang", "a");
  });

  test("Fitness-Sonderfall: kein Status (Fit) gewinnt gegen gesetzten Status (Spieler B, 'Fit' schlaegt 'Verletzt')", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Fitness", "b");
  });

  test("Schnitt: hoeherer average_points-Wert gewinnt (Spieler A)", async ({ mount }) => {
    const component = await renderModal(mount);
    await assertWinner(component, "Schnitt", "a");
  });
});
