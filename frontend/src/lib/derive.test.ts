import { describe, expect, it } from "vitest";
import { buildBudgetPlan, normalizeSearchText, plannedPriceFor, suggestBid } from "./derive";
import type { BidPremiumEntry, PlayerRecord, RawWunschkaderTarget } from "../types";

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

describe("plannedPriceFor", () => {
  const player = { market_value: 1_000_000, position: "Sturm", average_points: 250 };
  const bidHistory: BidPremiumEntry[] = [
    { player_id: "hist1", position: "Sturm", market_value_then: 900_000, average_points_then: 240, premium_pct: 0.05, purchased_at: "2026-01-01T00:00:00Z" },
    { player_id: "hist2", position: "Sturm", market_value_then: 1_100_000, average_points_then: 260, premium_pct: 0.08, purchased_at: "2026-01-02T00:00:00Z" },
    { player_id: "hist3", position: "Sturm", market_value_then: 950_000, average_points_then: 245, premium_pct: 0.1, purchased_at: "2026-01-03T00:00:00Z" },
  ];

  it("returns price 0 / source own when isOwn is true, regardless of liveBid or history", () => {
    expect(plannedPriceFor(player, true, 500_000, bidHistory)).toEqual({ price: 0, source: "own", suggestionN: null });
    expect(plannedPriceFor(player, true, null, [])).toEqual({ price: 0, source: "own", suggestionN: null });
  });

  it("returns liveBid / source liveBid when set, even if a suggestBid() estimate is available", () => {
    expect(plannedPriceFor(player, false, 777_000, bidHistory)).toEqual({ price: 777_000, source: "liveBid", suggestionN: null });
  });

  it("falls back to suggestBid()'s p75 estimate / source estimate when no liveBid but matching history exists", () => {
    const suggestion = suggestBid(player, bidHistory);
    expect(suggestion).not.toBeNull();
    expect(plannedPriceFor(player, false, null, bidHistory)).toEqual({
      price: suggestion!.p75,
      source: "estimate",
      suggestionN: suggestion!.n,
    });
  });

  it("falls back to market_value / source marketValue when no liveBid and no history for this position", () => {
    const otherPositionHistory: BidPremiumEntry[] = [
      { player_id: "hist4", position: "Torwart", market_value_then: 500_000, average_points_then: 150, premium_pct: 0.03, purchased_at: "2026-01-04T00:00:00Z" },
    ];
    expect(plannedPriceFor(player, false, null, otherPositionHistory)).toEqual({
      price: player.market_value,
      source: "marketValue",
      suggestionN: null,
    });
  });

  // Critical #1 (Final-Review 2026-08-02/03): market_value ist null, aber es
  // existiert passende gleichpositionierte Kaufhistorie - suggestBid() liefert
  // dann trotzdem ein Nicht-null-Ergebnis, dessen Perzentile (mv = 0) alle auf
  // 0 runden. Ohne den p75>0-Guard wuerde das faelschlich price: 0/
  // source: "estimate" zurueckgeben ("0 (Schätzung)", liest sich wie
  // "kostenlos") statt korrekt auf den market_value-Fallback (hier null, "–")
  // durchzufallen.
  it("falls through to market_value (null) instead of a bogus 0-estimate when market_value is null and matching history exists", () => {
    const playerUnknownValue = { market_value: null, position: "Sturm", average_points: 250 };
    const suggestion = suggestBid(playerUnknownValue, bidHistory);
    expect(suggestion).not.toBeNull();
    expect(suggestion!.p75).toBe(0); // Beweist die Praemisse: suggestBid() liefert hier 0, nicht null.
    expect(plannedPriceFor(playerUnknownValue, false, null, bidHistory)).toEqual({
      price: null,
      source: "marketValue",
      suggestionN: null,
    });
  });

  it("falls through to market_value (0) instead of a bogus 0-estimate when market_value is exactly 0 and matching history exists", () => {
    const playerZeroValue = { market_value: 0, position: "Sturm", average_points: 250 };
    const suggestion = suggestBid(playerZeroValue, bidHistory);
    expect(suggestion).not.toBeNull();
    expect(suggestion!.p75).toBe(0);
    expect(plannedPriceFor(playerZeroValue, false, null, bidHistory)).toEqual({
      price: 0,
      source: "marketValue",
      suggestionN: null,
    });
  });
});

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
