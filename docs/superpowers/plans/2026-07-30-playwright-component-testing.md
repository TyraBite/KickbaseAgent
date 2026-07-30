# Playwright Component Testing für WunschkaderTab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright Component Testing (`@playwright/experimental-ct-react`) für das Frontend einführen, mit zwei echten Regressionstests für zwei Bugs, die am 2026-07-30 live gefunden und in `WunschkaderTab.tsx` (Commit `e6eaef2`) gefixt wurden - ohne Firebase/Auth/Firestore, ohne Live-Daten.

**Architecture:** Jede Tab-Komponente ist eine reine Funktion eines `data: DashboardSnapshot`-Props (players-Map-Architektur). Component-Tests mounten `<WunschkaderTab data={fixture} />` direkt mit einem handgeschriebenen Fixture-Snapshot - kein Netzwerk, kein Firebase, deterministisch. Der `../firebase`-Import in `WunschkaderTab.tsx` wird per Vite-Alias auf einen leeren Mock umgeleitet, damit das echte SDK niemals im Testkontext lädt.

**Tech Stack:** `@playwright/test` + `@playwright/experimental-ct-react` (Version `1.62.0`, exakt gepinnt - das Paket selbst dokumentiert "does not respect semver"). Läuft in echtem Chromium (nicht jsdom).

## Global Constraints

- Alle neuen Test-Dateien (`*.ct.tsx`) liegen in `frontend/tests-ct/`, AUSSERHALB von `frontend/src/` - `tsconfig.json`s `include: ["src"]` würde sonst den `@playwright/experimental-ct-react`-Typ-Surface in den bestehenden `npm run typecheck`-Lauf hineinziehen. Fixture und Firebase-Mock liegen dagegen bewusst IN `frontend/src/test-fixtures/` (kein Playwright-Import, profitieren vom bestehenden Typecheck).
- Bestehende `frontend/package.json`-Scripts (`dev`, `build`, `preview`, `typecheck`) bleiben exakt unverändert - neue Scripts sind rein additiv.
- Kein echtes Firebase/Firestore/Auth in irgendeinem Test - der `../firebase`-Import wird immer über den Mock aufgelöst, nie über das echte SDK.
- `@playwright/test`/`@playwright/experimental-ct-react`: exakte Version `1.62.0` (kein `^`), da das Paket offiziell keinen Semver-Vertrag einhält.
- Nach JEDEM Task: `cd frontend && npm run typecheck` muss weiterhin fehlerfrei durchlaufen (bestehender Vertrag).
- Task 5 (CI-Workflow) ist eine CI/CD-Änderung - vor dem tatsächlichen Anlegen/Committen der neuen `.github/workflows/frontend-ct-tests.yml` explizit den Menschen bestätigen lassen, nicht automatisch mitcommitten.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`) - Repo-Owner pusht selbst.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/package.json` | Neue devDependencies (`@playwright/test`, `@playwright/experimental-ct-react`, `@types/node`) + Scripts `test:ct`/`test:ct:ui` |
| `frontend/playwright-ct.config.ts` | NEU - Playwright-CT-Konfiguration (Vite-Plugin, Firebase-Alias) |
| `frontend/playwright/index.html` + `frontend/playwright/index.tsx` | NEU - Playwright-CT-Pflicht-Mount-Template |
| `frontend/tests-ct/Smoke.ct.tsx` | NEU - Toolchain-Smoke-Test |
| `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts` | NEU - Fixture-Builder für `DashboardSnapshot` |
| `frontend/src/test-fixtures/firebase.mock.ts` | NEU - Leerer Stub für `../firebase`, per Vite-Alias eingehängt |
| `frontend/tests-ct/WunschkaderTab.ct.tsx` | NEU - die eigentlichen Regressionstests (Bug 1 + Bug 2) |
| `.github/workflows/frontend-ct-tests.yml` | NEU - unabhängiger, nicht-blockierender CI-Lauf |

---

