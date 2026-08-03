import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";
import type { RecordedSetDocCall } from "../src/test-fixtures/firestore.mock";

// NOTE_SAVE_DEBOUNCE_MS ist eine modul-private Konstante in
// WunschkaderTab.tsx (aktuell 800) - bewusst NICHT fuer diesen Test
// exportiert (Global Constraint: kein test-only Export in Produktivcode).
// 850ms als Sicherheitsabstand.
const DEBOUNCE_FASTFORWARD_MS = 850;

test.describe("Bug C - debounced Notiz-Save darf ein spaeter entferntes Ziel nicht wiederbeleben", () => {
  test("Notiz tippen, VOR Ablauf der 800ms ein anderes Ziel entfernen: der spaeter feuernde debounced Save schreibt die aktuelle, nicht die veraltete editState", async ({ mount, page }) => {
    // Fake-Clock installieren, BEVOR mount() navigiert.
    await page.clock.install();

    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.sturm.player_id, role: "Starter" },
    ];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    // 1) Notiz am ERSTEN Ziel tippen - plant den 800ms debounced Save.
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByLabel("Notiz").fill("wichtige Notiz");
    await component.getByRole("button", { name: "Schließen" }).click();

    // 2) VOR Ablauf der 800ms: das ANDERE Ziel entfernen - immediate Save,
    // enthaelt die Entfernung korrekt.
    await component.getByText(FIXTURE_PLAYERS.sturm.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);

    // 3) 800ms virtuell vorspulen - der debounced Save feuert jetzt.
    await page.clock.fastForward(DEBOUNCE_FASTFORWARD_MS);
    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(2);

    const calls: RecordedSetDocCall[] = await page.evaluate(() => (window as any).__ctFirestoreCalls ?? []);

    for (const call of calls) {
      const ids = (call.data as { targets: { player_id: string }[] }).targets.map((t) => t.player_id);
      // Kern-Regression: das entfernte Ziel darf in KEINEM Write wieder
      // auftauchen - auch nicht im spaeter feuernden debounced Save.
      expect(ids).not.toContain(FIXTURE_PLAYERS.sturm.player_id);
    }
    const lastTargets = (calls[calls.length - 1].data as { targets: { player_id: string; note?: string }[] }).targets;
    expect(lastTargets.find((t) => t.player_id === FIXTURE_PLAYERS.target.player_id)?.note).toBe("wichtige Notiz");
  });
});
