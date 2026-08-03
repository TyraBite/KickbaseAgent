# Playwright-Regressionsabdeckung für session-gefundene FE-Bugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright Component- und E2E-Tests einführen, die drei echte, nur per Real-Browser-Test gefundene Frontend-Bugs (Stale-Debounce-Save, Cursor-Teleport bei Tausenderpunkt-Löschung, Touch-Scrub-vs-Tab-Swipe-Konflikt) dauerhaft als automatisierte Regressionstests absichern — inklusive der bereits geplanten, aber nie ausgeführten Grundgerüst-Infrastruktur aus `docs/superpowers/plans/2026-07-30-playwright-component-testing.md`.

**Architecture:** Zwei getrennte Playwright-Projekte. (1) `@playwright/experimental-ct-react` Component-Tests (`frontend/tests-ct/`) mounten einzelne Tab-Komponenten gegen einen handgeschriebenen `DashboardSnapshot`-Fixture, Firebase wird per Vite-`resolve.alias` beim Import wegersetzt (`../firebase` und `firebase/firestore`) — kein echtes SDK läuft je in einem CT-Test. (2) `@playwright/test` E2E-Tests (`frontend/tests-e2e/`) starten die komplette App gegen einen echten, separat konfigurierten Vite-Dev-Server (`vite.e2e.config.ts`), der `firebase/auth` + `firebase/firestore` auf **Paket-Ebene** aliast, damit `App.tsx` selbst (Auth-Gate, zwei `getDoc`-Reads) transparent gefaked wird, ohne dass eine einzige Produktivdatei angefasst wird.

**Tech Stack:** `@playwright/test` + `@playwright/experimental-ct-react`, beide exakt Version `1.62.0` (kein `^` — das Paket dokumentiert, dass es keinem Semver-Vertrag folgt). Ausschließlich Chromium (inkl. CDP `Input.dispatchTouchEvent` für echte Touch-Emulation).

## Global Constraints

- Kein Test-only Code (keine `import.meta.env.VITE_TEST_*`-Verzweigungen, keine test-only Exports) in `frontend/src/App.tsx`, `frontend/src/components/WunschkaderTab.tsx`, `frontend/src/components/AlleSpielerTab.tsx`, `frontend/src/components/MlGenauigkeitTab.tsx`, `frontend/src/firebase.ts` — jedes Firebase-Fake läuft ausschließlich über Vite `resolve.alias` (Build-Zeit-Modul-Tausch). Keine dieser fünf Dateien wird in diesem Plan verändert.
- Kein Firebase Emulator Suite — alle Fakes sind handgeschriebene JS-Module, die per Alias eingehängt werden.
- Neue Test-Dateien (`*.ct.tsx`, `*.spec.ts`) liegen in `frontend/tests-ct/` bzw. `frontend/tests-e2e/`, AUSSERHALB von `frontend/src/` (`tsconfig.json`s `include: ["src"]` darf den Playwright-Typ-Surface nicht in `npm run typecheck` ziehen). Fixtures/Mocks liegen dagegen IN `frontend/src/test-fixtures/` (kein Playwright-Import, profitieren vom bestehenden Typecheck).
- Nach JEDEM Task: `cd frontend && npm run typecheck` muss fehlerfrei durchlaufen.
- Exakte Version `1.62.0` (kein `^`) für `@playwright/test`/`@playwright/experimental-ct-react`.
- Sandbox-Hinweis (nur für lokale Läufe in dieser Dev-Sandbox relevant, NICHT für CI): dieser Container hat kein root und keine Chromium-System-Libs — ein Workaround aus einer früheren Session extrahiert `.deb`-Pakete per `apt-get download`+`dpkg-deb -x` in einen Userspace-Root (`/tmp/chromedeps/root`) und setzt `LD_LIBRARY_PATH` entsprechend, bevor `npx playwright ...`-Befehle laufen. GitHub-Actions-Runner (`ubuntu-latest`) haben root — dort reicht `npx playwright install --with-deps chromium` ohne jeden Workaround.
- CI-Workflow-Erstellung (Task 10) ist für diesen gesamten Plan bereits vom Repo-Owner bestätigt — kein weiterer Rückfrage-Gate vor dem Anlegen der Workflow-Datei nötig.
- Dieser Plan ersetzt Task 2 und Task 5 von `docs/superpowers/plans/2026-07-30-playwright-component-testing.md` (Fixture war stale gegen den aktuellen `frontend/src/types.ts`-Stand; CI-Workflow-Name/Inhalt wird durch Task 10 hier ersetzt). Tasks 1/3/4 dieses Plans entsprechen inhaltlich den alten Tasks 1/3/4, mit einer notwendigen Korrektur an den `<WunschkaderTab>`-Mount-Aufrufen (die Komponente verlangt inzwischen zusätzliche Pflicht-Props `wunschkader`/`onSaved`, die es beim alten Plan noch nicht gab).

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/package.json` | Neue devDependencies + Scripts `test:ct`/`test:ct:ui`/`test:e2e`/`test:e2e:ui` |
| `frontend/playwright-ct.config.ts` | NEU — CT-Konfiguration, Vite-Plugin, zwei Firebase-Aliase |
| `frontend/playwright/index.html` + `frontend/playwright/index.tsx` | NEU — CT-Pflicht-Mount-Template |
| `frontend/tests-ct/Smoke.ct.tsx` | NEU — Toolchain-Smoke-Test |
| `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts` | NEU — Fixture-Builder für `DashboardSnapshot` |
| `frontend/src/test-fixtures/firebase.mock.ts` | NEU — Leerer Stub für `../firebase` (CT) |
| `frontend/src/test-fixtures/firestore.mock.ts` | NEU — Aufzeichnender Stub für `firebase/firestore` (CT) |
| `frontend/tests-ct/WunschkaderTab.ct.tsx` | NEU — Regressionstests Add-Dialog + Vorschläge/Freitext |
| `frontend/tests-ct/WunschkaderTabAutoSave.ct.tsx` | NEU — Regressionstest Stale-Debounce-Save |
| `frontend/tests-ct/AlleSpielerTab.ct.tsx` | NEU — Regressionstest Cursor-Position |
| `frontend/vite.e2e.config.ts` | NEU — Vite-Config für den E2E-Dev-Server, Firebase-Pakete aliast |
| `frontend/playwright-e2e.config.ts` | NEU — E2E-Konfiguration (`@playwright/test`, Pixel-5-Projekt) |
| `frontend/src/test-fixtures/firebaseAuth.e2e.mock.ts` | NEU — Fake `firebase/auth` für E2E |
| `frontend/src/test-fixtures/firebaseFirestore.e2e.mock.ts` | NEU — Fake `firebase/firestore` für E2E |
| `frontend/tests-e2e/touchHelpers.ts` | NEU — echte CDP-Touch-Drag-Emulation |
| `frontend/tests-e2e/TouchScrubVsSwipe.spec.ts` | NEU — Regressionstest Touch-Scrub vs. Tab-Swipe |
| `.github/workflows/frontend-playwright-tests.yml` | NEU — unabhängiger, nicht-blockierender CI-Lauf (beide Suiten) |

---

## Task 1: Playwright-CT-Grundgerüst + Smoke-Test

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright-ct.config.ts`
- Create: `frontend/playwright/index.html`
- Create: `frontend/playwright/index.tsx`
- Create: `frontend/tests-ct/Smoke.ct.tsx`

