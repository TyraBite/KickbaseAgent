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
});