## Task 1: Playwright-CT-Grundgerüst + Smoke-Test

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright-ct.config.ts`
- Create: `frontend/playwright/index.html`
- Create: `frontend/playwright/index.tsx`
- Create: `frontend/tests-ct/Smoke.ct.tsx`

**Interfaces:**
- Produces: `npm run test:ct` / `npm run test:ct:ui` als neue, funktionierende Scripts. Konsumiert von allen folgenden Tasks.

- [ ] **Step 1: devDependencies und Scripts ergänzen**

In `frontend/package.json`, `devDependencies` ergänzen (Reihenfolge egal, alphabetisch eingefügt):

```json
    "@playwright/experimental-ct-react": "1.62.0",
    "@playwright/test": "1.62.0",
    "@types/node": "^20.0.0",
```

`scripts` ergänzen (bestehende 4 Zeilen bleiben unverändert):

```json
    "test:ct": "playwright test -c playwright-ct.config.ts",
    "test:ct:ui": "playwright test -c playwright-ct.config.ts --ui",
```

- [ ] **Step 2: Installieren**

Run (aus `frontend/`): `npm install`
Expected: läuft durch, `package-lock.json` aktualisiert sich.

- [ ] **Step 3: Playwright-Browser installieren (einmalig, kein npm-Paket)**

Run (aus `frontend/`): `npx playwright install chromium`
Expected: lädt den Chromium-Browser herunter, kein Fehler.

- [ ] **Step 4: Smoke-Test schreiben**

Neue Datei `frontend/tests-ct/Smoke.ct.tsx`:

```tsx
import { test, expect } from "@playwright/experimental-ct-react";

test("Playwright-CT-Toolchain funktioniert", async ({ mount }) => {
  const component = await mount(<div>Playwright CT funktioniert</div>);
  await expect(component).toContainText("Playwright CT funktioniert");
});
```

- [ ] **Step 5: Testlauf, um das Fehlen der Config zu bestätigen**

Run (aus `frontend/`): `npm run test:ct`
Expected: FAIL - Playwright meldet, dass `playwright-ct.config.ts` nicht gefunden wurde (Config existiert noch nicht).

- [ ] **Step 6: Config + Mount-Template anlegen**

Neue Datei `frontend/playwright-ct.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";

