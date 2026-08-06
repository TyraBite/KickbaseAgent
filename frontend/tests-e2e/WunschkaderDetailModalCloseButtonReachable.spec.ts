import { test, expect } from "@playwright/test";
import { FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

// Regression fuer einen Critical-Fund im finalen Review des
// Frontend-Motion-Pilot-Plans (docs/superpowers/plans/2026-08-05-frontend-
// motion-pilot.md): der sticky Header liegt bei z-30 (angehoben von z-10,
// damit er ueber jedem offenen Tab-Detail-Modal klickbar bleibt - siehe
// Kommentar in App.tsx). Jedes Tab-Detail-Modal-Backdrop liegt bei z-10,
// normalerweise also sicher unter dem Header. Ist das PANEL eines Modals
// aber hoch genug, um bis in die ~64-72px-Bandbreite des Headers am oberen
// Bildschirmrand zu reichen, deckt der (undurchsichtige) Header genau diesen
// Bereich des Modals - inklusive dessen eigenem "✕"-Schliessen-Button. Live
// verifiziert: WunschkaderTab's DetailModal wird mit ausgeklapptem "Wechsel"
// (Vorschlaege + Freitextsuche) auf einem Pixel-5-Viewport 751px hoch,
// beginnend bei y=-12 - der Schliessen-Button landet dabei unter dem Header
// und ist unklickbar.
//
// Der Fix (ModalOverlay/AnimatedModalOverlay in components/ui.tsx) gibt dem
// PANEL (nicht nur dem Backdrop) eine max-h-[calc(100vh-12rem)]+
// overflow-y-auto-Kappung - das Panel kann dadurch physisch nie mehr bis in
// die Header-Bandbreite reichen, unabhaengig davon wie viel Inhalt (Wechsel
// ausgeklappt oder nicht) gerendert wird.
test.describe("Wunschkader-Detail-Modal: Schliessen-Button bleibt erreichbar", () => {
  test("Schliessen-Button bleibt klickbar, wenn 'Wechsel' das Panel bis unter die Header-Bandbreite waechst", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Wunschkader");

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    const noteField = page.getByLabel("Notiz");
    await expect(noteField).toBeVisible(); // DetailModal offen

    // "Wechsel" ausklappen - macht das Panel hoch genug, um live den Bug
    // auszuloesen (siehe Kommentar oben, 751px auf Pixel-5-Viewport).
    await page.getByRole("button", { name: "Wechsel" }).click();
    await expect(page.getByText("Vorschläge")).toBeVisible();

    // Der eigentliche Regressionstest: der Schliessen-Button muss trotzdem
    // klickbar sein (Playwright's .click() timeout't hier VOR dem Fix aus,
    // weil der z-30-Header ihn abdeckt) und das Modal tatsaechlich schliessen.
    await page.getByRole("button", { name: "Schließen" }).click({ timeout: 5000 });
    await expect(noteField).not.toBeVisible();
  });
});
