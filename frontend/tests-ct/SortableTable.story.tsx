import { SortableTable, type TableColumn } from "../src/components/table";

// "Test story" (siehe https://playwright.dev/docs/test-components#test-stories):
// columns/rows UND ihre render()/sortValue()-Closures leben hier im normalen
// App-Bundle, nicht in der Testdatei. Grund: SortableTable direkt mit
// columns={...}/rowKey={(r) => r.id} aus der Testdatei zu mounten schlug in CI
// fehl (component-tests-Check, PR #7) - Funktions-Props, die per mount() aus
// dem Node-Testkontext in den Browser uebertragen werden, werden dabei ueber
// Playwrights exposeFunctions-Mechanismus zu asynchronen Remote-Aufrufen -
// SortableTable ruft sortValue()/render() aber synchron auf (sort()-Comparator,
// direktes Rendering), was mit einem Promise statt dem echten Wert bricht.
// Eine Story-Datei umgeht das komplett: keine Funktion ueberquert die
// mount()-Grenze, alles laeuft browserseitig im selben Bundle.
export interface FixtureRow {
  id: string;
  name: string;
  value: number | null;
}

export const FIXTURE_ROWS: FixtureRow[] = [
  { id: "a", name: "Alpha", value: 30 },
  { id: "b", name: "Bravo", value: null },
  { id: "c", name: "Charlie", value: 10 },
  { id: "d", name: "Delta", value: 20 },
];

const columns: TableColumn<FixtureRow>[] = [
  { key: "name", label: "Name", render: (r) => r.name, sortValue: (r) => r.name },
  { key: "value", label: "Wert", align: "right", render: (r) => (r.value === null ? "–" : String(r.value)), sortValue: (r) => r.value },
];

export default function SortableTableStory() {
  return <SortableTable columns={columns} rows={FIXTURE_ROWS} rowKey={(r) => r.id} />;
}
