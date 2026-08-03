import { describe, expect, it } from "vitest";
import { buildBudgetPlan, normalizeSearchText, plannedPriceFor, suggestBid, buildDashboardSellCandidates, buildDashboardBuyCandidates, buildInvestmentSwaps, recentTransfersWithin24h, valuation, signalFor, nextUpdateCutoff, MIN_N_FOR_PERCENTILE_SPREAD, buildPlayerRow, buildTransfermarktRows, buildSpekulationRows, buildEigenesTeamSplit, buildAlleSpielerRows, ownerFor } from "./derive";
import type { BidPremiumEntry, Calibration, PlayerRecord, RawWunschkaderTarget, TransfermarktListing } from "../types";
import type { PlayerRow, TransfermarktRow } from "./derive";

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

describe("valuation", () => {
  const calibration: Calibration = {
    n: 10,
    global_k: null,
    position_k: { Sturm: { k: 5000, n: 10 } },
  };

  it("computes fairwert/signal from a known market_value/average_points/position/calibration quadruple", () => {
    // k=5000 (Sturm), averagePoints=200, marketValue=900_000.
    // fairwert = round(5000*200) = 1_000_000.
    // signal = round((5000 / (900_000/200)) * 100) / 100 = round(111.11) / 100 = 1.11.
    expect(valuation(900_000, 200, "Sturm", calibration)).toEqual({ fairwert: 1_000_000, signal: 1.11 });
  });

  it("returns null/null when calibration has no k for the position and no global_k fallback", () => {
    // position_k hat keinen Eintrag fuer "Torwart", global_k ist ebenfalls null -> kForPosition() liefert null.
    expect(valuation(900_000, 200, "Torwart", calibration)).toEqual({ fairwert: null, signal: null });
  });

  it("returns null/null when market_value is 0 (falsy guard), even with valid k/averagePoints", () => {
    expect(valuation(0, 200, "Sturm", calibration)).toEqual({ fairwert: null, signal: null });
  });

  it("returns null/null when average_points is 0 (falsy guard), even with valid k/marketValue", () => {
    expect(valuation(900_000, 0, "Sturm", calibration)).toEqual({ fairwert: null, signal: null });
  });

  it("returns null/null when calibration itself is null", () => {
    expect(valuation(900_000, 200, "Sturm", null)).toEqual({ fairwert: null, signal: null });
  });
});

describe("signalFor", () => {
  const calibration: Calibration = {
    n: 10,
    global_k: null,
    position_k: { Sturm: { k: 5000, n: 10 } },
  };

  it("returns exactly valuation()'s signal field for the same inputs", () => {
    expect(signalFor(900_000, 200, "Sturm", calibration)).toBe(valuation(900_000, 200, "Sturm", calibration).signal);
    expect(signalFor(900_000, 200, "Sturm", calibration)).toBe(1.11);
  });

  it("returns null when the null guard triggers (e.g. market_value 0)", () => {
    expect(signalFor(0, 200, "Sturm", calibration)).toBeNull();
  });
});

