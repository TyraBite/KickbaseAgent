import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

// Regression fuer einen Live-Nebenfund aus PR #16 (2026-08-06): die
// Kartenkopfzeile reserviert seit dem Drag-Handle rechts oben `pr-10`, ist
// aber weiterhin `flex flex-wrap` - bei knapper Kartenbreite (Grid-Minimum
// 220px) laeuft ein ausreichend langer Name in eine zweite Zeile, waehrend
// kuerzere Namen einzeilig bleiben. Karten derselben Positionsgruppe/Bank
// wurden dadurch unterschiedlich hoch. 480px Viewport (statt des CT-
// Standard-Viewports) erzwingt zwei ~220px-Spalten - genau die knappe Breite,
// bei der das reproduzierbar auftritt.
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
      const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
      return cards.map((el) => el.getBoundingClientRect().height);
    });

    expect(heights).toHaveLength(2);
    expect(heights[0]).toBe(heights[1]);
  });
});
