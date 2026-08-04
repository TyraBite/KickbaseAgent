import { test, expect } from "@playwright/experimental-ct-react";
import FeedbackTab from "../src/components/FeedbackTab";
import type { RecordedSetDocCall, RecordedArrayUnion } from "../src/test-fixtures/firestore.mock";

test.describe("Feedback-Typ (Bug/Idee) ist entfernt", () => {
  test("kein Bug/Idee-Toggle im Formular, neues Item hat kein type-Feld", async ({ mount, page }) => {
    const component = await mount(<FeedbackTab now={Date.now()} />);

    await expect(component.getByRole("button", { name: "🐛 Bug" })).toHaveCount(0);
    await expect(component.getByRole("button", { name: "💡 Idee" })).toHaveCount(0);

    await component.getByPlaceholder("Was ist kaputt oder was wäre hilfreich?").fill("Testeintrag ohne Typ");
    await component.getByRole("button", { name: "Hinzufügen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);

    const calls: RecordedSetDocCall[] = await page.evaluate(() => (window as any).__ctFirestoreCalls ?? []);
    const written = (calls[0].data as { items: RecordedArrayUnion }).items;
    const item = written.__ctArrayUnion[0];
    expect(item).not.toHaveProperty("type");
    expect(item.text).toBe("Testeintrag ohne Typ");
  });
});