**Interfaces:**
- Produces: `npm run test:ct` / `npm run test:ct:ui` als neue, funktionierende Scripts. Konsumiert von allen folgenden CT-Tasks.

- [ ] **Step 1: devDependencies und Scripts ergänzen**

In `frontend/package.json`, `devDependencies` ergänzen (alphabetisch):

```json
    "@playwright/experimental-ct-react": "1.62.0",
    "@playwright/test": "1.62.0",
    "@types/node": "^20.0.0",
```

`scripts` ergänzen (bestehende 5 Zeilen bleiben unverändert):

```json
    "test:ct": "playwright test -c playwright-ct.config.ts",
    "test:ct:ui": "playwright test -c playwright-ct.config.ts --ui",
```

- [ ] **Step 2: Installieren**

Run (aus `frontend/`): `npm install`
Expected: läuft durch, `package-lock.json` aktualisiert sich.

- [ ] **Step 3: Playwright-Browser installieren (einmalig, kein npm-Paket)**

Run (aus `frontend/`): `npx playwright install chromium`
Expected: lädt den Chromium-Browser herunter, kein Fehler. (In dieser Sandbox kann Chromium selbst mangels System-Libs trotzdem nicht LAUFEN ohne den `.deb`-Extraktion-Workaround aus den Global Constraints — der Download/Install-Schritt selbst funktioniert unabhängig davon.)

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
Expected: FAIL — Playwright meldet, dass `playwright-ct.config.ts` nicht gefunden wurde.

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

Neue Datei `frontend/playwright/index.tsx`:

```tsx
import "../src/index.css";
```

- [ ] **Step 7: Testlauf erneut, jetzt erfolgreich**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS — `1 passed`.

- [ ] **Step 8: Bestehende Scripts gegenchecken**

Run (aus `frontend/`): `npm run typecheck`
Expected: weiterhin 0 Fehler.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/playwright-ct.config.ts frontend/playwright/index.html frontend/playwright/index.tsx frontend/tests-ct/Smoke.ct.tsx
git commit -m "Playwright Component Testing: Grundgeruest + Smoke-Test"
```

---

## Task 2: Fixture-Builder + Firebase-Mock (korrigiert gegen aktuellen `types.ts`-Stand)

**Files:**
- Create: `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts`
- Create: `frontend/src/test-fixtures/firebase.mock.ts`
- Modify: `frontend/playwright-ct.config.ts`

**Interfaces:**
- Consumes: `DashboardSnapshot`, `PlayerRecord`, `MlMetrics`, `MlAccuracyTrendEntry` (`frontend/src/types.ts`).
- Produces: `buildFixtureSnapshot(overrides?: Partial<DashboardSnapshot>): DashboardSnapshot`, `FIXTURE_PLAYERS`, `FIXTURE_ML_METRICS`, `FIXTURE_ML_TREND`. Konsumiert von Task 3, 4, 6, 7, 8, 9.

**Warum korrigiert:** der alte Plan (2026-07-30) fehlten inzwischen pflichtige `DashboardSnapshot`-Felder (`fetched_at`, `generated_at` — beide seither ohne `?` im Typ) und enthielt ein Feld (`wunschkader_formation`), das es im aktuellen Typ gar nicht mehr gibt (Formation wird jetzt live aus den tatsächlichen Starter-Zählungen erkannt, `frontend/src/lib/formations.ts`s `matchedFormation()`). Die `[key: string]: unknown`-Indexsignatur auf `DashboardSnapshot` unterdrückt NUR Excess-Property-Checks, nicht fehlende Pflichtfelder — die Korrektur ist für `npm run typecheck` erforderlich, nicht kosmetisch.

- [ ] **Step 1: Fixture-Builder schreiben**

Neue Datei `frontend/src/test-fixtures/dashboardSnapshot.fixture.ts`:

```ts
import type {
  DashboardSnapshot,
  MlAccuracyTrendEntry,
  MlMetrics,
  PlayerRecord,
} from "../types";

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
// Freitextsuche auffindbar ist.
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
  // Bug-1-Regression (Task 3) braucht bewusst einen NICHT-Sturm-Spieler als
  // Haupt-Testsubjekt: der entfernte Code hatte "Sturm" als Default-Position -
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

// Minimal, aber vollstaendig typkorrekt gegen MlMetrics/MlAccuracyTrendEntry -
// NUR fuer Tests, die MlGenauigkeitTab mit sichtbarem Chart-Inhalt brauchen
// (Task 8/9: die E2E-Touch-vs-Swipe-Regression). Bewusst NICHT Default in
// buildFixtureSnapshot() (die bleibt ml_metrics:null) - explizit per
// overrides anfordern.
export const FIXTURE_ML_METRICS: MlMetrics = {
  model_type: "RandomForest",
  rmse: 500_000, mae: 300_000, r2: 0.6, sign_accuracy: 62.5,
  train_rows: 1000, test_rows: 200,
  per_model: {
    RandomForest: { rmse: 500_000, mae: 300_000, r2: 0.6, sign_accuracy: 62.5 },
    HistGradientBoosting: { rmse: 520_000, mae: 310_000, r2: 0.58, sign_accuracy: 60.1 },
  },
};
export const FIXTURE_ML_TREND: MlAccuracyTrendEntry[] = [
  { date: "2026-07-20", RandomForest: 58.2, HistGradientBoosting: 55.0 },
  { date: "2026-07-27", RandomForest: 61.4, HistGradientBoosting: 59.8 },
  { date: "2026-08-02", RandomForest: 62.5, HistGradientBoosting: 60.1 },
];

