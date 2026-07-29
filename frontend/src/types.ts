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
  auction_expires_at: string | null;
  is_hype_gipfel: boolean;
  near_floor: boolean;
}

export interface WunschkaderRow {
  name: string;
  position: string;
  role: string;
  note: string | null;
  planned_price: number | null;
  is_estimate: boolean;
  is_own: boolean;
  status: string;
  market_value: number | null;
  points_avg: number | null;
  team_name: string | null;
  starting_rank: number | null;
  status_code: number | null;
  signal: number | null;
  ml_prediction: number | null;
}

export interface RawWunschkaderTarget {
  name: string;
  position: string;
  role?: string;
  note?: string;
  actual_bid?: number;
}

export interface BudgetPlanSellRow {
  name: string;
  market_value: number | null;
}

export interface BudgetPlan {
  cash: number;
  sell_rows: BudgetPlanSellRow[];
  sell_proceeds: number;
  pool: number;
  committed: number;
  remaining: number;
}

export interface AlleSpielerRow {
  player_id: string;
  name: string;
  position: string;
  team_name: string | null;
  market_value: number | null;
  points_avg: number | null;
  starting_rank: number | null;
  status_label: string | null;
  owner: string;
  fairwert: number | null;
  signal: number | null;
}

export interface SignalThresholds {
  good: number;
  critical: number;
}

export interface DashboardSnapshot {
  spekulation: SpekulationRow[];
  wunschkader: WunschkaderRow[];
  wunschkader_raw: { targets: RawWunschkaderTarget[]; formation?: string | null; sell_list?: string[] } | null;
  wunschkader_formation: string | null;
  alle_spieler: AlleSpielerRow[];
  budget_plan: BudgetPlan | null;
  signal_thresholds: SignalThresholds;
  own_budget_exact: number | null;
  // Weitere Snapshot-Felder (transfermarkt, eigenes_team_split, ...)
  // werden erst in späteren Sub-Projekten typisiert, sobald der jeweilige
  // Tab migriert wird.
  [key: string]: unknown;
}
