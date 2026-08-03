import { test, expect } from "@playwright/experimental-ct-react";
import DashboardTab from "../src/components/DashboardTab";
import { buildFixtureSnapshot } from "../src/test-fixtures/dashboardSnapshot.fixture";
import type { PlayerRecord, RawWunschkaderTarget } from "../src/types";
import type { TransfermarktRow } from "../src/lib/derive";

// Ein einzelner echter Spieler mit gesetzter ml_prediction reicht als
// Verkaufskandidat (buildDashboardSellCandidates() filtert auf
// ml_prediction !== null und nimmt die Top 3). Fuer den 17/17-Kaderlimit-
// Test wird derselbe Spieler mit 16 zusaetzlichen own_squad_ids kombiniert,
// die NICHT in `players` existieren - buildDashboardSellCandidates() droppt
// diese IDs still (siehe derive.ts), das Ergebnis bleibt exakt 1 Karte.
const SELL_PLAYER: PlayerRecord = {
  player_id: "p-sell",
  name: "Vera Verkauf",
  position: "Sturm",
  team_name: null,
  status_code: null,
  starting_rank: null,
  market_value: 5_000_000,
  average_points: 100,
  ml_prediction: -80_000,
};

const BUY_ROW: TransfermarktRow = {
  player_id: "p-buy",
  name: "Bruno Kaufen",
  position: "Mittelfeld",
  team_name: null,
  status_label: null,
  starting_rank: null,
  market_value: 4_000_000,
  market_value_change_7d: null,
  market_value_low_92d: null,
  market_value_high_92d: null,
  average_points: 120,
  fairwert: null,
  signal: null,
  ml_prediction: 50_000,
  ml_prediction_3d: 60_000,
  price: 4_200_000,
  price_delta_pct: null,
  offering_username: null,
  is_system_offer: true,
  auction_status: "läuft",
  auction_remaining_seconds: 999_999,
  auction_urgent: false,
  auction_critical: false,
  auction_expires_at: null,
};

const WUNSCHKADER_TARGETS: RawWunschkaderTarget[] = [{ player_id: BUY_ROW.player_id, role: "Starter" }];

const NOW = Date.parse("2026-08-03T12:00:00.000Z");

function padIds(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `pad-${i + 2}`);
}

function buildData(ownSquadIds: string[]) {
  return buildFixtureSnapshot({
    players: { [SELL_PLAYER.player_id]: SELL_PLAYER },
    own_squad_ids: ownSquadIds,
  });
}

test.describe("DashboardTab - Sektionsreihenfolge nach Kaderlimit", () => {
  test("Kader voll (17/17): Verkaufen erscheint vor Kaufen", async ({ mount }) => {
    const data = buildData([SELL_PLAYER.player_id, ...padIds(16)]);
    expect(data.own_squad_ids.length).toBe(17);

    const component = await mount(
      <DashboardTab data={data} wunschkader={{ targets: WUNSCHKADER_TARGETS }} transfermarktRows={[BUY_ROW]} now={NOW} />
    );

    const headings = await component.locator("h3").allTextContents();
    expect(headings.indexOf("Verkaufen")).toBeGreaterThanOrEqual(0);
    expect(headings.indexOf("Kaufen")).toBeGreaterThanOrEqual(0);
    expect(headings.indexOf("Verkaufen")).toBeLessThan(headings.indexOf("Kaufen"));
  });

  test("Kader nicht voll (<17): Kaufen erscheint vor Verkaufen", async ({ mount }) => {
    const data = buildData([SELL_PLAYER.player_id]);
    expect(data.own_squad_ids.length).toBeLessThan(17);

    const component = await mount(
      <DashboardTab data={data} wunschkader={{ targets: WUNSCHKADER_TARGETS }} transfermarktRows={[BUY_ROW]} now={NOW} />
    );

    const headings = await component.locator("h3").allTextContents();
    expect(headings.indexOf("Kaufen")).toBeGreaterThanOrEqual(0);
    expect(headings.indexOf("Verkaufen")).toBeGreaterThanOrEqual(0);
    expect(headings.indexOf("Kaufen")).toBeLessThan(headings.indexOf("Verkaufen"));
  });
});

test.describe("DashboardTab - richtiges Detail-Modal je Kartentyp", () => {
  test("Klick auf Verkaufen-Karte oeffnet PlayerDetailModal, nicht TransfermarktDetailModal", async ({ mount }) => {
    const data = buildData([SELL_PLAYER.player_id]);

    const component = await mount(
      <DashboardTab data={data} wunschkader={{ targets: WUNSCHKADER_TARGETS }} transfermarktRows={[BUY_ROW]} now={NOW} />
    );

    await component.getByRole("button", { name: new RegExp(SELL_PLAYER.name) }).click();

    // Positiv: PlayerDetailModal-spezifischer "Vergleichen mit…"-Button.
    await expect(component.getByText("Vergleichen mit…")).toBeVisible();
    // Negativ: TransfermarktDetailModal-spezifische "Anbieter"-Zeile fehlt.
    await expect(component.getByText("Anbieter")).toHaveCount(0);
  });

  test("Klick auf Kaufen-Karte oeffnet TransfermarktDetailModal, nicht PlayerDetailModal", async ({ mount }) => {
    const data = buildData([SELL_PLAYER.player_id]);

    const component = await mount(
      <DashboardTab data={data} wunschkader={{ targets: WUNSCHKADER_TARGETS }} transfermarktRows={[BUY_ROW]} now={NOW} />
    );

    await component.getByRole("button", { name: new RegExp(BUY_ROW.name) }).click();

    // Positiv: TransfermarktDetailModal-spezifische "Anbieter"-Zeile.
    await expect(component.getByText("Anbieter")).toBeVisible();
    // Negativ: PlayerDetailModal-spezifischer "Vergleichen mit…"-Button fehlt.
    await expect(component.getByText("Vergleichen mit…")).toHaveCount(0);
  });
});
