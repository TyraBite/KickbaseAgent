import { test, expect } from "@playwright/experimental-ct-react";
import AlleSpielerTab from "../src/components/AlleSpielerTab";
import { buildFixtureSnapshot } from "../src/test-fixtures/dashboardSnapshot.fixture";
import type { PlayerRecord } from "../src/types";

test.describe("Bug D - Backspace neben einem Tausenderpunkt loescht die Nachbar-Ziffer, Cursor bleibt korrekt positioniert", () => {
  test("Cursor direkt nach dem zweiten Punkt in '1.234.567', Backspace: Ergebnis '123.567', Cursor bei Index 3 (nicht am Feldende)", async ({ mount }) => {
    const component = await mount(<AlleSpielerTab data={buildFixtureSnapshot()} />);

    const input = component.getByLabel("Marktwert min");
    await input.fill("1.234.567");
    await input.evaluate((el: HTMLInputElement) => el.setSelectionRange(6, 6));
    await input.press("Backspace");

    await expect(input).toHaveValue("123.567");
    const selection = await input.evaluate((el: HTMLInputElement) => [el.selectionStart, el.selectionEnd]);
    expect(selection).toEqual([3, 3]);
  });
});

// Kleiner, lokaler Player-Helper (bewusst nicht der private "player()" aus
// dashboardSnapshot.fixture.ts, der ist dort nicht exportiert) - erzwingt
// per Pick<> genau die Felder, die AlleSpielerTab fuer Filter-Kombinationen
// tatsaechlich auswertet, alle anderen PlayerRecord-Felder explizit statt
// undefined (siehe Task-Brief: keine impliziten undefined-Werte).
function player(
  p: Pick<PlayerRecord, "player_id" | "name" | "position" | "team_name" | "status_code" | "starting_rank" | "market_value" | "average_points">
): PlayerRecord {
  return p;
}

// Alle drei folgenden Tests pruefen bewusst KEINE Einzel-Filter (das waere
// unter- statt aussagekraeftig), sondern jeweils zwei UNABHAENGIGE aktive
// Filter GLEICHZEITIG - genau das AND-Verhalten in AlleSpielerTab.tsx' eigenem
// "visible"-useMemo. Stichprobenartig, nicht erschoepfend (siehe Plan): 3
// realistische Kombinationen, keine vierte "nur zur Sicherheit".

test.describe("Filter-Kombination: Position + Verfuegbarkeit", () => {
  test("Position=Sturm UND Verfuegbarkeit=Frei zusammen zeigen nur freie Stuermer, nicht andere Positionen oder vergebene Stuermer", async ({ mount }) => {
    const players = {
      sturmFrei1: player({
        player_id: "combo-a-sturm-frei-1", name: "Fritz Freistuermer", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100,
      }),
      sturmFrei2: player({
        player_id: "combo-a-sturm-frei-2", name: "Gustav Freistuermer", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 1_100_000, average_points: 110,
      }),
      sturmEigen: player({
        player_id: "combo-a-sturm-eigen", name: "Heiner Eigenstuermer", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 1_200_000, average_points: 120,
      }),
      sturmAndere: player({
        player_id: "combo-a-sturm-andere", name: "Ingo Fremdstuermer", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 1_300_000, average_points: 130,
      }),
      abwehrFrei: player({
        player_id: "combo-a-abwehr-frei", name: "Jonas Freiverteidiger", position: "Abwehr",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 1_400_000, average_points: 140,
      }),
    };

    const data = buildFixtureSnapshot({
      players: Object.fromEntries(Object.values(players).map((p) => [p.player_id, p])),
      own_squad_ids: [players.sturmEigen.player_id],
      owned_by: { [players.sturmAndere.player_id]: "Anderer Manager" },
    });
    const component = await mount(<AlleSpielerTab data={data} />);

    await component.getByLabel("Position").selectOption("Sturm");
    await component.getByLabel("Verfügbarkeit").selectOption("frei");

    // Erfuellen BEIDE Filter -> sichtbar.
    await expect(component.getByText(players.sturmFrei1.name, { exact: true })).toBeVisible();
    await expect(component.getByText(players.sturmFrei2.name, { exact: true })).toBeVisible();

    // Sturm, aber nicht frei (eigener Kader bzw. bei anderem Manager) -> ausgeblendet.
    await expect(component.getByText(players.sturmEigen.name, { exact: true })).toHaveCount(0);
    await expect(component.getByText(players.sturmAndere.name, { exact: true })).toHaveCount(0);
    // Frei, aber nicht Sturm -> ausgeblendet.
    await expect(component.getByText(players.abwehrFrei.name, { exact: true })).toHaveCount(0);
  });
});

