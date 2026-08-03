import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";

test.describe("Bug E - Touch-Scrubben im ML-Chart loest keinen Tab-Swipe aus", () => {
  test("Drag INNERHALB des Charts wechselt den Tab nicht; derselbe Drag AUSSERHALB (positive Kontrolle) wechselt ihn", async ({ page }) => {
    await page.goto("/");

    // Mobiles Burger-Menue -> "Modell-Tracking" (die Desktop-<nav> ist auf
    // < sm ausgeblendet, aber im DOM vorhanden - deshalb ueber die "Menü"-
    // Ueberschrift auf die mobile <nav> scopen, nicht global suchen).
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Modell-Tracking", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Modell-Tracking");

    const trendHeading = page.getByRole("heading", { name: /Richtungs-Genauigkeit/ });
    const chartSvg = trendHeading.locator("xpath=following-sibling::div[1]").locator("svg");
    await expect(chartSvg).toBeVisible();
    // Der Chart liegt auf dem Pixel-5-Viewport tief unten auf der Seite (nach
    // Kopf-an-Kopf-Bloecken etc.) - ohne Scroll ragt boundingBox() teils unter
    // den sichtbaren Viewport, und ein Touch auf die (dann ausserhalb
    // liegende) Mitte des Charts trifft real gar kein Element (elementFromPoint
    // liefert null / <html>), wodurch der Test faelschlich immer "besteht",
    // egal ob data-swipe-ignore vorhanden ist. Erst vollstaendig in den
    // sichtbaren Bereich scrollen macht die Pruefung nicht-vakuos.
    await chartSvg.scrollIntoViewIfNeeded();

    // 1) Drag INNERHALB des Charts - darf den Tab NICHT wechseln.
    const chartBox = await chartSvg.boundingBox();
    if (!chartBox) throw new Error("Chart-SVG hat kein boundingBox()");
    const midY = chartBox.y + chartBox.height / 2;
    await touchDrag(
      page,
      { x: chartBox.x + chartBox.width * 0.75, y: midY },
      { x: chartBox.x + chartBox.width * 0.25, y: midY }
    );
    await expect(heading).toHaveText("Modell-Tracking"); // unveraendert

    // 2) Positive Kontrolle: DERSELBE Drag ausserhalb des Charts (auf Hoehe
    // der mobilen Tab-Ueberschrift, oberhalb des Charts) - MUSS den Tab
    // wechseln, sonst waere Schritt 1 nur ein vakuoser Test.
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    // Der Scroll zum Chart oben (fuer den Inside-Chart-Drag) haette die
    // Ueberschrift sonst unter dem sticky <header> (z-10) verdeckt -
    // heading.scrollIntoViewIfNeeded() allein reicht nicht, weil es nur die
    // Layout-Ueberlappung mit dem Viewport prueft, nicht die visuelle
    // Verdeckung durch position:sticky-Elemente. Ganz nach oben scrollen
    // stellt den unverdeckten Ausgangszustand wieder her.
    await page.evaluate(() => window.scrollTo(0, 0));
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const headingMidY = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y: headingMidY }, { x: 20, y: headingMidY });
    await expect(heading).toHaveText("Bugs & Ideen"); // naechster Tab (dx<0 -> "next")
  });
});
