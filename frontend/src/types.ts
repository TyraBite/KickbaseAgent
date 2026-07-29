export interface PositionCalibrationEntry {
  k: number | null;
  n: number;
}

export interface Calibration {
  calibrated_at?: string;
  n: number;
  global_k: number | null;
  position_k: Record<string, PositionCalibrationEntry>;
}

export interface PlayerRecord {
  player_id: string;
  name: string;
  position: string;
  team_name: string | null;
  status_code: number | null;
  starting_rank: number | null;
  market_value: number | null;
  average_points: number | null;
  // Nur vorhanden fuer Spieler in own_squad/market_listings (light-path):
  market_value_change_7d?: number;
  market_value_low_92d?: number;
  market_value_high_92d?: number;
  market_value_in_drop_phase?: boolean;
  total_points?: number;
  // Nur vorhanden, wenn das ML-Modell einen Wert produziert hat:
  ml_prediction?: number;
}

export interface TransfermarktListing {
  player_id: string;
  price: number;
  price_delta_pct: number | null;
  offering_username: string | null;
  is_system_offer: boolean;
  pending_offers_count: number | null;
  leading_bid_username: string | null;
  leading_bid_price: number | null;
  is_own_leading_bid: boolean;
  listed_at: string | null;
  expires_at: string | null;
  expiry_is_estimate: boolean;
}


// NEU:
export interface RawWunschkaderTarget {
  player_id: string;
  role: string;
  note?: string;
}



export interface SignalThresholds {
  good: number;
  critical: number;
}

// Gemeinsame Basis-Felder aus src/dashboard_export.py::_player_row() - Basis
// fuer Transfermarkt- und Eigenes-Team-Zeilen (beide erweitern das mit ihren
// eigenen Feldern, wie serverseitig auch).
export interface PlayerRow {
  player_id: string;
  name: string;
  position: string;
  team_name: string | null;
  status_label: string | null;
  starting_rank: number | null;
  market_value: number | null;
  market_value_change_7d: number | null;
  market_value_low_92d: number | null;
  market_value_high_92d: number | null;
  average_points: number | null;
  total_points: number | null;
  fairwert: number | null;
  signal: number | null;
  ml_prediction: number | null;
}


export interface EigenesTeamRow extends PlayerRow {
  sell_signal?: "halten" | "verkaufen";
}

export interface LigaanalyseRow {
  name: string;
  is_self: boolean;
  season_placement: number | null;
  season_points: number | null;
  team_value: number | null;
  estimated_budget: number | null;
  available_budget: number | null;
  squad_size: number | null;
  squad_value: number | null;
  sell_count: number;
  regular_count: number | null;
}

export type MlModelType = "RandomForest" | "HistGradientBoosting";

export interface MlPerModelMetrics {
  rmse: number;
  mae: number;
  r2: number;
  sign_accuracy: number;
}

export interface MlRealizedWindow {
  n: number;
  sign_accuracy: number;
  mae: number;
}

export interface MlMetrics {
  model_type: MlModelType;
  synthetic_winner?: MlModelType;
  selection_reason?: string;
  rmse: number;
  mae: number;
  r2: number;
  sign_accuracy: number;
  train_rows: number;
  test_rows: number;
  per_model: Record<MlModelType, MlPerModelMetrics>;
  realized_by_model?: Record<MlModelType, { realized_7d: MlRealizedWindow | null; realized_30d: MlRealizedWindow | null }>;
}

export interface MlAccuracyTrendEntry {
  date: string;
  RandomForest: number | null;
  HistGradientBoosting: number | null;
}

export interface DashboardSnapshot {
  players: Record<string, PlayerRecord>;
  calibration: Calibration | null;
  transfermarkt_listings: TransfermarktListing[];
  own_squad_ids: string[];
  owned_by: Record<string, string>;
  wunschkader_targets: RawWunschkaderTarget[];
  wunschkader_sell_list: string[] | null;
  wunschkader_formation: string | null;
  ligaanalyse: LigaanalyseRow[];
  ml_metrics: MlMetrics | null;
  ml_accuracy_trend: MlAccuracyTrendEntry[] | null;
  signal_thresholds: SignalThresholds;
  own_budget_exact: number | null;
  own_available_budget: number | null;
  fetched_at: string;
  [key: string]: unknown;
}