test.describe("Filter-Kombination: Marktwert-Bereich + Namenssuche", () => {
  test("Marktwert 2.000.000-4.000.000 UND Suche 'Müller' zusammen zeigen nur Treffer, die BEIDE Kriterien erfuellen", async ({ mount }) => {
    const players = {
      nameInRange: player({
        player_id: "combo-b-name-in-range", name: "Manuel Müller", position: "Mittelfeld",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 3_000_000, average_points: 100,
      }),
      nameOutOfRange: player({
        player_id: "combo-b-name-out-of-range", name: "Thomas Müller", position: "Mittelfeld",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 6_000_000, average_points: 100,
      }),
      rangeOnly: player({
        player_id: "combo-b-range-only", name: "Erik Sonstig", position: "Mittelfeld",
        team_name: "SC Beispiel", status_code: null, starting_rank: null, market_value: 3_000_000, average_points: 100,
      }),
      neither: player({
        player_id: "combo-b-neither", name: "Piet Nirgends", position: "Mittelfeld",
        team_name: "Anderer Verein", status_code: null, starting_rank: null, market_value: 6_500_000, average_points: 100,
      }),
      // Suche trifft NICHT ueber den Namen, sondern ueber team_name - beweist,
      // dass die Suche wie beworben Name UND Verein durchsucht.
      teamInRange: player({
        player_id: "combo-b-team-in-range", name: "Karla Kandidatin", position: "Mittelfeld",
        team_name: "FC Müllerhausen", status_code: null, starting_rank: null, market_value: 3_500_000, average_points: 100,
      }),
    };

    const data = buildFixtureSnapshot({
      players: Object.fromEntries(Object.values(players).map((p) => [p.player_id, p])),
      own_squad_ids: [],
      owned_by: {},
    });
    const component = await mount(<AlleSpielerTab data={data} />);

    await component.getByLabel("Marktwert min").fill("2.000.000");
    await component.getByLabel("Marktwert max").fill("4.000.000");
    await component.getByPlaceholder("Spieler/Verein suchen…").fill("Müller");

    // Erfuellen BEIDE Filter (einmal ueber Name, einmal ueber Verein) -> sichtbar.
    await expect(component.getByText(players.nameInRange.name, { exact: true })).toBeVisible();
    await expect(component.getByText(players.teamInRange.name, { exact: true })).toBeVisible();

    // Name/Verein passt, aber Marktwert ausserhalb des Bereichs -> ausgeblendet.
    await expect(component.getByText(players.nameOutOfRange.name, { exact: true })).toHaveCount(0);
    // Marktwert im Bereich, aber weder Name noch Verein passen zur Suche -> ausgeblendet.
    await expect(component.getByText(players.rangeOnly.name, { exact: true })).toHaveCount(0);
    // Erfuellt keins von beiden -> ausgeblendet.
    await expect(component.getByText(players.neither.name, { exact: true })).toHaveCount(0);
  });
});

test.describe("Filter-Kombination: Startelf-Rang-Checkbox + Position", () => {
  test("Rang 1 UND Position=Sturm zusammen zeigen nur Sturm-Spieler mit Startelf-Rang 1", async ({ mount }) => {
    const players = {
      sturmRang1a: player({
        player_id: "combo-c-sturm-rang1-a", name: "Klaus Rangeins", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: 1, market_value: 1_000_000, average_points: 100,
      }),
      sturmRang1b: player({
        player_id: "combo-c-sturm-rang1-b", name: "Lena Rangeins", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: 1, market_value: 1_100_000, average_points: 110,
      }),
      sturmRang2: player({
        player_id: "combo-c-sturm-rang2", name: "Moritz Rangzwei", position: "Sturm",
        team_name: "SC Beispiel", status_code: null, starting_rank: 2, market_value: 1_200_000, average_points: 120,
      }),
      abwehrRang1: player({
        player_id: "combo-c-abwehr-rang1", name: "Nadja Abwehrrang", position: "Abwehr",
        team_name: "SC Beispiel", status_code: null, starting_rank: 1, market_value: 1_300_000, average_points: 130,
      }),
      mittelfeldRang3: player({
        player_id: "combo-c-mittelfeld-rang3", name: "Otto Mittendrin", position: "Mittelfeld",
        team_name: "SC Beispiel", status_code: null, starting_rank: 3, market_value: 1_400_000, average_points: 140,
      }),
    };

    const data = buildFixtureSnapshot({
      players: Object.fromEntries(Object.values(players).map((p) => [p.player_id, p])),
      own_squad_ids: [],
      owned_by: {},
    });
    const component = await mount(<AlleSpielerTab data={data} />);

    await component.getByLabel("Position").selectOption("Sturm");
    await component.getByRole("button", { name: /^Startelf-Rang/ }).click();
    await component.getByRole("checkbox", { name: "Rang 1", exact: true }).check();

    // Erfuellen BEIDE Filter -> sichtbar.
    await expect(component.getByText(players.sturmRang1a.name, { exact: true })).toBeVisible();
    await expect(component.getByText(players.sturmRang1b.name, { exact: true })).toBeVisible();

    // Sturm, aber Rang 2 statt 1 -> ausgeblendet.
    await expect(component.getByText(players.sturmRang2.name, { exact: true })).toHaveCount(0);
    // Rang 1, aber nicht Sturm -> ausgeblendet.
    await expect(component.getByText(players.abwehrRang1.name, { exact: true })).toHaveCount(0);
    // Erfuellt keins von beiden -> ausgeblendet.
    await expect(component.getByText(players.mittelfeldRang3.name, { exact: true })).toHaveCount(0);
  });
});