export function buildFixtureSnapshot(overrides?: Partial<DashboardSnapshot>): DashboardSnapshot {
  const players = Object.fromEntries(Object.values(FIXTURE_PLAYERS).map((p) => [p.player_id, p]));
  return {
    fetched_at: "2026-08-02T06:00:00.000Z",
    generated_at: "2026-08-02T06:05:00.000Z",
    players,
    calibration: null,
    transfermarkt_listings: [],
    // suggestion2 ist "Eigener Kader" (beweist, dass scoreReplacementPool()
    // sowohl Frei- als auch Eigener-Kader-Spieler als Kandidaten zulaesst).
    own_squad_ids: [FIXTURE_PLAYERS.suggestion2.player_id],
    owned_by: {},
    wunschkader_targets: [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }],
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
Expected: 0 Fehler.

- [ ] **Step 3: Firebase-Mock schreiben**

Neue Datei `frontend/src/test-fixtures/firebase.mock.ts`:

```ts
// Test-only Stub fuer "../firebase" - wird per Vite-Alias in
// playwright-ct.config.ts eingehaengt, damit z.B. WunschkaderTab.tsx's
// `import { db } from "../firebase"` in Component-Tests NIEMALS das echte
// Firebase-SDK laedt. Bewusst KEIN Import aus dem echten "firebase"-Paket -
// das macht es strukturell unmoeglich (nicht nur "wahrscheinlich harmlos"),
// dass initializeApp/getAuth/getFirestore in einem CT-Lauf ausgefuehrt
// werden.
export const auth = {};
export const db = {};
```

- [ ] **Step 4: Vite-Alias in die Config eintragen**

`frontend/playwright-ct.config.ts` ersetzen durch:

```ts
import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests-ct",
  // Playwrights Default-testMatch ("**/*.@(spec|test).?(c|m)[jt]s?(x)")
  // trifft NICHT auf "*.ct.tsx" (kein ".spec."/".test."-Segment) - ohne
  // diese Zeile findet "npm run test:ct" 0 Tests (in Task 1 empirisch
  // verifiziert). Diese Zeile MUSS bei jeder vollstaendigen Ersetzung
  // dieser Datei (auch in Task 5) erhalten bleiben.
  testMatch: /.*\.ct\.tsx$/,
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

(`path`/`fileURLToPath` statt eines rohen `__dirname`, weil `package.json`s `"type": "module"` echtes CommonJS-`__dirname` in diesem ESM-Kontext nicht existieren laesst. Die Regex trifft den Import unabhaengig von der Verzeichnistiefe. `testMatch` siehe Kommentar oben — Task 1 hat das bereits live gefixt, dieser Plan-Text war stale.)

- [ ] **Step 5: Bisherige Tests laufen weiterhin**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS — Smoke-Test unbeeinflusst (importiert kein Firebase).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/test-fixtures/dashboardSnapshot.fixture.ts frontend/src/test-fixtures/firebase.mock.ts frontend/playwright-ct.config.ts
git commit -m "Playwright CT: Fixture-Builder fuer DashboardSnapshot + Firebase-Mock-Alias"
```

---

## Task 3: Regressionstest Bug A — Add-Dialog positionsübergreifend

**Files:**
- Create: `frontend/tests-ct/WunschkaderTab.ct.tsx`

**Interfaces:**
- Consumes: `buildFixtureSnapshot()`/`FIXTURE_PLAYERS` (Task 2), `WunschkaderTab` (`frontend/src/components/WunschkaderTab.tsx` — Props: `data: DashboardSnapshot`, `wunschkader: {targets: RawWunschkaderTarget[]}`, `onSaved: (targets) => void`; die letzten beiden sind seit Commit `8c3d54e` (2026-08-01, Auto-Save-Feature) pflichtig — der historische Bug-Fix-Commit dieses Tasks (`e6eaef2`) predates das, daher hier die Korrektur gegenüber dem alten 2026-07-30-Plan).

**Testdesign-Entscheidung** (bewusst, nicht `AddTargetModal` isoliert testen): `AddTargetModal` ist eine nicht-exportierte lokale Funktion in `WunschkaderTab.tsx` — sie zu exportieren wäre eine Produktivcode-Änderung nur für Testzwecke (verstößt gegen Global Constraints). Der Test geht deshalb über die komplette `WunschkaderTab`-Komponente.

- [ ] **Step 1: Test schreiben**

Neue Datei `frontend/tests-ct/WunschkaderTab.ct.tsx`:

```tsx
import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Bug A - Add-Dialog ohne Positions-Zwang", () => {
  test("findet einen Torwart ueber den generischen Bank-Add-Dialog, ohne Position vorzuwaehlen", async ({ mount }) => {
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets: [] }} onSaved={() => {}} />
    );

    // Gezielt den Bank-"+ Ziel"-Button ansteuern, nicht den einer
    // Positions-Gruppe (beide rendern denselben Text "+ Ziel").
    const bankHeading = component.getByText(/^Bank \(\d+\)$/);
    const bankGrid = bankHeading.locator("xpath=following-sibling::div[1]");
    await bankGrid.getByRole("button", { name: "+ Ziel" }).click();

    // Fail-fast: der generische Dialog hat KEINEN "(Position)"-Suffix.
    await expect(component.getByRole("heading", { name: "Ziel hinzufügen", exact: true })).toBeVisible();

    // Regression-Guard: kein <select> mehr im generischen Add-Formular.
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
Expected: PASS — der zugrundeliegende Fix ist bereits in Produktion (Commit `e6eaef2`), dieser Test ist ein retroaktiver Regressionstest.

- [ ] **Step 3: Mutation-Check (Beweis: der Test ist nicht vakuos)**

```bash
cd /workspace/work
git show 48a9fe4:frontend/src/components/WunschkaderTab.tsx > /tmp/old-wunschkadertab.tsx
cp frontend/src/components/WunschkaderTab.tsx /tmp/current-wunschkadertab-backup.tsx
cp /tmp/old-wunschkadertab.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: FAIL — mit dem alten Code (Default-Position "Sturm", positionsgefilterte Suche) findet die Suche nach "Torsten" keinen Treffer.

Danach wiederherstellen:

```bash
cp /tmp/current-wunschkadertab-backup.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: PASS — wieder grün mit dem echten, gefixten Code.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/WunschkaderTab.ct.tsx
git commit -m "Playwright CT: Regressionstest fuer Bug A (Add-Dialog Positions-Zwang)"
```

---

## Task 4: Regressionstests Bug B — Vorschläge bleiben Compare-first, Freitext tauscht direkt

**Files:**
- Modify: `frontend/tests-ct/WunschkaderTab.ct.tsx`

**Interfaces:**
- Consumes: gleich wie Task 3, zusätzlich `PlayerCompareModal`-Textmarker ("Diesen als Ersatz wählen") als Nachweis, dass der Vergleich geöffnet wurde.

- [ ] **Step 1: Die drei Tests ergänzen**

In `frontend/tests-ct/WunschkaderTab.ct.tsx`, nach dem bestehenden `test.describe`-Block ergänzen:

```tsx
test.describe("Bug B - Vorschlaege vs. Freitext im Wechsel-Dialog", () => {
  async function openWechsel(mount: Parameters<Parameters<typeof test>[1]>[0]["mount"]) {
    const component = await mount(
      <WunschkaderTab
        data={buildFixtureSnapshot()}
        wunschkader={{ targets: [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }] }}
        onSaved={() => {}}
      />
    );
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Wechsel" }).click();
    return component;
  }

  test("Vorschlag-Chip oeffnet weiterhin zuerst den Vergleich, tauscht nicht direkt", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.suggestion1.name) }).click();

    await expect(component.getByText("Diesen als Ersatz wählen").first()).toBeVisible();
    await expect(component.getByText(FIXTURE_PLAYERS.target.name)).toBeVisible();
  });

  test("Freitext-Ergebnis (Hauptlabel) tauscht direkt, ohne den Vergleich zu oeffnen", async ({ mount }) => {
    const component = await openWechsel(mount);

    await component.getByPlaceholder("Anderen freien Spieler gleicher Position suchen…").fill("Weitweg");
    await component.getByRole("button", { name: new RegExp(FIXTURE_PLAYERS.searchOnly.name) }).click();

    await expect(component.getByText("Diesen als Ersatz wählen")).toHaveCount(0);

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
Expected: PASS — alle 5 Tests grün (1 aus Task 3 + 3 neue + der Smoke-Test aus Task 1).

- [ ] **Step 3: Mutation-Check für den Direkt-Tausch-Test**

```bash
cd /workspace/work
git show 4663dcf:frontend/src/components/WunschkaderTab.tsx > /tmp/old-wunschkadertab-2.tsx
cp frontend/src/components/WunschkaderTab.tsx /tmp/current-wunschkadertab-backup-2.tsx
cp /tmp/old-wunschkadertab-2.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: FAIL — unter diesem alten Stand öffnet ein Klick auf das Freitext-Hauptlabel noch den Vergleich statt direkt zu tauschen.

Danach wiederherstellen:

```bash
cp /tmp/current-wunschkadertab-backup-2.tsx frontend/src/components/WunschkaderTab.tsx
cd frontend && npm run test:ct
```

Expected: PASS — wieder alle 5 Tests grün.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/WunschkaderTab.ct.tsx
git commit -m "Playwright CT: Regressionstests fuer Bug B (Vorschlaege Compare-first, Freitext Direkt-Tausch)"
```

---

## Task 5: `firebase/firestore`-Mock für CT

**Files:**
- Create: `frontend/src/test-fixtures/firestore.mock.ts`
- Modify: `frontend/playwright-ct.config.ts`

**Interfaces:**
- Produces: `doc()`, `setDoc()`, `getDoc()`, `arrayUnion()` (Stub-Modul, ersetzt `firebase/firestore` global in allen CT-Tests), `RecordedSetDocCall`-Typ (konsumiert von Task 6).

**Warum nötig:** `WunschkaderTab.tsx` importiert `doc`/`setDoc` DIREKT aus dem echten `firebase/firestore`-npm-Paket (`import { doc, setDoc } from "firebase/firestore";`), nicht aus `../firebase`. Ohne diesen Mock würde ein Test, der tatsächlich "Speichern" auslöst, die echte SDK mit einer gefakten `db`-Instanz (`{}`) aufrufen — ein stiller Crash, der von `saveTargets()`s eigenem `try/catch` verschluckt und nur als Fehlermeldung auf dem Bildschirm sichtbar würde.

**Scoping-Check:** grep über `frontend/src` bestätigt, dass aktuell nur `WunschkaderTab.tsx` `firebase/firestore` direkt importiert. Da der CT-Alias global für alle `*.ct.tsx`-Dateien gilt, enthält der Mock vorsorglich auch `getDoc`/`arrayUnion`-Stubs, damit eine künftige CT-Komponente (z. B. `FeedbackTab.tsx`), die dieselben Named Exports braucht, nicht an einem fehlenden Export scheitert.

- [ ] **Step 1: Mock schreiben**

Neue Datei `frontend/src/test-fixtures/firestore.mock.ts`:

```ts
// Aliased (Vite resolve.alias, playwright-ct.config.ts) an Stelle des echten
// "firebase/firestore"-npm-Pakets fuer ALLE Playwright Component Tests - kein
// Import aus "firebase"/"firebase/firestore" hier, damit es strukturell
// unmoeglich ist, dass die echte SDK in einem CT-gemounteten Baum laeuft.
// Calls werden auf `window.__ctFirestoreCalls` aufgezeichnet (NICHT ein
// simples Modul-Array), weil dieses Modul im gemounteten Page-Kontext
// ausgefuehrt wird - einem GETRENNTEN Modul-Graph vom Node-seitigen
// Test-Code. Nur ein window-Global ueberlebt die Node<->Browser-Grenze
// via page.evaluate().

export interface RecordedSetDocCall {
  path: string;
  data: unknown;
  options: unknown;
}

function callLog(): RecordedSetDocCall[] {
  const w = window as unknown as { __ctFirestoreCalls?: RecordedSetDocCall[] };
  if (!w.__ctFirestoreCalls) w.__ctFirestoreCalls = [];
  return w.__ctFirestoreCalls;
}

export function doc(_db: unknown, ...pathSegments: string[]) {
  return { __ctDocPath: pathSegments.join("/") };
}

export async function setDoc(ref: { __ctDocPath: string }, data: unknown, options?: unknown): Promise<void> {
  callLog().push({ path: ref.__ctDocPath, data, options });
}

// Nicht von den aktuellen CT-Tests genutzt - reiner Vorsorge-Stub, falls
// kuenftig eine weitere Komponente (z.B. FeedbackTab.tsx) ebenfalls per CT
// gemountet wird und "firebase/firestore" importiert.
export async function getDoc(_ref: unknown) {
  return { exists: () => false, data: () => undefined };
}
export function arrayUnion(...items: unknown[]) {
  return { __ctArrayUnion: items };
}
```

- [ ] **Step 2: Alias ergänzen**

In `frontend/playwright-ct.config.ts`, `resolve.alias`-Array um einen zweiten Eintrag erweitern:

```ts
import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests-ct",
  // Muss aus Task 2 erhalten bleiben - siehe Kommentar dort. Ohne diese
  // Zeile findet "npm run test:ct" 0 Tests.
  testMatch: /.*\.ct\.tsx$/,
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
          {
            find: "firebase/firestore",
            replacement: path.resolve(__dirname, "src/test-fixtures/firestore.mock.ts"),
          },
        ],
      },
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