describe("nextUpdateCutoff", () => {
  // DST-Regressionstest fuer Commit 779b413 (derive.ts: DST-Cutoff-Bug gefixt).
  // Der Bug: der UTC-Offset wurde nur EINMAL an `now` aufgeloest - an den zwei
  // jaehrlichen Umstellungstagen weicht der Offset von `now` aber vom Offset
  // des Cutoffs (22 Uhr desselben Tages) ab, das ergab bis zu 1h Abweichung.

  it("resolves the correct 22:00 Berlin cutoff across the spring-forward transition (2026-03-29, CET->CEST)", () => {
    // now = kurz vor der Umstellung (01:30 CET, Umstellung selbst um 02:00->03:00
    // CEST via 01:00 UTC). Der Cutoff liegt am selben Tag um 22:00 Uhr - zu diesem
    // Zeitpunkt gilt bereits CEST (UTC+2), also 20:00 UTC. Der alte, nur an `now`
    // aufgeloeste Offset (CET, UTC+1) haette faelschlich 21:00 UTC (23:00 CEST,
    // 1h zu spaet) geliefert.
    const now = new Date("2026-03-29T00:30:00Z");
    expect(nextUpdateCutoff(now)).toEqual(new Date("2026-03-29T20:00:00Z"));
  });

  it("resolves the correct 22:00 Berlin cutoff across the fall-back transition (2026-10-25, CEST->CET)", () => {
    // now = kurz vor der Umstellung (02:30 CEST, Umstellung selbst um 03:00->02:00
    // CET via 01:00 UTC). Der Cutoff liegt am selben Tag um 22:00 Uhr - zu diesem
    // Zeitpunkt gilt bereits CET (UTC+1), also 21:00 UTC. Der alte, nur an `now`
    // aufgeloeste Offset (CEST, UTC+2) haette faelschlich 20:00 UTC (21:00 CET,
    // 1h zu frueh) geliefert.
    const now = new Date("2026-10-25T00:30:00Z");
    expect(nextUpdateCutoff(now)).toEqual(new Date("2026-10-25T21:00:00Z"));
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

describe("buildDashboardSellCandidates", () => {
  const players = {
    p1: { player_id: "p1", name: "A", position: "Sturm", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: -50_000, ml_prediction_3d: -100_000 },
    p2: { player_id: "p2", name: "B", position: "Abwehr", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 50_000, ml_prediction_3d: 100_000 },
    p3: { player_id: "p3", name: "C", position: "Mittelfeld", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 10_000, ml_prediction_3d: 20_000 },
    p4: { player_id: "p4", name: "D", position: "Torwart", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 200_000, ml_prediction_3d: 300_000 },
  };

  it("returns the 3 lowest-Prognose-1T players even when all values are positive", () => {
    const result = buildDashboardSellCandidates(players, ["p1", "p2", "p3", "p4"], null, null);
    expect(result.map((r) => r.player_id)).toEqual(["p1", "p3", "p2"]);
  });

  it("attaches the real sellSignal per row instead of hardcoding 'verkaufen'", () => {
    // mae=30_000: p1 (-50k) klar unter der Schwelle -> "verkaufen", p3 (10k) innerhalb
    // der Ungenauigkeit -> "unklar", p2 (50k) klar darueber -> "halten".
    const result = buildDashboardSellCandidates(players, ["p1", "p2", "p3", "p4"], null, 30_000);
    expect(result.map((r) => r.sell_signal)).toEqual(["verkaufen", "unklar", "halten"]);
  });

  it("returns fewer than 3 rows if fewer than 3 owned players have a prediction", () => {
    const onePlayer = { p1: players.p1 };
    const result = buildDashboardSellCandidates(onePlayer, ["p1"], null, null);
    expect(result.map((r) => r.player_id)).toEqual(["p1"]);
  });

  it("excludes players without a 1T prediction from the ranking", () => {
    const withUndefined = { ...players, p5: { ...players.p4, player_id: "p5", ml_prediction: undefined } };
    const result = buildDashboardSellCandidates(withUndefined, ["p1", "p2", "p3", "p4", "p5"], null, null);
    expect(result.map((r) => r.player_id)).not.toContain("p5");
  });
});

describe("buildDashboardBuyCandidates", () => {
  it("returns transfermarkt rows whose player_id is a wunschkader target", () => {
    const rows = [
      { player_id: "p1", name: "A" } as TransfermarktRow,
      { player_id: "p2", name: "B" } as TransfermarktRow,
    ];
    const targets = [{ player_id: "p2" }] as RawWunschkaderTarget[];
    const result = buildDashboardBuyCandidates(rows, targets);
    expect(result.map((r) => r.player_id)).toEqual(["p2"]);
  });
});

describe("buildInvestmentSwaps", () => {
  const ownRows = [
    { player_id: "own1", name: "Own1", ml_prediction_3d: -300_000 } as PlayerRow,
    { player_id: "own2", name: "Own2", ml_prediction_3d: 100_000 } as PlayerRow,
  ];
  const marketRows = [
    { player_id: "m1", name: "M1", ml_prediction_3d: 400_000 } as TransfermarktRow,
    { player_id: "m2", name: "M2", ml_prediction_3d: -50_000 } as TransfermarktRow,
  ];
  it("pairs worst-owned with best-market when the gap exceeds the strong threshold", () => {
    const result = buildInvestmentSwaps(ownRows, marketRows, 420_000);
    expect(result).toEqual([{ sell: ownRows[0], buy: marketRows[0] }]);
  });
  it("skips a pair whose gap does not reach the threshold", () => {
    const result = buildInvestmentSwaps([{ player_id: "own3", name: "Own3", ml_prediction_3d: 0 } as PlayerRow], marketRows, 420_000);
    expect(result).toEqual([]);
  });
});

describe("recentTransfersWithin24h", () => {
  it("keeps entries within the last 24 hours and drops older ones", () => {
    const now = new Date("2026-08-03T12:00:00Z");
    const entries = [
      { player_id: "p1", player_name: "A", buyer: "X", seller: "Y", price: 1, date: "2026-08-03T10:00:00Z" },
      { player_id: "p2", player_name: "B", buyer: "X", seller: "Y", price: 1, date: "2026-08-01T10:00:00Z" },
    ];
    expect(recentTransfersWithin24h(entries, now).map((e) => e.player_id)).toEqual(["p1"]);
  });
});
