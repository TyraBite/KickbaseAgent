# Wunschkader "Geplanter Preis" live berechnen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Wunschkader tab's "Geplanter Preis" — both the per-target detail value and the Budget-Planung "Eingeplant" sum — fall back to a `suggestBid()`-based p75 price estimate instead of the raw market value whenever no live own bid exists, and label that estimate in the UI exactly the way Transfermarkt/Spekulation already do.

**Architecture:** `plannedPriceFor()` (`frontend/src/lib/derive.ts`) changes its signature from a bare `marketValue: number | null` to the full player-shaped object (`market_value`, `position`, `average_points`) plus a `bidHistory: BidPremiumEntry[]` param, so it can call the already-existing, already-tested `suggestBid()` for a p75 estimate when no live bid exists. `buildBudgetPlan()` threads a new mandatory `bidHistory` param through to the same `plannedPriceFor()` call inside its `committed`-sum reduce, so the estimate flows into the budget total too. `WunschkaderTab.tsx` supplies `data.bid_premium_history ?? []` at both existing call sites and expands its local `selectedPlannedPrice` value from a bare number into a `{ price, isEstimate, suggestionN }` object, so the Detail-Modal's "Geplanter Preis" row can render the existing "(Schätzung)" / "(geringe Datenbasis, n=X)" suffix conventions already used in `TransfermarktTab.tsx`/`SpekulationTab.tsx`.

**Tech Stack:** React 18 + TypeScript + Vite (`frontend/`), Vitest for unit tests. No new dependencies. `derive.ts` stays a pure-function module (no React imports) per existing convention.

## Global Constraints

- Estimate-suffix copy must match `TransfermarktTab.tsx`/`SpekulationTab.tsx` verbatim: `" (Schätzung)"` when `suggestion.n >= MIN_N_FOR_PERCENTILE_SPREAD`, `" (geringe Datenbasis, n={n})"` when `suggestion.n < MIN_N_FOR_PERCENTILE_SPREAD`.
- `data.bid_premium_history` is optional on `DashboardSnapshot` (`frontend/src/types.ts:167`) — always read as `data.bid_premium_history ?? []`, never assume it's present.
- Do not modify `suggestBid()` itself or its existing usage in `TransfermarktTab.tsx`/`SpekulationTab.tsx`.
- Do not touch `EigenesTeamTab.tsx` — it does not call `buildBudgetPlan()`.
- No new UI component and no new export from `derive.ts` beyond the changed signatures — the four display-text cases are assembled locally in `WunschkaderTab.tsx`.
- The Budget-Planung "Eingeplant" sum is intentionally allowed to shift for existing users once this ships — that is an accepted, deliberate tradeoff for more accurate planning, not a regression to guard against.

---

## Task 1: `plannedPriceFor()` — p75 estimate instead of raw market-value fallback

**Files:**
- Modify: `frontend/src/lib/derive.ts:63-71` (the `plannedPriceFor` doc comment + function)
- Test: `frontend/src/lib/derive.test.ts` (append new `describe("plannedPriceFor")` block; extend the existing import lines)

**Interfaces:**
- Consumes: `suggestBid(listing: { position: string; market_value: number | null; average_points: number | null }, history: BidPremiumEntry[], k?: number): BidSuggestion | null` (already defined at `derive.ts:429-457`, unchanged by this task — function declarations are hoisted, so calling it from above its own definition in the same file is valid).
- Produces: `plannedPriceFor(player: { market_value: number | null; position: string; average_points: number | null }, isOwn: boolean, liveBid: number | null, bidHistory: BidPremiumEntry[]): number | null` — Task 2 and Task 3 both call this with the new 4-arg shape.

- [ ] **Step 1: Write the failing tests**

Open `frontend/src/lib/derive.test.ts`. Replace the current import lines:

```ts
import { describe, expect, it } from "vitest";
import { normalizeSearchText } from "./derive";
```

with:

```ts
import { describe, expect, it } from "vitest";
import { normalizeSearchText, plannedPriceFor, suggestBid } from "./derive";
import type { BidPremiumEntry } from "../types";
```

Then append this new `describe` block at the end of the file (after the existing `describe("normalizeSearchText", ...)` block):