(Zweiter Eintrag ist ein fixer String, kein Regex — `firebase/firestore` ist ein fester Bare-Import-Specifier, keine variable relative Pfadtiefe wie `../firebase`.)

- [ ] **Step 3: Bisherige Tests laufen weiterhin**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS — alle 5 bisherigen Tests unverändert grün.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/test-fixtures/firestore.mock.ts frontend/playwright-ct.config.ts
git commit -m "Playwright CT: firebase/firestore-Mock (doc/setDoc-Aufzeichnung ueber window-Global)"
```

---

## Task 6: Regressionstest — Stale-Debounce-Save (WunschkaderTab, Notiz)

**Files:**
- Create: `frontend/tests-ct/WunschkaderTabAutoSave.ct.tsx`

**Interfaces:**
- Consumes: `buildFixtureSnapshot`, `FIXTURE_PLAYERS` (Task 2), `RecordedSetDocCall` (Task 5), `WunschkaderTab` (reale Props: `data`, `wunschkader: {targets}`, `onSaved`).

**Bug-Mechanik (verifiziert gegen echte Git-Historie, `git show 457aecc^`):** Vor dem Fix wurde der Debounce so aufgerufen: `const debouncedSaveTargets = useDebouncedCallback(saveTargets, NOTE_SAVE_DEBOUNCE_MS);` und im Save-Effect `debouncedSaveTargets(editState);` — `editState` wurde dabei als ARGUMENT an den Ziel-Aufruf übergeben, `createDebouncedFunction` friert Argumente exakt zum Zeitpunkt DIESES Aufrufs ein (also beim Notiz-Tippen). Feuert danach — aber VOR Ablauf der 800ms — ein "immediate" Save (z. B. Ziel entfernen), schreibt der später feuernde debounced Save trotzdem noch den EINGEFRORENEN, veralteten Stand und überschreibt damit den korrekten, gerade geschriebenen Stand. Der aktuelle (fixe) Code liest stattdessen `latestEditStateRef.current` (immer der aktuellste Stand) in einem zero-Argument-Callback `debouncedSaveTargets()`.

- [ ] **Step 1: Test schreiben**

Neue Datei `frontend/tests-ct/WunschkaderTabAutoSave.ct.tsx`:

```tsx
import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";
import type { RecordedSetDocCall } from "../src/test-fixtures/firestore.mock";

