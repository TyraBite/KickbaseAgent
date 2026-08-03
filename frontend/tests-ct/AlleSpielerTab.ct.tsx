import { test, expect } from "@playwright/experimental-ct-react";
import AlleSpielerTab from "../src/components/AlleSpielerTab";
import { buildFixtureSnapshot } from "../src/test-fixtures/dashboardSnapshot.fixture";

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
