import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

// Regression fuer einen Live-Nebenfund aus PR #16 (2026-08-06): die
// Kartenkopfzeile reserviert seit dem Drag-Handle rechts oben `pr-10`, ist
// aber weiterhin `flex flex-wrap` - bei knapper Kartenbreite (Grid-Minimum
// 220px) laeuft ein ausreichend langer Name in eine zweite Zeile, waehrend
// kuerzere Namen einzeilig bleiben. 480px Viewport (statt des CT-
// Standard-Viewports) erzwingt zwei ~220px-Spalten - genau die knappe Breite,
// bei der das reproduzierbar auftritt.
//
// Wichtig fuer die Assertion: `.grid > div` ist der motion.div-Wrapper (das
// eigentliche Grid-Item) - CSS Grids Default `align-items: stretch` gleicht
// dessen Hoehe IMMER auf die groesste Karte der Zeile an, unabhaengig vom
// Bug. Die sichtbare, umrandete Karte ist ein Kind-`div[role="button"]`
// EINE Ebene darunter und wird vom Grid NICHT gestreckt - live per
// Diagnose-Lauf bestaetigt (2026-08-07): Grid-Item bei beiden Karten 224px,
// die sichtbare Karte darunter 200px (kurzer Name) vs. 224px (langer Name).
// Ein Test, der stattdessen `.grid > div` selbst misst, waere immer gruen
// (genau das ist PR #17s erstem Testversuch passiert).
test.use({ viewport: { width: 480, height: 800 } });

test.describe("Wunschkader-Kartenkopf bei langen Spielernamen", () => {
  test("Karten derselben Positionsgruppe bleiben gleich hoch, unabhaengig von der Namenslaenge", async ({
    mount,
    page,
  }) => {
    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.longName.player_id, role: "Starter" },
    ];
    await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    const heights = await page.evaluate(() => {
      const gridItems = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
      return gridItems.map(
        (el) => el.querySelector(':scope > div[role="button"]')!.getBoundingClientRect().height
      );
    });

    expect(heights).toHaveLength(2);
    expect(heights[0]).toBe(heights[1]);
  });
});
