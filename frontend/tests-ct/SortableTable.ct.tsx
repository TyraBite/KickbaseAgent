import { test, expect } from "@playwright/experimental-ct-react";
import { SortableTable, type TableColumn } from "../src/components/table";

// Task 7 (Test-Coverage Quick Wins Frontend): Sortier-Toggle + Null-Handling,
// geteilt ueber ~5 Tabs (AlleSpielerTab/TransfermarktTab/SpekulationTab/
// EigenesTeamTab/WunschkaderTab). Echtes DOM-Klick-Verhalten -> Playwright CT
// statt Vitest-Unit (kein Mocking noetig, reines Rendering).

interface FixtureRow {
  id: string;
  name: string;
  value: number | null;
}

const rows: FixtureRow[] = [
  { id: "a", name: "Alpha", value: 30 },
  { id: "b", name: "Bravo", value: null },
  { id: "c", name: "Charlie", value: 10 },
  { id: "d", name: "Delta", value: 20 },
];

const columns: TableColumn<FixtureRow>[] = [
  { key: "name", label: "Name", render: (r) => r.name, sortValue: (r) => r.name },
  { key: "value", label: "Wert", align: "right", render: (r) => (r.value === null ? "–" : String(r.value)), sortValue: (r) => r.value },
];

test.describe("SortableTable - Sortier-Toggle + Null-immer-zuletzt", () => {
  test("Spaltenkopf-Klick sortiert aufsteigend, null-Zeile landet am Ende", async ({ mount }) => {
    const component = await mount(
      <SortableTable columns={columns} rows={rows} rowKey={(r) => r.id} />
    );

    await component.getByRole("columnheader", { name: "Wert" }).click();

    const names = await component.locator("tbody tr td:first-child").allTextContents();
    expect(names).toEqual(["Charlie", "Delta", "Alpha", "Bravo"]);
  });

  test("erneuter Klick auf dieselbe Spalte sortiert absteigend, null-Zeile bleibt trotzdem am Ende", async ({ mount }) => {
    const component = await mount(
      <SortableTable columns={columns} rows={rows} rowKey={(r) => r.id} />
    );

    const wertHeader = component.getByRole("columnheader", { name: "Wert" });
    await wertHeader.click(); // aufsteigend
    await wertHeader.click(); // absteigend

    const names = await component.locator("tbody tr td:first-child").allTextContents();
    expect(names).toEqual(["Alpha", "Delta", "Charlie", "Bravo"]);
  });

  test("Klick auf eine ANDERE Spalte resettet die Sortierrichtung auf aufsteigend", async ({ mount }) => {
    const component = await mount(
      <SortableTable columns={columns} rows={rows} rowKey={(r) => r.id} />
    );

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
