import { test, expect, type ComponentFixtures } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Bug A - Add-Dialog ohne Positions-Zwang", () => {
  test("findet einen Torwart ueber den generischen Bank-Add-Dialog, ohne Position vorzuwaehlen", async ({ mount }) => {
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets: [] }} onSaved={() => {}} isActive={true} />
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

test.describe("Bug B - Vorschlaege vs. Freitext im Wechsel-Dialog", () => {
  async function openWechsel(mount: ComponentFixtures["mount"]) {
    const component = await mount(
      <WunschkaderTab
        data={buildFixtureSnapshot()}
        wunschkader={{ targets: [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }] }}
        onSaved={() => {}}
        isActive={true}
      />
    );
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Wechsel" }).click();
    return component;
  }

  test("Vorschlag-Chip oeffnet weiterhin zuerst den Vergleich, tauscht nicht direkt", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.suggestion1.name) }).click();

    await expect(component.getByText("Diesen als Ersatz wählen").first()).toBeVisible();
    await expect(component.getByText(FIXTURE_PLAYERS.target.name).first()).toBeVisible();
  });

  test("Freitext-Ergebnis (Hauptlabel) tauscht direkt, ohne den Vergleich zu oeffnen", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByPlaceholder("Anderen freien Spieler gleicher Position suchen…").fill("Weitweg");
    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.searchOnly.name) }).click();

    await expect(component.getByText("Diesen als Ersatz wählen")).toHaveCount(0);

    const abwehrHeading = component.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.searchOnly.name)).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name)).toHaveCount(0);
  });

  test("Freitext-Ergebnis 'Vergleichen'-Button oeffnet den Vergleich, ohne zu tauschen", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByPlaceholder("Anderen freien Spieler gleicher Position suchen…").fill("Weitweg");
    await component.getByRole("button", { name: "Vergleichen", exact: true }).click();

    await expect(component.getByText("Diesen als Ersatz wählen").first()).toBeVisible();

    const abwehrHeading = component.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name)).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.searchOnly.name)).toHaveCount(0);
  });
});
