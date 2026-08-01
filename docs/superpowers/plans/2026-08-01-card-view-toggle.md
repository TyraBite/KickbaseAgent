# Tabellen/Karten-Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transfermarkt- und Alle-Spieler-Tab bekommen denselben Tabellen/Karten-Toggle, den `SpekulationTab.tsx` schon hat — plus ein geteilter Hook, der beim ersten Laden automatisch nach Bildschirmbreite entscheidet (Handy → Karten, Desktop → Tabelle) und die manuelle Wahl je Tab persistiert.

**Architecture:** Neuer Hook `useViewMode(storageKey)` (`frontend/src/lib/useViewMode.ts`) kapselt Default-Erkennung (`window.matchMedia`) + `localStorage`-Persistenz. `SpekulationTab.tsx` migriert seinen bestehenden `useState<ViewMode>("cards")` darauf (Verhalten sonst unverändert). `TransfermarktTab.tsx`/`AlleSpielerTab.tsx` bekommen je eine neue, zum bestehenden `SpekulationCard`-Stil passende Card-Komponente + denselben Toggle.

**Tech Stack:** React/TypeScript, kein neues Package. Kein Test-Framework fürs Frontend (etabliert) — Verifikation über `tsc --noEmit` + manuellen Browser-Check durch den User.

## Global Constraints

- Jeder Tab hat einen EIGENEN `localStorage`-Key (`kickbaseagent_view_spekulation`/`kickbaseagent_view_transfermarkt`/`kickbaseagent_view_alle_spieler`) — kein geteilter globaler Zustand.
- Kein Resize-Listener — Default wird einmal beim Mount bestimmt (`window.matchMedia("(max-width: 639px)")`, Tailwind-`sm`-Breakpoint).
- Karten zeigen eine KURATIERTE Feldauswahl, nicht 1:1 alle Tabellenspalten (Vorbild `SpekulationCard`).
- Karten-Klick ruft denselben `onSelect`/`setSelected`-Callback auf wie heute schon der Tabellen-Zeilen-Klick — keine neue Modal-Logik.
- Nach JEDEM Task: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` muss weiterhin fehlerfrei durchlaufen.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`) - Repo-Owner pusht selbst.
- **Abhängigkeits-Warnung (2026-08-01 beim Cross-Plan-Check gefunden)**: falls `docs/superpowers/plans/2026-08-01-ml-horizonte-frontend-anzeige.md` vor diesem Plan umgesetzt wird (empfohlene Reihenfolge), ändert dessen Task 3 `TransfermarktTab.tsx`s ML-Prognose-Anzeige (Label "ML-Prognose" → "Prognose 1T"/"Prognose 3T", vermutlich entfällt die `player`/`PlayerRecord`-Prop-Durchreichung, die Task 2 Step 4 dieses Plans für die `ML-Prognose 3T`-Kartenzeile nutzt). **Vor Task 2 Step 4 den dann aktuellen Stand von `TransfermarktTab.tsx` neu lesen** und die `TransfermarktCard`-Prognose-Zeile(n) an das dort tatsächlich vorhandene Prop/Label anpassen — NICHT den unten stehenden Code blind übernehmen, falls er nicht mehr zum Datei-Stand passt.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/lib/useViewMode.ts` | NEU — geteilter Hook (Default-Erkennung + Persistenz) |
| `frontend/src/components/SpekulationTab.tsx` | Migriert auf den neuen Hook (Zeile 84) |
| `frontend/src/components/TransfermarktTab.tsx` | Neuer Toggle + neue `TransfermarktCard` |
| `frontend/src/components/AlleSpielerTab.tsx` | Neuer Toggle + neue `AlleSpielerCard` |

---

## Task 1: `useViewMode`-Hook + Migration von SpekulationTab

**Files:**
- Create: `frontend/src/lib/useViewMode.ts`
- Modify: `frontend/src/components/SpekulationTab.tsx`

**Interfaces:**
- Produces: `useViewMode(storageKey: string): [ViewMode, (mode: ViewMode) => void]`, `export type ViewMode = "cards" | "table"`. Konsumiert von Task 2 und Task 3.

- [ ] **Step 1: Hook implementieren**

Neue Datei `frontend/src/lib/useViewMode.ts`:

```ts
import { useState } from "react";