```ts
describe("plannedPriceFor", () => {
  const player = { market_value: 1_000_000, position: "Sturm", average_points: 250 };
  const bidHistory: BidPremiumEntry[] = [
    { player_id: "hist1", position: "Sturm", market_value_then: 900_000, average_points_then: 240, premium_pct: 0.05, purchased_at: "2026-01-01T00:00:00Z" },
    { player_id: "hist2", position: "Sturm", market_value_then: 1_100_000, average_points_then: 260, premium_pct: 0.08, purchased_at: "2026-01-02T00:00:00Z" },
    { player_id: "hist3", position: "Sturm", market_value_then: 950_000, average_points_then: 245, premium_pct: 0.1, purchased_at: "2026-01-03T00:00:00Z" },
  ];

  it("returns 0 when isOwn is true, regardless of liveBid or history", () => {
    expect(plannedPriceFor(player, true, 500_000, bidHistory)).toBe(0);
    expect(plannedPriceFor(player, true, null, [])).toBe(0);
  });

  it("returns liveBid when set, even if a suggestBid() estimate is available", () => {
    expect(plannedPriceFor(player, false, 777_000, bidHistory)).toBe(777_000);
  });

  it("falls back to suggestBid()'s p75 estimate when no liveBid but matching history exists", () => {
    const suggestion = suggestBid(player, bidHistory);
    expect(suggestion).not.toBeNull();
    expect(plannedPriceFor(player, false, null, bidHistory)).toBe(suggestion!.p75);
  });

  it("falls back to market_value when no liveBid and no history for this position", () => {
    const otherPositionHistory: BidPremiumEntry[] = [
      { player_id: "hist4", position: "Torwart", market_value_then: 500_000, average_points_then: 150, premium_pct: 0.03, purchased_at: "2026-01-04T00:00:00Z" },
    ];
    expect(plannedPriceFor(player, false, null, otherPositionHistory)).toBe(player.market_value);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test`

