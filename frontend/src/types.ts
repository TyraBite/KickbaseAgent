export interface PositionCalibrationEntry {
  k: number | null;
  n: number;
}

export interface Calibration {
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
  // Nur vorhanden fuer Spieler im eigenen Kader (own_squad) - Kickbase-Feld
  // "mvgl" (Market-Value-Gain/Loss seit Kauf), mv-mvgl = echter Kaufpreis.
  purchase_price?: number;
  // Nur vorhanden, wenn das ML-Modell einen Wert produziert hat:
  ml_prediction?: number;
  // Nur vorhanden, wenn das 3-Tage-Modell einen Wert produziert hat:
  ml_prediction_3d?: number;
}

export interface TransfermarktListing {
  player_id: string;
  price: number;
  price_delta_pct: number | null;
  offering_username: string | null;
  is_system_offer: boolean;
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
  squad_player_ids: string[];
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

export interface BidPremiumEntry {
  player_id: string;
  position: string;
  market_value_then: number;
  average_points_then: number | null;
  premium_pct: number;
  purchased_at: string;
  // Fehlt auf Eintraegen von vor diesem Feature - siehe Global Constraints
  // im Plan, immer mit `?? false`/truthy-Check lesen, nie als Pflichtfeld.
  bought_by_self?: boolean;
}

export interface BidPremiumOutcomeCountsEntry {
  rival_purchases: number;
  self_purchases: number;
  unsold: number;
}

export type BidPremiumOutcomeCounts = Record<string, BidPremiumOutcomeCountsEntry>;

export interface PositionNeedEntry {
  avg_coverage: number;
  n_rivals: number;
}

export type PositionNeed = Record<string, PositionNeedEntry>;

export interface FeedbackItem {
  id: string;
  type: "bug" | "feature";
  text: string;
  created_at: string; // ISO-Timestamp, new Date().toISOString()
  status: "open" | "done";
}

export interface DashboardSnapshot {
  fetched_at: string;
  generated_at: string;
  players: Record<string, PlayerRecord>;
  calibration: Calibration | null;
  transfermarkt_listings: TransfermarktListing[];
  own_squad_ids: string[];
  owned_by: Record<string, string>;
  wunschkader_targets: RawWunschkaderTarget[];
  ligaanalyse: LigaanalyseRow[];
  ml_metrics: MlMetrics | null;
  ml_accuracy_trend: MlAccuracyTrendEntry[] | null;
  signal_thresholds: SignalThresholds;
  own_budget_exact: number | null;
  own_available_budget: number | null;
  // Optional: Frontend-Deploys koennen live sein, bevor das Backend diese
  // Felder je geschrieben hat (echter Vorfall, siehe HANDOFF.md) - jeder
  // Verbraucher MUSS mit ?? []/?? {} lesen. Als "required" typisiert wuerde
  // der Compiler diese Guards als totes Codeschema behandeln und ein
  // kuenftiger Edit koennte einen davon entfernen, ohne dass tsc das merkt.
  bid_premium_history?: BidPremiumEntry[];
  bid_premium_outcome_counts?: BidPremiumOutcomeCounts;
  position_need?: PositionNeed;
  ml_metrics_3d?: MlMetrics | null;
  ml_accuracy_trend_3d?: MlAccuracyTrendEntry[] | null;
  [key: string]: unknown;
}
