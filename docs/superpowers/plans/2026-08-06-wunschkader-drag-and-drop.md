# Wunschkader Drag-and-Drop (Bank ↔ Startelf) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Karten im Wunschkader per Drag statt nur per Klick zwischen "Bank" und ihrer Positionsgruppe verschieben können (`HANDOFF.md`, Motion-Pilot-Folgearbeit (a), User-Idee vom 2026-08-05).

**Architecture:** Reine Input-Ebene, KEINE neue Domänenlogik. `toggleBench(uid)` (bereits vorhanden, `WunschkaderTab.tsx:251`) flippt schon heute unconditional zwischen `role: "Starter"` und `role: "Bank/Backup-Option"` — genau das, was der bestehende Button im `DetailModal` ("In Startelf verschieben"/"Auf die Bank") auslöst. Drag ist nur ein zweiter, zusätzlicher Weg, dieselbe Funktion aufzurufen — der Button bleibt unverändert bestehen (Desktop/Tastatur/Barrierefreiheit, additive Erweiterung, kein Ersatz).

Da `toggleBench()` bewusst KEINE Formations-Machbarkeit prüft (siehe Kommentar `WunschkaderTab.tsx:440-443` — eine ungültige Kombination wird zugelassen und nur über die "Formation: ..."-Anzeige sichtbar gemacht), braucht auch der Drag-Drop-Handler keine `canAddStarter()`-Gate-Logik — 1:1 dieselbe Semantik wie der bestehende Button, keine neue Regel erfinden.

Da jede Karte per Definition zu genau EINER Positionsgruppe gehört (`byPosition` gruppiert nach der echten, aufgelösten Spielerposition, nicht nach einem frei zuweisbaren Feld — `WunschkaderTab.tsx:202-211`), ist die Interaktion strukturell binär: **Bank vs. Positionsbereich**, nicht "welche der vier Positionsgruppen". Der Drop-Zonen-Check braucht deshalb nur EINE Grenze (das Bank-Grid-Rechteck) statt vier separaten Positionsgruppen-Rechtecken — Drop irgendwo außerhalb der Bank zählt als "Positionsbereich".

Motion-Bibliothek: `framer-motion` (bereits Dependency, `package.json:19`) — natives `drag` auf den existierenden, `layoutId`-tragenden `motion.div`-Wrappern der Karten. Keine neue Abhängigkeit.

**Tech Stack:** React + TypeScript, framer-motion, Playwright E2E (`frontend/tests-e2e/`, inkl. bereits vorhandenem `touchHelpers.ts::touchDrag()` für echte CDP-Touch-Gesten).

## Global Constraints

