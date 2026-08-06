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

  // Review-Fund (Coordinate-Space-Bug): handleCardDragEnd() verglich zunaechst
  // `info.point` (PanInfo - framer-motion baut das aus event.pageX/pageY,
  // siehe node_modules/framer-motion/dist/es/events/event-info.mjs,
  // Dokument-relativ INKLUSIVE Scroll-Offset) gegen `bankRect`
  // (getBoundingClientRect() - IMMER Viewport-relativ, OHNE Scroll-Offset).
  // Bei window.scrollY===0 sind beide Werte zufaellig identisch, weshalb die
  // beiden Tests oben den Bug nicht gefangen haben - die Standard-Fixture hat
  // nur EIN wunschkader_targets-Element und wurde in keinem der beiden Tests
  // aktiv gescrollt. Der Wunschkader-Tab ist aber bereits mit diesem einzigen
  // Ziel hoeher als der Pixel-5-Viewport (empirisch verifiziert:
  // scrollHeight ca. 1227px vs. innerHeight ca. 727px) - es braucht also
  // keine zusaetzlichen Ziele, nur einen expliziten Scroll vor dem Drag, um
  // die reale Nutzungssituation (Kader > 1 Bildschirm, siehe MAX_SQUAD_SIZE)
  // nachzustellen.
  test("Drag funktioniert korrekt, wenn die Seite gescrollt ist (Scroll-Offset darf die Drop-Zonen-Erkennung nicht verschieben)", async ({
    page,
  }) => {
    await openWunschkader(page);

    const maxScroll = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
    // Sanity-Check der eigentlichen Testpraemisse: ohne echten Scroll-Spielraum
    // wuerde dieser Test nichts beweisen (identisch zu den beiden Tests oben).
    expect(maxScroll).toBeGreaterThan(0);
    const scrollTarget = Math.min(200, maxScroll);
    await page.evaluate((y) => window.scrollTo(0, y), scrollTarget);
    const scrollY = await page.evaluate(() => window.scrollY);
    expect(scrollY).toBeGreaterThan(0);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    const card = abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true });
    await expect(card).toBeVisible();

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");

    // boundingBox() ist wie getBoundingClientRect() Viewport-relativ - liefert
    // nach dem Scroll oben automatisch die aktuell auf dem Bildschirm
    // sichtbare Position, exakt das, was auch ein echter Touch-Punkt treffen
    // wuerde.
    const cardBox = await card.boundingBox();
    const bankBox = await bankGrid.boundingBox();
    if (!cardBox || !bankBox) throw new Error("boundingBox fehlt");

    await touchDrag(
      page,
      { x: cardBox.x + cardBox.width / 2, y: cardBox.y + cardBox.height / 2 },
      { x: bankBox.x + bankBox.width / 2, y: bankBox.y + bankBox.height / 2 },
      12
    );

    await expect(bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0);
  });

  test("Ein reiner Tap auf eine Karte oeffnet weiterhin das Detail-Modal (Drag darf Tap nicht kaputt machen)", async ({ page }) => {
    await openWunschkader(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    await expect(page.getByLabel("Notiz")).toBeVisible();
  });

  test("Horizontales Ziehen auf einer Wunschkader-Karte wechselt NICHT versehentlich den Tab", async ({ page }) => {
    const heading = await openWunschkader(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    const card = abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true });
    const cardBox = await card.boundingBox();
    if (!cardBox) throw new Error("boundingBox fehlt");
    const cardMidY = cardBox.y + cardBox.height / 2;

    // Weiter Wisch nach links, wie ein echter Tab-Wechsel-Swipe (siehe
    // WunschkaderStatePersistsAcrossTabSwitch.spec.ts) - aber mit Start
    // GENAU auf der Karte statt auf der Ueberschrift, um data-swipe-ignore
    // zu pruefen.
    await touchDrag(page, { x: cardBox.x + cardBox.width - 5, y: cardMidY }, { x: cardBox.x - 200, y: cardMidY }, 8);

    await expect(heading).toHaveText("Wunschkader");
  });
});
