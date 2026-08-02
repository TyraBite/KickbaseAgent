# Feedback Quick Wins (2026-08-02) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 7 independent, low-risk frontend fixes from the `feedback/current` Firestore backlog (Quick Win category), each committed and verified on its own.

**Architecture:** All 7 tasks are frontend-only (`frontend/src`), touching existing tabs (`SpekulationTab.tsx`, `TransfermarktTab.tsx`, `FeedbackTab.tsx`, `MlGenauigkeitTab.tsx`, `App.tsx`) plus one new shared helper (`derive.ts::normalizeSearchText`) and one new hook file (`useHideOnScroll.ts`). Two tasks (6, 7) contain genuinely testable pure logic and introduce `vitest` as the project's first test runner; the other five are presentation-only and are verified via `npm run typecheck` + `npm run build` instead of unit tests — writing an assertion-free test for a JSX/text change would be a vacuous test, not TDD.

**Tech Stack:** React 18 + TypeScript + Vite 5 + Tailwind, no existing frontend test runner (confirmed via `frontend/package.json` — only `dev/build/preview/typecheck` scripts exist today).

## Global Constraints

- Frontend has zero test runner today. Task 6 adds `vitest` (default `node` environment — no jsdom/DOM testing library needed, since both testable pieces in this plan are pure functions with no DOM interaction) as the only new devDependency for the whole plan, plus a `"test": "vitest run"` script in `frontend/package.json`.
- Presentation-only tasks (1-5) are verified via `npm run typecheck` (must show 0 errors) and `npm run build` (must succeed) — no unit test required or expected for these.
- `npm install` is safe to run in this worktree (isolated `node_modules`, not the Windows-mounted main checkout) — confirmed pattern from the players-map redesign branch.
- Out of scope, explicitly: Wunschkader auto-save behavior change and the Transfermarkt/Alle-Spieler thousands-separator filter fix — both flagged ambiguous during investigation (product decisions needed) and excluded from this plan. Do not fold them in.
- Out of scope: `LigaanalyseTab.tsx`'s manager-name search box — the feedback item is specifically about *player* search ("Spielersuche"), not manager search. Task 6 does not touch `LigaanalyseTab.tsx`.
- Backend Python is untouched by every task in this plan — do not run the Python test suite as part of verifying these tasks.
- Run all `npm`/`vitest`/`tsc` commands with `frontend/` as the working directory.

---

### Task 1: "(Standard)" Zusatz bei Sortier-Labels entfernen

**Files:**
- Modify: `frontend/src/components/SpekulationTab.tsx:13`
- Modify: `frontend/src/components/TransfermarktTab.tsx:19`

**Interfaces:** None — isolated string literal changes, no other task depends on this.

- [ ] **Step 1: Edit `SpekulationTab.tsx:13`**

Change:
```tsx
    { value: "auction", label: "Auktion (Standard)" },
```
to:
```tsx
    { value: "auction", label: "Auktion" },
```

- [ ] **Step 2: Edit `TransfermarktTab.tsx:19`**

Apply the identical change (same line content) in this file.

- [ ] **Step 3: Verify no more occurrences remain**

Run: `grep -rn "(Standard)" frontend/src`
Expected: no output (zero matches).

- [ ] **Step 4: Verify typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SpekulationTab.tsx frontend/src/components/TransfermarktTab.tsx
git commit -m "Sortier-Label: '(Standard)'-Zusatz bei Auktion entfernen"
```

---

### Task 2: Zeichenlimit im Feedback-Formular erhöhen

**Files:**
- Modify: `frontend/src/components/FeedbackTab.tsx:163`
- Modify: `frontend/src/components/FeedbackTab.tsx:259`

**Interfaces:** None.

- [ ] **Step 1: Edit both `maxLength` occurrences**

At both `frontend/src/components/FeedbackTab.tsx:163` and `:259`, change:
```tsx
maxLength={1000}
```
to:
```tsx
maxLength={2000}
```
(Both are textarea props — one for the add-form, one for the edit-form of an existing item. Confirm each match with `grep -n "maxLength={1000}" frontend/src/components/FeedbackTab.tsx` before editing — it must show exactly 2 hits.)

- [ ] **Step 2: Verify**

Run: `grep -n "maxLength" frontend/src/components/FeedbackTab.tsx`
Expected: both occurrences now show `maxLength={2000}`.

Run: `npm run typecheck`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FeedbackTab.tsx
git commit -m "Feedback-Formular: Zeichenlimit von 1000 auf 2000 erhöht"
```

