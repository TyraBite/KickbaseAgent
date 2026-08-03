import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";
import { FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Bug F - Offenes Modal blockiert Tab-Swipe", () => {
  test("Drag bei offenem Wunschkader-DetailModal wechselt den Tab nicht; nach dem Schliessen (positive Kontrolle) wechselt derselbe Drag ihn", async ({
    page,
  }) => {
    await page.goto("/");

    // Mobiles Burger-Menue -> "Wunschkader" (gleiches Muster wie
    // TouchScrubVsSwipe.spec.ts).
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Wunschkader", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Wunschkader");

    // Der Fixture-Spielername ("Kai Zielspieler") existiert gleichzeitig auch
    // in EigenesTeamTab's Watchlist-Sektion (dort ungemountet gerendert, nur
    // per "hidden"-Klasse versteckt, siehe App.tsx-Tab-Umschaltung) - ein
    // ungescopter getByText(name) waere ein Strict-Mode-Verstoss. Die
    // "Abwehr · N belegt"-Ueberschrift wird NUR von WunschkaderTab gerendert,
    // deshalb darueber auf die richtige Karte scopen (identische Technik wie
    // in tests-ct/WunschkaderTab.ct.tsx).
    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    const closeButton = page.getByRole("button", { name: "Schließen" });
    await expect(closeButton).toBeVisible();

    // 1) Drag bei offenem Modal - darf den Tab NICHT wechseln. Frische
    // boundingBox() erst NACH dem Scroll-zu-oben einholen (Layout kann sich
    // durch den Modal-Overlay verschieben, siehe TouchScrubVsSwipe.spec.ts).
    await page.evaluate(() => window.scrollTo(0, 0));
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    // y ~40-60: nahe am oberen Viewport-Rand, ausserhalb der zentrierten
    // Modal-Karte (die ist vertikal mittig via items-center) - trifft damit
    // den fixed inset-0-Backdrop, der als DOM-Nachfahre von <main> die
    // Touch-Events trotz position:fixed weiterhin dorthin durchreicht.
    const dragY = 50;
    await touchDrag(page, { x: viewport.width - 20, y: dragY }, { x: 20, y: dragY });
    await expect(heading).toHaveText("Wunschkader"); // unveraendert - Modal blockiert den Swipe

    // 2) Modal schliessen.
    await closeButton.click();
    await expect(closeButton).toHaveCount(0);

    // 3) Positive Kontrolle: DERSELBE Drag nach dem Schliessen MUSS den Tab
    // wechseln, sonst waere Schritt 1 nur ein vakuoser Test.
    await page.evaluate(() => window.scrollTo(0, 0));
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const headingMidY = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y: headingMidY }, { x: 20, y: headingMidY });
    // "wunschkader" (Index 3) -> dx<0 -> naechster aktiver Tab "transfermarkt"
    // (Index 4) in ACTIVE_TABS-Reihenfolge, Label "Transfermarkt".
    await expect(heading).toHaveText("Transfermarkt");
  });
});
