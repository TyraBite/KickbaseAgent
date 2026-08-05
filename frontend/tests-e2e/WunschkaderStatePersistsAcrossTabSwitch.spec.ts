import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";
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

    // Bewusst lange, kuenstliche Wartezeit - deutlich laenger als jede
    // denkbare Exit-/Fallback-Animationsdauer (WUNSCHKADER_FADE_EXIT_S=450ms,
    // WUNSCHKADER_EXIT_FALLBACK_MS=700ms in App.tsx). Der Zustandserhalt beruht
    // seit dem Strukturfix NICHT mehr auf einem Zeitfenster - WunschkaderTab
    // bleibt immer gemountet, wunschkaderPhase steuert nur noch display:none -
    // dieser Delay beweist genau das: die Notiz/das offene Modal ueberleben
    // auch ein Vielfaches jeder Animationsdauer, nicht nur ein kurzes Fenster.
    await page.waitForTimeout(2000);

    // Zurueckwechseln - Wunschkader ist durchgehend gemountet, das
    // Detail-Modal muss deshalb OHNE erneuten Klick noch offen sein.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();
    await expect(heading).toHaveText("Wunschkader");

    await expect(page.getByLabel("Notiz")).toHaveValue("Zwischenstand-Test");
  });

  // Seit dem Strukturfix bleibt WunschkaderTab (und damit sein DetailModal)
  // beim Wegwechseln permanent gemountet statt zu unmounten - dessen globale
  // Seiteneffekte (Modal-Zaehler fuer isAnyModalOpen(), Escape-Listener)
  // muessen deshalb pausiert werden, waehrend Wunschkader nicht der sichtbare
  // Tab ist, sonst bleiben sie fuer den Rest der Session aktiv (Review-Fund).
  // Die beiden folgenden Tests falsifizieren genau diese zwei Faelle.
  test("Offenes Wunschkader-Detail-Modal im Hintergrund blockiert Swipe auf einem anderen Tab nicht", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Wunschkader");

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    const noteField = page.getByLabel("Notiz");
    await expect(noteField).toBeVisible(); // Detail-Modal offen

    // Wegwechseln, OHNE das Modal zu schliessen.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Dashboard", exact: true }).click();
    await expect(heading).toHaveText("Dashboard");
    // MobileTabMenu haengt selbst (Backdrop/Panel-Animation, siehe
    // TabSwitchReducedMotion.spec.ts) noch kurz als exiting AnimatePresence-
    // Kind im DOM inkl. seiner eigenen useModalOpenTracking() - abwarten,
    // sonst waere ein Fehlschlag hier dem Menue selbst zuzuschreiben, nicht
    // dem eigentlich zu pruefenden Wunschkader-Hintergrund-Modal.
    await expect(mobileNav).toHaveCount(0);

    // Positive Kontrolle: der Swipe auf dem jetzt sichtbaren Tab MUSS den Tab
    // wechseln. Waere isAnyModalOpen() durch das im Hintergrund offene
    // Wunschkader-Modal faelschlich weiter "true", waere jedes Wischen ab
    // hier fuer den Rest der Session app-weit blockiert.
    await page.evaluate(() => window.scrollTo(0, 0));
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const headingMidY = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y: headingMidY }, { x: 20, y: headingMidY });
    // "dashboard" (Index 0) -> dx<0 -> naechster aktiver Tab "team" (Index 1),
    // Label "Eigenes Team".
    await expect(heading).toHaveText("Eigenes Team");
  });

  test("Escape auf einem anderen Tab schliesst das im Hintergrund offene Wunschkader-Detail-Modal nicht", async ({ page }) => {
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
    await noteField.fill("Hintergrund-Test");

    // Wegwechseln, OHNE das Modal zu schliessen.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Dashboard", exact: true }).click();
    await expect(heading).toHaveText("Dashboard");

    // Escape auf dem jetzt sichtbaren Tab darf das im Hintergrund offene
    // Wunschkader-Modal NICHT schliessen - dessen Escape-Listener muss
    // pausiert sein, waehrend Wunschkader nicht der sichtbare Tab ist.
    await page.keyboard.press("Escape");

    // Zurueckwechseln - das Detail-Modal (inkl. Notiz) muss unveraendert
    // offen sein.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();
    await expect(heading).toHaveText("Wunschkader");
    await expect(page.getByLabel("Notiz")).toHaveValue("Hintergrund-Test");
  });
});
