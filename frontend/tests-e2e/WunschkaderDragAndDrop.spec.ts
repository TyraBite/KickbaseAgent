import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";
import { FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

async function openWunschkader(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Menü öffnen" }).click();
  await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();
  const heading = page.getByRole("heading", { level: 2 });
  await expect(heading).toHaveText("Wunschkader");
  return heading;
}

// Der Bank<->Startelf-Wechsel triggert eine framer-motion `layoutId`-Shared-
// Layout-Animation (dieselbe layoutId existiert in der Positionsgruppen- UND
// der Bank-motion.div, siehe WunschkaderTab.tsx) - beim Umsetzen per Klick
// "fliegt" die Karte sichtbar von ihrer alten an ihre neue Position, mit
// framer-motions Default-Spring (keine eigene Transition-Config hinterlegt).
// boundingBox() waehrend dieser Animation liefert eine Zwischenposition, an
// der ein direkt danach gestarteter Touch-Drag ins Leere greift (live
// beobachtet: Drop landete daneben, Testassertion schlug fehl). Es wird
// deshalb per Polling auf eine ueber mehrere Messungen hinweg unveraenderte
// Position gewartet, statt eine feste Wartezeit zu raten.
async function waitForBoundingBoxSettled(locator: import("@playwright/test").Locator) {
  let lastKey = "";
  let stableReads = 0;
  for (let i = 0; i < 30; i++) {
    const box = await locator.boundingBox();
    const key = box ? `${box.x.toFixed(1)}:${box.y.toFixed(1)}` : "none";
    if (key === lastKey && key !== "none") {
      stableReads++;
      if (stableReads >= 3) return box;
    } else {
      stableReads = 0;
      lastKey = key;
    }
    await locator.page().waitForTimeout(100);
  }
  throw new Error("boundingBox() wurde nicht stabil (Layout-Animation vermutlich haengengeblieben)");
}

test.describe("Wunschkader Drag-and-Drop (Bank ↔ Startelf)", () => {
  test("Karte aus einer Positionsgruppe auf die Bank ziehen verschiebt sie dorthin", async ({ page }) => {
    await openWunschkader(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    const card = abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true });
    await expect(card).toBeVisible();

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");

    const cardBox = await card.boundingBox();
    const bankBox = await bankGrid.boundingBox();
    if (!cardBox || !bankBox) throw new Error("boundingBox fehlt");

    await touchDrag(
      page,
      { x: cardBox.x + cardBox.width / 2, y: cardBox.y + cardBox.height / 2 },
      { x: bankBox.x + bankBox.width / 2, y: bankBox.y + bankBox.height / 2 },
      12
    );

    // Karte erscheint jetzt unter Bank, nicht mehr unter Abwehr.
    await expect(bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0);
  });

  test("Karte von der Bank in den Positionsbereich ziehen macht sie zum Starter", async ({ page }) => {
    await openWunschkader(page);

    // Erst per bestehendem Button auf die Bank legen (Vorbedingung fuer diesen Test,
    // nutzt bewusst den unveraenderten, bereits funktionierenden Weg statt Drag).
    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    // Tatsaechlicher Button-Text ist "Bank" (siehe WunschkaderTab.tsx,
    // IconActionBank-Beschriftung um Zeile 819) - nicht "Auf die Bank" wie im
    // Task-Brief angenommen. Der Accessible Name enthaelt zusaetzlich das
    // aria-label des Icons selbst (IconActionBank hat aria-label="Bank"),
    // daher kein exact-Match.
    await page.getByRole("button", { name: /Bank/ }).click();
    await page.keyboard.press("Escape");

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    const card = bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true });
    await expect(card).toBeVisible();

    const cardBox = await waitForBoundingBoxSettled(card);
    const abwehrBox = await abwehrGrid.boundingBox();
    if (!cardBox || !abwehrBox) throw new Error("boundingBox fehlt");

    await touchDrag(
      page,
      { x: cardBox.x + cardBox.width / 2, y: cardBox.y + cardBox.height / 2 },
      { x: abwehrBox.x + abwehrBox.width / 2, y: abwehrBox.y + abwehrBox.height / 2 },
      12
    );

    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0);
  });
});
