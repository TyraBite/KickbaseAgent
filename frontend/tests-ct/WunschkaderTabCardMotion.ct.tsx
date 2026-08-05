import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Wunschkader-Kartenliste mit Motion-Wrapper", () => {
  test("Klick auf eine Karte oeffnet weiterhin das Detail-Modal", async ({ mount }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await expect(component.getByLabel("Notiz")).toBeVisible();
  });

  test("Entfernen loescht die Karte weiterhin und schreibt korrekt nach Firestore", async ({ mount, page }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0, { timeout: 1000 });
  });
});