export default defineConfig({
  testDir: "./tests-ct",
  timeout: 10_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    trace: "on-first-retry",
    ctViteConfig: {
      plugins: [react()],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

Neue Datei `frontend/playwright/index.html`:

```html
<html lang="de">
  <body>
    <div id="root"></div>
    <script type="module" src="./index.tsx"></script>
  </body>
</html>
```

Neue Datei `frontend/playwright/index.tsx` (lädt die echten Tailwind-Utility-Klassen, damit Traces/Screenshots wie in Produktion aussehen):

```tsx
import "../src/index.css";
```

- [ ] **Step 7: Testlauf erneut, jetzt erfolgreich**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS - `1 passed`.

- [ ] **Step 8: Bestehende Scripts gegenchecken**

Run (aus `frontend/`): `npm run typecheck`
Expected: weiterhin 0 Fehler (die neuen Dateien liegen außerhalb `src/`, `tsconfig.json` bleibt unverändert).

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/playwright-ct.config.ts frontend/playwright/index.html frontend/playwright/index.tsx frontend/tests-ct/Smoke.ct.tsx
git commit -m "Playwright Component Testing: Grundgeruest + Smoke-Test"
```

---

## Task 2: Fixture-Builder + Firebase-Mock

**Files:**
- Create: `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts`
- Create: `frontend/src/test-fixtures/firebase.mock.ts`
- Modify: `frontend/playwright-ct.config.ts`

**Interfaces:**
- Consumes: `DashboardSnapshot`, `PlayerRecord` (`frontend/src/types.ts`, bereits vorhanden).
- Produces: `buildFixtureSnapshot(overrides?: Partial<DashboardSnapshot>): DashboardSnapshot` und `FIXTURE_PLAYERS` (benannte Spieler-Konstanten). Konsumiert von Task 3 und Task 4.

- [ ] **Step 1: Fixture-Builder schreiben**

Neue Datei `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts`:

```ts
import type { DashboardSnapshot, PlayerRecord } from "../types";

function player(
  overrides: Partial<PlayerRecord> & Pick<PlayerRecord, "player_id" | "name" | "position">
): PlayerRecord {
  return {
    team_name: null,
    status_code: null,
    starting_rank: null,
    market_value: null,
    average_points: null,
    ...overrides,
  };
}

// Marktwert/Punkte der drei "close"-Spieler liegen absichtlich nah am Ziel
// (werden dadurch automatisch die 3 Vorschlaege - suggestReplacements()
// nimmt immer die 3 naechsten). "searchOnly" liegt absichtlich weit weg,
// damit er NICHT unter den 3 Vorschlaegen landet und nur ueber die
// Freitextsuche auffindbar ist - mit nur 1-2 Alternativen waere das nicht
// gleichzeitig darstellbar (siehe Plan-Kontext).
export const FIXTURE_PLAYERS = {
  target: player({
    player_id: "p-target-abwehr", name: "Kai Zielspieler", position: "Abwehr",
    market_value: 5_000_000, average_points: 180,
  }),
  suggestion1: player({
    player_id: "p-abwehr-close-1", name: "Lukas Nahstand", position: "Abwehr",
    market_value: 5_100_000, average_points: 175,
  }),
  suggestion2: player({
    player_id: "p-abwehr-close-2", name: "Jonas Nahstand", position: "Abwehr",
    market_value: 4_800_000, average_points: 190,
  }),
  suggestion3: player({
    player_id: "p-abwehr-close-3", name: "Peter Mittelnah", position: "Abwehr",
    market_value: 5_500_000, average_points: 165,
  }),
  searchOnly: player({
    player_id: "p-abwehr-weitweg", name: "Werner Weitweg", position: "Abwehr",
    market_value: 500_000, average_points: 20,
  }),
  // Bug-1-Regression braucht bewusst einen NICHT-Sturm-Spieler als Haupt-
  // Testsubjekt: der entfernte Code hatte "Sturm" als Default-Position -
  // ein Test, der nur nach einem Sturm-Spieler sucht, waere auch mit dem
  // alten, kaputten Code zufaellig gruen gewesen.
  torwart: player({
    player_id: "p-tw-frei", name: "Torsten Torwart", position: "Torwart",
    market_value: 2_000_000, average_points: 90,
  }),
  sturm: player({
    player_id: "p-sturm-frei", name: "Stefan Stürmer", position: "Sturm",
    market_value: 8_000_000, average_points: 220,
  }),
  mittelfeld: player({
    player_id: "p-mf-frei", name: "Micha Mittelfeld", position: "Mittelfeld",
    market_value: 3_000_000, average_points: 140,
  }),
};

export function buildFixtureSnapshot(overrides?: Partial<DashboardSnapshot>): DashboardSnapshot {
  const players = Object.fromEntries(Object.values(FIXTURE_PLAYERS).map((p) => [p.player_id, p]));
  return {
    players,
    calibration: null,
    transfermarkt_listings: [],
    // suggestion2 ist "Eigener Kader" (beweist, dass scoreReplacementPool()
    // sowohl Frei- als auch Eigener-Kader-Spieler als Kandidaten zulaesst).
    own_squad_ids: [FIXTURE_PLAYERS.suggestion2.player_id],
    owned_by: {},
    wunschkader_targets: [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }],
    wunschkader_formation: "3-4-3",
    ligaanalyse: [],
    ml_metrics: null,
    ml_accuracy_trend: null,
    signal_thresholds: { good: 1.1, critical: 0.9 },
    own_budget_exact: 10_000_000,
    own_available_budget: null,
    ...overrides,
  };
}
```

- [ ] **Step 2: Typecheck**

Run (aus `frontend/`): `npm run typecheck`
Expected: 0 Fehler (Fixture ist vollstaendig typsicher gegen `DashboardSnapshot`/`PlayerRecord`).

- [ ] **Step 3: Firebase-Mock schreiben**

Neue Datei `frontend/src/test-fixtures/firebase.mock.ts`:

```ts
// Test-only Stub fuer "../firebase" - wird per Vite-Alias in
// playwright-ct.config.ts eingehaengt, damit WunschkaderTab.tsx's
// `import { db } from "../firebase"` in Component-Tests NIEMALS das echte
// Firebase-SDK laedt. Bewusst KEIN Import aus dem echten "firebase"-Paket -
// das macht es strukturell unmoeglich (nicht nur "wahrscheinlich harmlos"),
// dass initializeApp/getAuth/getFirestore in einem CT-Lauf ausgefuehrt
// werden.
export const auth = {};
export const db = {};
```

- [ ] **Step 4: Vite-Alias in die Config eintragen**

In `frontend/playwright-ct.config.ts`, `ctViteConfig` erweitern:

```ts
import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests-ct",
  timeout: 10_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    trace: "on-first-retry",
    ctViteConfig: {
      plugins: [react()],
      resolve: {
        alias: [
          {
            find: /^(\.\.\/)+firebase$/,
            replacement: path.resolve(__dirname, "src/test-fixtures/firebase.mock.ts"),
          },
        ],
      },
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

(`path`/`fileURLToPath` statt eines rohen `__dirname`, weil `package.json`s `"type": "module"` bedeutet, dass echtes CommonJS-`__dirname` in diesem ESM-Kontext nicht existiert. Die Regex `/^(\.\.\/)+firebase$/` trifft den Import unabhaengig davon, aus welcher Verzeichnistiefe importiert wird - aktuell nur `WunschkaderTab.tsx`, aber robust falls spaeter weitere Tab-Komponenten CT-Tests bekommen.)

- [ ] **Step 5: Bisherige Tests laufen weiterhin**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS - der Smoke-Test aus Task 1 ist von der neuen Alias-Regel nicht betroffen (er importiert kein Firebase).

**Hinweis für Task 3:** Der Alias wird hier nur verdrahtet, aber erst von Task 3 wirklich durchlaufen (das ist der erste Test, der `WunschkaderTab.tsx` - und damit den `../firebase`-Import - tatsächlich mountet).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/test-fixtures/dashboardSnapshot.fixture.ts frontend/src/test-fixtures/firebase.mock.ts frontend/playwright-ct.config.ts
git commit -m "Playwright CT: Fixture-Builder fuer DashboardSnapshot + Firebase-Mock-Alias"
```

---

## Task 3: Regressionstest Bug 1 - Add-Dialog positionsübergreifend

**Files:**
- Create: `frontend/tests-ct/WunschkaderTab.ct.tsx`

**Interfaces:**
- Consumes: `buildFixtureSnapshot()`/`FIXTURE_PLAYERS` (Task 2), `WunschkaderTab` (`frontend/src/components/WunschkaderTab.tsx`, bereits vorhanden, unverändert).

**Testdesign-Entscheidung** (bewusst, nicht `AddTargetModal` isoliert testen): `AddTargetModal` ist eine nicht-exportierte lokale Funktion in `WunschkaderTab.tsx` - sie zu exportieren wäre eine Produktivcode-Änderung nur für Testzwecke. Ein gefaktes `onAdd`-Prop würde außerdem nur den Modal-internen Aufruf-Shape prüfen, nicht die eigentliche Bug-Stelle (das Zusammenspiel aus entferntem `<select>`, `searchAnyPosition()` und dem echten Parent-State). Der Test geht deshalb über die komplette `WunschkaderTab`-Komponente.

- [ ] **Step 1: Test schreiben**

Neue Datei `frontend/tests-ct/WunschkaderTab.ct.tsx`:

```tsx
import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Bug 1 - Add-Dialog ohne Positions-Zwang", () => {
  test("findet einen Torwart ueber den generischen Bank-Add-Dialog, ohne Position vorzuwaehlen", async ({ mount }) => {
    const component = await mount(<WunschkaderTab data={buildFixtureSnapshot()} />);

    // Gezielt den Bank-"+ Ziel"-Button ansteuern, nicht den einer
    // Positions-Gruppe (beide rendern denselben Text "+ Ziel").
    const bankHeading = component.getByText(/^Bank \(\d+\)$/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    await bankGrid.getByRole("button", { name: "+ Ziel" }).click();

    // Fail-fast: der generische Dialog hat KEINEN "(Position)"-Suffix.
    await expect(component.getByRole("heading", { name: "Ziel hinzufügen", exact: true })).toBeVisible();

    // Regression-Guard: kein <select> mehr im generischen Add-Formular
    // (das Formation-Select liegt ausserhalb dieses <form>).
    await expect(component.locator("form select")).toHaveCount(0);

    // Kern-Assertion: Suche nach einem NICHT-Sturm-Spieler funktioniert
    // ohne vorherige Positionsauswahl. Unter dem alten Code (Default
    // "Sturm") haette das 0 Treffer ergeben.
    await component.getByPlaceholder("Spieler suchen…").fill("Torsten");
    const result = component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.torwart.name) });
    await expect(result).toBeVisible();

    await result.click();
    await component.getByRole("button", { name: "Hinzufügen" }).click();

    await expect(component.getByText("Bank (1)")).toBeVisible();
    await expect(bankGrid.getByText(FIXTURE_PLAYERS.torwart.name)).toBeVisible();
  });
});
```

- [ ] **Step 2: Testlauf**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS - der zugrundeliegende Fix ist bereits in Produktion (Commit `e6eaef2`), dieser Test ist ein retroaktiver Regressionstest, keine Neuimplementierung.

- [ ] **Step 3: Beweisen, dass der Test nicht vakuos ist (Mutation-Check)**

```bash
cd /workspace/work
git show 48a9fe4:frontend/src/components/WunschkaderTab.tsx > /tmp/old-wunschkadertab.tsx
cp frontend/src/components/WunschkaderTab.tsx /tmp/current-wunschkadertab-backup.tsx
cp /tmp/old-wunschkadertab.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: FAIL - mit dem alten Code (Default-Position "Sturm", positionsgefilterte Suche) findet die Suche nach "Torsten" keinen Treffer, der Test schlägt fehl.

