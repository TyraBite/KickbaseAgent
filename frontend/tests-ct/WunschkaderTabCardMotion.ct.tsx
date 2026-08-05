import { test, expect, type Page } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";
import { STAGGER_STEP_S } from "../src/lib/motionVariants";

// Statt gegen echte Animation-Frames zu racen (flaky - haengt vom
// Sample-Zeitpunkt ab), lesen wir die KONFIGURIERTEN Timing-Werte der
// Web-Animations-API direkt aus getAnimations() aus. Framer Motion nutzt fuer
// diese Opacity/Y-Tweens native WAAPI-Animationen; deren `delay` ist
// deterministisch aus der uebergebenen Transition abgeleitet, unabhaengig vom
// Sample-Zeitpunkt (im Gegensatz zum aktuellen Fortschritt/`opacity`-Wert, der
// sich mit echter Zeit aendert). Empirisch gegen diese Seite verifiziert
// (2026-08-05): getAnimations() liefert fuer die Karten-Wrapper zuverlaessig
// genau ein Animation-Objekt mit dem konfigurierten delay/duration.
// Nur ".grid > div"-Elemente MIT <dl> sind Karten-Wrapper (TargetCard nutzt
// <dl> fuer Marktwert/Schnitt/etc.) - schliesst die "+ Ziel"-Buttons und die
// Budget-Planungs-Karte (hat ein eigenes ".grid", aber keine <dl>) sicher aus.
async function readCardDelaysMs(page: Page): Promise<(number | null)[]> {
  return page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
    return cards.map((el) => {
      const anim = (el as HTMLElement).getAnimations()[0];
      return anim?.effect?.getComputedTiming().delay ?? null;
    });
  });
}

test.describe("Wunschkader-Kartenliste mit Motion-Wrapper", () => {
  test("Klick auf eine Karte oeffnet weiterhin das Detail-Modal", async ({ mount }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await expect(component.getByLabel("Notiz")).toBeVisible();
  });

  test("Entfernen loescht die Karte weiterhin und schreibt korrekt nach Firestore", async ({ mount, page }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0, { timeout: 1000 });
  });

  // Regression-Fang fuer den Live-Review-Fund (2026-08-05): der urspruengliche
  // Task-4-Stagger war strukturell tot - jede Karte war ueber initial/animate/
  // exit "self-controlling" (noetig fuer den Einzel-Exit beim Entfernen), und
  // ein self-controlling Kind wird von Framer Motion NICHT ins
  // variantChildren-Set des Elternteils aufgenommen, wodurch dessen
  // staggerChildren wirkungslos blieb - alle Karten kamen gleichzeitig rein.
  // Der Fix ersetzt das durch einen manuellen Delay pro Karten-Index
  // (custom-Prop + dynamische Variante in motionVariants.ts).
  test("Stagger: Enter-Delay ist pro Karten-Index gestaffelt, nicht gleichzeitig", async ({ mount, page }) => {
    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion1.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion2.player_id, role: "Starter" },
    ];
    await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    // Alle drei Ziele sind "Abwehr" (siehe FIXTURE_PLAYERS) - landen also in
    // derselben Positionsgruppe, in Eingabereihenfolge (Index 0/1/2). Ein
    // wirklich toter Stagger wuerde hier [0, 0, 0] liefern.
    const stepMs = STAGGER_STEP_S * 1000;
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs, stepMs * 2]);
  });

  // Regression-Fang fuer den zweiten, unabhaengigen Fund: WunschkaderTab
  // bleibt seit einem spaeteren Task permanent gemountet (App.tsx), eine
  // reine "beim Mount einmal animieren"-Loesung waere deshalb fuer den Nutzer
  // NIE sichtbar (die Animation liefe laengst hinter display:none ab, bevor
  // der Tab je besucht wird). isActive (von App.tsx als
  // `activeTab === "wunschkader"` durchgereicht) gated deshalb animate/initial
  // pro Karte, damit der Stagger bei jedem (Wieder-)Besuch neu ablaeuft.
  test("Stagger: Enter-Animation wird bei jedem (Wieder-)Aktivieren des Tabs neu abgespielt", async ({
    mount,
    page,
  }) => {
    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion1.player_id, role: "Starter" },
    ];
    const stepMs = STAGGER_STEP_S * 1000;

    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    // Erster Besuch: Stagger laeuft, dann vollstaendig fertig (keine
    // Animation mehr aktiv - Framer Motion raeumt WAAPI-Animationen nach
    // Abschluss aus getAnimations() auf).
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs]);
    await expect.poll(() => readCardDelaysMs(page)).toEqual([null, null]);

    // Tab verlassen: isActive faellt auf false, Karten fallen auf den
    // initial-State (opacity 0) zurueck (im echten App.tsx laengst hinter
    // display:none, hier direkt sichtbar simuliert). Erst NACH diesem
    // vollstaendigen Ruecksprung wieder aktivieren, damit der naechste Schritt
    // eindeutig ein frischer Neustart ist, kein blosses Weiterlaufen einer
    // schon laufenden Animation.
    await component.update(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={false} />
    );
    await expect
      .poll(() =>
        page.evaluate(() => {
          const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
          return cards.map((el) => getComputedStyle(el).opacity);
        })
      )
      .toEqual(["0", "0"]);

    // Tab erneut betreten: der Stagger MUSS erneut mit denselben
    // index-basierten Delays ablaufen - das ist der eigentliche Beweis fuer
    // den zweiten Fix (kein "nur beim allerersten Mount"-Verhalten mehr).
    await component.update(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs]);
  });

  // Empirische Absicherung (auf Wunsch des Reviews, kein Ersatz fuer den
  // manuellen Smoke-Test aus Task 6): stellt sicher, dass das neue
  // isActive-gate (initial/animate-Umschaltung) nicht mit der bestehenden
  // layoutId-Reorder-Animation kollidiert, wenn eine Karte per Button
  // zwischen Positionsgruppe und Bank wechselt - danach darf exakt eine
  // sichtbare, voll eingeblendete Instanz uebrig bleiben, keine haengengebliebene
  // zweite Kopie.
  test("Reorder: Karte bleibt nach Bank/Startelf-Wechsel als genau eine, voll sichtbare Instanz stehen", async ({
    mount,
    page,
  }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await expect.poll(() => readCardDelaysMs(page)).toEqual([null]);

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Bank" }).click();
    await component.getByRole("button", { name: "Schließen" }).click();

    await expect
      .poll(() =>
        page.evaluate(() => {
          const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
          return cards.map((el) => getComputedStyle(el).opacity);
        })
      )
      .toEqual(["1"]);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(1);
  });
});