---

### Task 3: "Marktwert-Update"-Hinweiszeile in Spekulation + Transfermarkt

**Files:**
- Modify: `frontend/src/components/SpekulationTab.tsx` (near line 152, existing `HINT` paragraph)
- Modify: `frontend/src/components/TransfermarktTab.tsx` (near line 264, existing `HINT` paragraph)

**Interfaces:** None.

**Context:** Both files already render a bottom hint paragraph with the exact class `text-xs text-slate-500 dark:text-slate-400` (the established hint-styling convention in this codebase, see `[[feedback_hints_at_bottom]]`). Add one more line in the same style, directly below the existing `HINT` paragraph in each file, with the literal text `Marktwert-Update` (German label mirroring Kickbase's own "Market Value Update" convention per the feedback item — no elaboration, just the label).

- [ ] **Step 1: `SpekulationTab.tsx`**

Find the existing line (around line 152):
```tsx
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
```
Add immediately after it:
```tsx
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Marktwert-Update</p>
```

- [ ] **Step 2: `TransfermarktTab.tsx`**

Find the equivalent existing line (around line 264) and apply the identical addition immediately after it.

- [ ] **Step 3: Verify**

Run: `npm run typecheck`
Expected: 0 errors.
Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SpekulationTab.tsx frontend/src/components/TransfermarktTab.tsx
git commit -m "Spekulation/Transfermarkt: Marktwert-Update-Hinweiszeile ergänzt"
```

---

### Task 4: Mobile Tab-Überschrift ergänzen

**Files:**
- Modify: `frontend/src/App.tsx` (near line 311, `<main>` content wrapper)

**Interfaces:**
- Consumes: the existing `TABS` constant (`frontend/src/App.tsx:33-42`), each entry shaped `{ key: string; label: string }`, and the existing `activeTab` state variable already in scope in this component.

**Context:** Since the mobile burger menu closes after selecting a tab, mobile users lose all indication of which tab is active (desktop keeps the `<nav>` bar visible with a highlighted state). Add a heading showing the active tab's German label, visible only below the `sm` breakpoint.

- [ ] **Step 1: Edit `App.tsx`**

Find the existing content wrapper (around line 311):
```tsx
      <main className="px-6 py-6" ...>
```
Immediately inside it, as the first child, add:
```tsx
        <h1 className="mb-4 text-lg font-semibold text-slate-900 sm:hidden dark:text-slate-100">
          {TABS.find((t) => t.key === activeTab)?.label}
        </h1>
```

- [ ] **Step 2: Verify**

Run: `npm run typecheck`
Expected: 0 errors.
Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "Mobile: Tab-Überschrift ergänzt (Burger-Menü zeigt sonst nicht, welcher Tab aktiv ist)"
```

---

### Task 5: Kopf-an-Kopf-Kacheln 1T/3T zusammenlegen (Desktop-Breite)

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx:77-78` (call sites)
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx` (the `HeadToHeadBlock` component definition, lines 90-138 — only its outer wrapper `className`)

**Interfaces:** None — `HeadToHeadBlock`'s props (`metrics`, `heading`) are unchanged, only its own outer wrapper class and its call sites change.

**Context:** Currently both head-to-head tiles stack vertically at full width on every screen size (each is its own `mb-6` block, no shared grid). On desktop this wastes horizontal space. Wrap both calls in a grid container that is 1 column by default (mobile: unchanged, still stacked) and 2 columns from the `lg` breakpoint up (desktop: side by side).

- [ ] **Step 1: Change the call sites (lines 77-78)**

From:
```tsx
      <HeadToHeadBlock metrics={metrics} heading="Kopf-an-Kopf (1-Tages-Horizont)" />
      {metrics3d && <HeadToHeadBlock metrics={metrics3d} heading="Kopf-an-Kopf (3-Tages-Horizont)" />}
```
to:
```tsx
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <HeadToHeadBlock metrics={metrics} heading="Kopf-an-Kopf (1-Tages-Horizont)" />
        {metrics3d && <HeadToHeadBlock metrics={metrics3d} heading="Kopf-an-Kopf (3-Tages-Horizont)" />}
      </div>
```

- [ ] **Step 2: Remove the now-redundant spacing from `HeadToHeadBlock`'s own wrapper**

In the `HeadToHeadBlock` definition, find its outer div:
```tsx
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
```
Change to (drop `mb-6` — spacing now comes from the parent grid container added in Step 1):
```tsx
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
```

- [ ] **Step 3: Verify**

Run: `npm run typecheck`
Expected: 0 errors.
Run: `npm run build`
Expected: build succeeds.
Manually confirm in the diff: mobile behavior is unchanged (grid defaults to 1 column without the `lg:` prefix active), only `lg:` (desktop) width gets the 2-column layout.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "Modell-Tracking: Kopf-an-Kopf 1T/3T auf Desktop-Breite in einer Reihe"
```

---

### Task 6: Umlaute/Apostrophe-insensitive Spielersuche (TDD, adds vitest)

**Files:**
- Modify: `frontend/package.json` (add `vitest` devDependency + `test` script)
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/src/lib/derive.ts` (add `normalizeSearchText` export)
- Create: `frontend/src/lib/derive.test.ts`
- Modify: `frontend/src/components/PlayerNamePicker.tsx:17,20`
- Modify: `frontend/src/components/AlleSpielerTab.tsx:56,64`
- Modify: `frontend/src/components/SpekulationTab.tsx:89-90`
- Modify: `frontend/src/components/TransfermarktTab.tsx:79,84`
- Modify: `frontend/src/components/WunschkaderTab.tsx:74,76,85,88`

**Interfaces:**
- Produces: `normalizeSearchText(input: string): string` exported from `frontend/src/lib/derive.ts` — lowercases, strips diacritics (NFD-decompose + remove combining marks), and strips apostrophe variants (`'` and `’`). Every later step in this task imports and uses this exact function; no other task in this plan depends on it.

- [ ] **Step 1: Add vitest to the project**

Edit `frontend/package.json`:
- In `"scripts"`, add: `"test": "vitest run"`
- In `"devDependencies"`, add: `"vitest": "^2.1.9"`

Run: `cd frontend && npm install`
Expected: installs cleanly, `frontend/node_modules/.bin/vitest` exists.

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
  },
});
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/derive.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { normalizeSearchText } from "./derive";

