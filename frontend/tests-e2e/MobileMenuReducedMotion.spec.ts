import { test, expect } from "@playwright/test";

test.describe("Mobile-Menue bleibt unter prefers-reduced-motion funktional", () => {
  test("Oeffnen, Tab waehlen, Menue schliesst sich selbst - keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await expect(mobileNav).toBeVisible();

    await mobileNav.getByRole("button", { name: "Ligaanalyse", exact: true }).click();
    await expect(mobileNav).toHaveCount(0);

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Ligaanalyse");
    expect(consoleErrors).toEqual([]);
  });

  test("Escape schliesst das Menue", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await expect(mobileNav).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(mobileNav).toHaveCount(0);
  });

  // Regression: der Header ist `sticky top-0` und (bewusst, siehe App.tsx
  // z-30-Kommentar) oberhalb jedes Tab-Detail-Modals - das Drawer-Overlay
  // muss trotzdem NOCH darueber liegen (z-40), sonst verdeckt der Header
  // genau die Titelzeile des Drawers (Label "Menü" + eigener "✕"-Button) und
  // der Button ist unklickbar. Auf `mobileNav` scopen, nicht global suchen -
  // PlayerCompareModal hat ebenfalls einen "Schließen"-Button.
  test("eigener Schliessen-Button (X) im Drawer schliesst das Menue", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await expect(mobileNav).toBeVisible();

    await mobileNav.getByRole("button", { name: "Schließen" }).click();
    await expect(mobileNav).toHaveCount(0);
  });
});
