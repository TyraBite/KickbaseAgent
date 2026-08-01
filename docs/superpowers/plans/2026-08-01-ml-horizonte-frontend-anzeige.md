# ML-Horizonte im Frontend sichtbar machen (Prognose 1T/3T) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die qualitative "Einschätzung"-Zeile (`momentumAssessment()`, derive.ts) überall durch zwei rohe Zahlen ersetzen — "Prognose 1T" (umbenannt von "ML-Prognose") und neu "Prognose 3T" (+ MAE falls vorhanden) — in allen 4 Detail-Modals, den Kartenfronten wo heute schon 1T sichtbar ist, einer neuen Transfermarkt-Tabellenspalte, und einem zweiten Kopf-an-Kopf-Block im Modell-Tracking-Tab.

**Architecture:** `PlayerRow` (derive.ts) bekommt `ml_prediction_3d` als Feld, damit alle 4 Tab-Zeilentypen es automatisch mitführen. `momentumAssessment()` wird komplett gelöscht (nach dem Umbau aller 4 Aufrufstellen ungenutzt). Modell-Tracking extrahiert seinen bestehenden Kopf-an-Kopf-Block + Trend-Chart-Wrapper in parametrisierte Komponenten, die für 1T und 3T zweimal gerendert werden.

**Tech Stack:** React + TypeScript (Vite), kein Test-Framework im Frontend (kein Jest/Vitest) — Verifikation ausschließlich über `tsc --noEmit` + manuelle Live-Prüfung im Browser, wie bei jeder bisherigen Frontend-Änderung dieses Repos.

## Global Constraints

- **Kein `npm install` im Haupt-Checkout** (Windows-DrvFs-Mount, geteilte `node_modules` mit der Windows-Seite — ein `npm install` hier würde Unix-Bin-Shims statt `.cmd`-Dateien erzeugen und `npm run` auf der Windows/Rider-Seite brechen). `node_modules` existiert bereits, `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` ist der einzige nötige/zulässige Verifikationsbefehl.
- **Kein Test-Framework im Frontend** — es gibt keine `.test.ts(x)`-Dateien und kein Jest/Vitest-Setup. TDD im klassischen Rot-Grün-Sinn ist hier nicht anwendbar; jeder Task verifiziert stattdessen per `tsc --noEmit` (Fehleranzahl/-ort explizit genannt) und der letzte Task zusätzlich per manueller Browser-Prüfung.
- **Backend-Tests unberührt, aber vor jedem Commit laufen lassen**: `python3 -m unittest discover -s tests` (Standard-Vorgehen dieses Repos vor jedem Push, auch wenn dieses Vorhaben rein Frontend ist).
- **Push auf `main` ist erlaubt, aber NUR wenn direkt vorher alle Tests grün sind** (Backend-Suite + `tsc --noEmit`) — kein Feature-Branch/PR-Umweg, siehe `HANDOFF.md`/Warnings.
- **Reine Zahl ohne Trend-Pfeil für Prognose 3T** — `trendArrow`/`trendClass` werden für den 3T-Wert NICHT verwendet (nur `fmtSigned`), da die bestehenden `ML_PREDICTION_THRESHOLDS` aus der 1-Tages-Verteilung kalibriert sind und für 3T noch keine eigene Kalibrierung existiert (folgt separat, siehe Spec).
- **`momentumAssessment()`/`MomentumAssessment`/`MomentumConfidence` werden komplett gelöscht**, nicht nur ungenutzt liegen gelassen — nach Task 1–5 gibt es keinen einzigen Aufrufer mehr.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/lib/derive.ts` | `PlayerRow`/`SpekulationRow` um `ml_prediction_3d` erweitert, `momentumAssessment()`+Typen gelöscht |
| `frontend/src/components/EigenesTeamTab.tsx` | `MlPredictionRow` zeigt 1T+3T, in Karten UND beiden Detail-Modals |
| `frontend/src/components/TransfermarktTab.tsx` | Neue Tabellenspalte "Prognose 3T", Modal-Zeile ergänzt |
| `frontend/src/components/SpekulationTab.tsx` | Karte+Tabelle+Modal bekommen "Prognose 3T", `players`-Prop entfällt (Row trägt 3T jetzt selbst) |
| `frontend/src/App.tsx` | `SpekulationTab`-Aufruf: `players`-Prop durch `mlMetrics3d`-Prop ersetzt |
| `frontend/src/components/WunschkaderTab.tsx` | Detail-Modal bekommt neu "Prognose 1T"/"Prognose 3T"-Zeilen (gab's vorher gar nicht) |
| `frontend/src/components/MlGenauigkeitTab.tsx` | Kopf-an-Kopf-Block + Trend-Chart-Überschrift in parametrisierte Komponenten extrahiert, je zweimal gerendert (1T/3T) |

---

## Task 1: derive.ts — Datenmodell + Cleanup

**Files:**
- Modify: `frontend/src/lib/derive.ts:1-527`

**Interfaces:**
- Consumes: nichts Neues (nur bestehende `PlayerRecord.ml_prediction_3d`, bereits in `types.ts` vorhanden).
- Produces: `PlayerRow.ml_prediction_3d: number | null`, `SpekulationRow.ml_prediction_3d: number | null`. Entfernt: `momentumAssessment()`, `MomentumAssessment`, `MomentumConfidence` (keine anderen Dateien dürfen diese danach noch importieren — wird in Task 2–5 behoben).

- [ ] **Step 1: `momentumAssessment()` + Typen löschen**

In `frontend/src/lib/derive.ts`, den kompletten Block von `export type MomentumConfidence = ...` bis zum Ende der `momentumAssessment()`-Funktion entfernen:

Alt (löschen):
```typescript
export type MomentumConfidence = "sicher" | "wahrscheinlich" | "unsicher";

export interface MomentumAssessment {
  confidence: MomentumConfidence;
  direction: "steigend" | "fallend";
  agreesWith3d: boolean | null;
  label: string;
}

// Reine Ableitung aus bereits vorhandenen Zahlen (1-Tages-Prognose, primaer;
// 3-Tages-Prognose als Relativierer; MAE des 1-Tages-Modells als
// Unsicherheits-Mass) - kein neues Training noetig. Konfidenz-Schwellen
// beziehen sich bewusst NUR auf die 1-Tages-Prognose (der primaere
// Indikator), die 3-Tages-Prognose beeinflusst nur den Text, nicht die
// Konfidenz-Stufe selbst.
export function momentumAssessment(
  prediction1d: number | null,
  prediction3d: number | null,
  mae: number | null
): MomentumAssessment | null {
  if (prediction1d === null) return null;

  const direction: "steigend" | "fallend" = prediction1d > 0 ? "steigend" : "fallend";
  let confidence: MomentumConfidence;
  if (mae === null) {
    confidence = "wahrscheinlich";
  } else if (Math.abs(prediction1d) > 2 * mae) {
    confidence = "sicher";
  } else if (Math.abs(prediction1d) > mae) {
    confidence = "wahrscheinlich";
  } else {
    // Schwelle identisch zu sellSignal()s "unklar"-Trigger - bewusst, siehe dort
    confidence = "unsicher";
  }

  const confidenceLabel = confidence.charAt(0).toUpperCase() + confidence.slice(1);
  let label = `${confidenceLabel} ${direction} (${fmtSigned(prediction1d)}`;
  label += mae !== null ? `, Modell-Ungenauigkeit ±${fmtNum(mae)})` : ")";

  let agreesWith3d: boolean | null = null;
  if (prediction3d !== null) {
    agreesWith3d = Math.sign(prediction3d) === Math.sign(prediction1d) || prediction3d === 0;
    if (agreesWith3d) {
      label += ` — 3-Tage-Trend bestätigt (${fmtSigned(prediction3d)})`;
    } else {
      const dir3d = prediction3d > 0 ? "steigend" : "fallend";
      label += ` — 3-Tage-Trend zeigt aber ${dir3d} (${fmtSigned(prediction3d)}), evtl. nur kurzfristiges Rauschen`;
    }
  }

  return { confidence, direction, agreesWith3d, label };
}