Danach wiederherstellen:

```bash
cp /tmp/current-wunschkadertab-backup.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: PASS - wieder grün mit dem echten, gefixten Code.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/WunschkaderTab.ct.tsx
git commit -m "Playwright CT: Regressionstest fuer Bug 1 (Add-Dialog Positions-Zwang)"
```

---

## Task 4: Regressionstests Bug 2 - Vorschläge bleiben Compare-first, Freitext tauscht direkt

**Files:**
- Modify: `frontend/tests-ct/WunschkaderTab.ct.tsx`

**Interfaces:**
- Consumes: gleich wie Task 3, zusätzlich `PlayerCompareModal`-Textmarker ("Diesen als Ersatz wählen") als Nachweis, dass der Vergleich geöffnet wurde.

Jeder der drei Fälle ist ein eigener, unabhängiger `test()` mit frischem `mount()` (nicht auf demselben Component-State aufeinander aufbauend) - sonst würde z.B. Test 2 (der wirklich tauscht) den Ausgangszustand für Test 3 verändern.

- [ ] **Step 1: Die drei Tests ergänzen**

In `frontend/tests-ct/WunschkaderTab.ct.tsx`, nach dem bestehenden `test.describe`-Block ergänzen:

```tsx
test.describe("Bug 2 - Vorschlaege vs. Freitext im Wechsel-Dialog", () => {
  async function openWechsel(mount: Parameters<Parameters<typeof test>[1]>[0]["mount"]) {
    const component = await mount(<WunschkaderTab data={buildFixtureSnapshot()} />);
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Wechsel" }).click();
    return component;
  }

  test("Vorschlag-Chip oeffnet weiterhin zuerst den Vergleich, tauscht nicht direkt", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.suggestion1.name) }).click();

    await expect(component.getByText("Diesen als Ersatz wählen").first()).toBeVisible();
    // Noch kein Tausch passiert - das Ziel steht weiterhin auf der Karte.
    await expect(component.getByText(FIXTURE_PLAYERS.target.name)).toBeVisible();
  });

  test("Freitext-Ergebnis (Hauptlabel) tauscht direkt, ohne den Vergleich zu oeffnen", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByPlaceholder("Anderen freien Spieler gleicher Position suchen…").fill("Weitweg");
    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.searchOnly.name) }).click();

    // Kein Vergleichs-Marker sollte je erscheinen.
    await expect(component.getByText("Diesen als Ersatz wählen")).toHaveCount(0);

    // replaceTarget() schliesst das Detail-Modal komplett (setSelected(null)) -
    // die richtige Assertion ist daher NICHT "Name im noch offenen Modal
    // geaendert" (es ist nicht mehr offen), sondern: das Ziel in der
    // Abwehr-Positionsgruppe hat gewechselt.
    const abwehrHeading = component.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.searchOnly.name)).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name)).toHaveCount(0);
  });

  test("Freitext-Ergebnis 'Vergleichen'-Button oeffnet den Vergleich, ohne zu tauschen", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByPlaceholder("Anderen freien Spieler gleicher Position suchen…").fill("Weitweg");
    await component.getByRole("button", { name: "Vergleichen", exact: true }).click();

    await expect(component.getByText("Diesen als Ersatz wählen").first()).toBeVisible();

    const abwehrHeading = component.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.target.name)).toBeVisible();
    await expect(abwehrGrid.getByText(FIXTURE_PLAYERS.searchOnly.name)).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Testlauf**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS - alle 5 Tests grün (1 aus Task 3 + 3 neue + der Smoke-Test aus Task 1).

- [ ] **Step 3: Mutation-Check für den Direkt-Tausch-Test**

```bash
cd /workspace/work
git show 4663dcf:frontend/src/components/WunschkaderTab.tsx > /tmp/old-wunschkadertab-2.tsx
cp frontend/src/components/WunschkaderTab.tsx /tmp/current-wunschkadertab-backup-2.tsx
cp /tmp/old-wunschkadertab-2.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