// NOTE_SAVE_DEBOUNCE_MS ist eine modul-private Konstante in
// WunschkaderTab.tsx (aktuell 800) - bewusst NICHT fuer diesen Test
// exportiert (Global Constraint: kein test-only Export in Produktivcode).
// 850ms als Sicherheitsabstand.
const DEBOUNCE_FASTFORWARD_MS = 850;

test.describe("Bug C - debounced Notiz-Save darf ein spaeter entferntes Ziel nicht wiederbeleben", () => {
  test("Notiz tippen, VOR Ablauf der 800ms ein anderes Ziel entfernen: der spaeter feuernde debounced Save schreibt die aktuelle, nicht die veraltete editState", async ({ mount, page }) => {
    // Fake-Clock installieren, BEVOR mount() navigiert.
    await page.clock.install();

    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.sturm.player_id, role: "Starter" },
    ];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    // 1) Notiz am ERSTEN Ziel tippen - plant den 800ms debounced Save.
    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByLabel("Notiz").fill("wichtige Notiz");
    await component.getByRole("button", { name: "Schließen" }).click();

    // 2) VOR Ablauf der 800ms: das ANDERE Ziel entfernen - immediate Save,
    // enthaelt die Entfernung korrekt.
    await component.getByText(FIXTURE_PLAYERS.sturm.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);

    // 3) 800ms virtuell vorspulen - der debounced Save feuert jetzt.
    await page.clock.fastForward(DEBOUNCE_FASTFORWARD_MS);
    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(2);

    const calls: RecordedSetDocCall[] = await page.evaluate(() => (window as any).__ctFirestoreCalls ?? []);

    for (const call of calls) {
      const ids = (call.data as { targets: { player_id: string }[] }).targets.map((t) => t.player_id);
      // Kern-Regression: das entfernte Ziel darf in KEINEM Write wieder
      // auftauchen - auch nicht im spaeter feuernden debounced Save.
      expect(ids).not.toContain(FIXTURE_PLAYERS.sturm.player_id);
    }
    const lastTargets = (calls[calls.length - 1].data as { targets: { player_id: string; note?: string }[] }).targets;
    expect(lastTargets.find((t) => t.player_id === FIXTURE_PLAYERS.target.player_id)?.note).toBe("wichtige Notiz");
  });
});
```

- [ ] **Step 2: Testlauf**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS.

- [ ] **Step 3: Mutation-Check**

Temporär BEIDE folgenden Stellen in `frontend/src/components/WunschkaderTab.tsx` zurücksetzen (nur zusammen reproduzieren sie den historischen Bug — der Ref-Read allein war nie der Mechanismus):

1. Die Deklaration:
```tsx
const debouncedSaveTargets = useDebouncedCallback(saveTargets, NOTE_SAVE_DEBOUNCE_MS);
```
(ersetzt die aktuelle Wrapper-Closure-Version.)

2. Den `else`-Zweig im Save-Effect:
```tsx
} else {
  debouncedSaveTargets(editState);
}
```
(ersetzt den aktuellen zero-Argument-Aufruf.)

```bash
cd frontend && npm run test:ct
```
Expected: FAIL — die zweite `setDoc`-Aufzeichnung enthält wieder das entfernte Ziel (`expect(ids).not.toContain(...)` schlägt fehl).

Danach beide Stellen auf den aktuellen (gefixten) Stand zurücksetzen:
```tsx
const debouncedSaveTargets = useDebouncedCallback(() => {
  saveTargets(latestEditStateRef.current);
}, NOTE_SAVE_DEBOUNCE_MS);
```
```tsx
} else {
  debouncedSaveTargets();
}
```

```bash
cd frontend && npm run test:ct
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/WunschkaderTabAutoSave.ct.tsx
git commit -m "Playwright CT: Regressionstest fuer stale debounced Notiz-Save (Bug C)"
```

---

## Task 7: Regressionstest — Cursor-Position bei Tausenderpunkt-Backspace (AlleSpielerTab)

**Files:**
- Create: `frontend/tests-ct/AlleSpielerTab.ct.tsx`

**Interfaces:**
- Consumes: `buildFixtureSnapshot` (Task 2), `AlleSpielerTab` (importiert kein Firebase — kein Alias nötig, per grep verifiziert).

**Handverifizierte Erwartung:** Wert `"1.234.567"` (Ziffern `1234567`), Cursor direkt nach dem ZWEITEN Punkt (Index 6). Backspace dort löscht laut `handleKeyDown`/`deleteDigitAt()` die dem Punkt benachbarte Ziffer (`4`, Index 4) → verbleibende Ziffern `123567` → reformatiert `"123.567"`, Cursor bei Index 3 (direkt vor dem neuen Punkt) — NICHT am Feldende.

- [ ] **Step 1: Test schreiben**

Neue Datei `frontend/tests-ct/AlleSpielerTab.ct.tsx`:

```tsx
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
```

- [ ] **Step 2: Testlauf**

Run (aus `frontend/`): `npm run test:ct`
Expected: PASS.

- [ ] **Step 3: Mutation-Check**

In `frontend/src/components/AlleSpielerTab.tsx`s `MarketValueInput` temporär `onKeyDown={handleKeyDown}` aus dem `<input>` entfernen.

```bash
cd frontend && npm run test:ct
```
Expected: FAIL — nativer Backspace löscht nur den Punkt selbst, Ziffern bleiben unverändert, React überspringt das Re-Render, Cursor landet nicht bei Index 3.

`onKeyDown={handleKeyDown}` wiederherstellen.

```bash
cd frontend && npm run test:ct
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-ct/AlleSpielerTab.ct.tsx
git commit -m "Playwright CT: Regressionstest fuer Cursor-Position bei Tausenderpunkt-Backspace (Bug D)"
```

---

## Task 8: E2E-Infrastruktur (voller App-Lauf, Firebase auf Paket-Ebene gefaked)

**Files:**
- Create: `frontend/vite.e2e.config.ts`
- Create: `frontend/playwright-e2e.config.ts`
- Create: `frontend/src/test-fixtures/firebaseAuth.e2e.mock.ts`
- Create: `frontend/src/test-fixtures/firebaseFirestore.e2e.mock.ts`
- Create: `frontend/tests-e2e/touchHelpers.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `npm run test:e2e`/`test:e2e:ui`, `touchDrag(page, from, to, steps?)` (konsumiert von Task 9), einen laufenden, voll gefakten App-Server auf Port 4300.