```

Ersatzlos entfernen (nichts Neues an dieser Stelle einfügen — `liveModelMae()` direkt davor und der `kForPosition()`-Kommentar direkt danach bleiben unverändert, nur eine Leerzeile dazwischen).

- [ ] **Step 2: `PlayerRow` um `ml_prediction_3d` erweitern**

Alt:
```typescript
export interface PlayerRow {
  player_id: string; name: string; position: string; team_name: string | null;
  status_label: string | null; starting_rank: number | null;
  market_value: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  average_points: number | null;
  fairwert: number | null; signal: number | null; ml_prediction: number | null;
}
```

Neu:
```typescript
export interface PlayerRow {
  player_id: string; name: string; position: string; team_name: string | null;
  status_label: string | null; starting_rank: number | null;
  market_value: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  average_points: number | null;
  fairwert: number | null; signal: number | null;
  ml_prediction: number | null; ml_prediction_3d: number | null;
}
```

- [ ] **Step 3: `buildPlayerRow()` füllt das neue Feld**

Alt:
```typescript
export function buildPlayerRow(player: PlayerRecord, calibration: Calibration | null): PlayerRow {
  const { fairwert, signal } = valuation(player.market_value, player.average_points, player.position, calibration);
  return {
    player_id: player.player_id, name: player.name, position: player.position, team_name: player.team_name,
    status_label: statusLabel(player.status_code),
    starting_rank: player.starting_rank, market_value: player.market_value,
    market_value_change_7d: player.market_value_change_7d ?? null,
    market_value_low_92d: player.market_value_low_92d ?? null,
    market_value_high_92d: player.market_value_high_92d ?? null,
    average_points: player.average_points,
    fairwert, signal, ml_prediction: player.ml_prediction ?? null,
  };
}
```

Neu:
```typescript
export function buildPlayerRow(player: PlayerRecord, calibration: Calibration | null): PlayerRow {
  const { fairwert, signal } = valuation(player.market_value, player.average_points, player.position, calibration);
  return {
    player_id: player.player_id, name: player.name, position: player.position, team_name: player.team_name,
    status_label: statusLabel(player.status_code),
    starting_rank: player.starting_rank, market_value: player.market_value,
    market_value_change_7d: player.market_value_change_7d ?? null,
    market_value_low_92d: player.market_value_low_92d ?? null,
    market_value_high_92d: player.market_value_high_92d ?? null,
    average_points: player.average_points,
    fairwert, signal,
    ml_prediction: player.ml_prediction ?? null,
    ml_prediction_3d: player.ml_prediction_3d ?? null,
  };
}
```

- [ ] **Step 4: `sellSignal()`s Kommentar korrigieren (verweist sonst auf gelöschte Funktion)**

Alt:
```typescript
export function sellSignal(
  mlPrediction: number | null | undefined,
  mae: number | null
): "halten" | "verkaufen" | "unklar" {
  const pred = mlPrediction ?? 0;
  // Schwelle identisch zu momentumAssessment()s "unsicher"-Stufe - bewusst, siehe dort
  if (mae !== null && Math.abs(pred) <= mae) return "unklar";
  return pred > 0 ? "halten" : "verkaufen";
}
```

Neu:
```typescript
export function sellSignal(
  mlPrediction: number | null | undefined,
  mae: number | null
): "halten" | "verkaufen" | "unklar" {
  const pred = mlPrediction ?? 0;
  // "unklar", wenn die Prognose betragsmaessig innerhalb der Modell-Ungenauigkeit
  // (MAE) liegt - dann ist die Richtung nicht verlaesslich genug fuer eine klare
  // Kauf/Verkauf-Aussage.
  if (mae !== null && Math.abs(pred) <= mae) return "unklar";
  return pred > 0 ? "halten" : "verkaufen";
}
```

- [ ] **Step 5: `SpekulationRow` um `ml_prediction_3d` erweitern**

Alt:
```typescript
export interface SpekulationRow {
  player_id: string; name: string; position: string; team_name: string | null; price: number;
  market_value: number | null;
  roi_pct: number; average_points: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  ml_prediction: number | null; auction_status: string | null; auction_urgent: boolean; auction_critical: boolean;
  auction_remaining_seconds: number | null; auction_expires_at: string | null;
}
```

Neu:
```typescript
export interface SpekulationRow {
  player_id: string; name: string; position: string; team_name: string | null; price: number;
  market_value: number | null;
  roi_pct: number; average_points: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  ml_prediction: number | null; ml_prediction_3d: number | null;
  auction_status: string | null; auction_urgent: boolean; auction_critical: boolean;
  auction_remaining_seconds: number | null; auction_expires_at: string | null;
}
```

- [ ] **Step 6: `buildSpekulationRows()` füllt das neue Feld**

Alt:
```typescript
export function buildSpekulationRows(transfermarktRows: TransfermarktRow[]): SpekulationRow[] {
  return transfermarktRows
    .filter((r) => r.is_system_offer && roiPct(r.ml_prediction, r.price) !== null)
    .map((r) => ({
      player_id: r.player_id, name: r.name, position: r.position, team_name: r.team_name, price: r.price,
      market_value: r.market_value,
      roi_pct: roiPct(r.ml_prediction, r.price)!,
      average_points: r.average_points, market_value_change_7d: r.market_value_change_7d,
      ml_prediction: r.ml_prediction,
      auction_status: r.auction_status, auction_remaining_seconds: r.auction_remaining_seconds,
      auction_urgent: r.auction_urgent, auction_critical: r.auction_critical, auction_expires_at: r.auction_expires_at,
      market_value_low_92d: r.market_value_low_92d, market_value_high_92d: r.market_value_high_92d,
    }))
    .sort((a, b) => b.roi_pct - a.roi_pct);
}
```

Neu:
```typescript
export function buildSpekulationRows(transfermarktRows: TransfermarktRow[]): SpekulationRow[] {
  return transfermarktRows
    .filter((r) => r.is_system_offer && roiPct(r.ml_prediction, r.price) !== null)
    .map((r) => ({
      player_id: r.player_id, name: r.name, position: r.position, team_name: r.team_name, price: r.price,
      market_value: r.market_value,
      roi_pct: roiPct(r.ml_prediction, r.price)!,
      average_points: r.average_points, market_value_change_7d: r.market_value_change_7d,
      ml_prediction: r.ml_prediction, ml_prediction_3d: r.ml_prediction_3d,
      auction_status: r.auction_status, auction_remaining_seconds: r.auction_remaining_seconds,
      auction_urgent: r.auction_urgent, auction_critical: r.auction_critical, auction_expires_at: r.auction_expires_at,
      market_value_low_92d: r.market_value_low_92d, market_value_high_92d: r.market_value_high_92d,
    }))
    .sort((a, b) => b.roi_pct - a.roi_pct);
}
```

- [ ] **Step 7: `tsc` laufen lassen — Fehler in ANDEREN Dateien sind hier erwartet**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` (aus `frontend/`, oder mit `-p frontend/tsconfig.json` aus dem Repo-Root)

