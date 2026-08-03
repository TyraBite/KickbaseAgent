import { test, expect, type ComponentFixtures } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";
import type { RecordedSetDocCall } from "../src/test-fixtures/firestore.mock";

// NOTE_SAVE_DEBOUNCE_MS ist eine modul-private Konstante in
// WunschkaderTab.tsx (aktuell 800) - bewusst NICHT fuer diesen Test
// exportiert (Global Constraint: kein test-only Export in Produktivcode).
// 850ms als Sicherheitsabstand, gleiches Muster wie WunschkaderTabAutoSave.ct.tsx.
const DEBOUNCE_FASTFORWARD_MS = 850;

// Reiner Bequemlichkeits-Wrapper um die exakte Interaktionsfolge aus
// WunschkaderTab.ct.tsx ("Bug A"): ueber den generischen Bank-"+ Ziel"-Button
// (kein presetPosition) einen freien Spieler ohne vorherige Positionsauswahl
// hinzufuegen. FIXTURE_PLAYERS.torwart ist dafuer der etablierte Kandidat.
async function addTorwartViaBankDialog(component: Awaited<ReturnType<ComponentFixtures["mount"]>>) {
  const bankHeading = component.getByText(/^Bank \(\d+\)$/);
  const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
  await bankGrid.getByRole("button", { name: "+ Ziel" }).click();
  await component.getByPlaceholder("Spieler suchen…").fill("Torsten");
  await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.torwart.name) }).click();
  await component.getByRole("button", { name: "Hinzufügen" }).click();
}

test.describe("Planungsmodus - waehrend der Simulation schreibt nichts nach Firestore", () => {
  test("Ziel hinzufuegen im Planungsmodus loest KEINEN Firestore-Write aus (Sofort-Pfad)", async ({ mount, page }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    await component.getByRole("button", { name: "Planungsmodus starten" }).click();
    await addTorwartViaBankDialog(component);

    // Die Aenderung ist im UI sichtbar (editState wurde aktualisiert)...
    await expect(component.getByText("Bank (1)")).toBeVisible();
    // ...aber saveTargets() greift der simulationModeRef-Guard, der
    // Sofort-Pfad (Bank-Add) darf NICHT nach Firestore schreiben.
    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(0);
  });

  test("Notiz aendern im Planungsmodus loest auch nach Ablauf der 800ms-Debounce-Frist KEINEN Firestore-Write aus", async ({
    mount,
    page,
  }) => {
    // Fake-Clock installieren, BEVOR mount() navigiert - sonst laesst sich
    // die Debounce-Frist nicht deterministisch vorspulen.
    await page.clock.install();

    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    await component.getByRole("button", { name: "Planungsmodus starten" }).click();
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByLabel("Notiz").fill("Notiz waehrend der Planung");
    await component.getByRole("button", { name: "Schließen" }).click();

    // 800ms virtuell vorspulen - der debounced Notiz-Save (debouncedSaveTargets)
    // wuerde jetzt ausserhalb des Planungsmodus feuern. simulationModeRef wird
    // beim Fristablauf gelesen (nicht der Stand zum Zeitpunkt des Timer-Starts),
    // ist hier aber immer noch true, weil der Modus nie verlassen wurde.
    await page.clock.fastForward(DEBOUNCE_FASTFORWARD_MS);

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(0);
  });
});

test.describe("Planungsmodus - Verwerfen/Speichern", () => {
  test("Verwerfen stellt exakt den Zielstand von vor dem Eintritt in den Planungsmodus wieder her", async ({
    mount,
  }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    // Stand VOR dem Planungsmodus: ein Starter-Ziel, keine Bank-Ziele.
    await expect(component.getByText("Bank (0)")).toBeVisible();
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();

    await component.getByRole("button", { name: "Planungsmodus starten" }).click();
    await addTorwartViaBankDialog(component);
    await expect(component.getByText("Bank (1)")).toBeVisible();
    await expect(component.getByText(FIXTURE_PLAYERS.torwart.name)).toBeVisible();

    await component.getByRole("button", { name: "Verwerfen" }).click();

    // discardSimulation() setzt editState auf die vor enterSimulationMode()
    // gesicherte baseline zurueck - das neu hinzugefuegte Ziel ist wieder weg,
    // das urspruengliche Ziel unveraendert vorhanden, und der Modus ist
    // verlassen (Button-Beschriftung wieder "Planungsmodus starten").
    await expect(component.getByText("Bank (0)")).toBeVisible();
    await expect(component.getByText(FIXTURE_PLAYERS.torwart.name)).toHaveCount(0);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(component.getByRole("button", { name: "Planungsmodus starten" })).toBeVisible();
  });

  test("Speichern loest genau EINEN Firestore-Write aus, mit dem Endzustand inkl. des neuen Ziels als Payload", async ({
    mount,
    page,
  }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    await component.getByRole("button", { name: "Planungsmodus starten" }).click();
    await addTorwartViaBankDialog(component);
    await component.getByRole("button", { name: "Speichern" }).click();

    // commitSimulation() schaltet den Modus zuerst ab (Ref synchron) und ruft
    // dann saveTargets(editState) genau einmal direkt auf - kein zusaetzlicher
    // Write durch einen ggf. noch anstehenden pendingSaveKind-Effect.
    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);

    const calls: RecordedSetDocCall[] = await page.evaluate(() => (window as any).__ctFirestoreCalls ?? []);
    const written = (calls[0].data as { targets: { player_id: string; role?: string }[] }).targets;

    expect(written).toHaveLength(2);
    expect(written.find((t) => t.player_id === FIXTURE_PLAYERS.target.player_id)?.role).toBe("Starter");
    expect(written.find((t) => t.player_id === FIXTURE_PLAYERS.torwart.player_id)?.role).toBe(
      "Bank/Backup-Option"
    );

    // Modus ist verlassen, UI zeigt wieder den Ausgangs-Button.
    await expect(component.getByRole("button", { name: "Planungsmodus starten" })).toBeVisible();
  });
});
