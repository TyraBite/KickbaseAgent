import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Bug A - Add-Dialog ohne Positions-Zwang", () => {
  test("findet einen Torwart ueber den generischen Bank-Add-Dialog, ohne Position vorzuwaehlen", async ({ mount }) => {
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets: [] }} onSaved={() => {}} />
    );

    // Gezielt den Bank-"+ Ziel"-Button ansteuern, nicht den einer
    // Positions-Gruppe (beide rendern denselben Text "+ Ziel").
    const bankHeading = component.getByText(/^Bank \(\d+\)$/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    await bankGrid.getByRole("button", { name: "+ Ziel" }).click();

    // Fail-fast: der generische Dialog hat KEINEN "(Position)"-Suffix.
    await expect(component.getByRole("heading", { name: "Ziel hinzufügen", exact: true })).toBeVisible();

    // Regression-Guard: kein <select> mehr im generischen Add-Formular.
    await expect(component.locator("form select")).toHaveCount(0);

    // Kern-Assertion: Suche nach einem NICHT-Sturm-Spieler funktioniert
    // ohne vorherige Positionsauswahl. Unter dem alten Code (Default
    // "Sturm") haette das 0 Treffer ergeben.
    await component.getByPlaceholder("Spieler suchen…").fill("Torsten");
    const result = component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.torwart.name) });
    await expect(result).toBeVisible();

    await result.click();
    await component.getByRole("button", { name: "Hinzufügen" }).click();

    await expect(component.getByText("Bank (1)")).toBeVisible();
    await expect(bankGrid.getByText(FIXTURE_PLAYERS.torwart.name)).toBeVisible();
  });
});
