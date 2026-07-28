export interface SpekulationRow {
  name: string;
  position: string;
  team_name: string | null;
  price: number;
  roi_pct: number;
  average_points: number | null;
  market_value_change_7d: number | null;
  market_value_low_92d: number | null;
  market_value_high_92d: number | null;
  ml_prediction: number | null;
  auction_status: string | null;
  auction_urgent: boolean;
  auction_remaining_seconds: number | null;
  is_hype_gipfel: boolean;
  near_floor: boolean;
}

export interface DashboardSnapshot {
  spekulation: SpekulationRow[];
  // Weitere Snapshot-Felder (transfermarkt, wunschkader, alle_spieler, ...)
  // werden erst in späteren Sub-Projekten typisiert, sobald der jeweilige
  // Tab migriert wird.
  [key: string]: unknown;
}
