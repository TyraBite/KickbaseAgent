import { formatDurationMs } from "../format";
import type { Calibration, PlayerRecord, TransfermarktListing } from "../types";

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

const NEXT_MARKET_VALUE_UPDATE_HOUR = 22;
const NO_EXPIRY_SENTINEL_SECONDS = 9_999_999;

function berlinParts(date: Date) {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Berlin", hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const map: Record<string, number> = {};
  for (const p of dtf.formatToParts(date)) if (p.type !== "literal") map[p.type] = Number(p.value);
  return map as { year: number; month: number; day: number; hour: number; minute: number; second: number };
}

// 1:1 Port von dashboard_export.py::_next_update_cutoff() - DST-sicher ueber
// Intl.DateTimeFormat statt hartkodiertem UTC-Offset.
export function nextUpdateCutoff(now: Date): Date {
  const p = berlinParts(now);
  const localNowAsUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  let cutoffLocalAsUtc = Date.UTC(p.year, p.month - 1, p.day, NEXT_MARKET_VALUE_UPDATE_HOUR, 0, 0, 0);
  if (localNowAsUtc >= cutoffLocalAsUtc) cutoffLocalAsUtc += 24 * 3600 * 1000;
  const offsetMinutes = Math.round((localNowAsUtc - now.getTime()) / 60000);
  return new Date(cutoffLocalAsUtc - offsetMinutes * 60000);
}

// 1:1 Port von dashboard_export.py::_auction_status()
export function auctionLabelAndRemaining(
  listedAt: string | null,
  expiresAt: string | null,
  expiryIsEstimate: boolean,
  now: Date
): { label: string; remainingSeconds: number } {
  if (!expiresAt) {
    return { label: "kein Zeitlimit", remainingSeconds: NO_EXPIRY_SENTINEL_SECONDS };
  }
  const remainingMs = new Date(expiresAt).getTime() - now.getTime();
  const remainingSeconds = Math.max(Math.round(remainingMs / 1000), 0);
  if (remainingSeconds <= 0) return { label: "Frist abgelaufen", remainingSeconds: 0 };
  const suffix = expiryIsEstimate ? " (geschätzt)" : "";
  return { label: `läuft ab in ${formatDurationMs(remainingMs)}${suffix}`, remainingSeconds };
}

export interface AuctionStatus { label: string; remainingSeconds: number; urgent: boolean }

export function auctionStatus(
  listedAt: string | null,
  expiresAt: string | null,
  expiryIsEstimate: boolean,
  now: Date
): AuctionStatus {
  const { label, remainingSeconds } = auctionLabelAndRemaining(listedAt, expiresAt, expiryIsEstimate, now);
  const cutoffSeconds = (nextUpdateCutoff(now).getTime() - now.getTime()) / 1000;
  const urgent = remainingSeconds > 0 && remainingSeconds < cutoffSeconds;
  return { label, remainingSeconds, urgent };
}

export function isAffordable(price: number | null, ownAvailableBudget: number | null): boolean {
  return ownAvailableBudget !== null && price !== null && price <= ownAvailableBudget;
}
