import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";

test.describe("Tab-Wechsel bleibt unter prefers-reduced-motion funktional", () => {
  test("Klick-Wechsel (Fade) landet auf dem richtigen Tab, keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Modell-Tracking", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Modell-Tracking");
    expect(consoleErrors).toEqual([]);
  });

  test("Swipe-Wechsel (Slide) landet auf dem richtigen Tab, keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Spekulation", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Spekulation");
    // MobileTabMenu haengt jetzt (Backdrop/Panel-Animation) noch kurz als
    // exiting AnimatePresence-Kind im DOM, inkl. useModalOpenTracking() - ein
    // Swipe direkt danach waere sonst durch isAnyModalOpen() blockiert
    // (gleiches Muster wie die "Modal schliessen"-Wartestelle in
    // SwipeBlockedByModal.spec.ts).
    await expect(mobileNav).toHaveCount(0);

    await page.evaluate(() => window.scrollTo(0, 0));
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const y = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y }, { x: 20, y });

    await expect(heading).toHaveText("Wunschkader");
    expect(consoleErrors).toEqual([]);
  });
});
