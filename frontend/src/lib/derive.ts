import { formatDurationMs } from "../format";
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

// 1:1 Port von dashboard_export.py::_parse_iso_z() - strikte Validierung des exakten
// Formats "%Y-%m-%dT%H:%M:%SZ" (kein new Date(str), das parst Z-lose Strings permissiv
// als Browser-Lokalzeit statt UTC und Bruchteile/Offsets, die Python ablehnen wuerde).
function parseIsoZ(raw: string | null): Date | null {
  if (!raw) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/.exec(raw);
  if (!m) return null;
  const [year, month, day, hour, minute, second] = m.slice(1).map(Number);
  const ts = Date.UTC(year, month - 1, day, hour, minute, second);
  const d = new Date(ts);
  // Date.UTC rollt ungueltige Felder (z.B. Monat 13, Tag 32) einfach in den naechsten
  // Zeitraum - Rueckvergleich der Felder faengt das ab, analog zu strptime()'s ValueError.
  if (
    d.getUTCFullYear() !== year ||
    d.getUTCMonth() !== month - 1 ||
    d.getUTCDate() !== day ||
    d.getUTCHours() !== hour ||
    d.getUTCMinutes() !== minute ||
    d.getUTCSeconds() !== second
  ) {
    return null;
  }
  return d;
}

// 1:1 Port von dashboard_export.py::_next_update_cutoff() - DST-sicher: der UTC-Offset
// wird zweistufig aufgeloest (erst an `now`, dann am so ermittelten Ziel-Zeitpunkt neu),
// weil an den zwei jaehrlichen Umstellungstagen der Offset von `now` vom Offset des
// Cutoffs (22 Uhr desselben Tages) abweichen kann - einmaliges Aufloesen an `now` allein
// reicht dann nicht (siehe Task-12-Review: bis zu 1h falsch in einem ca. 9h/Jahr-Fenster).
export function nextUpdateCutoff(now: Date): Date {
  const p = berlinParts(now);
  const localNowAsUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  let cutoffLocalAsUtc = Date.UTC(p.year, p.month - 1, p.day, NEXT_MARKET_VALUE_UPDATE_HOUR, 0, 0, 0);
  if (localNowAsUtc >= cutoffLocalAsUtc) cutoffLocalAsUtc += 24 * 3600 * 1000;

  const offsetAt = (d: Date) => {
    const parts = berlinParts(d);
    const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
    return asUtc - d.getTime();
  };
  let cutoff = new Date(cutoffLocalAsUtc - offsetAt(now));
  cutoff = new Date(cutoffLocalAsUtc - offsetAt(cutoff)); // Offset am Ziel-Zeitpunkt neu aufloesen
  return cutoff;
}

// 1:1 Port von dashboard_export.py::_auction_status()
export function auctionLabelAndRemaining(
  listedAt: string | null,
  expiresAt: string | null,
  expiryIsEstimate: boolean,
  now: Date
): { label: string; remainingSeconds: number } {
  if (!expiresAt) {
    const listed = parseIsoZ(listedAt);
    if (listed === null) {
      return { label: "unbekannt", remainingSeconds: NO_EXPIRY_SENTINEL_SECONDS };
    }
    const ageMs = now.getTime() - listed.getTime();
    return {
      label: `kein Zeitlimit ermittelbar (gelistet seit ${formatDurationMs(ageMs)})`,
      remainingSeconds: NO_EXPIRY_SENTINEL_SECONDS,
    };
  }
  const expires = parseIsoZ(expiresAt);
  if (expires === null) {
    return { label: "unbekannt", remainingSeconds: NO_EXPIRY_SENTINEL_SECONDS };
  }
  const remainingMs = expires.getTime() - now.getTime();
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