Expected: Fehler der Form `Module '"../lib/derive"' has no exported member 'momentumAssessment'.` in genau diesen 4 Dateien: `EigenesTeamTab.tsx`, `TransfermarktTab.tsx`, `SpekulationTab.tsx`, `WunschkaderTab.tsx`. **Das ist erwartet** — behoben in Task 2–5. `derive.ts` selbst darf KEINEN Fehler zeigen (falls doch: Copy-Paste-Fehler in einem der Steps oben prüfen).

- [ ] **Step 8: Commit**

```bash
cd /workspace/work
python3 -m unittest discover -s tests
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: PlayerRow/SpekulationRow um ml_prediction_3d erweitert, momentumAssessment() geloescht (Grundlage fuer Prognose-1T/3T-Anzeige)"
```

---

## Task 2: EigenesTeamTab.tsx

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Consumes: `PlayerRow.ml_prediction_3d` (Task 1, über `EigenesTeamRow extends PlayerRow`), `liveModelMae()` (unverändert, aus derive.ts).
- Produces: nichts, das andere Tasks brauchen (eigenständiger Tab).

- [ ] **Step 1: Import bereinigen**

Alt: `import { buildEigenesTeamSplit, liveModelMae, momentumAssessment, type EigenesTeamRow } from "../lib/derive";`

Neu: `import { buildEigenesTeamSplit, liveModelMae, type EigenesTeamRow } from "../lib/derive";`

- [ ] **Step 2: `WatchlistRow`-Typ um `ml_prediction_3d` erweitern**

Alt: `type WatchlistRow = ResolvedTarget & { ml_prediction: number | null };`

Neu: `type WatchlistRow = ResolvedTarget & { ml_prediction: number | null; ml_prediction_3d: number | null };`

- [ ] **Step 3: `mae3d` berechnen**

Alt:
```typescript
export default function EigenesTeamTab({ data }: { data: DashboardSnapshot }) {
  const liveMae = liveModelMae(data.ml_metrics);
```

Neu:
```typescript
export default function EigenesTeamTab({ data }: { data: DashboardSnapshot }) {
  const liveMae = liveModelMae(data.ml_metrics);
  const liveMae3d = liveModelMae(data.ml_metrics_3d ?? null);
```

- [ ] **Step 4: `watchlist`-Mapping um `ml_prediction_3d` erweitern**

Alt:
```typescript
  const watchlist: WatchlistRow[] = useMemo(
    () =>
      data.wunschkader_targets
        .filter((t) => !ownSquadIdSet.has(t.player_id))
        .map((t) => ({
          ...resolveTarget(t.player_id, data.players, ownSquadIdSet, listingsByPlayerId, data.owned_by, data.calibration),
          ml_prediction: data.players[t.player_id]?.ml_prediction ?? null,
        })),
    [data.wunschkader_targets, ownSquadIdSet, data.players, listingsByPlayerId, data.owned_by, data.calibration]
  );
```

Neu:
```typescript
  const watchlist: WatchlistRow[] = useMemo(
    () =>
      data.wunschkader_targets
        .filter((t) => !ownSquadIdSet.has(t.player_id))
        .map((t) => ({
          ...resolveTarget(t.player_id, data.players, ownSquadIdSet, listingsByPlayerId, data.owned_by, data.calibration),
          ml_prediction: data.players[t.player_id]?.ml_prediction ?? null,
          ml_prediction_3d: data.players[t.player_id]?.ml_prediction_3d ?? null,
        })),
    [data.wunschkader_targets, ownSquadIdSet, data.players, listingsByPlayerId, data.owned_by, data.calibration]
  );
```

- [ ] **Step 5: `mae3d` an beide Detail-Modals durchreichen**

Alt:
```typescript
      {selected?.kind === "player" && (
        <PlayerDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
      {selected?.kind === "watchlist" && (
        <WatchlistDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
```

Neu:
```typescript
      {selected?.kind === "player" && (
        <PlayerDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          mae3d={liveMae3d}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
      {selected?.kind === "watchlist" && (
        <WatchlistDetailModal
          row={selected.row}
          thresholds={thresholds}
          mae={liveMae}
          mae3d={liveMae3d}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
```

- [ ] **Step 6: `MlPredictionRow` auf 1T+3T erweitern**

Alt:
```typescript
function MlPredictionRow({ value, mae }: { value: number | null; mae?: number | null }) {
  return (
    <Row label="ML-Prognose">
      <span className={trendClass(value)}>
        {trendArrow(value, ML_PREDICTION_THRESHOLDS)} {fmtSigned(value)}
      </span>
      {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
    </Row>
  );
}
```

Neu:
```typescript
function MlPredictionRow({
  value1d,
  mae1d,
  value3d,
  mae3d,
}: {
  value1d: number | null;
  mae1d?: number | null;
  value3d: number | null;
  mae3d?: number | null;
}) {
  return (
    <>
      <Row label="Prognose 1T">
        <span className={trendClass(value1d)}>
          {trendArrow(value1d, ML_PREDICTION_THRESHOLDS)} {fmtSigned(value1d)}
        </span>
        {mae1d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae1d)})</span>}
      </Row>
      <Row label="Prognose 3T">
        {fmtSigned(value3d)}
        {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
      </Row>
    </>
  );
}
```

- [ ] **Step 7: `PlayerCard`-Aufruf anpassen**

Alt: `      <MlPredictionRow value={row.ml_prediction} />` (innerhalb von `PlayerCard`)

Neu: `      <MlPredictionRow value1d={row.ml_prediction} value3d={row.ml_prediction_3d} />`

- [ ] **Step 8: `WunschkaderWatchlistCard`-Aufruf anpassen**

Alt: `      <MlPredictionRow value={row.ml_prediction} />` (innerhalb von `WunschkaderWatchlistCard`)

Neu: `      <MlPredictionRow value1d={row.ml_prediction} value3d={row.ml_prediction_3d} />`

- [ ] **Step 9: `PlayerDetailModal` — Signatur + Body**

Alt (Signatur):
```typescript
function PlayerDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: EigenesTeamRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
```

Neu (Signatur):
```typescript
function PlayerDetailModal({
  row,
  thresholds,
  mae,
  mae3d,
  players,
  calibration,
  onClose,
}: {
  row: EigenesTeamRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  mae3d: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
```

Alt (Body, innerhalb von `PlayerDetailModal`):
```typescript
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        {(() => {
          const assessment = momentumAssessment(row.ml_prediction, players[row.player_id]?.ml_prediction_3d ?? null, mae);
          return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
        })()}
        <Row label="Trend 7T">
```

Neu:
```typescript
        <MlPredictionRow value1d={row.ml_prediction} mae1d={mae} value3d={row.ml_prediction_3d} mae3d={mae3d} />
        <Row label="Trend 7T">
```

- [ ] **Step 10: `WatchlistDetailModal` — Signatur + Body**

Alt (Signatur):
```typescript
function WatchlistDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: WatchlistRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
```

Neu (Signatur):
```typescript
function WatchlistDetailModal({
  row,
  thresholds,
  mae,
  mae3d,
  players,
  calibration,
  onClose,
}: {
  row: WatchlistRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  mae3d: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
```

