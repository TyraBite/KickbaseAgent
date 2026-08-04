import { describe, expect, it } from "vitest";
import { buildBudgetPlan, normalizeSearchText, plannedPriceFor, suggestBid, buildDashboardSellCandidates, buildDashboardBuyCandidates, buildInvestmentSwaps, recentTransfersWithin24h, valuation, signalFor, nextUpdateCutoff, MIN_N_FOR_PERCENTILE_SPREAD, buildPlayerRow, buildTransfermarktRows, buildSpekulationRows, buildEigenesTeamSplit, buildAlleSpielerRows, ownerFor, mlBaselineDeltaPct } from "./derive";
import type { BidPremiumEntry, Calibration, MlRealizedWindow, PlayerRecord, RawWunschkaderTarget, TransfermarktListing } from "../types";
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

describe("suggestBid", () => {
  it("computes p50/p75/p90 as distinct percentiles from an n>=MIN_N_FOR_PERCENTILE_SPREAD same-position history", () => {
    const listing = { position: "Abwehr", market_value: 500_000, average_points: 100 };
    // Alle 8 Eintraege haben dieselbe market_value_then/average_points_then wie das
    // Listing -> distance 0 fuer alle, stabile Sortierung erhaelt die hier bereits
    // aufsteigend sortierte premium_pct-Reihenfolge.
    const history: BidPremiumEntry[] = [0.01, 0.03, 0.05, 0.07, 0.09, 0.11, 0.13, 0.15].map((premium_pct, i) => ({
      player_id: `hist${i}`, position: "Abwehr", market_value_then: 500_000, average_points_then: 100,
      premium_pct, purchased_at: "2026-01-01T00:00:00Z",
    }));

    const result = suggestBid(listing, history);
    expect(result).not.toBeNull();
    expect(result!.n).toBe(8);
    expect(result!.n).toBeGreaterThanOrEqual(MIN_N_FOR_PERCENTILE_SPREAD);
    // pct(0.5) -> index floor(0.5*7)=3 -> premiums[3]=0.07 -> round(500_000*1.07)
    expect(result!.p50).toBe(535_000);
    // pct(0.75) -> index floor(0.75*7)=5 -> premiums[5]=0.11 -> round(500_000*1.11)
    expect(result!.p75).toBe(555_000);
    // pct(0.9) -> index floor(0.9*7)=6 -> premiums[6]=0.13 -> round(500_000*1.13)
    expect(result!.p90).toBe(565_000);
    expect(new Set([result!.p50, result!.p75, result!.p90]).size).toBe(3); // alle drei unterscheiden sich
  });

  it("only considers the k nearest-by-distance entries, ignoring far-away history even if it exists", () => {
    const listing = { position: "Sturm", market_value: 1_000_000, average_points: 200 };
    const history: BidPremiumEntry[] = [
      // distance 0 (identisch zum Listing).
      { player_id: "close1", position: "Sturm", market_value_then: 1_000_000, average_points_then: 200, premium_pct: 0.10, purchased_at: "2026-01-01T00:00:00Z" },
      // distance 0.1 (leicht abweichend).
      { player_id: "close2", position: "Sturm", market_value_then: 1_050_000, average_points_then: 210, premium_pct: 0.20, purchased_at: "2026-01-02T00:00:00Z" },
      // distance 5.5 (weit entfernt) - darf bei k=2 NICHT in die Perzentile einfliessen,
      // obwohl sein premium_pct (0.99) das Ergebnis stark verzerren wuerde.
      { player_id: "far", position: "Sturm", market_value_then: 3_000_000, average_points_then: 900, premium_pct: 0.99, purchased_at: "2026-01-03T00:00:00Z" },
    ];

    const result = suggestBid(listing, history, 2);
    expect(result).not.toBeNull();
    expect(result!.n).toBe(2); // nur die 2 naechstliegenden, nicht alle 3 Eintraege
    // n=2 kollabiert alle Perzentile auf denselben Index (premiums[0]=0.10).
    expect(result!.p50).toBe(1_100_000);
    expect(result!.p75).toBe(1_100_000);
    expect(result!.p90).toBe(1_100_000);
    // Waere der weit entfernte Eintrag mit eingeflossen, laege p90 bei round(1_000_000*1.99)=1_990_000.
    expect(result!.p90).not.toBe(1_990_000);
  });

  it("flags a low data basis (n < MIN_N_FOR_PERCENTILE_SPREAD) via a small suggestionN, percentiles collapse to one value", () => {
    const listing = { position: "Torwart", market_value: 300_000, average_points: 50 };
    const history: BidPremiumEntry[] = [0.02, 0.06, 0.10].map((premium_pct, i) => ({
      player_id: `tw${i}`, position: "Torwart", market_value_then: 300_000, average_points_then: 50,
      premium_pct, purchased_at: "2026-01-01T00:00:00Z",
    }));

    const result = suggestBid(listing, history);
    expect(result).not.toBeNull();
    expect(result!.n).toBe(3);
    expect(result!.n).toBeLessThan(MIN_N_FOR_PERCENTILE_SPREAD); // "geringe Datenbasis"
    // n=3 -> (n-1)=2, floor(0.5*2)=1, floor(0.75*2)=1, floor(0.9*2)=1 -> alle 3 Perzentile identisch.
    expect(result!.p50).toBe(318_000);
    expect(result!.p75).toBe(318_000);
    expect(result!.p90).toBe(318_000);
  });

  it("returns null when no history entry matches the listing's position", () => {
    const listing = { position: "Sturm", market_value: 1_000_000, average_points: 200 };
    const otherPosition: BidPremiumEntry[] = [
      { player_id: "gk1", position: "Torwart", market_value_then: 500_000, average_points_then: 100, premium_pct: 0.05, purchased_at: "2026-01-01T00:00:00Z" },
    ];
    expect(suggestBid(listing, otherPosition)).toBeNull();
    expect(suggestBid(listing, [])).toBeNull();
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

  it("computes sell_proceeds/pool/cash/remaining correctly when a sell candidate AND a live bid on a target both exist", () => {
    const players: Record<string, PlayerRecord> = {
      // Im eigenen Kader, aber NICHT unter den Zielen -> Verkaufskandidat.
      p1: {
        player_id: "p1", name: "Verkaufskandidat", position: "Abwehr", team_name: null,
        status_code: null, starting_rank: null, market_value: 800_000, average_points: 120,
      },
      // Ziel, nicht im eigenen Kader, hat ein laufendes eigenes Hoechstgebot.
      p2: {
        player_id: "p2", name: "Wunschziel", position: "Mittelfeld", team_name: null,
        status_code: null, starting_rank: null, market_value: 500_000, average_points: 150,
      },
    };
    const targets: RawWunschkaderTarget[] = [{ player_id: "p2", role: "Starter" }];
    const listingsByPlayerId = new Map([
      [
        "p2",
        {
          player_id: "p2", price: 650_000, price_delta_pct: null, offering_username: null,
          is_system_offer: false, leading_bid_price: 600_000, is_own_leading_bid: true,
          listed_at: null, expires_at: null, expiry_is_estimate: false,
        },
      ],
    ]);

    const plan = buildBudgetPlan({
      players,
      ownSquadIds: new Set(["p1"]),
      targets,
      ownBudgetExact: 2_000_000,
      listingsByPlayerId,
      bidHistory: [],
    });

    expect(plan.cash).toBe(2_000_000);
    expect(plan.sell_rows).toEqual([{ player_id: "p1", market_value: 800_000 }]);
    expect(plan.sell_proceeds).toBe(800_000);
    expect(plan.pool).toBe(2_800_000); // cash + sell_proceeds
    expect(plan.committed).toBe(600_000); // liveBid hat Vorrang vor jeder Schaetzung
    expect(plan.remaining).toBe(2_200_000); // pool - committed
  });
});

describe("buildPlayerRow", () => {
  const calibration: Calibration = {
    n: 10,
    global_k: null,
    position_k: { Sturm: { k: 5000, n: 10 } },
  };

  it("builds a full row with computed fairwert/signal and status_label, all optional fields populated", () => {
    const player: PlayerRecord = {
      player_id: "p1", name: "Test Spieler", position: "Sturm", team_name: "Bayern",
      status_code: 1, starting_rank: 2, market_value: 900_000, average_points: 200,
      market_value_change_7d: 5_000, market_value_low_92d: 800_000, market_value_high_92d: 950_000,
      ml_prediction: 10_000, ml_prediction_3d: 20_000,
    };
    expect(buildPlayerRow(player, calibration)).toEqual({
      player_id: "p1", name: "Test Spieler", position: "Sturm", team_name: "Bayern",
      status_label: "Verletzt", starting_rank: 2,
      market_value: 900_000, market_value_change_7d: 5_000,
      market_value_low_92d: 800_000, market_value_high_92d: 950_000,
      average_points: 200,
      fairwert: 1_000_000, signal: 1.11,
      ml_prediction: 10_000, ml_prediction_3d: 20_000,
    });
  });

  it("defaults every optional field to null when absent from the PlayerRecord", () => {
    const player: PlayerRecord = {
      player_id: "p2", name: "Minimal Spieler", position: "Torwart", team_name: null,
      status_code: null, starting_rank: null, market_value: null, average_points: null,
    };
    const row = buildPlayerRow(player, calibration);
    expect(row.status_label).toBeNull();
    expect(row.market_value_change_7d).toBeNull();
    expect(row.market_value_low_92d).toBeNull();
    expect(row.market_value_high_92d).toBeNull();
    expect(row.ml_prediction).toBeNull();
    expect(row.ml_prediction_3d).toBeNull();
    expect(row.fairwert).toBeNull(); // market_value ist null -> Guard greift
    expect(row.signal).toBeNull();
  });
});

describe("buildTransfermarktRows", () => {
  it("joins listings against the players map, drops listings for unknown players, copies auction fields through", () => {
    const players: Record<string, PlayerRecord> = {
      p1: {
        player_id: "p1", name: "Gelisteter Spieler", position: "Sturm", team_name: null,
        status_code: null, starting_rank: null, market_value: 900_000, average_points: 200,
      },
    };
    const now = new Date("2026-08-03T12:00:00Z");
    const listings: TransfermarktListing[] = [
      {
        player_id: "p1", price: 950_000, price_delta_pct: 5.5, offering_username: "RivalManager",
        is_system_offer: false, leading_bid_price: null, is_own_leading_bid: false,
        listed_at: "2026-08-03T10:00:00Z", expires_at: "2026-08-03T14:00:00Z", expiry_is_estimate: false,
      },
      // Listing fuer einen Spieler, der nicht in der players-Map existiert -> muss rausgefiltert werden.
      {
        player_id: "unknown", price: 100_000, price_delta_pct: null, offering_username: null,
        is_system_offer: true, leading_bid_price: null, is_own_leading_bid: false,
        listed_at: null, expires_at: null, expiry_is_estimate: false,
      },
    ];

    const rows = buildTransfermarktRows(players, listings, null, now);
    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row.player_id).toBe("p1");
    expect(row.name).toBe("Gelisteter Spieler");
    expect(row.price).toBe(950_000);
    expect(row.price_delta_pct).toBe(5.5);
    expect(row.offering_username).toBe("RivalManager");
    expect(row.is_system_offer).toBe(false);
    expect(row.auction_expires_at).toBe("2026-08-03T14:00:00Z");
    // 2h Restlaufzeit ab now bis expires_at, nicht geschaetzt -> kein "(geschätzt)"-Suffix.
    expect(row.auction_status).toBe("läuft ab in 2h 0m");
    expect(row.auction_remaining_seconds).toBe(2 * 60 * 60);
    // Listing laeuft um 14:00 ab, der naechste 22-Uhr-Cutoff ist noch 8h entfernt ->
    // die Auktion endet VOR dem Cutoff, also urgent. Nicht critical (2h > 60min-Schwelle).
    expect(row.auction_urgent).toBe(true);
    expect(row.auction_critical).toBe(false);
  });
});

describe("buildSpekulationRows", () => {
  it("filters to system offers with a positive roi_pct and sorts descending by roi_pct", () => {
    const rows = [
      { player_id: "row1", name: "R1", is_system_offer: true, ml_prediction: 50_000, price: 1_000_000 } as TransfermarktRow,
      // Nicht is_system_offer -> ausgeschlossen, obwohl roi_pct positiv waere.
      { player_id: "row2", name: "R2", is_system_offer: false, ml_prediction: 80_000, price: 1_000_000 } as TransfermarktRow,
      // ml_prediction null -> roiPct() liefert null -> ausgeschlossen.
      { player_id: "row3", name: "R3", is_system_offer: true, ml_prediction: null, price: 500_000 } as TransfermarktRow,
      { player_id: "row4", name: "R4", is_system_offer: true, ml_prediction: 200_000, price: 1_000_000 } as TransfermarktRow,
      // ml_prediction negativ -> roiPct() liefert null (mlPrediction<=0) -> ausgeschlossen.
      { player_id: "row5", name: "R5", is_system_offer: true, ml_prediction: -10_000, price: 1_000_000 } as TransfermarktRow,
    ];

    const result = buildSpekulationRows(rows);
    expect(result.map((r) => r.player_id)).toEqual(["row4", "row1"]);
    expect(result.map((r) => r.roi_pct)).toEqual([20, 5]);
  });
});

describe("buildEigenesTeamSplit", () => {
  it("splits own-squad players into bleibt (still a target) vs verkaufen (no longer a target, gets sell_signal)", () => {
    const players: Record<string, PlayerRecord> = {
      p1: {
        player_id: "p1", name: "Bleibt-Spieler", position: "Sturm", team_name: null,
        status_code: null, starting_rank: null, market_value: 900_000, average_points: 200,
      },
      p2: {
        player_id: "p2", name: "Verkaufs-Spieler", position: "Abwehr", team_name: null,
        status_code: null, starting_rank: null, market_value: 500_000, average_points: 100,
        ml_prediction: -50_000,
      },
    };
    const targets: RawWunschkaderTarget[] = [{ player_id: "p1", role: "Starter" }];

    const split = buildEigenesTeamSplit(players, ["p1", "p2"], targets, null, 30_000);

    expect(split.bleibt.map((r) => r.player_id)).toEqual(["p1"]);
    expect(split.bleibt[0].sell_signal).toBeUndefined();

    expect(split.verkaufen.map((r) => r.player_id)).toEqual(["p2"]);
    // mae=30_000, ml_prediction=-50_000: |−50_000| > 30_000 -> klar "verkaufen" (nicht "unklar").
    expect(split.verkaufen[0].sell_signal).toBe("verkaufen");
  });
});

describe("ownerFor", () => {
  it("returns 'Eigener Kader' when the player is in the own squad, taking priority over ownedBy", () => {
    expect(ownerFor("p1", new Set(["p1"]), {})).toBe("Eigener Kader");
    expect(ownerFor("p1", new Set(["p1"]), { p1: "Jemand Anders" })).toBe("Eigener Kader");
  });

  it("returns the ownedBy manager name when set and not in the own squad", () => {
    expect(ownerFor("p2", new Set(), { p2: "Manager Meier" })).toBe("Manager Meier");
  });

  it("returns 'Frei' when neither in the own squad nor in ownedBy", () => {
    expect(ownerFor("p3", new Set(), {})).toBe("Frei");
  });
});

describe("buildAlleSpielerRows", () => {
  it("attaches the correct owner category (own squad / ownedBy manager / Frei) to every player", () => {
    const players: Record<string, PlayerRecord> = {
      p1: {
        player_id: "p1", name: "Eigener", position: "Sturm", team_name: null,
        status_code: null, starting_rank: null, market_value: 900_000, average_points: 200,
      },
      p2: {
        player_id: "p2", name: "Fremdbesitz", position: "Abwehr", team_name: null,
        status_code: null, starting_rank: null, market_value: 500_000, average_points: 100,
      },
      p3: {
        player_id: "p3", name: "Freier Spieler", position: "Mittelfeld", team_name: null,
        status_code: null, starting_rank: null, market_value: 300_000, average_points: 80,
      },
    };
    const rows = buildAlleSpielerRows(players, ["p1"], { p2: "Manager Meier" }, null);
    expect(rows).toHaveLength(3);
    const owners = Object.fromEntries(rows.map((r) => [r.player_id, r.owner]));
    expect(owners).toEqual({ p1: "Eigener Kader", p2: "Manager Meier", p3: "Frei" });
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

describe("mlBaselineDeltaPct", () => {
  it("gibt die Differenz Modell- minus Baseline-Trefferquote in Prozentpunkten zurueck", () => {
    const realized: MlRealizedWindow = {
      n: 10, sign_accuracy: 75, mae: 100, mae_given_correct_sign: 80,
      baseline_sign_accuracy: 60, baseline_mae: 120, reversal_sign_accuracy: 50, reversal_n: 2,
    };
    expect(mlBaselineDeltaPct(realized)).toBeCloseTo(15, 5);
  });

  it("gibt null zurueck wenn keine Baseline-Daten vorhanden sind", () => {
    const realized: MlRealizedWindow = {
      n: 10, sign_accuracy: 75, mae: 100, mae_given_correct_sign: null,
      baseline_sign_accuracy: null, baseline_mae: null, reversal_sign_accuracy: null, reversal_n: 0,
    };
    expect(mlBaselineDeltaPct(realized)).toBeNull();
  });

  it("gibt null zurueck bei fehlendem realized-Objekt", () => {
    expect(mlBaselineDeltaPct(null)).toBeNull();
    expect(mlBaselineDeltaPct(undefined)).toBeNull();
  });
});