- `toggleBench()`, `canAddStarter()`, `matchedFormation()`, Autosave/Simulationsmodus — UNVERÄNDERT. Dieser Plan fügt nur eine zusätzliche Auslöse-Möglichkeit für den bereits bestehenden Zustandsübergang hinzu.
- Der bestehende Klick-Button im `DetailModal` bleibt erhalten (additiv, kein Ersatz).
- Tap zum Öffnen des Detail-Modals (`TargetCard`'s `onClick={onSelect}`, `WunschkaderTab.tsx:627`) MUSS weiterhin funktionieren — framer-motions `drag` hat eine kleine Bewegungsschwelle vor Aktivierung, ein reiner Tap darf nicht als Drag interpretiert werden. Live-verifizieren, nicht nur aus der Doku annehmen.
- Mobile: neue Drag-Geste darf die bestehende Wisch-Gesten-Tab-Navigation (`useSwipeTabs`, `App.tsx:124-161`) NICHT auslösen. Etablierter Escape-Hatch: `data-swipe-ignore` auf dem draggable Wrapper (gleiches Muster wie `table.tsx:54` für horizontal scrollende Tabellen).
- Tap-Ziele/Card-Größe unverändert (≥44px bereits durch bestehende Card-Größe erfüllt).
- Keine neue `<form>`-Nutzung, keine neuen `localStorage`-Keys.
- Jedes neue Verhalten braucht einen automatisierten Test (TDD: erst rot, dann grün) plus Mutation-Check.
- `npm install`/`npm run` nur in dieser isolierten Worktree, nicht im Haupt-Checkout (bereits erledigt — `node_modules` hier bereits installiert).

---

## File Structure

- Modify: `frontend/src/components/WunschkaderTab.tsx` — Refs, `handleCardDragEnd()`, `drag`-Props auf den beiden bestehenden Karten-`motion.div`-Blöcken (Positionsgruppen-Loop + Bank-Loop).
- Create: `frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts` — Kern-Interaktion (Drag Starter→Bank, Drag Bank→Starter) über `touchDrag()`.
- Create (oder ergänzen, falls Task 1 sie schon anlegt): Regressionstests für Tap-weiterhin-funktioniert und Swipe-Tab-Wechsel-bleibt-unberührt, im selben Spec-File oder einem zweiten.

---

### Task 1: Drag-Mechanik + Kern-Interaktionstest (Bank ↔ Startelf)

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`
- Create: `frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts`

**Interfaces:**
- Consumes: `touchDrag(page, from, to)` aus `frontend/tests-e2e/touchHelpers.ts` (bereits vorhanden, CDP-basierte echte Touch-Drag-Geste). `FIXTURE_PLAYERS` aus `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts` (bereits vorhanden, siehe `WunschkaderStatePersistsAcrossTabSwitch.spec.ts` für exakt dasselbe Navigations-/Fixture-Muster).
- Produces: keine neuen Exporte, keine geänderte Snapshot-/Firestore-Struktur — reine UI-Interaktion auf bestehendem `EditTarget[]`-State.

- [ ] **Step 1: Failing Test schreiben**

`frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts`:

```ts
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
    await page.getByRole("button", { name: /Auf die Bank/ }).click();
    await page.keyboard.press("Escape");

    const bankHeading = page.getByText(/^Bank \(/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    const card = bankGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true });
    await expect(card).toBeVisible();

    const cardBox = await card.boundingBox();
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
```

Hinweis fuer den Implementer: falls sich der genaue Button-Text fuer "Auf die Bank" (Regex `/Auf die Bank/`) nicht exakt in `WunschkaderTab.tsx` (Zeilen um 808-820, `IconActionBank`/`IconActionField`-Beschriftungen) wiederfindet, den Test an den tatsaechlichen Text anpassen — NICHT den Produktivcode an den Test.

- [ ] **Step 2: Test laufen lassen, rot bestätigen**

```bash
cd frontend && npx playwright test WunschkaderDragAndDrop.spec.ts
```
Expected: FAIL — Karten sind noch nicht draggable, `touchDrag()` bewegt nichts, beide Assertions auf die verschobene Position schlagen fehl.

- [ ] **Step 3: `WunschkaderTab.tsx` ändern**

Import-Zeile 2 erweitern (zusätzlicher Typ-Import, `PanInfo` fuer den `onDragEnd`-Handler-Typ):

```tsx
import { AnimatePresence, motion, type PanInfo } from "framer-motion";
```

Zwei neue Refs + Handler-Funktion einfügen, direkt vor dem `return (` der Komponente (aktuell Zeile 430):

```tsx
  const cardsAreaRef = useRef<HTMLDivElement>(null);
  const bankGridRef = useRef<HTMLDivElement>(null);

  // Drop-Zonen-Check ist bewusst binaer (Bank-Rechteck vs. "ausserhalb") statt
  // vier separaten Positionsgruppen-Rechtecken - jede Karte gehoert per
  // Definition zu genau einer Positionsgruppe (byPosition gruppiert nach der
  // echten Spielerposition, siehe oben), es gibt also nur EINE sinnvolle
  // Zielzone pro Karte ausserhalb der Bank. toggleBench() prueft bewusst
  // KEINE Formations-Machbarkeit (Kommentar weiter unten bei "Formation:") -
  // der Drag-Handler uebernimmt dieselbe Semantik 1:1, keine neue Regel.
  function handleCardDragEnd(target: EditTarget, info: PanInfo) {
    const bankEl = bankGridRef.current;
    if (!bankEl) return;
    const bankRect = bankEl.getBoundingClientRect();
    const droppedOverBank =
      info.point.x >= bankRect.left &&
      info.point.x <= bankRect.right &&
      info.point.y >= bankRect.top &&
      info.point.y <= bankRect.bottom;
    if (droppedOverBank !== isBench(target)) {
      toggleBench(target._uid);
    }
  }
```

Den Positionsgruppen- und Bank-Rendering-Block (aktuell Zeilen 507-570, von `{POSITIONS.map((position) => {` bis zum schliessenden `</div>` des Bank-Blocks) mit einem zusaetzlichen, layout-neutralen Wrapper-Div umschliessen (nur fuer den `cardsAreaRef` als `dragConstraints`-Grenze, `display: contents` haelt ihn layout-unsichtbar):

```tsx
      <div ref={cardsAreaRef} className="contents">
        {POSITIONS.map((position) => {
          /* ... unveraendert ... */
        })}

        <div className="mb-6">
          {/* ... unveraendert bis auf die beiden unten genannten Aenderungen ... */}
        </div>
      </div>
```

In den beiden bestehenden Karten-`motion.div`s (Positionsgruppen-Block UM Zeile 520, Bank-Block um Zeile 555) jeweils diese Props ergaenzen (Beispiel fuer den Positionsgruppen-Block, Bank-Block identisch):

```tsx
                    <motion.div
                      key={t._uid}
                      layoutId={`wunschkader-${t._uid}`}
                      custom={index}
                      variants={staggerItemVariants}
                      initial="initial"
                      animate={isActive ? "animate" : "initial"}
                      exit="exit"
                      drag
                      dragConstraints={cardsAreaRef}
                      dragSnapToOrigin
                      dragElastic={0.15}
                      whileDrag={{ scale: 1.03, zIndex: 10 }}
                      onDragEnd={(_event, info) => handleCardDragEnd(t, info)}
                      data-swipe-ignore
                    >
```

Am Bank-Grid-Container-Div (aktuell Zeile 550, `<div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">` direkt unter der "Bank (n)"-Überschrift) `ref={bankGridRef}` ergänzen:

```tsx
        <div ref={bankGridRef} className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

```bash
cd frontend && npx playwright test WunschkaderDragAndDrop.spec.ts
```
Expected: PASS, beide Tests.

**Falls `dragSnapToOrigin` + `layoutId` sichtbar ruckelt/kurz an der falschen Stelle aufblitzt** (nur live im Browser zuverlässig zu beurteilen, siehe "Nach Abschluss" unten): `dragSnapToOrigin` entfernen und stattdessen NUR auf die layoutId-getriebene Layout-Animation verlassen (bei einem No-Op-Drop bleibt die Karte dann ohne Snap-back-Animation kurz leicht versetzt stehen, bis die naechste Render-Passage sie einrastet — dokumentiere die getroffene Wahl kurz im Code-Kommentar, falls geaendert).

- [ ] **Step 5: Mutation-Check**

Setze `handleCardDragEnd()` temporär auf einen No-Op (`function handleCardDragEnd() {}`), laufe beide Tests erneut — MÜSSEN rot werden (Karte bleibt an ihrem Ausgangsort). Danach wiederherstellen und beide Tests erneut grün bestätigen.

- [ ] **Step 6: Vollen Frontend-Testlauf**

```bash
cd frontend && npm run build && npx vitest run && npx playwright test -c playwright-ct.config.ts
```
Expected: Build ohne TS-Fehler, alle Vitest-/Playwright-CT-Tests weiterhin grün (bestätigt, dass `TargetCard`/`toggleBench`/`byPosition` von aussen unverändert genutzt werden).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts
git commit -m "Wunschkader: Drag-and-Drop zwischen Bank und Positionsgruppe (framer-motion drag, kein neuer Dependency)"
```

---

### Task 2: Regressionstests — Tap öffnet weiterhin das Modal, Swipe-Tab-Wechsel bleibt unberührt

**Files:**
- Modify: `frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts`

**Interfaces:**
- Consumes: dieselben Helfer wie Task 1 (`touchDrag`, `FIXTURE_PLAYERS`), zusätzlich `page.getByLabel("Notiz")` als Nachweis "Detail-Modal ist offen" (identisches Muster wie `WunschkaderStatePersistsAcrossTabSwitch.spec.ts:19-20`).

- [ ] **Step 1: Failing Tests schreiben**

Im selben Spec-File (`WunschkaderDragAndDrop.spec.ts`) ergänzen:

```ts
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
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen (nur der zweite ist als echte Regression relevant)**

```bash
cd frontend && npx playwright test WunschkaderDragAndDrop.spec.ts
```
Erwartung: der erste neue Test ("reiner Tap") sollte bereits grün sein, wenn Task 1 korrekt implementiert ist (kein eigener Fix nötig, reine Abnahme). Der zweite Test ist die eigentliche Regressionsabsicherung fuer `data-swipe-ignore` — falls `data-swipe-ignore` in Task 1 vergessen wurde, schlägt er hier fehl (Tab wechselt faelschlich zu "Eigenes Team"). Falls beide bereits grün sind: Step 3 (Mutation-Check) ist dann der Beweis, dass die Tests nicht vakuos sind.

- [ ] **Step 3: Mutation-Check**

Entferne temporär `data-swipe-ignore` von den Karten-`motion.div`s (aus Task 1), laufe den zweiten Test erneut — MUSS rot werden (Tab wechselt zu "Eigenes Team" statt "Wunschkader" zu bleiben). Danach wiederherstellen, beide Tests erneut grün bestätigen.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/WunschkaderDragAndDrop.spec.ts
git commit -m "Wunschkader-Drag: Regressionstests fuer Tap-Weiterhin-Funktioniert und Swipe-Tab-Wechsel-Isolation"
```

---

## Nach Abschluss (Haupt-Thread, kein Subagent)

- **Live im Browser verifizieren** (CLAUDE.md: Touch-Gesten sind per Unit-/E2E-Test nicht zuverlässig vollständig abgedeckt) — Dev-Server starten (`npm run dev`), Wunschkader öffnen:
  - Desktop-Maus: Karte von einer Positionsgruppe auf die Bank ziehen und zurück, prüfen dass es sich "richtig" anfühlt (kein Ruckeln, kein Kleben am Cursor nach Drop).
  - Mobile-Emulation (Chrome DevTools Touch-Emulation oder echtes Gerät): dieselbe Geste per Touch, UND prüfen dass ein normaler Tab-Wechsel-Swipe ausserhalb der Karten weiterhin funktioniert.
  - Prüfen, ob `dragSnapToOrigin` (Step 4 in Task 1) die richtige Wahl war oder entfernt werden musste — falls geändert, Commit-Nachricht/Kommentar entsprechend nachziehen.
- `HANDOFF.md`: den Punkt "(a) Drag-and-Drop für Wunschkader-Karten" unter "Motion-Pilot Folge-Arbeit" entfernen (Punkt (b), Phase-2-Rollout, bleibt unverändert stehen — separates, weiterhin zurückgestelltes Thema).