**Design-Entscheidung (minimaler Diff):** aliased werden die rohen npm-Pakete `firebase/auth` und `firebase/firestore` (NICHT `../firebase.ts`, NICHT `firebase/app`). `frontend/src/firebase.ts` ruft `initializeApp()` aus `firebase/app` auf (bleibt real — reine In-Memory-Konstruktion, kein Netzwerk) und danach `getAuth(app)`/`getFirestore(app)` aus den beiden aliasten Paketen — dadurch produziert `firebase.ts` ein gefaktes `auth`/`db`, OHNE dass eine einzige Zeile dieser Datei angefasst wird. Jeder andere Konsument (`App.tsx`s `onAuthStateChanged`/`doc`/`getDoc`, `WunschkaderTab.tsx`s `doc`/`setDoc`, `FeedbackTab.tsx`s `arrayUnion`/`doc`/`getDoc`/`setDoc`, `Login.tsx`s `signInWithEmailAndPassword`) läuft transitiv über dieselben zwei Aliase.

- [ ] **Step 1: `firebaseAuth.e2e.mock.ts` schreiben**

Neue Datei `frontend/src/test-fixtures/firebaseAuth.e2e.mock.ts`:

```ts
// Aliased (Vite resolve.alias, vite.e2e.config.ts) an Stelle des echten
// "firebase/auth"-npm-Pakets fuer das E2E-Projekt. Kein Import aus
// "firebase"/"firebase/auth" hier - strukturell unmoeglich, dass die echte
// Auth-SDK (oder irgendein Netzwerk-Call) laeuft.

const FAKE_UID = "e2e-fake-uid";

export function getAuth(_app: unknown) {
  return { currentUser: { uid: FAKE_UID } };
}

// App.tsx: useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])
// Feuert SYNCHRON mit einem eingeloggten Fake-User - App.tsx's
// `if (user === undefined) return null;`-Gate loest sich sofort auf, kein
// Login-Formular-Aufblitzen, kein echtes Warten.
export function onAuthStateChanged(
  _auth: unknown,
  callback: (user: { uid: string } | null) => void
): () => void {
  callback({ uid: FAKE_UID });
  return () => {};
}

// Wird nie aufgerufen (Login.tsx wird dank des sofort feuernden
// onAuthStateChanged oben nie gemountet) - Stub trotzdem vorhanden, damit
// der benannte Import in Login.tsx nicht ins Leere zeigt.
export async function signInWithEmailAndPassword(): Promise<never> {
  throw new Error("signInWithEmailAndPassword ist im E2E-Fake nicht implementiert.");
}
```

- [ ] **Step 2: `firebaseFirestore.e2e.mock.ts` schreiben**

Neue Datei `frontend/src/test-fixtures/firebaseFirestore.e2e.mock.ts`:

```ts
// Aliased an Stelle des echten "firebase/firestore"-npm-Pakets fuer das
// E2E-Projekt - siehe firebaseAuth.e2e.mock.ts fuer die Begruendung.
// Unterlegt App.tsx's zwei getDoc()-Reads mit einem In-Memory-Fixture statt
// einem echten Firestore-Roundtrip. Writes (setDoc) werden akzeptiert und
// In-Memory gemergt, nie persistiert, nie ueber Netzwerk.

import { buildFixtureSnapshot, FIXTURE_ML_METRICS, FIXTURE_ML_TREND } from "./dashboardSnapshot.fixture";

const store = new Map<string, unknown>();
const fixture = buildFixtureSnapshot({ ml_metrics: FIXTURE_ML_METRICS, ml_accuracy_trend: FIXTURE_ML_TREND });
store.set("dashboard_snapshot/latest", fixture);
store.set("wunschkader/current", { targets: fixture.wunschkader_targets });

export function getFirestore(_app: unknown) {
  return {};
}

export function doc(_db: unknown, ...pathSegments: string[]) {
  return { __e2eDocPath: pathSegments.join("/") };
}

export async function getDoc(ref: { __e2eDocPath: string }) {
  const data = store.get(ref.__e2eDocPath);
  return { exists: () => data !== undefined, data: () => data };
}

export async function setDoc(
  ref: { __e2eDocPath: string },
  data: Record<string, unknown>,
  options?: { merge?: boolean }
): Promise<void> {
  const existing = (store.get(ref.__e2eDocPath) as Record<string, unknown> | undefined) ?? {};
  store.set(ref.__e2eDocPath, options?.merge ? { ...existing, ...data } : data);
}

export function arrayUnion(...items: unknown[]) {
  return { __e2eArrayUnion: items };
}
```

