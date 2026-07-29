import { formatDurationMs } from "../format";
import type { Calibration, PlayerRecord, RawWunschkaderTarget, TransfermarktListing } from "../types";

// 1:1 Port von dashboard_export.py::_k_per_point()
export function costPerPoint(marketValue: number | null, averagePoints: number | null): number | null {
  if (!marketValue || !averagePoints) return null;
  return marketValue / averagePoints;
}

// 1:1 Port von player_valuation.py::k_for_position()
export function kForPosition(calibration: Calibration | null, position: string): number | null {
  if (!calibration) return null;
  return calibration.position_k?.[position]?.k ?? calibration.global_k ?? null;
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

// Eingeplanter Preis fuer ein Ziel: 0 wenn schon im eigenen Kader (bereits
// bezahlt, nicht nochmal einplanen), sonst das eigene laufende Hoechstgebot
// falls eins existiert (echte Kickbase-Daten aus dem Transfermarkt-Listing -
// praeziser als jede Schaetzung), sonst der reine Marktwert.
export function plannedPriceFor(marketValue: number | null, isOwn: boolean, liveBid: number | null): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  return marketValue;
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

const HYPE_CHANGE_THRESHOLD = 1_500_000;
const SPEKULATION_FLOOR_PROTECTED = 1_000_000;

export function trendDirection(change7d: number | null | undefined): "flat" | "up" | "down" {
  if (change7d === null || change7d === undefined || change7d === 0) return "flat";
  return change7d > 0 ? "up" : "down";
}

export function isHypeGipfel(p: {
  market_value_change_7d?: number | null;
  market_value: number | null;
  market_value_high_92d?: number | null;
  average_points: number | null;
}): boolean {
  return Boolean(
    p.market_value_change_7d &&
      p.market_value_change_7d > HYPE_CHANGE_THRESHOLD &&
      p.market_value !== null &&
      p.market_value_high_92d === p.market_value &&
      !p.average_points
  );
}

export function isNearFloor(price: number | null): boolean {
  return Boolean(price && price < SPEKULATION_FLOOR_PROTECTED);
}

export function roiPct(mlPrediction: number | null, price: number | null): number | null {
  if (!mlPrediction || mlPrediction <= 0 || !price) return null;
  return Math.round((mlPrediction / price) * 1000) / 10;
}

export function sellSignal(
  playerId: string,
  mlPrediction: number | null | undefined,
  sellListIds: ReadonlySet<string>
): "halten" | "verkaufen" {
  return sellListIds.has(playerId) && (mlPrediction ?? 0) > 0 ? "halten" : "verkaufen";
}

export interface PlayerRow {
  player_id: string; name: string; position: string; team_name: string | null;
  status_label: string | null; starting_rank: number | null;
  market_value: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  average_points: number | null; total_points: number | null;
  fairwert: number | null; signal: number | null; ml_prediction: number | null;
}

export function buildPlayerRow(player: PlayerRecord, calibration: Calibration | null): PlayerRow {
  const { fairwert, signal } = valuation(player.market_value, player.average_points, player.position, calibration);
  return {
    player_id: player.player_id, name: player.name, position: player.position, team_name: player.team_name,
    status_label: statusLabel(player.status_code),
    starting_rank: player.starting_rank, market_value: player.market_value,
    market_value_change_7d: player.market_value_change_7d ?? null,
    market_value_low_92d: player.market_value_low_92d ?? null,
    market_value_high_92d: player.market_value_high_92d ?? null,
    average_points: player.average_points, total_points: player.total_points ?? null,
    fairwert, signal, ml_prediction: player.ml_prediction ?? null,
  };
}

export interface TransfermarktRow extends PlayerRow {
  price: number; price_delta_pct: number | null; offering_username: string | null;
  is_system_offer: boolean; affordable: boolean;
  auction_status: string; auction_remaining_seconds: number; auction_urgent: boolean;
  auction_expires_at: string | null;
}

export function buildTransfermarktRows(
  players: Record<string, PlayerRecord>,
  listings: TransfermarktListing[],
  calibration: Calibration | null,
  ownAvailableBudget: number | null,
  now: Date
): TransfermarktRow[] {
  return listings
    .filter((l) => players[l.player_id])
    .map((l) => {
      const player = players[l.player_id];
      const base = buildPlayerRow(player, calibration);
      const { label, remainingSeconds, urgent } = auctionStatus(l.listed_at, l.expires_at, l.expiry_is_estimate, now);
      return {
        ...base,
        price: l.price, price_delta_pct: l.price_delta_pct, offering_username: l.offering_username,
        is_system_offer: l.is_system_offer,
        affordable: isAffordable(l.price, ownAvailableBudget),
        auction_status: label, auction_remaining_seconds: remainingSeconds, auction_urgent: urgent,
        auction_expires_at: l.expires_at,
      };
    });
}

export interface SpekulationRow {
  player_id: string; name: string; position: string; team_name: string | null; price: number;
  roi_pct: number; average_points: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  ml_prediction: number | null; auction_status: string | null; auction_urgent: boolean;
  auction_remaining_seconds: number | null; auction_expires_at: string | null;
  is_hype_gipfel: boolean; near_floor: boolean;
}

// Nimmt TransfermarktRow[] als Input, NICHT players+listings unabhaengig -
// garantiert identische Auktions-Werte zwischen Transfermarkt- und
// Spekulation-Tab fuer dasselbe Listing (spiegelt Python's
// _build_spekulation(transfermarkt_rows) exakt).
export function buildSpekulationRows(transfermarktRows: TransfermarktRow[]): SpekulationRow[] {
  return transfermarktRows
    .filter((r) => r.is_system_offer && roiPct(r.ml_prediction, r.price) !== null)
    .map((r) => ({
      player_id: r.player_id, name: r.name, position: r.position, team_name: r.team_name, price: r.price,
      roi_pct: roiPct(r.ml_prediction, r.price)!,
      average_points: r.average_points, market_value_change_7d: r.market_value_change_7d,
      ml_prediction: r.ml_prediction,
      is_hype_gipfel: isHypeGipfel(r), near_floor: isNearFloor(r.price),
      auction_status: r.auction_status, auction_remaining_seconds: r.auction_remaining_seconds,
      auction_urgent: r.auction_urgent, auction_expires_at: r.auction_expires_at,
      market_value_low_92d: r.market_value_low_92d, market_value_high_92d: r.market_value_high_92d,
    }))
    .sort((a, b) => b.roi_pct - a.roi_pct);
}

export interface EigenesTeamRow extends PlayerRow { sell_signal?: "halten" | "verkaufen" }
export interface EigenesTeamSplit { verkaufen: EigenesTeamRow[]; bleibt: EigenesTeamRow[] }

export function buildEigenesTeamSplit(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  targets: RawWunschkaderTarget[],
  sellListIds: string[],
  calibration: Calibration | null
): EigenesTeamSplit {
  const targetIds = new Set(targets.map((t) => t.player_id));
  const sellSet = new Set(sellListIds);
  const verkaufen: EigenesTeamRow[] = [];
  const bleibt: EigenesTeamRow[] = [];
  for (const pid of ownSquadIds) {
    const player = players[pid];
    if (!player) continue;
    const row = buildPlayerRow(player, calibration);
    if (targetIds.has(pid)) {
      bleibt.push(row);
    } else {
      verkaufen.push({ ...row, sell_signal: sellSignal(pid, player.ml_prediction, sellSet) });
    }
  }
  return { verkaufen, bleibt };
}

export function ownerFor(
  playerId: string, ownSquadIds: ReadonlySet<string>, ownedBy: Record<string, string>
): string {
  if (ownSquadIds.has(playerId)) return "Eigener Kader";
  return ownedBy[playerId] ?? "Frei";
}

export interface AlleSpielerRow extends PlayerRow { owner: string }

export function buildAlleSpielerRows(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  ownedBy: Record<string, string>,
  calibration: Calibration | null
): AlleSpielerRow[] {
  const ownSet = new Set(ownSquadIds);
  return Object.values(players).map((p) => ({
    ...buildPlayerRow(p, calibration),
    owner: ownerFor(p.player_id, ownSet, ownedBy),
  }));
}

export interface BudgetPlanSellRow { player_id: string; market_value: number | null }
export interface BudgetPlan {
  cash: number; sell_rows: BudgetPlanSellRow[]; sell_proceeds: number;
  pool: number; committed: number; remaining: number;
}

// Eigenes laufendes Hoechstgebot fuer einen Spieler, falls er aktuell auf dem
// Transfermarkt steht UND wir dort selbst fuehren (is_own_leading_bid) - sonst
// null (dann greift in plannedPriceFor() der Marktwert-Fallback). Einzige
// Quelle fuer diese Ableitung im ganzen Frontend (Review-Fund 2026-07-29:
// buildBudgetPlan() und WunschkaderTab.tsx's DetailModal-Preisanzeige hatten
// denselben Ausdruck byte-identisch dupliziert - genau das Divergenz-Risiko,
// das diese ganze players-Map-Umstellung vermeiden soll).
export function liveBidFor(playerId: string, listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>): number | null {
  const listing = listingsByPlayerId.get(playerId);
  return listing?.is_own_leading_bid && listing.leading_bid_price != null ? listing.leading_bid_price : null;
}

export function buildBudgetPlan(params: {
  players: Record<string, PlayerRecord>;
  ownSquadIds: Set<string>;
  targets: RawWunschkaderTarget[];
  ownBudgetExact: number | null;
  listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>;
}): BudgetPlan {
  const { players, ownSquadIds, targets, ownBudgetExact, listingsByPlayerId } = params;
  // Verkaufserloese: nicht aus einer separaten, manuell gepflegten Liste
  // (Bug, gefunden 2026-07-29, siehe WunschkaderTab.tsx), sondern automatisch
  // aus dem eigenen Kader abgeleitet - jeder Spieler im eigenen Kader, der
  // NICHT (mehr) unter den aktuellen Wunschkader-Zielen steht, ist ein
  // Verkaufskandidat.
  const targetPlayerIds = new Set(targets.map((t) => t.player_id));
  const sellRows: BudgetPlanSellRow[] = [...ownSquadIds]
    .filter((pid) => !targetPlayerIds.has(pid) && players[pid])
    .map((pid) => ({ player_id: pid, market_value: players[pid].market_value }));
  const sellProceeds = sellRows.reduce((sum, r) => sum + (r.market_value || 0), 0);
  const cash = ownBudgetExact || 0;
  const pool = cash + sellProceeds;
  const committed = targets.reduce((sum, t) => {
    if (t.role === "Bank/Backup-Option") return sum;
    const isOwn = ownSquadIds.has(t.player_id);
    if (isOwn) return sum;
    const marketValue = players[t.player_id]?.market_value ?? null;
    const liveBid = liveBidFor(t.player_id, listingsByPlayerId);
    return sum + (plannedPriceFor(marketValue, isOwn, liveBid) || 0);
  }, 0);
  return { cash, sell_rows: sellRows, sell_proceeds: sellProceeds, pool, committed, remaining: pool - committed };
}