Expected: FAIL. The 3rd test ("falls back to suggestBid()'s p75 estimate...") and 4th test ("falls back to market_value...") fail, because the current `plannedPriceFor(marketValue, isOwn, liveBid)` implementation ignores its 4th argument and, when `liveBid === null`, does `return marketValue` — which here is the `player` object itself (passed positionally as the old `marketValue` param), not a number. `toBe(suggestion!.p75)` and `toBe(player.market_value)` both fail against an object. (The 1st and 2nd tests happen to pass even against the old code, since `isOwn` and the `liveBid !== null` branch don't depend on the first argument's shape — that's expected and fine, the 3rd/4th tests are what prove the red state.)

- [ ] **Step 3: Write the minimal implementation**

In `frontend/src/lib/derive.ts`, replace:

```ts
// Eingeplanter Preis fuer ein Ziel: 0 wenn schon im eigenen Kader (bereits
// bezahlt, nicht nochmal einplanen), sonst das eigene laufende Hoechstgebot
// falls eins existiert (echte Kickbase-Daten aus dem Transfermarkt-Listing -
// praeziser als jede Schaetzung), sonst der reine Marktwert.
export function plannedPriceFor(marketValue: number | null, isOwn: boolean, liveBid: number | null): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  return marketValue;
}
```

with:

```ts
// Eingeplanter Preis fuer ein Ziel: 0 wenn schon im eigenen Kader (bereits
// bezahlt, nicht nochmal einplanen), sonst das eigene laufende Hoechstgebot
// falls eins existiert (echte Kickbase-Daten aus dem Transfermarkt-Listing -
// praeziser als jede Schaetzung), sonst eine Aufschlags-Schaetzung ueber
// suggestBid() (p75-Perzentil aehnlicher historischer Kaeufe derselben
// Position, siehe suggestBid() weiter unten), sonst - falls fuer diese
// Position noch keine Kaufhistorie existiert - der reine Marktwert
// (User-Feedback 297fc4aa, 2026-08-02: reiner Marktwert ohne jeden Aufschlag
// war zu optimistisch).
export function plannedPriceFor(
  player: { market_value: number | null; position: string; average_points: number | null },
  isOwn: boolean,
  liveBid: number | null,
  bidHistory: BidPremiumEntry[]
): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  const suggestion = suggestBid(player, bidHistory);
  if (suggestion !== null) return suggestion.p75;
  return player.market_value;
}
```

(`BidPremiumEntry` is already imported at the top of `derive.ts` — no new import line needed there.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test`

Expected: PASS — all tests in `derive.test.ts` green, including the pre-existing `normalizeSearchText` tests and all 4 new `plannedPriceFor` tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "plannedPriceFor(): p75-Schaetzung aus suggestBid() statt reinem Marktwert-Fallback"
```

---

## Task 2: `buildBudgetPlan()` — thread `bidHistory` through to the committed sum

**Files:**
- Modify: `frontend/src/lib/derive.ts:375-406` (`buildBudgetPlan` params + the `committed` reduce)
- Test: `frontend/src/lib/derive.test.ts` (append new `describe("buildBudgetPlan")` block; extend import lines)

**Interfaces:**
- Consumes: `plannedPriceFor(player, isOwn, liveBid, bidHistory)` from Task 1; `liveBidFor(playerId, listingsByPlayerId): number | null` (unchanged, `derive.ts:370-373`).
- Produces: `buildBudgetPlan(params: { players: Record<string, PlayerRecord>; ownSquadIds: Set<string>; targets: RawWunschkaderTarget[]; ownBudgetExact: number | null; listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>; bidHistory: BidPremiumEntry[] }): BudgetPlan` — Task 3's `WunschkaderTab.tsx` call site must supply the new `bidHistory` field.

- [ ] **Step 1: Write the failing test**

In `frontend/src/lib/derive.test.ts`, extend the import lines (from Task 1) to:

```ts
import { describe, expect, it } from "vitest";
import { buildBudgetPlan, normalizeSearchText, plannedPriceFor, suggestBid } from "./derive";
import type { BidPremiumEntry, PlayerRecord, RawWunschkaderTarget } from "../types";
```

Append this new `describe` block at the end of the file:

```ts
describe("buildBudgetPlan", () => {
  it("uses suggestBid()'s p75 estimate for committed, not the raw market_value, when no liveBid exists", () => {
    const players: Record<string, PlayerRecord> = {
      p1: {
        player_id: "p1", name: "Test Stuermer", position: "Sturm", team_name: null,
        status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 250,
      },
    };
    const bidHistory: BidPremiumEntry[] = [
      { player_id: "hist1", position: "Sturm", market_value_then: 900_000, average_points_then: 240, premium_pct: 0.05, purchased_at: "2026-01-01T00:00:00Z" },
      { player_id: "hist2", position: "Sturm", market_value_then: 1_100_000, average_points_then: 260, premium_pct: 0.08, purchased_at: "2026-01-02T00:00:00Z" },
      { player_id: "hist3", position: "Sturm", market_value_then: 950_000, average_points_then: 245, premium_pct: 0.1, purchased_at: "2026-01-03T00:00:00Z" },
    ];
    const targets: RawWunschkaderTarget[] = [{ player_id: "p1", role: "Starter" }];

    const plan = buildBudgetPlan({
      players,
      ownSquadIds: new Set(),
      targets,
      ownBudgetExact: 5_000_000,
      listingsByPlayerId: new Map(),
      bidHistory,
    });

    const expectedEstimate = suggestBid(players.p1, bidHistory)!.p75;
    expect(plan.committed).toBe(expectedEstimate);
    expect(plan.committed).not.toBe(players.p1.market_value);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test`

Expected: FAIL with a thrown `TypeError` (not a clean assertion failure) — `buildBudgetPlan`'s current `committed` reduce still calls `plannedPriceFor(marketValue, isOwn, liveBid)` with only 3 arguments. After Task 1, `plannedPriceFor`'s 4th parameter (`bidHistory`) is `undefined` in that call, and since `liveBid` is `null` here, execution reaches `suggestBid(player, bidHistory)` inside `plannedPriceFor` with `bidHistory === undefined`, and `suggestBid`'s `history.filter(...)` throws on `undefined`.

- [ ] **Step 3: Write the minimal implementation**

In `frontend/src/lib/derive.ts`, replace:

```ts
export function buildBudgetPlan(params: {
  players: Record<string, PlayerRecord>;
  ownSquadIds: Set<string>;
  targets: RawWunschkaderTarget[];
  ownBudgetExact: number | null;
  listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>;
}): BudgetPlan {
  const { players, ownSquadIds, targets, ownBudgetExact, listingsByPlayerId } = params;
```

with:

```ts
export function buildBudgetPlan(params: {
  players: Record<string, PlayerRecord>;
  ownSquadIds: Set<string>;
  targets: RawWunschkaderTarget[];
  ownBudgetExact: number | null;
  listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>;
  bidHistory: BidPremiumEntry[];
}): BudgetPlan {
  const { players, ownSquadIds, targets, ownBudgetExact, listingsByPlayerId, bidHistory } = params;
```

Then replace:

```ts
  const committed = targets.reduce((sum, t) => {
    const isOwn = ownSquadIds.has(t.player_id);
    if (isOwn) return sum;
    const marketValue = players[t.player_id]?.market_value ?? null;
    const liveBid = liveBidFor(t.player_id, listingsByPlayerId);
    return sum + (plannedPriceFor(marketValue, isOwn, liveBid) || 0);
  }, 0);
```

with:

```ts
  const committed = targets.reduce((sum, t) => {
    const isOwn = ownSquadIds.has(t.player_id);
    if (isOwn) return sum;
    // players[t.player_id] kann fehlen (Ziel-player_id nicht in der players-Map,
    // siehe resolveTarget()'s "Nicht gefunden"-Fall) - das Fallback-Objekt haelt
    // plannedPriceFor()'s Signatur ein und landet beim selben Marktwert-null-
    // Ergebnis wie vorher (suggestBid() findet fuer position: "" nie eine
    // passende Historie).
    const player = players[t.player_id] ?? { market_value: null, position: "", average_points: null };
    const liveBid = liveBidFor(t.player_id, listingsByPlayerId);
    return sum + (plannedPriceFor(player, isOwn, liveBid, bidHistory) || 0);
  }, 0);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test`

Expected: PASS — all tests green, including Task 1's 4 `plannedPriceFor` tests, the pre-existing `normalizeSearchText` tests, and this new `buildBudgetPlan` test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "buildBudgetPlan(): bidHistory durchreichen, Eingeplant-Summe nutzt jetzt dieselbe p75-Schaetzung"
```

---

## Task 3: `WunschkaderTab.tsx` — wire `bid_premium_history` through and show the estimate label

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx:5` (import line)
- Modify: `frontend/src/components/WunschkaderTab.tsx:146-156` (`buildBudgetPlan({...})` call)
- Modify: `frontend/src/components/WunschkaderTab.tsx:186-198` (`selectedPlannedPrice`)
- Modify: `frontend/src/components/WunschkaderTab.tsx:466-482` (`DetailModal` prop type)
- Modify: `frontend/src/components/WunschkaderTab.tsx:554` (`<Row label="Geplanter Preis">` rendering)

**Interfaces:**
- Consumes: `plannedPriceFor(player, isOwn, liveBid, bidHistory)` and `buildBudgetPlan({ ..., bidHistory })` from Tasks 1/2; `suggestBid` and `MIN_N_FOR_PERCENTILE_SPREAD` from `derive.ts` (both already exported, unchanged).
- Produces: `selectedPlannedPrice: { price: number | null; isEstimate: boolean; suggestionN: number | null }` — a local value, not exported; only `DetailModal`'s `plannedPrice` prop (same file) consumes it.

This task has no dedicated new automated test — it is pure call-site wiring plus presentation logic in a component file with no existing test harness for its rendering (matching the precedent already set in this codebase for presentation-only Wunschkader changes: verify via `npm run typecheck` + `npm run build`, plus a full `npm run test` run to confirm no regression in the unit tests from Tasks 1/2).

- [ ] **Step 1: Update the import line**

In `frontend/src/components/WunschkaderTab.tsx`, replace:

```ts
import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, liveModelMae, normalizeSearchText, plannedPriceFor, type AlleSpielerRow, type BudgetPlan } from "../lib/derive";
```

with:

```ts
import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, normalizeSearchText, plannedPriceFor, suggestBid, type AlleSpielerRow, type BudgetPlan } from "../lib/derive";
```

- [ ] **Step 2: Add `bidHistory` to the `buildBudgetPlan()` call**

Replace:

```tsx
  const liveBudgetPlan: BudgetPlan = useMemo(
    () =>
      buildBudgetPlan({
        players: data.players,
        ownSquadIds,
        targets: editState,
        ownBudgetExact: data.own_budget_exact,
        listingsByPlayerId,
      }),
    [data.players, ownSquadIds, editState, data.own_budget_exact, listingsByPlayerId]
  );
```

with:

```tsx
  const liveBudgetPlan: BudgetPlan = useMemo(
    () =>
      buildBudgetPlan({
        players: data.players,
        ownSquadIds,
        targets: editState,
        ownBudgetExact: data.own_budget_exact,
        listingsByPlayerId,
        bidHistory: data.bid_premium_history ?? [],
      }),
    [data.players, ownSquadIds, editState, data.own_budget_exact, listingsByPlayerId, data.bid_premium_history]
  );
```

- [ ] **Step 3: Rework `selectedPlannedPrice` into `{ price, isEstimate, suggestionN }`**

Replace:

```tsx
  // Geplanter Preis fuer die aktuell geoeffnete Detailansicht - ausserhalb von
  // buildBudgetPlan() (das summiert nur ueber alle Ziele), daher hier per
  // liveBidFor()/plannedPriceFor() (derive.ts) - dieselben Funktionen, die
  // buildBudgetPlan() intern nutzt, damit Kachel-Einzelpreis und Budget-Summe
  // garantiert nie divergieren (Review-Fund 2026-07-29: vorher war der
  // Live-Gebots-Ausdruck hier separat dupliziert).
  const selectedPlannedPrice = useMemo(() => {
    if (!selected) return null;
    const computed = resolvedByPlayerId.get(selected.player_id);
    if (!computed) return null;
    const liveBid = liveBidFor(selected.player_id, listingsByPlayerId);
    return plannedPriceFor(computed.market_value, ownSquadIds.has(selected.player_id), liveBid);
  }, [selected, resolvedByPlayerId, listingsByPlayerId, ownSquadIds]);
```

with:

```tsx
  // Geplanter Preis fuer die aktuell geoeffnete Detailansicht - ausserhalb von
  // buildBudgetPlan() (das summiert nur ueber alle Ziele), daher hier per
  // liveBidFor()/plannedPriceFor() (derive.ts) - dieselben Funktionen, die
  // buildBudgetPlan() intern nutzt, damit Kachel-Einzelpreis und Budget-Summe
  // garantiert nie divergieren (Review-Fund 2026-07-29: vorher war der
  // Live-Gebots-Ausdruck hier separat dupliziert). Jetzt ein kleines Objekt
  // statt nur einer Zahl (Feedback 297fc4aa, 2026-08-02): die Detailansicht
  // muss zwischen "echte Zahl" (isOwn/liveBid) und "Schaetzung" (suggestBid()
  // p75) unterscheiden koennen, um denselben Zusatztext wie Transfermarkt/
  // Spekulation zu zeigen.
  const selectedPlannedPrice = useMemo(() => {
    const empty = { price: null as number | null, isEstimate: false, suggestionN: null as number | null };
    if (!selected) return empty;
    const computed = resolvedByPlayerId.get(selected.player_id);
    if (!computed) return empty;
    const isOwn = ownSquadIds.has(selected.player_id);
    const liveBid = liveBidFor(selected.player_id, listingsByPlayerId);
    const bidHistory = data.bid_premium_history ?? [];
    const price = plannedPriceFor(computed, isOwn, liveBid, bidHistory);
    if (isOwn || liveBid !== null) return { price, isEstimate: false, suggestionN: null };
    const suggestion = suggestBid(computed, bidHistory);
    return { price, isEstimate: suggestion !== null, suggestionN: suggestion?.n ?? null };
  }, [selected, resolvedByPlayerId, listingsByPlayerId, ownSquadIds, data.bid_premium_history]);
```

- [ ] **Step 4: Update `DetailModal`'s `plannedPrice` prop type and its rendering**

Replace the prop type line:

```tsx
  plannedPrice: number | null;
```

with:

```tsx
  plannedPrice: { price: number | null; isEstimate: boolean; suggestionN: number | null };
```

Then replace the rendering line:

```tsx
            <Row label="Geplanter Preis">{fmtNum(plannedPrice)}</Row>
```

with:

```tsx
            <Row label="Geplanter Preis">
              {fmtNum(plannedPrice.price)}
              {plannedPrice.isEstimate && plannedPrice.suggestionN !== null && plannedPrice.suggestionN < MIN_N_FOR_PERCENTILE_SPREAD ? (
                <span className="text-slate-400 dark:text-slate-500"> (geringe Datenbasis, n={plannedPrice.suggestionN})</span>
              ) : plannedPrice.isEstimate ? (
                <span className="text-slate-400 dark:text-slate-500"> (Schätzung)</span>
              ) : null}
            </Row>
```

(No change needed where `DetailModal` is invoked — `plannedPrice={selectedPlannedPrice}` already passes the whole value through unchanged; only its shape changed.)

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS with no errors. (Before Steps 1-4, this command would fail with type errors on the stale 3-arg `plannedPriceFor` call and the missing `bidHistory` field in the `buildBudgetPlan()` call — both are now fixed.)

- [ ] **Step 6: Run the production build**

Run: `cd frontend && npm run build`

Expected: PASS, build completes with no errors.

- [ ] **Step 7: Run the full test suite**

Run: `cd frontend && npm run test`

Expected: PASS — all `derive.test.ts` tests (Tasks 1 and 2, plus the pre-existing `normalizeSearchText` tests) remain green; this file has no test suite of its own so this step is a regression check, not new coverage.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: Geplanter Preis zeigt Schaetzung/geringe-Datenbasis-Hinweis wie Transfermarkt/Spekulation"
```

---