(`feedback/current` wird bewusst NICHT vorbefüllt — `getDoc` auf einem nicht gesetzten Pfad liefert korrekt `exists() === false`, ein bereits vorhandener "noch keine Daten"-Pfad in `FeedbackTab.tsx` greift.)

- [ ] **Step 3: `vite.e2e.config.ts` schreiben**

Neue Datei `frontend/vite.e2e.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: [
      { find: "firebase/auth", replacement: path.resolve(__dirname, "src/test-fixtures/firebaseAuth.e2e.mock.ts") },
      { find: "firebase/firestore", replacement: path.resolve(__dirname, "src/test-fixtures/firebaseFirestore.e2e.mock.ts") },
    ],
  },
});
```

(`base: "/"` statt der Produktions-`base: "/KickbaseAgent/"` — die GitHub-Pages-Basis ist für einen lokal servierten E2E-Dev-Server irrelevant.)

- [ ] **Step 4: `playwright-e2e.config.ts` schreiben**

Neue Datei `frontend/playwright-e2e.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

const PORT = 4300;

export default defineConfig({
  testDir: "./tests-e2e",
  timeout: 15_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
  },
  webServer: {
    command: `npx vite --config vite.e2e.config.ts --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    // Pixel 5 statt eines iPhone-Presets, weil dessen defaultBrowserType
    // chromium ist (konsistent mit dem CT-Projekt) - liefert hasTouch:true,
    // isMobile:true und einen Viewport <640px (MlGenauigkeitTab's
    // isMobileViewport()-matchMedia-Schwelle).
    { name: "mobile-chromium-touch", use: { ...devices["Pixel 5"] } },
  ],
});
```

- [ ] **Step 5: `touchHelpers.ts` schreiben**

Neue Datei `frontend/tests-e2e/touchHelpers.ts`:

```ts
import type { Page } from "@playwright/test";

export interface TouchPoint {
  x: number;
  y: number;
}

// Echte (CDP-vertraute) Touch-Drag-Geste ueber Input.dispatchTouchEvent - JS-
// synthetisierte `el.dispatchEvent(new TouchEvent(...))` werden von Chromium
// als "nicht vertrauenswuerdig" markiert und loesen touch-spezifisches
// Browser-/Framework-Verhalten nicht zuverlaessig aus. CDP-dispatchte Events
// sind fuer die Seite von echten Hardware-Touch-Events nicht unterscheidbar.
// Chromium-only (CDP ist Chromium-spezifisch). WICHTIG: touchEnd/touchCancel
// duerfen laut CDP-Spec KEINE touchPoints enthalten (nur touchStart/
// touchMove).
export async function touchDrag(page: Page, from: TouchPoint, to: TouchPoint, steps = 6): Promise<void> {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: from.x, y: from.y, id: 0 }],
    });
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      await client.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t, id: 0 }],
      });
    }
    await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  } finally {
    await client.detach();
  }
}
```

- [ ] **Step 6: Scripts ergänzen**

In `frontend/package.json`, `scripts` ergänzen:

```json
    "test:e2e": "playwright test -c playwright-e2e.config.ts",
    "test:e2e:ui": "playwright test -c playwright-e2e.config.ts --ui",
```

(Kein neues devDependency — `@playwright/test` ist bereits seit Task 1 explizit gepinnt.)

- [ ] **Step 7: Typecheck**

Run (aus `frontend/`): `npm run typecheck`
Expected: 0 Fehler (die zwei neuen Mock-Dateien liegen unter `src/test-fixtures/`, kein Playwright-Import, bleiben im Programm; `vite.e2e.config.ts`/`playwright-e2e.config.ts`/`tests-e2e/` liegen außerhalb `include: ["src"]`).

- [ ] **Step 8: Commit**

```bash
git add frontend/vite.e2e.config.ts frontend/playwright-e2e.config.ts frontend/src/test-fixtures/firebaseAuth.e2e.mock.ts frontend/src/test-fixtures/firebaseFirestore.e2e.mock.ts frontend/tests-e2e/touchHelpers.ts frontend/package.json
git commit -m "Playwright E2E: Infrastruktur (Vite-Config, Firebase-Fakes auf Paket-Ebene, CDP-Touch-Helper)"
```

---

## Task 9: Regressionstest — Touch-Scrub im ML-Chart löst keinen Tab-Swipe aus

**Files:**
- Create: `frontend/tests-e2e/TouchScrubVsSwipe.spec.ts`

**Interfaces:**
- Consumes: `touchDrag` (Task 8).

**Locator-Design-Entscheidung:** die Chart-Koordinaten werden NICHT über `[data-swipe-ignore]` selbst bestimmt — genau das ist das Attribut, das der Mutation-Check entfernt; würde der Locator selbst davon abhängen, wäre der Test-Setup schon vor der eigentlichen Prüfung kaputt. Stattdessen: Überschrift-Text + `xpath=following-sibling::div[1]`-Idiom (wie in Task 3/4 bereits verwendet), dann das `<svg>` innerhalb dieses gescopten Subtrees.

- [ ] **Step 1: Test schreiben**

Neue Datei `frontend/tests-e2e/TouchScrubVsSwipe.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";

