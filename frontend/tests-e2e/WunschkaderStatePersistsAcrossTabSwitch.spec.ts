import { test, expect } from "@playwright/test";
import { FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Wunschkader bleibt bei Tab-Wechsel gemountet", () => {
  test("Ungespeicherte Notiz und offenes Detail-Modal ueberleben Wegwechseln und Zurueckwechseln", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Wunschkader");

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    const noteField = page.getByLabel("Notiz");
    await expect(noteField).toBeVisible();
    await noteField.fill("Zwischenstand-Test");

    // Wegwechseln, OHNE das Modal zu schliessen oder die Notiz zu speichern.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Dashboard", exact: true }).click();
    await expect(heading).toHaveText("Dashboard");

    // Zurueckwechseln - Wunschkader ist durchgehend gemountet, das
    // Detail-Modal muss deshalb OHNE erneuten Klick noch offen sein.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();
    await expect(heading).toHaveText("Wunschkader");

    await expect(page.getByLabel("Notiz")).toHaveValue("Zwischenstand-Test");
  });
});