Alt (Body, innerhalb von `WatchlistDetailModal`):
```typescript
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        {(() => {
          const assessment = momentumAssessment(row.ml_prediction, players[row.player_id]?.ml_prediction_3d ?? null, mae);
          return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
        })()}
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
```

Neu:
```typescript
        <MlPredictionRow value1d={row.ml_prediction} mae1d={mae} value3d={row.ml_prediction_3d} mae3d={mae3d} />
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
```

- [ ] **Step 11: `tsc` — diese Datei muss jetzt 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: keine Fehler mehr in `EigenesTeamTab.tsx`. Fehler in `TransfermarktTab.tsx`/`SpekulationTab.tsx`/`WunschkaderTab.tsx` (aus Task 1) sind an diesem Punkt noch normal — werden in Task 3–5 behoben.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/components/EigenesTeamTab.tsx
git commit -m "EigenesTeamTab: Prognose 1T/3T statt Einschaetzung (Karten + beide Detail-Modals)"
```

---

## Task 3: TransfermarktTab.tsx

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Consumes: `TransfermarktRow.ml_prediction_3d` (Task 1, via `PlayerRow`-Vererbung).
- Produces: nichts, das andere Tasks brauchen.

- [ ] **Step 1: Imports bereinigen**

Alt: `import type { BidPremiumEntry, DashboardSnapshot, PlayerRecord, PositionNeed } from "../types";`

Neu: `import type { BidPremiumEntry, DashboardSnapshot, PositionNeed } from "../types";`

(`PlayerRecord` wird nach Step 6/7 unten nirgends mehr in dieser Datei gebraucht.)

Alt: `import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, momentumAssessment, suggestBid, type TransfermarktRow } from "../lib/derive";`

Neu: `import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, suggestBid, type TransfermarktRow } from "../lib/derive";`

- [ ] **Step 2: Sort-Dropdown-Label umbenennen**

Alt: `  { value: "ml", label: "ML-Prognose" },`

Neu: `  { value: "ml", label: "Prognose 1T" },`

- [ ] **Step 3: `mae3d` berechnen**

Alt:
```typescript
  const thresholds = data.signal_thresholds;
  const mae = liveModelMae(data.ml_metrics);
```

Neu:
```typescript
  const thresholds = data.signal_thresholds;
  const mae = liveModelMae(data.ml_metrics);
  const mae3d = liveModelMae(data.ml_metrics_3d ?? null);
