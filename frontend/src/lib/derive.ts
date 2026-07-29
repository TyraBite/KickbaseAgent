import type { Calibration, PlayerRecord } from "../types";

// 1:1 Port von dashboard_export.py::_k_per_point()
export function costPerPoint(marketValue: number | null, averagePoints: number | null): number | null {
  if (!marketValue || !averagePoints) return null;
  return marketValue / averagePoints;
}

// 1:1 Port von player_valuation.py::k_for_position()
export function kForPosition(calibration: Calibration | null, position: string): number | null {
  if (!calibration) return null;
  return calibration.position_k[position]?.k ?? calibration.global_k ?? null;
}

// 1:1 Port von dashboard_export.py::_valuation()
export function valuation(
  marketValue: number | null,
  averagePoints: number | null,
  position: string,
  calibration: Calibration | null
): { fairwert: number | null; signal: number | null } {
  const k = kForPosition(calibration, position);
  if (!k || !marketValue || !averagePoints) return { fairwert: null, signal: null };
  const fairwert = Math.round(k * averagePoints);
  const signal = Math.round((k / (marketValue / averagePoints)) * 100) / 100;
  return { fairwert, signal };
}

export function signalFor(
  marketValue: number | null,
  averagePoints: number | null,
  position: string,
  calibration: Calibration | null
): number | null {
  return valuation(marketValue, averagePoints, position, calibration).signal;
}

// 1:1 Port von kickbase_client.py::STATUS_LABELS, finalisiert 2026-07-29
const STATUS_LABELS: Record<number, string> = { 1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau" };

export function statusLabel(statusCode: number | null): string | null {
  if (statusCode === null || statusCode === 0) return null;
  if (statusCode in STATUS_LABELS) return STATUS_LABELS[statusCode];
  return `Status-Code ${statusCode} (Bedeutung in v4-API nicht zweifelsfrei bestätigt)`;
}

// 1:1 Port von dashboard_export.py::_estimate_price() (schon in WunschkaderTab.tsx
// vorhanden, wandert nur hierher)
export function estimatePrice(marketValue: number | null): number | null {
  if (!marketValue) return null;
  return Math.round(marketValue * 1.1);
}

export function plannedPriceFor(
  target: { actual_bid?: number },
  marketValue: number | null,
  isOwn: boolean
): number | null {
  if (target.actual_bid !== undefined) return target.actual_bid;
  if (isOwn) return 0;
  return estimatePrice(marketValue);
}