(`4663dcf` ist der Stand direkt NACH der ursprünglichen Compare-Einführung, aber VOR dem Direkt-Tausch-Fix - zu diesem Zeitpunkt öffneten Freitext-Ergebnisse noch den Vergleich statt direkt zu tauschen.)

Expected: FAIL - mindestens der zweite neue Test ("Freitext-Ergebnis (Hauptlabel) tauscht direkt...") schlägt fehl, weil unter diesem alten Stand ein Klick auf das Hauptlabel den Vergleich öffnet statt zu tauschen.

Danach wiederherstellen:

```bash
cp /tmp/current-wunschkadertab-backup-2.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: PASS - wieder alle 5 Tests grün.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/WunschkaderTab.ct.tsx
git commit -m "Playwright CT: Regressionstests fuer Bug 2 (Vorschlaege Compare-first, Freitext Direkt-Tausch)"
```

---

## Task 5: CI-Workflow (separat, nicht blockierend)

**Files:**
- Create: `.github/workflows/frontend-ct-tests.yml`

**Vor diesem Task:** explizit beim Menschen nachfragen/bestätigen lassen, dass ein neuer GitHub-Actions-Workflow angelegt werden soll (CI/CD-Änderung, siehe Global Constraints) - nicht automatisch mitcommitten.

