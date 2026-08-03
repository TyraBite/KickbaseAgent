import { describe, expect, it } from "vitest";
import { resolveTarget } from "./wunschkaderResolve";
import type { Calibration, PlayerRecord, TransfermarktListing } from "../types";

const calibration: Calibration = {
  n: 10,
  global_k: null,
  position_k: { Sturm: { k: 5000, n: 10 } },
};

function makePlayer(overrides: Partial<PlayerRecord> & { player_id: string }): PlayerRecord {
  return {
    name: "Spieler", position: "Sturm", team_name: "Bayern",
    status_code: null, starting_rank: null, market_value: 900_000, average_points: 200,
    ...overrides,
  };
}

describe("resolveTarget", () => {
  it("status 'Eigener Kader' when the player is in the own squad", () => {
    const players = { p1: makePlayer({ player_id: "p1", name: "Eigener Spieler" }) };
    const result = resolveTarget("p1", players, new Set(["p1"]), new Map(), {}, calibration);
    expect(result.status).toBe("Eigener Kader");
    expect(result.name).toBe("Eigener Spieler");
    // valuation(900_000, 200, "Sturm", calibration): fairwert=1_000_000, signal=1.11 (siehe derive.test.ts).
    expect(result.signal).toBe(1.11);
  });

  it("status 'Markt (Anbieter, Preis)' with the offering username when a system offer is NOT set", () => {
    const players = { p2: makePlayer({ player_id: "p2", name: "Markt Spieler (User)" }) };
    const listingsByPlayerId = new Map<string, TransfermarktListing>([
      [
        "p2",
        {
          player_id: "p2", price: 250_000, price_delta_pct: null, offering_username: "RivalManager",
          is_system_offer: false, leading_bid_price: null, is_own_leading_bid: false,
          listed_at: null, expires_at: null, expiry_is_estimate: false,
        },
      ],
    ]);
    const result = resolveTarget("p2", players, new Set(), listingsByPlayerId, {}, calibration);
    expect(result.status).toBe("Markt (RivalManager, 250.000)");
  });

  it("status 'Markt (System, Preis)' when it IS a system offer", () => {
    const players = { p2b: makePlayer({ player_id: "p2b", name: "Markt Spieler (System)" }) };
    const listingsByPlayerId = new Map<string, TransfermarktListing>([
      [
        "p2b",
        {
          player_id: "p2b", price: 100_000, price_delta_pct: null, offering_username: null,
          is_system_offer: true, leading_bid_price: null, is_own_leading_bid: false,
          listed_at: null, expires_at: null, expiry_is_estimate: false,
        },
      ],
    ]);
    const result = resolveTarget("p2b", players, new Set(), listingsByPlayerId, {}, calibration);
    expect(result.status).toBe("Markt (System, 100.000)");
  });

  it("status 'Bei X' when owned by another manager and not listed", () => {
    const players = { p3: makePlayer({ player_id: "p3", name: "Fremdbesitz Spieler" }) };
    const result = resolveTarget("p3", players, new Set(), new Map(), { p3: "Manager Meier" }, calibration);
    expect(result.status).toBe("Bei Manager Meier");
  });

  it("status 'Frei' when the player exists but is not owned, not listed, and not in ownedBy", () => {
    const players = { p4: makePlayer({ player_id: "p4", name: "Freier Spieler" }) };
    const result = resolveTarget("p4", players, new Set(), new Map(), {}, calibration);
    expect(result.status).toBe("Frei");
  });

  it("status 'Nicht gefunden' with fallback fields when the player_id is unknown everywhere", () => {
    const players: Record<string, PlayerRecord> = {}; // p5 existiert nirgends
    const result = resolveTarget("p5", players, new Set(), new Map(), {}, calibration);
    expect(result.status).toBe("Nicht gefunden");
    expect(result.name).toBe("Unbekannt (p5)");
    expect(result.position).toBe("Sturm"); // Fallback-Position
    expect(result.market_value).toBeNull();
    expect(result.average_points).toBeNull();
    expect(result.starting_rank).toBeNull();
    expect(result.signal).toBeNull();
    expect(result.team_name).toBeNull();
    expect(result.status_label).toBeNull();
  });
});
