import { test, expect } from "@playwright/experimental-ct-react";
import SortableTableStory from "./SortableTable.story";

// Task 7 (Test-Coverage Quick Wins Frontend): Sortier-Toggle + Null-Handling,
// geteilt ueber ~5 Tabs (AlleSpielerTab/TransfermarktTab/SpekulationTab/
// EigenesTeamTab/WunschkaderTab). Echtes DOM-Klick-Verhalten -> Playwright CT
// statt Vitest-Unit (kein Mocking noetig, reines Rendering). Fixture +
// columns/render()/sortValue() leben in SortableTable.story.tsx (siehe dort
// fuer den Grund).
test.describe("SortableTable - Sortier-Toggle + Null-immer-zuletzt", () => {
  test("Spaltenkopf-Klick sortiert aufsteigend, null-Zeile landet am Ende", async ({ mount }) => {
    const component = await mount(<SortableTableStory />);

    await component.getByRole("columnheader", { name: "Wert" }).click();

    const names = await component.locator("tbody tr td:first-child").allTextContents();
    expect(names).toEqual(["Charlie", "Delta", "Alpha", "Bravo"]);
  });

  test("erneuter Klick auf dieselbe Spalte sortiert absteigend, null-Zeile bleibt trotzdem am Ende", async ({ mount }) => {
    const component = await mount(<SortableTableStory />);

    const wertHeader = component.getByRole("columnheader", { name: "Wert" });
    await wertHeader.click(); // aufsteigend
    await wertHeader.click(); // absteigend

    const names = await component.locator("tbody tr td:first-child").allTextContents();
    expect(names).toEqual(["Alpha", "Delta", "Charlie", "Bravo"]);
  });

  test("Klick auf eine ANDERE Spalte resettet die Sortierrichtung auf aufsteigend", async ({ mount }) => {
    const component = await mount(<SortableTableStory />);

    const wertHeader = component.getByRole("columnheader", { name: "Wert" });
    await wertHeader.click(); // aufsteigend
    await wertHeader.click(); // absteigend (dir=-1 fuer die "Wert"-Spalte gespeichert)

    // Spaltenwechsel: "Name" ist eine neue Spalte -> muss wieder mit aufsteigend starten,
    // nicht die absteigende dir von "Wert" uebernehmen.
    await component.getByRole("columnheader", { name: "Name" }).click();

    const names = await component.locator("tbody tr td:first-child").allTextContents();
    expect(names).toEqual(["Alpha", "Bravo", "Charlie", "Delta"]);
  });
});