```

- [ ] **Step 4: Tabellenspalte umbenennen + neue Spalte "Prognose 3T"**

Alt:
```typescript
    {
      key: "ml_prediction",
      label: "ML-Prognose",
      align: "right",
      sortValue: (r) => r.ml_prediction,
      render: (r) => (
        <span className={trendClass(r.ml_prediction)}>
          {trendArrow(r.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(r.ml_prediction)}
        </span>
      ),
    },
    {
      key: "market_value_change_7d",
```

Neu:
```typescript
    {
      key: "ml_prediction",
      label: "Prognose 1T",
      align: "right",
      sortValue: (r) => r.ml_prediction,
      render: (r) => (
        <span className={trendClass(r.ml_prediction)}>
          {trendArrow(r.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(r.ml_prediction)}
        </span>
      ),
    },
    {
      key: "ml_prediction_3d",
      label: "Prognose 3T",
      align: "right",
      sortValue: (r) => r.ml_prediction_3d,
      render: (r) => fmtSigned(r.ml_prediction_3d),
    },
    {
      key: "market_value_change_7d",
```

- [ ] **Step 5: `mae3d` an Modal durchreichen, `player`-Prop entfernen (nicht mehr gebraucht)**

Alt:
```typescript
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          mae={mae}
          player={data.players[selected.player_id]}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
```

Neu:
```typescript
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          mae={mae}
          mae3d={mae3d}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
```

- [ ] **Step 6: `TransfermarktDetailModal` — Signatur ohne `player`, mit `mae3d`**

Alt:
```typescript
function TransfermarktDetailModal({
  row,
  mae,
  player,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: TransfermarktRow;
  mae: number | null;
  player: PlayerRecord | undefined;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
```

Neu:
```typescript
function TransfermarktDetailModal({
  row,
  mae,
  mae3d,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: TransfermarktRow;
  mae: number | null;
  mae3d: number | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
```

- [ ] **Step 7: Modal-Body — Zeile umbenennen + neue Zeile, Einschätzung entfernen**

Alt:
```typescript
        <dl className="space-y-2 text-sm">
          <Row label="ML-Prognose">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          {(() => {
            const assessment = momentumAssessment(row.ml_prediction, player?.ml_prediction_3d ?? null, mae);
            return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
          })()}
          <Row label="Trend 7T">
```

Neu:
```typescript
        <dl className="space-y-2 text-sm">
          <Row label="Prognose 1T">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          <Row label="Prognose 3T">
            {fmtSigned(row.ml_prediction_3d)}
            {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
          </Row>
          <Row label="Trend 7T">
```

- [ ] **Step 8: `tsc` — diese Datei muss jetzt 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: keine Fehler mehr in `TransfermarktTab.tsx`. `SpekulationTab.tsx`/`WunschkaderTab.tsx` zeigen an diesem Punkt noch Fehler aus Task 1 — normal, folgt in Task 4/5.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktTab: Prognose 1T/3T-Spalte statt ML-Prognose/Einschaetzung"
```

---

## Task 4: SpekulationTab.tsx + App.tsx

**Files:**
- Modify: `frontend/src/components/SpekulationTab.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `SpekulationRow.ml_prediction_3d` (Task 1).
- Produces: `SpekulationTab` erwartet ab jetzt eine neue Prop `mlMetrics3d: MlMetrics | null` statt `players` — App.tsx muss das mit anpassen (Teil dieses Tasks).

- [ ] **Step 1: Imports bereinigen**

Alt: `import type { BidPremiumEntry, MlMetrics, PlayerRecord, PositionNeed } from "../types";`

Neu: `import type { BidPremiumEntry, MlMetrics, PositionNeed } from "../types";`

Alt: `import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, momentumAssessment, suggestBid, type SpekulationRow } from "../lib/derive";`

Neu: `import { liveModelMae, MIN_N_FOR_PERCENTILE_SPREAD, suggestBid, type SpekulationRow } from "../lib/derive";`

- [ ] **Step 2: `SpekulationTab`-Signatur — `players` raus, `mlMetrics3d` rein**

Alt:
```typescript
export default function SpekulationTab({
  rows,
  now,
  mlMetrics,
  bidHistory,
  positionNeed,
  players,
}: {
  rows: SpekulationRow[];
  now: number;
  mlMetrics: MlMetrics | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  players: Record<string, PlayerRecord>;
}) {
  const mae = liveModelMae(mlMetrics);
```

Neu:
```typescript
export default function SpekulationTab({
  rows,
  now,
  mlMetrics,
  mlMetrics3d,
  bidHistory,
  positionNeed,
}: {
  rows: SpekulationRow[];
  now: number;
  mlMetrics: MlMetrics | null;
  mlMetrics3d: MlMetrics | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
}) {
  const mae = liveModelMae(mlMetrics);
  const mae3d = liveModelMae(mlMetrics3d);
```

- [ ] **Step 3: `SpekulationCard` — neue "Prognose 3T"-Zeile**

Alt:
```typescript
      <CardHeader row={row} />
      <dl className="space-y-1.5 text-sm">
        <Row label="ML-Prognose">
          <span className={trendClass(row.ml_prediction)}>
            {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
          </span>
        </Row>
        <Row label="Preis">{fmtNum(row.price)}</Row>
```

Neu:
```typescript
      <CardHeader row={row} />
      <dl className="space-y-1.5 text-sm">
        <Row label="Prognose 1T">
          <span className={trendClass(row.ml_prediction)}>
            {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
          </span>
        </Row>
        <Row label="Prognose 3T">{fmtSigned(row.ml_prediction_3d)}</Row>
        <Row label="Preis">{fmtNum(row.price)}</Row>
```

- [ ] **Step 4: `SpekulationTable` — Spalte umbenennen + neue Spalte**

Alt:
```typescript
    {
      key: "ml_prediction",
      label: "ML-Prognose",
      align: "right",
      sortValue: (r) => r.ml_prediction,
      render: (r) => (
        <span className={trendClass(r.ml_prediction)}>
          {trendArrow(r.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(r.ml_prediction)}
        </span>
      ),
    },
    { key: "price", label: "Preis", align: "right", sortValue: (r) => r.price, render: (r) => fmtNum(r.price) },
```

Neu:
```typescript
    {
      key: "ml_prediction",
      label: "Prognose 1T",
      align: "right",
      sortValue: (r) => r.ml_prediction,
      render: (r) => (
        <span className={trendClass(r.ml_prediction)}>
          {trendArrow(r.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(r.ml_prediction)}
        </span>
      ),
    },
    {
      key: "ml_prediction_3d",
      label: "Prognose 3T",
      align: "right",
      sortValue: (r) => r.ml_prediction_3d,
      render: (r) => fmtSigned(r.ml_prediction_3d),
    },
    { key: "price", label: "Preis", align: "right", sortValue: (r) => r.price, render: (r) => fmtNum(r.price) },
```

- [ ] **Step 5: Modal-Aufruf — `mae3d` statt `player`**

Alt:
```typescript
      {selected && (
        <SpekulationDetailModal
          row={selected}
          now={now}
          mae={mae}
          player={players[selected.player_id]}
          bidHistory={bidHistory}
          positionNeed={positionNeed}
          onClose={() => setSelected(null)}
        />
      )}
```

Neu:
```typescript
      {selected && (
        <SpekulationDetailModal
          row={selected}
          now={now}
          mae={mae}
          mae3d={mae3d}
          bidHistory={bidHistory}
          positionNeed={positionNeed}
          onClose={() => setSelected(null)}
        />
      )}
```

- [ ] **Step 6: `SpekulationDetailModal` — Signatur ohne `player`, mit `mae3d`**

Alt:
```typescript
function SpekulationDetailModal({
  row,
  now,
  mae,
  player,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: SpekulationRow;
  now: number;
  mae: number | null;
  player: PlayerRecord | undefined;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
```

Neu:
```typescript
function SpekulationDetailModal({
  row,
  now,
  mae,
  mae3d,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: SpekulationRow;
  now: number;
  mae: number | null;
  mae3d: number | null;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
```

- [ ] **Step 7: Modal-Body — Zeile umbenennen + neue Zeile, Einschätzung entfernen**

Alt:
```typescript
          <Row label="ML-Prognose">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          {(() => {
            const assessment = momentumAssessment(row.ml_prediction, player?.ml_prediction_3d ?? null, mae);
            return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
          })()}
          <Row label="Trend 7T">
```

Neu:
```typescript
          <Row label="Prognose 1T">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          <Row label="Prognose 3T">
            {fmtSigned(row.ml_prediction_3d)}
            {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
          </Row>
          <Row label="Trend 7T">
```

- [ ] **Step 8: App.tsx — `SpekulationTab`-Aufruf anpassen**

Alt (in `frontend/src/App.tsx`):
```typescript
            <SpekulationTab
              rows={spekulationRows}
              now={now}
              mlMetrics={data.ml_metrics}
              bidHistory={data.bid_premium_history ?? []}
              positionNeed={data.position_need ?? {}}
              players={data.players}
            />
```

Neu:
```typescript
            <SpekulationTab
              rows={spekulationRows}
              now={now}
              mlMetrics={data.ml_metrics}
              mlMetrics3d={data.ml_metrics_3d ?? null}
              bidHistory={data.bid_premium_history ?? []}
              positionNeed={data.position_need ?? {}}
            />
```

- [ ] **Step 9: `tsc` — beide Dateien müssen jetzt 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: keine Fehler mehr in `SpekulationTab.tsx`/`App.tsx`. `WunschkaderTab.tsx` zeigt an diesem Punkt noch Fehler aus Task 1 — normal, folgt in Task 5.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/SpekulationTab.tsx frontend/src/App.tsx
git commit -m "SpekulationTab: Prognose 1T/3T in Karte+Tabelle+Modal, ungenutzte players-Prop durch mlMetrics3d ersetzt"
```

---

## Task 5: WunschkaderTab.tsx

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `PlayerRecord.ml_prediction`/`ml_prediction_3d` (bereits in `types.ts` vorhanden, unabhängig von Task 1 — dieser Tab liest direkt aus der rohen `players`-Map, nicht über `PlayerRow`).
- Produces: nichts, das andere Tasks brauchen.

- [ ] **Step 1: Imports erweitern**

Alt: `import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, liveModelMae, momentumAssessment, plannedPriceFor, type AlleSpielerRow, type BudgetPlan } from "../lib/derive";`

Neu: `import { buildAlleSpielerRows, buildBudgetPlan, liveBidFor, liveModelMae, plannedPriceFor, type AlleSpielerRow, type BudgetPlan } from "../lib/derive";`

Alt: `import { fmtNum } from "../format";`

Neu: `import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";`

- [ ] **Step 2: `ML_PREDICTION_THRESHOLDS`-Konstante ergänzen (gab's in dieser Datei bisher nicht)**

Alt:
```typescript
const MAX_SQUAD_SIZE = 17;
```

Neu:
```typescript
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const MAX_SQUAD_SIZE = 17;
```

- [ ] **Step 3: `mae3d` berechnen**

Alt:
```typescript
  const thresholds = data.signal_thresholds;
  const liveMae = liveModelMae(data.ml_metrics);
```

Neu:
```typescript
  const thresholds = data.signal_thresholds;
  const liveMae = liveModelMae(data.ml_metrics);
  const liveMae3d = liveModelMae(data.ml_metrics_3d ?? null);
```

- [ ] **Step 4: `mae3d` an `DetailModal` durchreichen**

Alt:
```typescript
      {selected && (
        <DetailModal
          target={selected}
          computed={resolvedByPlayerId.get(selected.player_id)!}
          plannedPrice={selectedPlannedPrice}
          thresholds={thresholds}
          mae={liveMae}
          alleSpieler={alleSpieler}
          players={data.players}
          calibration={data.calibration}
          ownSquadIds={ownSquadIds}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(playerId) => replaceTarget(selected._uid, playerId)}
          onNoteChange={(note) => updateNote(selected._uid, note)}
        />
      )}
```

Neu:
```typescript
      {selected && (
        <DetailModal
          target={selected}
          computed={resolvedByPlayerId.get(selected.player_id)!}
          plannedPrice={selectedPlannedPrice}
          thresholds={thresholds}
          mae={liveMae}
          mae3d={liveMae3d}
          alleSpieler={alleSpieler}
          players={data.players}
          calibration={data.calibration}
          ownSquadIds={ownSquadIds}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(playerId) => replaceTarget(selected._uid, playerId)}
          onNoteChange={(note) => updateNote(selected._uid, note)}
        />
      )}
```

- [ ] **Step 5: `DetailModal`-Signatur um `mae3d` erweitern**

Alt:
```typescript
function DetailModal({
  target,
  computed,
  plannedPrice,
  thresholds,
  mae,
  alleSpieler,
  players,
  calibration,
  ownSquadIds,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
  onNoteChange,
}: {
  target: EditTarget;
  computed: ResolvedTarget;
  plannedPrice: number | null;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  alleSpieler: AlleSpielerRow[];
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  ownSquadIds: Set<string>;
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (playerId: string) => void;
  onNoteChange: (note: string) => void;
}) {
```

Neu:
```typescript
function DetailModal({
  target,
  computed,
  plannedPrice,
  thresholds,
  mae,
  mae3d,
  alleSpieler,
  players,
  calibration,
  ownSquadIds,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
  onNoteChange,
}: {
  target: EditTarget;
  computed: ResolvedTarget;
  plannedPrice: number | null;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  mae3d: number | null;
  alleSpieler: AlleSpielerRow[];
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  ownSquadIds: Set<string>;
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (playerId: string) => void;
  onNoteChange: (note: string) => void;
}) {
```

- [ ] **Step 6: Modal-Body — Einschätzung durch Prognose 1T/3T ersetzen (gab's hier vorher gar nicht)**

Alt:
```typescript
          <Row label="Verfügbarkeit">{computed.status}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
          {(() => {
            const assessment = momentumAssessment(
              players[target.player_id]?.ml_prediction ?? null,
              players[target.player_id]?.ml_prediction_3d ?? null,
              mae
            );
            return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
          })()}
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
```

Neu:
```typescript
          <Row label="Verfügbarkeit">{computed.status}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
          <Row label="Prognose 1T">
            <span className={trendClass(players[target.player_id]?.ml_prediction ?? null)}>
              {trendArrow(players[target.player_id]?.ml_prediction ?? null, ML_PREDICTION_THRESHOLDS)}{" "}
              {fmtSigned(players[target.player_id]?.ml_prediction ?? null)}
            </span>
            {mae != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae)})</span>}
          </Row>
          <Row label="Prognose 3T">
            {fmtSigned(players[target.player_id]?.ml_prediction_3d ?? null)}
            {mae3d != null && <span className="text-slate-400 dark:text-slate-500"> (± {fmtNum(mae3d)})</span>}
          </Row>
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
```

- [ ] **Step 7: `tsc` — Projekt muss jetzt komplett 0 Fehler zeigen**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: **0 Fehler im gesamten Projekt** (Task 1–5 sind jetzt alle konsistent — keine Datei importiert `momentumAssessment` mehr).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: neue Prognose-1T/3T-Zeilen im Detail-Modal statt Einschaetzung (gab es hier vorher gar nicht)"
```

---

## Task 6: MlGenauigkeitTab.tsx — zweiter Kopf-an-Kopf-Block für 3T

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx`

**Interfaces:**
- Consumes: `data.ml_metrics_3d`/`data.ml_accuracy_trend_3d` (bereits in `types.ts`/`DashboardSnapshot` vorhanden).
- Produces: nichts, das andere Tasks brauchen.

- [ ] **Step 1: Kopf-an-Kopf-Block in eigene Komponente extrahieren**

Alt (der komplette Bereich von `const reasonLabel = ...` bis zum `return`-Statement-Ende, aktuell Zeilen ~73–126):
```typescript
export default function MlGenauigkeitTab({ data }: { data: DashboardSnapshot }) {
  const metrics = data.ml_metrics;
  const trend = data.ml_accuracy_trend ?? [];
  const outcomeCounts: BidPremiumOutcomeCounts = data.bid_premium_outcome_counts ?? {};

  // Unabhaengig von ml_metrics (kommt aus market_predictor, kann bei einem
  // Heavy-Lauf ohne Prognose oder einem aelteren Snapshot null sein) - das
  // Bid-Premium-Tracking darf deshalb NICHT hinter dem !metrics-Guard
  // unten verschwinden.
  const bidPremiumSection = Object.keys(outcomeCounts).length > 0 && (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Gebotsvorschläge-Tracking</h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
        {POSITIONS.filter((position) => !!outcomeCounts[position]).map((position) => {
          const counts = outcomeCounts[position];
          return (
            <div key={position} className="rounded-xl border border-slate-200 p-3 text-xs dark:border-slate-800">
              <div className="mb-1 text-sm font-medium text-slate-900 dark:text-slate-50">{position}</div>
              <div className="text-slate-500 dark:text-slate-400">
                {counts.rival_purchases} Fremd-Käufe · {counts.self_purchases} eigene · {counts.unsold} unverkauft
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Was aus abgeschlossenen Systemangeboten wurde, pro Position – Fremd-Käufe (echtes Gewinner-Gebot),
        eigene Käufe (Gebot war ausreichend, echter Mindestpreis unbekannt), unverkauft abgelaufen (0% Aufschlag
        hätte gereicht). Fließt nicht in die Gebotsempfehlungen ein, reine Beobachtung.
      </p>
    </div>
  );

  if (!metrics) {
    return (
      <div>
        {bidPremiumSection}
        <p className="text-sm text-slate-500 dark:text-slate-400">Noch keine ML-Metriken verfügbar.</p>
      </div>
    );
  }

  const reasonLabel = metrics.selection_reason
    ? SELECTION_REASON_LABELS[metrics.selection_reason] ?? metrics.selection_reason
    : "unbekannt";

  return (
    <div>
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Kopf-an-Kopf</h3>
        <p className="mb-1 text-sm text-slate-700 dark:text-slate-300">
          Aktuell live: <b>{MODEL_LABELS[metrics.model_type] ?? metrics.model_type}</b>
        </p>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          Auswahlgrund: {reasonLabel} · Kartenwerte unten = 30-Tage-Fenster für die Modellauswahl, unabhängig vom
          Betrachtungszeitraum im Chart weiter unten (komplette Historie).
        </p>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {MODEL_ORDER.map((name) => {
            const isLive = metrics.model_type === name;
            const realized = metrics.realized_by_model?.[name]?.realized_30d;
            return (
              <div key={name} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
                <div className="mb-1 flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-50">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: MODEL_COLORS[name].light }}
                  />
                  {MODEL_LABELS[name]}
                  {isLive && <Badge tone="good">Live</Badge>}
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  {realized ? (
                    <>
                      Richtung korrekt <b>{fmtAccPct(realized.sign_accuracy)}</b> · MAE <b>{fmtNum(realized.mae)}</b> · n={realized.n}
                    </>
                  ) : (
                    "Noch keine abgeschlossenen Prognosen im 30-Tage-Fenster"
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          MAE = mittlere Abweichung der Prognose vom tatsächlichen Marktwert, unabhängig von der Richtung (zu hoch
          und zu niedrig zählen beide gleich) – ein grobes Maß fürs "Rauschen" der Prognose.
        </p>
      </div>

      {bidPremiumSection}

      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Trend: Richtungs-Genauigkeit über die Zeit</h3>
      <TrendChart trend={trend} />
    </div>
  );
}
```

Neu (ersetzt den kompletten obigen Block):
```typescript
export default function MlGenauigkeitTab({ data }: { data: DashboardSnapshot }) {
  const metrics = data.ml_metrics;
  const trend = data.ml_accuracy_trend ?? [];
  const metrics3d = data.ml_metrics_3d ?? null;
  const trend3d = data.ml_accuracy_trend_3d ?? [];
  const outcomeCounts: BidPremiumOutcomeCounts = data.bid_premium_outcome_counts ?? {};

  // Unabhaengig von ml_metrics (kommt aus market_predictor, kann bei einem
  // Heavy-Lauf ohne Prognose oder einem aelteren Snapshot null sein) - das
  // Bid-Premium-Tracking darf deshalb NICHT hinter dem !metrics-Guard
  // unten verschwinden.
  const bidPremiumSection = Object.keys(outcomeCounts).length > 0 && (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Gebotsvorschläge-Tracking</h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
        {POSITIONS.filter((position) => !!outcomeCounts[position]).map((position) => {
          const counts = outcomeCounts[position];
          return (
            <div key={position} className="rounded-xl border border-slate-200 p-3 text-xs dark:border-slate-800">
              <div className="mb-1 text-sm font-medium text-slate-900 dark:text-slate-50">{position}</div>
              <div className="text-slate-500 dark:text-slate-400">
                {counts.rival_purchases} Fremd-Käufe · {counts.self_purchases} eigene · {counts.unsold} unverkauft
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Was aus abgeschlossenen Systemangeboten wurde, pro Position – Fremd-Käufe (echtes Gewinner-Gebot),
        eigene Käufe (Gebot war ausreichend, echter Mindestpreis unbekannt), unverkauft abgelaufen (0% Aufschlag
        hätte gereicht). Fließt nicht in die Gebotsempfehlungen ein, reine Beobachtung.
      </p>
    </div>
  );

  if (!metrics) {
    return (
      <div>
        {bidPremiumSection}
        <p className="text-sm text-slate-500 dark:text-slate-400">Noch keine ML-Metriken verfügbar.</p>
      </div>
    );
  }

  return (
    <div>
      <HeadToHeadBlock metrics={metrics} heading="Kopf-an-Kopf (1-Tages-Horizont)" />
      {metrics3d && <HeadToHeadBlock metrics={metrics3d} heading="Kopf-an-Kopf (3-Tages-Horizont)" />}

      {bidPremiumSection}

      <TrendSection heading="Trend: Richtungs-Genauigkeit über die Zeit (1-Tages-Horizont)" trend={trend} />
      {metrics3d && (
        <TrendSection heading="Trend: Richtungs-Genauigkeit über die Zeit (3-Tages-Horizont)" trend={trend3d} />
      )}
    </div>
  );
}

function HeadToHeadBlock({ metrics, heading }: { metrics: MlMetrics; heading: string }) {
  const reasonLabel = metrics.selection_reason
    ? SELECTION_REASON_LABELS[metrics.selection_reason] ?? metrics.selection_reason
    : "unbekannt";

  return (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">{heading}</h3>
      <p className="mb-1 text-sm text-slate-700 dark:text-slate-300">
        Aktuell live: <b>{MODEL_LABELS[metrics.model_type] ?? metrics.model_type}</b>
      </p>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Auswahlgrund: {reasonLabel} · Kartenwerte unten = 30-Tage-Fenster für die Modellauswahl, unabhängig vom
        Betrachtungszeitraum im Chart weiter unten (komplette Historie).
      </p>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {MODEL_ORDER.map((name) => {
          const isLive = metrics.model_type === name;
          const realized = metrics.realized_by_model?.[name]?.realized_30d;
          return (
            <div key={name} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <div className="mb-1 flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-50">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: MODEL_COLORS[name].light }}
                />
                {MODEL_LABELS[name]}
                {isLive && <Badge tone="good">Live</Badge>}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                {realized ? (
                  <>
                    Richtung korrekt <b>{fmtAccPct(realized.sign_accuracy)}</b> · MAE <b>{fmtNum(realized.mae)}</b> · n={realized.n}
                  </>
                ) : (
                  "Noch keine abgeschlossenen Prognosen im 30-Tage-Fenster"
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        MAE = mittlere Abweichung der Prognose vom tatsächlichen Marktwert, unabhängig von der Richtung (zu hoch
        und zu niedrig zählen beide gleich) – ein grobes Maß fürs "Rauschen" der Prognose.
      </p>
    </div>
  );
}

function TrendSection({ heading, trend }: { heading: string; trend: MlAccuracyTrendEntry[] }) {
  return (
    <div className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">{heading}</h3>
      <TrendChart trend={trend} />
    </div>
  );
}
```

Wichtig: `MlMetrics` und `MlAccuracyTrendEntry` sind bereits importiert (Zeile 2: `import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlModelType } from "../types";` — `MlMetrics` fehlt hier noch, siehe Step 2). Die bestehende `TrendChart`-Komponente (nimmt weiterhin nur `{ trend }` entgegen) bleibt komplett unverändert — nur ihr Aufrufer bekommt jetzt einen Wrapper mit Überschrift.

- [ ] **Step 2: `MlMetrics`-Typ-Import ergänzen**

Alt: `import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlModelType } from "../types";`

Neu: `import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlMetrics, MlModelType } from "../types";`

- [ ] **Step 3: `tsc` — 0 Fehler**

Run: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`

Expected: 0 Fehler im gesamten Projekt (identisch zu Task 5, Step 7 — diese Datei hatte `momentumAssessment` nie genutzt, ist also unabhängig von Task 1–5).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "MlGenauigkeitTab: Kopf-an-Kopf-Block + Trend-Chart-Ueberschrift parametrisiert, zweiter Block fuer 3-Tages-Horizont"
```

---

## Task 7: Abschluss — Verifikation, Feedback-Item, HANDOFF.md, Push

**Files:**
- Modify: `HANDOFF.md` (neuer Completed-Eintrag)
- Keine Code-Änderung sonst — dieser Task ist reine Verifikation + Dokumentation + Betriebs-Schritte.

**Interfaces:**
- Consumes: alle vorherigen Tasks (dies ist der letzte, zusammenfassende Task).

- [ ] **Step 1: Volle Verifikation**

```bash
cd /workspace/work
node frontend/node_modules/typescript/bin/tsc -p frontend/tsconfig.json --noEmit
python3 -m unittest discover -s tests
```

Expected: beides ohne Fehler (`tsc`: 0 Ausgabe = Erfolg; Backend-Suite: `OK`, aktuell 226 Tests).

- [ ] **Step 2: Manuelle Live-Verifikation im Browser**

`cd frontend && npm run dev` (Dev-Server, KEIN `npm install` davor — `node_modules` existiert bereits) — oder falls kein lokaler Kickbase-Zugang gewünscht ist, den bestehenden Produktions-Build unter der GitHub-Pages-URL prüfen. Für jeden der 4 Tabs (Eigenes Team, Transfermarkt, Spekulation, Wunschkader) mindestens einen Spieler mit vorhandener `ml_prediction_3d` öffnen und prüfen:

- "Prognose 1T" UND "Prognose 3T" erscheinen (nicht mehr "ML-Prognose"/"Einschätzung").
- EigenesTeam: auch auf der Kartenfront (nicht nur im Modal).
- Transfermarkt: Prognose 3T ist eine eigene, sortierbare Tabellenspalte.
- Spekulation: auch auf der Kartenfront UND in der Tabellenansicht.
- Wunschkader: Prognose 1T/3T erscheinen im Detail-Modal (vorher war dort gar nichts ML-Bezogenes).
- Modell-Tracking-Tab: zwei "Kopf-an-Kopf"-Blöcke ("1-Tages-Horizont"/"3-Tages-Horizont") + zwei Trend-Charts untereinander.

Falls kein Spieler mit `ml_prediction_3d` sichtbar ist (Cold-Start/aktueller Snapshot älter als der letzte Heavy-Lauf): kurz in den Browser-DevTools `data.players` auf einen Eintrag mit `ml_prediction_3d` prüfen, bevor "kein Fund" als Bug gewertet wird.

- [ ] **Step 3: `feedback/current`-Item auf `status: "done"` setzen**

Read-Modify-Write gegen den frischen Serverstand (etabliertes Muster, siehe `FeedbackTab.tsx`) — Item identifiziert über sein `created_at` (eindeutig, aus der Firestore-Live-Prüfung zu Sessionbeginn bekannt: `"2026-08-01T07:18:41.006Z"`, Text beginnt mit "Die 3Tages Prediction auch einfach anzeigen"):

```bash
GOOGLE_APPLICATION_CREDENTIALS=firebase-service-account.json python3 -c "
from google.cloud import firestore
c = firestore.Client()
ref = c.collection('feedback').document('current')
doc = ref.get()
data = doc.to_dict()
items = data['items']
target_created_at = '2026-08-01T07:18:41.006Z'
updated = False
for item in items:
    if item.get('created_at') == target_created_at:
        item['status'] = 'done'
        updated = True
if not updated:
    raise RuntimeError('Item nicht gefunden - created_at in feedback/current pruefen, evtl. hat sich das Array seit Session-Start veraendert')
ref.set({'items': items}, merge=True)
print('OK, status=done gesetzt fuer:', target_created_at)
"
```

Expected: `OK, status=done gesetzt fuer: 2026-08-01T07:18:41.006Z`. Falls `RuntimeError` — Item könnte inzwischen gelöscht/geändert worden sein (z.B. vom User direkt im Feedback-Tab); in dem Fall `feedback/current` frisch lesen und die Diskrepanz dem User melden statt blind zu erzwingen.

- [ ] **Step 4: HANDOFF.md ergänzen**

Neuen Bullet unter `## Completed` einfügen (Position: ans Ende der Liste, vor `## Not Yet Done`). Commit-Hashes durch die echten kurzen Hashes aus `git log --oneline` für die 6 Commits dieses Plans ersetzen (Task 1–6, in der Reihenfolge, in der sie oben tatsächlich committet wurden):

```markdown
- [x] **ML-Horizonte im Frontend sichtbar gemacht: Prognose 1T/3T statt "ML-Prognose"/"Einschätzung"** (2026-08-01, Spec `docs/superpowers/specs/2026-08-01-ml-horizonte-frontend-anzeige-design.md` + 7-Task-Plan `docs/superpowers/plans/2026-08-01-ml-horizonte-frontend-anzeige.md`, User-Feedback aus `feedback/current`). `momentumAssessment()` (qualitative Konfidenz-Text-Zeile) komplett gelöscht, ersetzt durch zwei rohe Zahlen überall dort, wo vorher "ML-Prognose" stand: EigenesTeam (Karten UND beide Detail-Modals), Transfermarkt (neue Tabellenspalte "Prognose 3T"), Spekulation (Karte UND Tabelle UND Modal), Wunschkader (Detail-Modal bekam die Anzeige neu — hatte vorher gar keine rohe ML-Prognose gezeigt). `PlayerRow`/`SpekulationRow` (derive.ts) um `ml_prediction_3d` erweitert. Modell-Tracking-Tab zeigt jetzt zwei Kopf-an-Kopf-Blöcke + zwei Trend-Charts (1-Tages-/3-Tages-Horizont), Kopf-an-Kopf-Block+Trend-Chart-Überschrift dafür in parametrisierte Komponenten extrahiert. **3T-Trend-Pfeil-Einfärbung bewusst noch nicht umgesetzt** (reine Zahl mit Vorzeichen) — eigene Schwellenwerte kommen als Nebenprodukt der 3-Tage-Hyperparameter-Suche (`docs/superpowers/specs/2026-08-01-ml-3d-tuning-design.md`), siehe Not Yet Done. Commits `COMMIT_TASK1`–`COMMIT_TASK6`. Backend-Tests unberührt (226/226 weiterhin grün), `tsc --noEmit` 0 Fehler. Feedback-Item (`feedback/current`, erstellt 2026-08-01T07:18:41.006Z) auf `status: "done"` gesetzt.
```

- [ ] **Step 5: HANDOFF.md committen**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Prognose-1T/3T-Feature (Task 1-6 dieses Plans) als abgeschlossen dokumentiert"
```

- [ ] **Step 6: Push**

Nur ausführen, wenn Step 1 (tsc + Backend-Suite) tatsächlich fehlerfrei war — Push-Policy dieses Repos (`HANDOFF.md`/Warnings).

```bash
git push origin main
```

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle Abschnitte der Spec (`PlayerRow`-Erweiterung, `momentumAssessment()`-Löschung, alle 4 Pro-Tab-Abschnitte, Modell-Tracking-Verdopplung, Verification-Schritte inkl. Feedback-Item+HANDOFF) sind auf Task 1–7 abgebildet.
- **Platzhalter-Scan**: keine TBD/"analog zu Task N ohne Code" gefunden. Die einzigen bewusst offenen Werte (`COMMIT_TASK1`–`COMMIT_TASK6` in Task 7/Step 4) sind Commit-Hashes, die erst beim tatsächlichen Committen entstehen — kein Implementierungs-Placeholder, sondern zwingend nachträglich einzusetzende Metadaten, exakter Einfügeort ist vorgegeben.
- **Typ-Konsistenz geprüft**: `MlPredictionRow({value1d, mae1d, value3d, mae3d})` (Task 2) wird an allen 4 Aufrufstellen (`PlayerCard`, `WunschkaderWatchlistCard`, `PlayerDetailModal`, `WatchlistDetailModal`) mit denselben Prop-Namen aufgerufen. `mae3d`/`mlMetrics3d` heißen in jeder Datei konsistent so (nicht z.B. `mae_3d` an einer Stelle). `HeadToHeadBlock`/`TrendSection` (Task 6) nutzen `MlMetrics`/`MlAccuracyTrendEntry` exakt wie in `types.ts` definiert.
- **Gegen den echten Code verifiziert**: `derive.ts`, alle 4 Tab-Dateien, `MlGenauigkeitTab.tsx`, `App.tsx` (SpekulationTab-Aufruf) und `types.ts` wurden für diesen Plan frisch gelesen (nicht aus Konversationskontext rekonstruiert). Dabei zwei Punkte gefunden, die die Spec nicht explizit vorwegnahm: (1) `WatchlistRow` in `EigenesTeamTab.tsx` ist ein lokal erweiterter Typ, kein `PlayerRow`-Erbe — braucht eigene manuelle Erweiterung um `ml_prediction_3d` (Task 2, Step 2+4). (2) `players`/`player`-Props in `SpekulationTab.tsx`/`TransfermarktTab.tsx` wurden AUSSCHLIESSLICH für den jetzt entfallenden `momentumAssessment()`-Aufruf gebraucht — nach dessen Entfernen ungenutzt, deshalb in Task 3/4 mit entfernt statt tot liegen gelassen (inkl. des einzigen abhängigen `App.tsx`-Aufrufs für `SpekulationTab`).
