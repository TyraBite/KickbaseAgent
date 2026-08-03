import { describe, expect, it } from "vitest";
import { normalizeSearchText, plannedPriceFor, suggestBid } from "./derive";
import type { BidPremiumEntry } from "../types";

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
