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

// Desktop-Variante: ab `sm:` ist der "Menü öffnen"-Button ausgeblendet
// (App.tsx: `sm:hidden`) und die horizontale Tab-Leiste sichtbar - der
// mobile Weg oben ist dort nicht klickbar. Auch die <h2>-Tab-Ueberschrift ist
// ab `sm:` ausgeblendet (die Tab-Leiste zeigt den Namen bereits), der
// Ankunfts-Check laeuft deshalb ueber den Tab-Inhalt selbst.
async function openWunschkaderDesktop(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Wunschkader", exact: true }).click();
  await expect(page.getByText(/^Bank \(/)).toBeVisible();
}

// Seit dem Final-Review-Umbau (2026-08-06) startet ein Drag NICHT mehr auf dem
// Kartenkoerper, sondern ausschliesslich auf dem kleinen Drag-Handle in der
// rechten oberen Kartenecke (framer-motion `dragListener={false}` +
// `useDragControls()`, siehe WunschkaderTab.tsx). Alle Drag-Gesten hier setzen
// deshalb am Handle an, nicht in der Kartenmitte.
function dragHandleIn(grid: import("@playwright/test").Locator) {
  return grid.getByRole("button", { name: "Karte ziehen" });
}

function center(box: { x: number; y: number; width: number; height: number }) {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
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

// Verschiebung, die framer-motion aktuell per x/y-MotionValue auf das
// Karten-Element schreibt. "none" (Ruhelage) und die Identitaetsmatrix werden
// beide als 0/0 gelesen - der Test interessiert sich nur fuer die
// Translation, nicht fuer das (nach dem Drag zurueckfedernde) whileDrag-Scale.
async function readTranslation(locator: import("@playwright/test").Locator): Promise<{ x: number; y: number }> {
  return locator.evaluate((el) => {
    const transform = getComputedStyle(el as HTMLElement).transform;
    if (!transform || transform === "none") return { x: 0, y: 0 };
    const matrix = new DOMMatrixReadOnly(transform);
    return { x: matrix.m41, y: matrix.m42 };
  });
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

    const handleBox = await waitForBoundingBoxSettled(dragHandleIn(abwehrGrid));
    const bankBox = await bankGrid.boundingBox();
    if (!handleBox || !bankBox) throw new Error("boundingBox fehlt");

    await touchDrag(page, center(handleBox), center(bankBox), 12);

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

    await waitForBoundingBoxSettled(card);
    const handleBox = await waitForBoundingBoxSettled(dragHandleIn(bankGrid));
    const abwehrBox = await abwehrGrid.boundingBox();
    if (!handleBox || !abwehrBox) throw new Error("boundingBox fehlt");

    await touchDrag(page, center(handleBox), center(abwehrBox), 12);

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
    const handleBox = await waitForBoundingBoxSettled(dragHandleIn(abwehrGrid));
    const bankBox = await bankGrid.boundingBox();
    if (!handleBox || !bankBox) throw new Error("boundingBox fehlt");

    await touchDrag(page, center(handleBox), center(bankBox), 12);

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

  // Regression fuer Finding 3 des Final-Reviews (2026-08-06): der haeufigste
  // Fehlversuch dieses Features ist ein Drop, der KEINE Zone wechselt (Ziel
  // verfehlt oder an derselben Stelle wieder losgelassen). Vorher federte die
  // Karte dabei nicht zurueck: framer-motion liess die Inertia-Animation
  // innerhalb des weiten ref-Rechtecks (dragConstraints={cardsAreaRef})
  // auslaufen und schrieb x/y als "protected" MotionValues - die Karte blieb
  // dauerhaft versetzt stehen (live gemessen: y+108.5px, ueber Re-Renders
  // hinweg). Mit den Origin-Constraints (DRAG_RETURN_TO_ORIGIN) zielt dieselbe
  // Inertia-Animation auf {min:0,max:0} pro Achse und landet damit garantiert
  // wieder auf der Ausgangsposition.
  test("Drop in derselben Zone laesst die Karte an ihre Ausgangsposition zurueckfedern (kein Steckenbleiben)", async ({
    page,
  }) => {
    await openWunschkader(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    const card = abwehrGrid.locator("[data-swipe-ignore]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    const bankBox = await bankGrid.boundingBox();
    const cardBoxBefore = await waitForBoundingBoxSettled(card);
    const handleBox = await dragHandleIn(abwehrGrid).boundingBox();
    if (!bankBox || !cardBoxBefore || !handleBox) throw new Error("boundingBox fehlt");

    // Kurzer Zug, der die eigene Zone NICHT verlaesst. Die Praemisse wird hart
    // geprueft, statt sie anzunehmen: liegt der Loslass-Punkt (auch nur
    // knapp) im Bank-Rechteck, wuerde der Test eine ganz andere Situation
    // messen (echter Zonenwechsel) und seine Aussage verlieren.
    const from = center(handleBox);
    const to = { x: from.x - 40, y: from.y + 60 };
    const insideBank =
      to.x >= bankBox.x && to.x <= bankBox.x + bankBox.width && to.y >= bankBox.y && to.y <= bankBox.y + bankBox.height;
    expect(insideBank).toBe(false);

    await touchDrag(page, from, to, 10);

    // Kein Zonenwechsel - die Karte bleibt in ihrer Positionsgruppe.
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0);

    // ... und sie steht wieder genau dort, wo sie vorher stand: weder als
    // Rest-Translation im transform (framer-motions x/y-MotionValues) noch in
    // der tatsaechlichen Bildschirmposition.
    await expect.poll(async () => Math.max(...Object.values(await readTranslation(card)).map(Math.abs))).toBeLessThan(1.5);
    const cardBoxAfter = await waitForBoundingBoxSettled(card);
    if (!cardBoxAfter) throw new Error("boundingBox fehlt");
    expect(Math.abs(cardBoxAfter.x - cardBoxBefore.x)).toBeLessThan(1.5);
    expect(Math.abs(cardBoxAfter.y - cardBoxBefore.y)).toBeLessThan(1.5);
  });

  // Regression fuer Finding 2 des Final-Reviews (2026-08-06): framer-motion
  // setzt `touch-action: none` inline auf jedes Element mit `drag`, solange
  // `dragListener !== false` (render/html/use-props.mjs). Solange die GANZE
  // Karte draggable war, war damit mobil das vertikale Seiten-Scrollen
  // praktisch im gesamten Tab blockiert (einspaltige Karten fuellen fast die
  // volle Viewport-Breite) - auf einem Tab, der ohne Scrollen nicht bedienbar
  // ist (bis zu MAX_SQUAD_SIZE Ziele in 4 Positionsgruppen + Bank).
  test("Vertikales Wischen auf dem Kartenkoerper scrollt weiterhin die Seite", async ({ page }) => {
    await openWunschkader(page);

    const maxScroll = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
    expect(maxScroll).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    const cardBox = await waitForBoundingBoxSettled(abwehrGrid.locator("[data-swipe-ignore]"));
    if (!cardBox) throw new Error("boundingBox fehlt");

    // Start bewusst im unteren Kartenbereich (klar unterhalb des 44px hohen
    // Drag-Handles in der rechten oberen Ecke - dort ist touch-action: none
    // gewollt), Wisch nach oben wie beim Weiterscrollen.
    await touchDrag(
      page,
      { x: cardBox.x + cardBox.width / 2, y: cardBox.y + cardBox.height - 8 },
      { x: cardBox.x + cardBox.width / 2, y: cardBox.y + cardBox.height - 8 - 150 },
      12
    );

    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  });
});

// Eigener Kontext ohne Touch-Emulation: das E2E-Projekt (siehe
// playwright-e2e.config.ts) emuliert bewusst ein Pixel 5 (hasTouch/isMobile),
// und genau deshalb ist der Desktop-Maus-Pfad in dieser Suite bisher nie
// gelaufen - Finding 1 des Final-Reviews (Chromium feuert nach
// mousedown+mousemove+mouseup trotz laufender framer-motion-Drag-Geste ein
// echtes `click`) war dadurch unsichtbar. test.use() ueberschreibt die
// Kontext-Optionen nur fuer diesen describe-Block, damit die uebrigen Tests
// (und die uebrigen Spec-Dateien) unveraendert im Touch-Kontext bleiben.
test.describe("Wunschkader Drag-and-Drop mit der Maus (Desktop, ohne Touch-Emulation)", () => {
  test.use({ viewport: { width: 1280, height: 900 }, hasTouch: false, isMobile: false, deviceScaleFactor: 1 });

  test("Maus-Drag am Handle verschiebt die Karte und oeffnet danach NICHT das Detail-Modal", async ({ page }) => {
    await openWunschkaderDesktop(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");

    const handleBox = await waitForBoundingBoxSettled(dragHandleIn(abwehrGrid));
    const bankBox = await bankGrid.boundingBox();
    if (!handleBox || !bankBox) throw new Error("boundingBox fehlt");

    const from = center(handleBox);
    const to = center(bankBox);
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    const steps = 12;
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      await page.mouse.move(from.x + (to.x - from.x) * t, from.y + (to.y - from.y) * t);
    }
    await page.mouse.up();

    await expect(bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0);
    // Der eigentliche Fund: vorher stand hier hinterher das Detail-Modal
    // offen. Die Notiz-Textarea existiert ausschliesslich in diesem Modal.
    await expect(page.getByLabel("Notiz")).toHaveCount(0);
  });

  test("Reiner Maus-Klick auf den Kartenkoerper oeffnet weiterhin das Detail-Modal", async ({ page }) => {
    await openWunschkaderDesktop(page);

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    await expect(page.getByLabel("Notiz")).toBeVisible();
  });
});
