import type { Calibration, PlayerRecord, TransfermarktListing } from "../types";
import { signalFor, statusLabel } from "./derive";
import { fmtNum } from "../format";

export interface ResolvedTarget {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  average_points: number | null;
  starting_rank: number | null;
  signal: number | null;
  team_name: string | null;
  status: string;
  // Verletzt/Angeschlagen/Im Aufbau (statusLabel()) - NICHT dasselbe wie
  // `status` oben (das ist Markt-/Besitz-Verfuegbarkeit, ein komplett
  // anderes Konzept, siehe MDs/codes.md).
  status_label: string | null;
}

// Ersetzt WunschkaderTab.tsx's alte computedFor() - jetzt EINE Quelle
// (players[player_id]) statt zwei mit Per-Feld-Fallback, da player_id ein
// verlaesslicher Join-Key ist (kein Namens-Mismatch mehr moeglich).
export function resolveTarget(
  playerId: string,
  players: Record<string, PlayerRecord>,
  ownSquadIds: ReadonlySet<string>,
  listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>,
  ownedBy: Record<string, string>,
  calibration: Calibration | null
): ResolvedTarget {
  const player = players[playerId];
  const listing = listingsByPlayerId.get(playerId);

  let status: string;
  if (ownSquadIds.has(playerId)) {
    status = "Eigener Kader";
  } else if (listing) {
    const anbieter = listing.is_system_offer ? "System" : listing.offering_username ?? "?";
    status = `Markt (${anbieter}, ${fmtNum(listing.price)})`;
  } else if (ownedBy[playerId]) {
    status = `Bei ${ownedBy[playerId]}`;
  } else if (player) {
    status = "Frei";
  } else {
    status = "Nicht gefunden";
  }

  return {
    player_id: playerId,
    name: player?.name ?? `Unbekannt (${playerId})`,
    position: player?.position ?? "Sturm",
    market_value: player?.market_value ?? null,
    average_points: player?.average_points ?? null,
    starting_rank: player?.starting_rank ?? null,
    signal: player ? signalFor(player.market_value, player.average_points, player.position, calibration) : null,
    team_name: player?.team_name ?? null,
    status,
    status_label: player ? statusLabel(player.status_code) : null,
  };
}