- [ ] **Step 1: Workflow-Datei anlegen**

Neue Datei `.github/workflows/frontend-ct-tests.yml`:

```yaml
name: Frontend Component Tests (Playwright)

# Unabhaengiger, NICHT blockierender Testlauf fuer die Playwright-Component-
# Tests (frontend/tests-ct/) - laeuft parallel zu "Frontend Deploy (GitHub
# Pages)" (frontend-pilot.yml), aber ohne "needs:"-Abhaengigkeit, blockiert
# den Deploy also nie. Alle Tests mocken Firebase (siehe
# frontend/src/test-fixtures/firebase.mock.ts) - kein echtes Firestore/Auth,
# keine Secrets noetig.

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - '.github/workflows/frontend-ct-tests.yml'
  pull_request:
    paths:
      - 'frontend/**'
  workflow_dispatch: {}

jobs:
  component-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright browser
        working-directory: frontend
        run: npx playwright install --with-deps chromium

      - name: Run component tests
        working-directory: frontend
        run: npm run test:ct
```

- [ ] **Step 2: Verifikation**

Nach dem Push: `gh workflow run "Frontend Component Tests (Playwright)"` (oder abwarten, bis der nächste `frontend/**`-Push ihn automatisch auslöst), dann `gh run watch <run-id> --exit-status` - muss grün durchlaufen UND darf den "Frontend Deploy (GitHub Pages)"-Lauf nicht beeinflussen (beide laufen unabhängig, kein gegenseitiges Warten).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/frontend-ct-tests.yml
git commit -m "CI: unabhaengiger, nicht-blockierender Playwright-Component-Test-Workflow"
```

---

## Bewusst außen vor

- **Dark-Mode-Kontrast-Lesbarkeits-Bug** (der dritte, live gefundene Bug): reine DOM-Struktur/Verhalten-Assertions können unlesbaren-aber-strukturell-vorhandenen Text nicht erkennen. Der betroffene `<select>` wurde ohnehin als Teil des Bug-1-Fixes entfernt. Für zukünftige Fälle dieser Bugklasse bräuchte es zusätzlich visuelles Screenshot-Diffing oder `@axe-core/playwright`-Kontrast-Checks - nicht Teil dieses Plans.
- **Volles E2E / echter Login-Flow**: keine Firebase-Auth-Emulation, keine echten Firestore-Reads. `firestore.rules` erlaubt Lesen ohnehin nur einer einzigen, hartcodierten Firebase-UID - ein Emulator-Setup wäre ein separates, deutlich größeres Projekt.
- **Save-Flow (`handleSave()`/`setDoc`)**: keiner der Tests klickt "Speichern" - der `db`-Mock ist ein leeres Objekt, absichtlich nicht für echte Firestore-Schreib-Simulation ausgelegt. Ein künftiger Test dafür bräuchte einen sorgfältigeren Fake oder müsste `setDoc` selbst abfangen.

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: beide vom User benannten, konkreten Bugs haben je einen Task mit echtem Regressionstest (Task 3 = Bug 1, Task 4 = Bug 2). Die explizit gewünschte Einschränkung (Component statt E2E, kein Firebase) ist durchgängig eingehalten (Task 2s Mock, Global Constraints). Die bewusst ausgeschlossene dritte Bugklasse ist explizit benannt, nicht stillschweigend übergangen.
- **Platzhalter-Scan**: keine TBD/"siehe oben"/unvollständigen Code-Blöcke gefunden - jeder Step hat echten, lauffähigen Code oder einen konkreten Shell-Befehl mit exaktem Erwartungswert.
- **Typ-Konsistenz**: `FIXTURE_PLAYERS`/`buildFixtureSnapshot()` (Task 2) werden in Task 3 und 4 mit identischen Property-Namen (`.name`, `.player_id`) referenziert. Alle in der Fixture verwendeten `DashboardSnapshot`/`PlayerRecord`-Felder wurden gegen den echten aktuellen Stand von `frontend/src/types.ts` verifiziert (nicht aus Erinnerung übernommen). Die Distanz-Berechnung für die 3 Vorschläge (Task 2s Kommentar) wurde händisch gegen `scoreReplacementPool()`s echte Formel (`WunschkaderTab.tsx:40-56`) durchgerechnet, um zu bestätigen, dass genau `suggestion1/2/3` die 3 Vorschläge werden und `searchOnly` draußen bleibt.
- **Gegen den echten Code verifiziert**: `WunschkaderTab.tsx` wurde in voller Länge gelesen (aktueller main-Stand, Commit `e6eaef2` + `a719204`), nicht aus Session-Erinnerung übernommen - exakte Texte (`"Ziel hinzufügen"`, `"Spieler suchen…"`, `"Bank (0)"`, `"Diesen als Ersatz wählen"` aus `PlayerCompareModal.tsx`) sind 1:1 aus der Datei zitiert. Die Mutation-Check-Commits (`48a9fe4` für Bug 1, `4663dcf` für Bug 2) wurden per `git log` exakt verifiziert, nicht geraten.