test.describe("Bug E - Touch-Scrubben im ML-Chart loest keinen Tab-Swipe aus", () => {
  test("Drag INNERHALB des Charts wechselt den Tab nicht; derselbe Drag AUSSERHALB (positive Kontrolle) wechselt ihn", async ({ page }) => {
    await page.goto("/");

    // Mobiles Burger-Menue -> "Modell-Tracking" (die Desktop-<nav> ist auf
    // < sm ausgeblendet, aber im DOM vorhanden - deshalb ueber die "Menü"-
    // Ueberschrift auf die mobile <nav> scopen, nicht global suchen).
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Modell-Tracking", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Modell-Tracking");

    const trendHeading = page.getByRole("heading", { name: /Richtungs-Genauigkeit/ });
    const chartSvg = trendHeading.locator("xpath=following-sibling::div[1]").locator("svg");
    await expect(chartSvg).toBeVisible();

    // 1) Drag INNERHALB des Charts - darf den Tab NICHT wechseln.
    const chartBox = await chartSvg.boundingBox();
    if (!chartBox) throw new Error("Chart-SVG hat kein boundingBox()");
    const midY = chartBox.y + chartBox.height / 2;
    await touchDrag(
      page,
      { x: chartBox.x + chartBox.width * 0.75, y: midY },
      { x: chartBox.x + chartBox.width * 0.25, y: midY }
    );
    await expect(heading).toHaveText("Modell-Tracking"); // unveraendert

    // 2) Positive Kontrolle: DERSELBE Drag ausserhalb des Charts (auf Hoehe
    // der mobilen Tab-Ueberschrift, oberhalb des Charts) - MUSS den Tab
    // wechseln, sonst waere Schritt 1 nur ein vakuoser Test.
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const headingMidY = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y: headingMidY }, { x: 20, y: headingMidY });
    await expect(heading).toHaveText("Bugs & Ideen"); // naechster Tab (dx<0 -> "next")
  });
});
```

- [ ] **Step 2: Testlauf**

Run (aus `frontend/`): `npm run test:e2e`
Expected: PASS.

- [ ] **Step 3: Mutation-Check**

In `frontend/src/components/MlGenauigkeitTab.tsx`s `TrendChart` temporär das `data-swipe-ignore`-Attribut vom Chart-Container-`<div>` entfernen.

```bash
cd frontend && npm run test:e2e
```
Expected: FAIL — direkt nach dem Inside-Chart-Drag ist die Überschrift bereits `"Bugs & Ideen"` (der Drag löst jetzt fälschlich auch einen Tab-Wechsel aus), die Assertion `toHaveText("Modell-Tracking")` schlägt fehl.

`data-swipe-ignore` wiederherstellen.

```bash
cd frontend && npm run test:e2e
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/TouchScrubVsSwipe.spec.ts
git commit -m "Playwright E2E: Regressionstest fuer Touch-Scrub vs. Tab-Swipe (Bug E)"
```

---

## Task 10: CI-Integration

**Files:**
- Create: `.github/workflows/frontend-playwright-tests.yml`

- [ ] **Step 1: Workflow-Datei anlegen**

Neue Datei `.github/workflows/frontend-playwright-tests.yml`:

```yaml
name: Frontend Playwright Tests (Component + E2E)

# Zwei unabhaengige, NICHT blockierende Playwright-Testlaeufe - component-tests
# (frontend/tests-ct/, mounten einzelne Tab-Komponenten, firebase/firestore
# komplett wegaliasiert) und e2e-touch-swipe (frontend/tests-e2e/, startet die
# komplette App gegen einen echten Vite-Dev-Server mit wegaliastem
# firebase/auth+firebase/firestore). Beide laufen parallel zu "Frontend Deploy
# (GitHub Pages)" (frontend-pilot.yml), ohne "needs:"-Abhaengigkeit - blockieren
# den Deploy nie, auch nicht gegenseitig.

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - '.github/workflows/frontend-playwright-tests.yml'
  pull_request:
    paths:
      - 'frontend/**'
  workflow_dispatch: {}

permissions:
  contents: read

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

  e2e-touch-swipe:
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
      - name: Run E2E tests
        working-directory: frontend
        run: npm run test:e2e
```

- [ ] **Step 2: Verifikation**

Nach dem Push: `gh workflow run "Frontend Playwright Tests (Component + E2E)"` (oder abwarten, bis der nächste `frontend/**`-Push ihn automatisch auslöst), dann `gh run watch <run-id> --exit-status` — beide Jobs müssen grün durchlaufen UND dürfen den "Frontend Deploy (GitHub Pages)"-Lauf nicht beeinflussen.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/frontend-playwright-tests.yml
git commit -m "CI: unabhaengiger, nicht-blockierender Playwright-Test-Workflow (Component + E2E)"
```

---

## Bewusst außen vor

- **Dark-Mode-Kontrast-Lesbarkeits-Bug** (aus dem alten Plan): reine DOM-Struktur/Verhalten-Assertions können unlesbaren-aber-strukturell-vorhandenen Text nicht erkennen. Für zukünftige Fälle dieser Bugklasse bräuchte es zusätzlich visuelles Screenshot-Diffing oder `@axe-core/playwright`-Kontrast-Checks — nicht Teil dieses Plans.
- **Firebase Emulator Suite**: bewusst nicht verwendet (Global Constraints) — alle Fakes sind handgeschriebene JS-Module.
- **"0 (Schätzung)"-Bug (Wunschkader-Geplanter-Preis)**: bereits über eine reine Vitest-Unit-Test-Regression in `frontend/src/lib/derive.test.ts` abgedeckt (pure Function `plannedPriceFor`), kein Playwright nötig.
- **Backend-Bugs dieser Session** (transformers-Pinning, requirements-Split, KeyError-Handling): reine Python-Backend-Themen, bereits über `tests/test_market_predictor.py`/`tests/test_news_sentiment.py` abgedeckt, kein Frontend-Playwright-Bezug.

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle 3 session-gefundenen Bugs (Stale-Debounce-Save, Cursor-Teleport, Touch-Scrub-vs-Swipe) haben je einen eigenen Task mit Regressionstest + Mutation-Check (Tasks 6, 7, 9). Die alte Grundgerüst-Infrastruktur ist vollständig integriert (Tasks 1-4), korrigiert gegen den aktuellen Code-Stand (Task 2, Mount-Call-Fix in Task 3/4).
- **Platzhalter-Scan**: keine TBD/"siehe oben"/unvollständigen Code-Blöcke — jeder Step hat echten, lauffähigen Code oder einen konkreten Shell-Befehl mit exaktem Erwartungswert.
- **Typ-Konsistenz**: `FIXTURE_PLAYERS`/`buildFixtureSnapshot()`/`FIXTURE_ML_METRICS`/`FIXTURE_ML_TREND` (Task 2) werden in Tasks 3/4/6/7/8/9 konsistent referenziert. `RecordedSetDocCall` (Task 5) wird in Task 6 importiert. `touchDrag()` (Task 8) wird in Task 9 importiert — Signaturen stimmen überein.
- **Gegen den echten Code verifiziert**: alle vier betroffenen Komponenten (`WunschkaderTab.tsx`, `AlleSpielerTab.tsx`, `App.tsx`, `MlGenauigkeitTab.tsx`) wurden im aktuellen Stand gelesen, exakte Texte/Selektoren 1:1 zitiert. Der Bug-1-Mutation-Check wurde gegen die echte Git-Historie (`git show 457aecc^`) verifiziert, nicht aus einer Session-Zusammenfassung übernommen — die ursprünglich angenommene "Ref-vs-Closure"-Mutation wäre vakuos gewesen und wurde korrigiert.