describe("normalizeSearchText", () => {
  it("lowercases plain ASCII", () => {
    expect(normalizeSearchText("Diaz")).toBe("diaz");
  });

  it("strips diacritics so accented names match plain queries", () => {
    expect(normalizeSearchText("Luis Díaz")).toBe("luis diaz");
    expect(normalizeSearchText("Díaz")).toBe(normalizeSearchText("Diaz"));
  });

  it("strips apostrophe variants", () => {
    expect(normalizeSearchText("N'Guessan")).toBe("nguessan");
    expect(normalizeSearchText("N’Guessan")).toBe("nguessan");
  });

  it("handles German umlauts", () => {
    expect(normalizeSearchText("Müller")).toBe("muller");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `normalizeSearchText` is not exported from `./derive` (module has no such export).

- [ ] **Step 4: Implement `normalizeSearchText` in `derive.ts`**

Add this export to `frontend/src/lib/derive.ts` (anywhere among the other exported helpers):
```ts
export function normalizeSearchText(input: string): string {
  return input
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/['’]/g, "")
    .toLowerCase();
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS, all 4 assertions in `derive.test.ts` green.

- [ ] **Step 6: Apply `normalizeSearchText` at every player-name search site**

At each site below, wrap both the query variable and the compared name(s) in `normalizeSearchText(...)` instead of the current bare `.toLowerCase()`. Read each file first to confirm the exact current surrounding code before editing (line numbers below are from investigation and may have shifted slightly from tasks 1-5's commits touching the same files).

`frontend/src/components/PlayerNamePicker.tsx` (around lines 17, 20) — current:
```tsx
    const q = query.trim().toLowerCase();
```
```tsx
      .filter((p) => p.player_id !== excludePlayerId && p.name.toLowerCase().includes(q))
```
Change to:
```tsx
    const q = normalizeSearchText(query.trim());
```
```tsx
      .filter((p) => p.player_id !== excludePlayerId && normalizeSearchText(p.name).includes(q))
```
Add the import: `import { normalizeSearchText } from "../lib/derive";` (match this file's existing relative import path style for `derive` — check how other imports from `lib/derive` are written in this same file or a sibling component and mirror it exactly).

`frontend/src/components/AlleSpielerTab.tsx` (around lines 56, 64) — current:
```tsx
    const q = search.trim().toLowerCase();
```
```tsx
    if (q && !`${r.name} ${r.team_name ?? ""}`.toLowerCase().includes(q)) return false;
```
Change to:
```tsx
    const q = normalizeSearchText(search.trim());
```
```tsx
    if (q && !normalizeSearchText(`${r.name} ${r.team_name ?? ""}`).includes(q)) return false;
```

`frontend/src/components/SpekulationTab.tsx` (around lines 89-90) — current:
```tsx
    const q = search.trim().toLowerCase();
    const filtered = q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : rows;
```
Change to:
```tsx
    const q = normalizeSearchText(search.trim());
    const filtered = q ? rows.filter((r) => normalizeSearchText(r.name).includes(q)) : rows;
```

`frontend/src/components/TransfermarktTab.tsx` (around lines 79, 84) — same pattern as `AlleSpielerTab.tsx` (name + team search) — apply the identical transformation.

`frontend/src/components/WunschkaderTab.tsx` — two separate local functions, `searchReplacementPool` (around lines 74, 76) and `searchAnyPosition` (around lines 85, 88), each with the same `.toLowerCase()` pattern on a query and a player name. Apply the identical `normalizeSearchText` transformation in both functions.

Add `import { normalizeSearchText } from "../lib/derive";` (or the correct relative path — match the existing import style already used for other `derive` imports in each file) to every file touched in this step that doesn't already import from `derive.ts`.

- [ ] **Step 7: Verify**

Run: `cd frontend && npm test`
Expected: still passes (this step didn't change `derive.test.ts`).
Run: `cd frontend && npm run typecheck`
Expected: 0 errors.
Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts frontend/src/components/PlayerNamePicker.tsx frontend/src/components/AlleSpielerTab.tsx frontend/src/components/SpekulationTab.tsx frontend/src/components/TransfermarktTab.tsx frontend/src/components/WunschkaderTab.tsx
git commit -m "Spielersuche: Umlaute/Diakritika/Apostrophe ignorieren (normalizeSearchText)"
```

---

### Task 7: Mobiler Header verschwindet kontextsensitiv beim Scrollen

**Files:**
- Create: `frontend/src/lib/useHideOnScroll.ts`
- Create: `frontend/src/lib/useHideOnScroll.test.ts`
- Modify: `frontend/src/App.tsx` (header element, around line 256)

**Interfaces:**
- Produces: `nextHeaderVisible(previousY: number, currentY: number, wasVisible: boolean): boolean` (pure, exported for testing) and `useHideOnScroll(): boolean` (React hook wrapping it) from `frontend/src/lib/useHideOnScroll.ts`.
- Consumes: nothing from earlier tasks in this plan.

**Context:** The header (`frontend/src/App.tsx:256`) is currently a plain flow element, not sticky, shared by mobile and desktop. Behavior only changes on mobile — desktop keeps the header always visible via a Tailwind `sm:` override, no JS branching needed.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/useHideOnScroll.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { nextHeaderVisible } from "./useHideOnScroll";

describe("nextHeaderVisible", () => {
  it("is always visible at the very top of the page", () => {
    expect(nextHeaderVisible(120, 0, false)).toBe(true);
  });

  it("hides when scrolling down past the threshold", () => {
    expect(nextHeaderVisible(100, 140, true)).toBe(false);
  });

  it("shows when scrolling up past the threshold", () => {
    expect(nextHeaderVisible(140, 100, false)).toBe(true);
  });

  it("keeps the previous state on small jitter deltas", () => {
    expect(nextHeaderVisible(100, 102, true)).toBe(true);
    expect(nextHeaderVisible(100, 102, false)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `frontend/src/lib/useHideOnScroll.ts` does not exist yet.

- [ ] **Step 3: Implement `useHideOnScroll.ts`**

Create `frontend/src/lib/useHideOnScroll.ts`:
```ts
import { useEffect, useRef, useState } from "react";

const SCROLL_DELTA_THRESHOLD = 4;

export function nextHeaderVisible(previousY: number, currentY: number, wasVisible: boolean): boolean {
  if (currentY <= 0) return true;
  const delta = currentY - previousY;
  if (delta > SCROLL_DELTA_THRESHOLD) return false;
  if (delta < -SCROLL_DELTA_THRESHOLD) return true;
  return wasVisible;
}

export function useHideOnScroll(): boolean {
  const [visible, setVisible] = useState(true);
  const lastY = useRef(0);

  useEffect(() => {
    function onScroll() {
      const currentY = window.scrollY;
      setVisible((prev) => nextHeaderVisible(lastY.current, currentY, prev));
      lastY.current = currentY;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return visible;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS, all 4 assertions in `useHideOnScroll.test.ts` green, plus the 4 from `derive.test.ts` (Task 6) still green.

- [ ] **Step 5: Wire the hook into `App.tsx`'s header**

Find the current header (around line 256):
```tsx
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-800 dark:bg-slate-950">
```
Add the import near the other `lib` imports in this file:
```ts
import { useHideOnScroll } from "./lib/useHideOnScroll";
```
Call the hook inside the `App` component body (near its other top-level hook calls):
```ts
  const headerVisible = useHideOnScroll();
```
Change the header element to:
```tsx
      <header
        className={`sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4 transition-transform duration-200 dark:border-slate-800 dark:bg-slate-950 sm:!translate-y-0 ${
          headerVisible ? "translate-y-0" : "-translate-y-full"
        }`}
      >
```
(The mobile menu overlay uses `z-20` at `App.tsx:134` — `z-10` on the header keeps it correctly below that overlay. The `sm:!translate-y-0` override pins the header fully visible on desktop regardless of `headerVisible`, satisfying "nur im mobilen Bereich" without any JS breakpoint branching.)

- [ ] **Step 6: Verify**

Run: `cd frontend && npm test`
Expected: still all green.
Run: `cd frontend && npm run typecheck`
Expected: 0 errors.
Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/useHideOnScroll.ts frontend/src/lib/useHideOnScroll.test.ts frontend/src/App.tsx
git commit -m "Mobile: Header versteckt sich beim Runterscrollen, erscheint beim Hochscrollen"
```