export type ViewMode = "cards" | "table";

// Tailwind-sm-Breakpoint (640px) - konsistent mit den `sm:`-Klassen im Rest
// der App. Nur EIN Check beim ersten Mount, kein Resize-Listener (YAGNI) -
// wer waehrend der Session vom Handy zum Desktop wechselt, nutzt den
// manuellen Toggle.
function defaultViewMode(): ViewMode {
  if (typeof window === "undefined") return "table";
  return window.matchMedia("(max-width: 639px)").matches ? "cards" : "table";
}

export function useViewMode(storageKey: string): [ViewMode, (mode: ViewMode) => void] {
  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const stored = localStorage.getItem(storageKey);
    return stored === "cards" || stored === "table" ? stored : defaultViewMode();
  });

  function setViewMode(mode: ViewMode) {
    setViewModeState(mode);
    localStorage.setItem(storageKey, mode);
  }

  return [viewMode, setViewMode];
}
```

- [ ] **Step 2: `SpekulationTab.tsx` migrieren**

In `frontend/src/components/SpekulationTab.tsx`, Import ergänzen (nach Zeile 7, der `useModalOpenTracking`-Import-Zeile):

```ts
import { useViewMode } from "../lib/useViewMode";
```

Die lokale `type ViewMode = "cards" | "table";`-Zeile (aktuell Zeile 63) entfernen (kommt jetzt aus dem Hook).

Zeile 84 (`const [viewMode, setViewMode] = useState<ViewMode>("cards");`) ersetzen durch:

```ts
  const [viewMode, setViewMode] = useViewMode("kickbaseagent_view_spekulation");
```

Rest der Datei (Toggle-Buttons, `SpekulationCard`, `SpekulationTable`, alles andere) bleibt unverändert.

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/useViewMode.ts frontend/src/components/SpekulationTab.tsx
git commit -m "useViewMode: geteilter Hook fuer Tabellen/Karten-Default+Persistenz, SpekulationTab migriert"
```

---

## Task 2: `TransfermarktTab.tsx` — Toggle + `TransfermarktCard`

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Consumes: `useViewMode()` (Task 1).

- [ ] **Step 1: Import + State ergänzen**

In `frontend/src/components/TransfermarktTab.tsx`, Import ergänzen (nach Zeile 6, der `format`-Import-Zeile):

```ts
import { useViewMode } from "../lib/useViewMode";
```

Nach der bestehenden Zeile `const [selected, setSelected] = useState<TransfermarktRow | null>(null);` (aktuell Zeile 72) ergänzen:

```ts
  const [viewMode, setViewMode] = useViewMode("kickbaseagent_view_transfermarkt");
```

- [ ] **Step 2: Toggle-Buttons in die Filter-Zeile einfügen**

Direkt vor dem schließenden `</div>` der Filter-`<div className="mb-4 flex flex-wrap items-center gap-3">` (nach dem `<span>{visible.length} von {rows.length} Angeboten</span>`-Block, aktuell endend bei Zeile 216) ergänzen:

