import { test, expect } from "@playwright/experimental-ct-react";
import SignalBadgeStory from "./SignalBadge.story";

// Task 6 (Test-Coverage Quick Wins Frontend): SignalBadge's Tone-Wahl
// (good/warn/crit) ist reine Ableitungslogik, aber steckt komplett INLINE im
// JSX der Komponente (kein extrahierbarer Helper wie kForPosition() o.ae.) -
// siehe frontend/src/components/ui.tsx. Dieses Projekt hat eine Standing Rule
// gegen Extraktion NUR fuer Testbarkeit (kein test-only Export), deshalb hier
// ein Playwright-CT-Smoke-Test statt einer Vitest-Unit fuer eine erfundene
// Helper-Funktion. Die Fixture-Werte selbst leben in SignalBadge.story.tsx.
test.describe("SignalBadge - Schwellenwert-Grenzfaelle", () => {
  test("rendert alle Schwellenwert-Faelle mit korrektem Tone und Text", async ({ mount }) => {
    const component = await mount(<SignalBadgeStory />);

    // signal === thresholds.good (Grenzwert exakt): faellt auf 'warn', nicht 'good'
    // (nur signal > good zaehlt als 'good').
    await expect(component.getByTestId("at-good")).toHaveText("1.10 · im Rauschen");
    await expect(component.getByTestId("at-good").locator("span")).toHaveClass(/bg-amber-100/);

    // signal === thresholds.critical (Grenzwert exakt): faellt auf 'warn', nicht 'crit'
    // (nur signal < critical zaehlt als 'crit').
    await expect(component.getByTestId("at-critical")).toHaveText("0.90 · im Rauschen");
    await expect(component.getByTestId("at-critical").locator("span")).toHaveClass(/bg-amber-100/);

    // signal strikt zwischen critical und good ist 'warn'.
    await expect(component.getByTestId("between")).toHaveText("1.00 · im Rauschen");
    await expect(component.getByTestId("between").locator("span")).toHaveClass(/bg-amber-100/);

    // signal knapp ueber thresholds.good ist 'good'/'unter Fairwert'.
    await expect(component.getByTestId("above-good")).toHaveText("1.11 · unter Fairwert");
    await expect(component.getByTestId("above-good").locator("span")).toHaveClass(/bg-brand-100/);

    // signal knapp unter thresholds.critical ist 'crit'/'Prämie'.
    await expect(component.getByTestId("below-critical")).toHaveText("0.89 · Prämie");
    await expect(component.getByTestId("below-critical").locator("span")).toHaveClass(/bg-red-100/);

    // signal null/undefined zeigt 'nicht kalibriert' ohne Badge-Tone.
    await expect(component.getByTestId("null-signal")).toHaveText("nicht kalibriert");
    await expect(component.getByTestId("undefined-signal")).toHaveText("nicht kalibriert");
  });
});
