import { test, expect } from "@playwright/experimental-ct-react";
import { SignalBadge } from "../src/components/ui";

// Task 6 (Test-Coverage Quick Wins Frontend): SignalBadge's Tone-Wahl
// (good/warn/crit) ist reine Ableitungslogik, aber steckt komplett INLINE im
// JSX der Komponente (kein extrahierbarer Helper wie kForPosition() o.ae.) -
// siehe frontend/src/components/ui.tsx. Dieses Projekt hat eine Standing Rule
// gegen Extraktion NUR fuer Testbarkeit (kein test-only Export), deshalb hier
// ein Playwright-CT-Smoke-Test statt einer Vitest-Unit fuer eine erfundene
// Helper-Funktion.
const thresholds = { good: 1.1, critical: 0.9 };

test.describe("SignalBadge - Schwellenwert-Grenzfaelle", () => {
  test("signal === thresholds.good (Grenzwert exakt) faellt auf 'warn', nicht 'good' (nur > good zaehlt als 'good')", async ({ mount }) => {
    const component = await mount(<SignalBadge signal={thresholds.good} thresholds={thresholds} />);
    const badge = component.locator("span").first();
    await expect(badge).toHaveText("1.10 · im Rauschen");
    await expect(badge).toHaveClass(/bg-amber-100/);
  });

  test("signal === thresholds.critical (Grenzwert exakt) faellt auf 'warn', nicht 'crit' (nur < critical zaehlt als 'crit')", async ({ mount }) => {
    const component = await mount(<SignalBadge signal={thresholds.critical} thresholds={thresholds} />);
    const badge = component.locator("span").first();
    await expect(badge).toHaveText("0.90 · im Rauschen");
    await expect(badge).toHaveClass(/bg-amber-100/);
  });

  test("signal strikt zwischen critical und good ist 'warn'", async ({ mount }) => {
    const component = await mount(<SignalBadge signal={1.0} thresholds={thresholds} />);
    const badge = component.locator("span").first();
    await expect(badge).toHaveText("1.00 · im Rauschen");
    await expect(badge).toHaveClass(/bg-amber-100/);
  });

  test("signal knapp ueber thresholds.good ist 'good'/'unter Fairwert'", async ({ mount }) => {
    const component = await mount(<SignalBadge signal={1.11} thresholds={thresholds} />);
    const badge = component.locator("span").first();
    await expect(badge).toHaveText("1.11 · unter Fairwert");
    await expect(badge).toHaveClass(/bg-brand-100/);
  });

  test("signal knapp unter thresholds.critical ist 'crit'/'Prämie'", async ({ mount }) => {
    const component = await mount(<SignalBadge signal={0.89} thresholds={thresholds} />);
    const badge = component.locator("span").first();
    await expect(badge).toHaveText("0.89 · Prämie");
    await expect(badge).toHaveClass(/bg-red-100/);
  });

  test("signal null/undefined zeigt 'nicht kalibriert' ohne Badge-Tone", async ({ mount }) => {
    const componentNull = await mount(<SignalBadge signal={null} thresholds={thresholds} />);
    await expect(componentNull.locator("span").first()).toHaveText("nicht kalibriert");

    const componentUndefined = await mount(<SignalBadge signal={undefined} thresholds={thresholds} />);
    await expect(componentUndefined.locator("span").first()).toHaveText("nicht kalibriert");
  });
});