```tsx
        <div className="flex overflow-hidden rounded-lg border border-slate-300 text-sm dark:border-slate-700">
          <button
            type="button"
            onClick={() => setViewMode("cards")}
            className={`px-3 py-2 ${viewMode === "cards" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Karten
          </button>
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className={`px-3 py-2 ${viewMode === "table" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Liste
          </button>
        </div>
```

- [ ] **Step 3: Bestehende `<SortableTable .../>`-Zeile konditional machen**

Die bestehende Zeile (aktuell Zeile 218):

```tsx
      <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
```

ersetzen durch:

```tsx
      {viewMode === "cards" ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {visible.map((r) => (
            <TransfermarktCard
              key={r.player_id}
              row={r}
              player={data.players[r.player_id]}
              bidHistory={data.bid_premium_history ?? []}
              thresholds={thresholds}
              onSelect={() => setSelected(r)}
            />
          ))}
        </div>
      ) : (
        <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
      )}
```

- [ ] **Step 4: `TransfermarktCard`-Komponente ergänzen**

Am Ende der Datei ergänzen (nach der bestehenden `TransfermarktDetailModal`-Funktion):

```tsx
function TransfermarktCard({
  row,
  player,
  bidHistory,
  thresholds,
  onSelect,
}: {
  row: TransfermarktRow;
  player: PlayerRecord | undefined;
  bidHistory: BidPremiumEntry[];
  thresholds: DashboardSnapshot["signal_thresholds"];
  onSelect: () => void;
}) {
  const suggestion = row.is_system_offer ? suggestBid(row, bidHistory) : null;
  const hasValidSuggestion = !!suggestion && suggestion.p75 > 0;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-600"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TeamCrest teamName={row.team_name} />
        <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        <PositionBadge position={row.position} />
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Preis">{fmtNum(row.price)}</Row>
        <Row label="ML-Prognose">
          <span className={trendClass(row.ml_prediction)}>
            {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
          </span>
        </Row>
        <Row label="ML-Prognose 3T">
          {player?.ml_prediction_3d != null ? (
            <span className={trendClass(player.ml_prediction_3d)}>
              {trendArrow(player.ml_prediction_3d, ML_PREDICTION_THRESHOLDS)} {fmtSigned(player.ml_prediction_3d)}
            </span>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">n/v</span>
          )}
        </Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Auktion">
          {row.auction_critical ? (
            <Badge tone="crit">⏰ {row.auction_status}</Badge>
          ) : row.auction_urgent ? (
            <Badge tone="crit">{row.auction_status}</Badge>
          ) : (
            row.auction_status ?? <span className="text-slate-400 dark:text-slate-500">unbekannt</span>
          )}
        </Row>
        <Row label="Gebotsempfehlung">
          {row.is_system_offer && hasValidSuggestion && suggestion ? (
            `${fmtNum(suggestion.p75)} (n=${suggestion.n})`
          ) : (
            <span className="text-slate-400 dark:text-slate-500">n/v</span>
          )}
        </Row>
      </dl>
    </div>
  );
}
```

(`TransfermarktRow`, `PlayerRecord`, `BidPremiumEntry`, `DashboardSnapshot`, `Badge`, `PositionBadge`, `Row`, `SignalBadge`, `TeamCrest`, `fmtNum`, `fmtSigned`, `trendArrow`, `trendClass`, `suggestBid`, `TREND_7D_THRESHOLDS`, `ML_PREDICTION_THRESHOLDS` sind alle schon oben in der Datei importiert/definiert — `PlayerRecord` insbesondere schon für `TransfermarktDetailModal`s `player`-Prop genutzt, `player?.ml_prediction_3d` ist derselbe Zugriffspfad wie in `momentumAssessment(row.ml_prediction, player?.ml_prediction_3d ?? null, mae)` weiter unten in derselben Datei — keine neuen Imports nötig.)

- [ ] **Step 5: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktTab: Tabellen/Karten-Toggle + TransfermarktCard"
```

---

## Task 3: `AlleSpielerTab.tsx` — Toggle + `AlleSpielerCard`

**Files:**
- Modify: `frontend/src/components/AlleSpielerTab.tsx`

**Interfaces:**
- Consumes: `useViewMode()` (Task 1).

- [ ] **Step 1: Import + State ergänzen**

In `frontend/src/components/AlleSpielerTab.tsx`, Import ergänzen (nach Zeile 9, der `useModalOpenTracking`-Import-Zeile):

```ts
import { useViewMode } from "../lib/useViewMode";
```

Nach der bestehenden Zeile `const [selected, setSelected] = useState<AlleSpielerRow | null>(null);` (aktuell Zeile 51) ergänzen:

```ts
  const [viewMode, setViewMode] = useViewMode("kickbaseagent_view_alle_spieler");
```

- [ ] **Step 2: Toggle-Buttons in die Filter-Zeile einfügen**

Direkt vor dem schließenden `</div>` der Filter-`<div className="mb-4 flex flex-wrap items-end gap-3">` (nach dem `<span>{visible.length} von {allRows.length} Spielern sichtbar</span>`-Block, aktuell endend bei Zeile 150) ergänzen:

```tsx
        <div className="flex overflow-hidden rounded-lg border border-slate-300 text-sm dark:border-slate-700">
          <button
            type="button"
            onClick={() => setViewMode("cards")}
            className={`px-3 py-2 ${viewMode === "cards" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Karten
          </button>
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className={`px-3 py-2 ${viewMode === "table" ? "bg-brand-600 text-white" : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"}`}
          >
            Liste
          </button>
        </div>
```

- [ ] **Step 3: Bestehende `<SortableTable .../>`-Zeile konditional machen**

Die bestehende Zeile (aktuell Zeile 151):

```tsx
      <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
```

ersetzen durch:

```tsx
      {viewMode === "cards" ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {visible.map((r) => (
            <AlleSpielerCard key={r.player_id} row={r} thresholds={thresholds} onSelect={() => setSelected(r)} />
          ))}
        </div>
      ) : (
        <SortableTable columns={columns} rows={visible} rowKey={(r) => r.player_id} onRowClick={setSelected} />
      )}
```

- [ ] **Step 4: `AlleSpielerCard`-Komponente ergänzen**

Nach der bestehenden `RankFilter`-Funktion (vor `const ML_PREDICTION_THRESHOLDS = ...`, aktuell Zeile 218) ergänzen:

```tsx
function AlleSpielerCard({
  row,
  thresholds,
  onSelect,
}: {
  row: AlleSpielerRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  onSelect: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-600"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TeamCrest teamName={row.team_name} />
        <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        <PositionBadge position={row.position} />
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Verfügbarkeit">
          <Badge tone={ownerTone(row.owner)}>{row.owner}</Badge>
        </Row>
        <Row label="Fitness">
          <FitnessBadge label={row.status_label} />
        </Row>
        <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      </dl>
    </div>
  );
}
```

(`AlleSpielerRow`, `DashboardSnapshot`, `Badge`, `FitnessBadge`, `PositionBadge`, `Row`, `SignalBadge`, `TeamCrest`, `fmtNum`, `ownerTone` sind alle schon oben in der Datei importiert/definiert — keine neuen Imports nötig.)

- [ ] **Step 5: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AlleSpielerTab.tsx
git commit -m "AlleSpielerTab: Tabellen/Karten-Toggle + AlleSpielerCard"
```

---

## Task 4: Abschluss

**Files:** keine (Verifikations-Task)

- [ ] **Step 1**: Volle Verifikation

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler über alle drei geänderten Dateien hinweg.

- [ ] **Step 2**: Manueller Browser-Test durch den User (Sandbox kann kein `npm run dev`)

- Handy-Breite (oder Browser-DevTools auf <640px verkleinert): Transfermarkt, Alle Spieler UND Spekulation starten alle drei mit Karten.
- Desktop-Breite: alle drei starten mit Tabelle.
- In jedem der drei Tabs manuell auf die jeweils andere Ansicht umschalten, Seite neu laden → Wahl bleibt erhalten, UND ist je Tab unabhängig (z.B. Transfermarkt bewusst auf Tabelle lassen, während Alle Spieler auf Karten steht).
- Kartenklick in Transfermarkt/Alle Spieler öffnet dasselbe Detail-Modal wie ein Tabellen-Zeilen-Klick.

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: geteilter Hook (Task 1), beide neuen Tabs (Task 2/3), Spekulation-Migration (Task 1) — alle Punkte der Spec haben eine Task.
- **Platzhalter-Scan**: keine TBD/"analog zu"-ohne-Code gefunden — jeder Card-Komponenten-Code ist vollständig ausgeschrieben.
- **Typ-Konsistenz**: `useViewMode`/`ViewMode`/Storage-Keys durchgängig gleich benannt zwischen Task 1 und den Konsumenten in Task 2/3. Card-Props-Namen (`row`/`thresholds`/`onSelect`, zusätzlich `bidHistory` bei Transfermarkt) konsistent mit den jeweiligen Detail-Modal-Props derselben Datei.
- **Gegen den echten Code verifiziert**: `SpekulationTab.tsx`, `TransfermarktTab.tsx`, `AlleSpielerTab.tsx` wurden vollständig gelesen (aktueller main-Stand) — exakte Zeilennummern/Variablennamen/Importe stammen direkt aus den Dateien, nicht aus Erinnerung. `FitnessBadge`s `label`-Prop (nicht `tone`+children wie der generische `Badge`) wurde gegen `AlleSpielerTab.tsx`s bestehende Nutzung (Zeile 274) verifiziert.
