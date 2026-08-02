# ML-Charts Mobile-Lesbarkeit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Macht die beiden ML-Trend-Charts in `MlGenauigkeitTab.tsx` auf Mobile bedienbar und lesbar: kürzerer Zeitraum (14 statt bis zu ~90 Punkte), Tap-und-Drag-Interaktion statt reiner Maus-Hover, und ein Tooltip, der nie über den Bildschirmrand hinausragt.

**Architecture:** `TrendChart` bleibt handgebautes SVG, keine neue Chart-Bibliothek. Zwei pure functions — `nearestTrendIndex` (Extraktion der bestehenden Maus-Hover-Formel, unverändert in ihrer Rechnung) und `clampTooltipLeftPercent` (neue Randklemm-Logik) — wandern in eine eigene, unabhängig testbare Datei `frontend/src/lib/mlChartMobile.ts` mit vitest-Unit-Tests. Die Komponente bekommt einen einmalig-beim-Mount ermittelten `isMobile`-Flag, kürzt darüber das fürs Chart genutzte Array (`chartTrend = isMobile ? trend.slice(-14) : trend`, memoisiert), verdrahtet Touch-Events analog zu den bestehenden Maus-Events (inkl. `data-swipe-ignore`, damit ein Chart-Drag nicht gleichzeitig die App-weite Tab-Swipe-Geste auslöst — bestehendes Muster aus `table.tsx`), und klemmt die Tooltip-Position anhand der per `useRef` gemessenen Container-Breite.

**Tech Stack:** React 18 + TypeScript (strict), Vite 5, vitest 2 (bereits installiert, `environment: "node"` in `vite.config.ts` — keine DOM/jsdom nötig für die zwei pure functions), Tailwind (nur Klassen, keine neue Bibliothek).

## Global Constraints

- Mobile-Erkennung: `window.matchMedia("(max-width: 639px)").matches` — identischer Breakpoint wie `frontend/src/lib/useViewMode.ts`, einmalig beim Mount ermittelt, **kein** Resize-Listener (Fenster-Resize während der Session ändert die Chart-Darstellung nicht nachträglich, konsistent mit `useViewMode.ts`).
- Chart zeigt auf Mobile nur die letzten **14** Einträge von `trend` (`trend.slice(-14)`); die "Als Tabelle anzeigen"-Ansicht (`showTable`) bleibt unverändert und zeigt weiterhin die volle Historie.
- Keine neue Chart-Bibliothek (kein recharts/d3/etc.) — das bestehende handgebaute SVG bleibt.
- `TOOLTIP_WIDTH_PX = 140` ist ein fester Schätzwert, keine dynamische Messung der tatsächlichen Tooltip-Breite.
- Desktop-Verhalten bleibt vollständig unverändert: voller Zeitraum, reine Maus-Interaktion, unlimitierte Tooltip-Position.
- Die zwei neuen pure functions leben in `frontend/src/lib/mlChartMobile.ts` (eigene Datei, nicht in `derive.ts` — thematisch eng an `TrendChart`, nicht app-weite Logik).
- Touch-Event-Verdrahtung (JSX-Handler) ist ohne echten Browser nicht sinnvoll unit-testbar — Verifikation dafür ist `npm run typecheck` + `npm run build`, nicht vitest.

---

### Task 1: `nearestTrendIndex` pure function

**Files:**
- Create: `frontend/src/lib/mlChartMobile.ts`
- Create: `frontend/src/lib/mlChartMobile.test.ts`

**Interfaces:**
- Produces: `nearestTrendIndex(relX: number, plotW: number, padLeft: number, pointCount: number): number` — gibt den nächstgelegenen gültigen Index in `[0, pointCount - 1]` für eine gegebene X-Position `relX` (im SVG-`viewBox`-Koordinatensystem, siehe `CHART_WIDTH` in `MlGenauigkeitTab.tsx`) zurück. Wird von Task 3 (Maus-Handler-Refactor) und Task 4 (Touch-Handler) konsumiert.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/mlChartMobile.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { nearestTrendIndex } from "./mlChartMobile";

describe("nearestTrendIndex", () => {
  // plotW/padLeft entsprechen CHART_WIDTH (760) - PAD.left (36) - PAD.right (88)
  // aus MlGenauigkeitTab.tsx, pointCount=11 -> gueltige Indizes 0..10.
  const plotW = 636;
  const padLeft = 36;
  const pointCount = 11;

  it("findet den mittleren Index bei einer Position in Chart-Mitte", () => {
    expect(nearestTrendIndex(padLeft + plotW / 2, plotW, padLeft, pointCount)).toBe(5);
  });

  it("findet Index 0 am linken Rand des Plots", () => {
    expect(nearestTrendIndex(padLeft, plotW, padLeft, pointCount)).toBe(0);
  });

  it("findet den letzten Index am rechten Rand des Plots", () => {
    expect(nearestTrendIndex(padLeft + plotW, plotW, padLeft, pointCount)).toBe(pointCount - 1);
  });

  it("clamped auf 0 bei einer Position weit links außerhalb des Plots", () => {
    expect(nearestTrendIndex(-1000, plotW, padLeft, pointCount)).toBe(0);
  });

  it("clamped auf den letzten Index bei einer Position weit rechts außerhalb des Plots", () => {
    expect(nearestTrendIndex(5000, plotW, padLeft, pointCount)).toBe(pointCount - 1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/mlChartMobile.test.ts`
Expected: FAIL — `Cannot find module './mlChartMobile'` (Datei existiert noch nicht).

- [ ] **Step 3: Write the minimal implementation**

Create `frontend/src/lib/mlChartMobile.ts`:

```ts
// Reine Hilfsfunktionen fuer TrendChart in MlGenauigkeitTab.tsx (User-Feedback
// 2026-08-01: Chart auf Mobile kaum bedienbar/lesbar) - bewusst aus der
// Komponente ausgelagert, damit sie ohne Browser/DOM per vitest testbar sind.

// Extraktion der bisherigen Inline-Formel aus TrendChart's onMouseMove
// (unveraendert in ihrer Rechnung) - jetzt wiederverwendbar fuer Maus- UND
// Touch-Handler statt zweimal dieselbe Formel zu schreiben.
export function nearestTrendIndex(relX: number, plotW: number, padLeft: number, pointCount: number): number {
  const i = Math.round(((relX - padLeft) / plotW) * (pointCount - 1));
  return Math.min(Math.max(i, 0), pointCount - 1);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/mlChartMobile.test.ts`
Expected: PASS (5 Tests grün).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/mlChartMobile.ts frontend/src/lib/mlChartMobile.test.ts
git commit -m "ML-Charts Mobile: nearestTrendIndex als testbare pure function extrahiert"
```

---

### Task 2: `clampTooltipLeftPercent` pure function

**Files:**
- Modify: `frontend/src/lib/mlChartMobile.ts`
- Modify: `frontend/src/lib/mlChartMobile.test.ts`

**Interfaces:**
- Consumes: nichts aus Task 1 (unabhängige Funktion, gleiche Datei aus organisatorischen Gründen).
- Produces: `clampTooltipLeftPercent(pointXPercent: number, tooltipWidthPercent: number): number` — gibt eine linke Prozent-Position zurück, geklemmt auf `[0, max(0, 100 - tooltipWidthPercent)]`. Wird von Task 5 (Tooltip-Positionierung) konsumiert.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/mlChartMobile.test.ts` (Import-Zeile erweitern und neuen `describe`-Block anhängen):

```ts
import { describe, expect, it } from "vitest";
import { clampTooltipLeftPercent, nearestTrendIndex } from "./mlChartMobile";
```

```ts
describe("clampTooltipLeftPercent", () => {
  it("klemmt nicht, wenn der Punkt weit links liegt", () => {
    expect(clampTooltipLeftPercent(5, 40)).toBe(5);
  });

  it("klemmt nicht, wenn der Punkt in der Mitte liegt", () => {
    expect(clampTooltipLeftPercent(50, 40)).toBe(50);
  });

  it("klemmt auf 100 - tooltipWidthPercent, wenn der Punkt weit rechts liegt", () => {
    const result = clampTooltipLeftPercent(95, 40);
    expect(result).toBe(60);
    expect(result).toBeLessThanOrEqual(100 - 40);
  });

  it("klemmt nach unten auf 0, wenn die Tooltip-Breite groesser als der Container ist", () => {
    expect(clampTooltipLeftPercent(50, 150)).toBe(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/mlChartMobile.test.ts`
Expected: FAIL — `clampTooltipLeftPercent is not exported` / `is not a function`.

- [ ] **Step 3: Write the minimal implementation**

Append to `frontend/src/lib/mlChartMobile.ts`:

```ts
// Haelt die linke Tooltip-Position (in % der Container-Breite) innerhalb
// [0, 100 - tooltipWidthPercent], damit der Tooltip nie ueber den rechten
// (oder bei sehr breitem Tooltip: linken) Rand hinausragt.
export function clampTooltipLeftPercent(pointXPercent: number, tooltipWidthPercent: number): number {
  const maxLeft = Math.max(0, 100 - tooltipWidthPercent);
  return Math.min(Math.max(pointXPercent, 0), maxLeft);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/mlChartMobile.test.ts`
Expected: PASS (9 Tests grün — 5 aus Task 1 + 4 neue).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/mlChartMobile.ts frontend/src/lib/mlChartMobile.test.ts
git commit -m "ML-Charts Mobile: clampTooltipLeftPercent fuer Rand-Klemmung des Tooltips"
```

---

### Task 3: Mobile-Zeitraum-Kürzung (`chartTrend`) + Maus-Handler auf `nearestTrendIndex` umstellen

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx` (aktuell Zeilen 1-6 Imports, 151-153 Konstanten, 167-262 `TrendChart`-Anfang inkl. `onMouseMove`, 302-312 Tick-Labels, 324-336 Tooltip-Inhalt — Zeilen können sich durch vorherige Tasks in diesem Plan bereits leicht verschoben haben, per Code-Kontext statt exakter Zeilennummer matchen)

**Interfaces:**
- Consumes: `nearestTrendIndex` aus Task 1 (`frontend/src/lib/mlChartMobile.ts`).
- Produces: `chartTrend` (lokale `useMemo`-Variable innerhalb `TrendChart`, Typ `MlAccuracyTrendEntry[]`) — wird von Task 4 (Touch-Handler) und Task 5 (Tooltip-Klemmung) weiterverwendet. `isMobile` (lokaler `useState`-Wert, `boolean`) — wird von Task 4 indirekt über `chartTrend` genutzt.

- [ ] **Step 1: Import `nearestTrendIndex` und `isMobileViewport`-Helper ergänzen**

In `frontend/src/components/MlGenauigkeitTab.tsx`, Import-Block ergänzen (nach der `formations`-Zeile):

```tsx
import { POSITIONS } from "../lib/formations";
import { nearestTrendIndex } from "../lib/mlChartMobile";
```

Direkt vor `function TrendChart(...)` einen neuen Helper einfügen (nach `shortDate`, vor `function TrendChart`):

```tsx
// Gleicher Breakpoint wie useViewMode.ts (Tabellen/Karten-Toggle,
// Burger-Menue) - konsistent mit dem Rest der App. Einmalig beim Mount
// ermittelt, kein Resize-Listener (gleiches Muster wie useViewMode.ts).
function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 639px)").matches;
}
```

- [ ] **Step 2: `chartTrend` einführen und `xFor`/`paths`/`tickIndices` darauf umstellen**

Aktueller Code (Anfang von `TrendChart`):

```tsx
function TrendChart({ trend }: { trend: MlAccuracyTrendEntry[] }) {
  const [showTable, setShowTable] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const plotW = CHART_WIDTH - PAD.left - PAD.right;
  const plotH = CHART_HEIGHT - PAD.top - PAD.bottom;

  const xFor = (i: number) => PAD.left + (trend.length > 1 ? (i / (trend.length - 1)) * plotW : plotW / 2);
  const yFor = (v: number) => PAD.top + plotH - (v / 100) * plotH;

  const paths = useMemo(
    () =>
      MODEL_ORDER.map((name) => {
        const points = trend
          .map((entry, i) => (entry[name] === null ? null : { x: xFor(i), y: yFor(entry[name] as number) }))
          .filter((p): p is { x: number; y: number } => p !== null);
        return { name, points, d: points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ") };
      }),
    [trend]
  );
```

Ersetzen durch:

```tsx
function TrendChart({ trend }: { trend: MlAccuracyTrendEntry[] }) {
  const [showTable, setShowTable] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [isMobile] = useState(isMobileViewport);

  // Mobile: nur die letzten 14 Eintraege im Chart (User-Feedback 2026-08-01,
  // Punkte lagen auf schmalen Viewports zu eng beieinander) - die
  // Tabellen-Ansicht (showTable) zeigt weiterhin die volle Historie.
  const chartTrend = useMemo(() => (isMobile ? trend.slice(-14) : trend), [trend, isMobile]);

  const plotW = CHART_WIDTH - PAD.left - PAD.right;
  const plotH = CHART_HEIGHT - PAD.top - PAD.bottom;

  const xFor = (i: number) =>
    PAD.left + (chartTrend.length > 1 ? (i / (chartTrend.length - 1)) * plotW : plotW / 2);
  const yFor = (v: number) => PAD.top + plotH - (v / 100) * plotH;

  const paths = useMemo(
    () =>
      MODEL_ORDER.map((name) => {
        const points = chartTrend
          .map((entry, i) => (entry[name] === null ? null : { x: xFor(i), y: yFor(entry[name] as number) }))
          .filter((p): p is { x: number; y: number } => p !== null);
        return { name, points, d: points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ") };
      }),
    [chartTrend]
  );
```

- [ ] **Step 3: `tickIndices` auf `chartTrend` umstellen**

Aktueller Code:

```tsx
  const tickIndices = useMemo(() => {
    if (trend.length <= X_TICK_COUNT) return trend.map((_, i) => i);
    const step = (trend.length - 1) / (X_TICK_COUNT - 1);
    return Array.from(new Set(Array.from({ length: X_TICK_COUNT }, (_, i) => Math.round(i * step))));
  }, [trend.length]);
```

Ersetzen durch:

```tsx
  const tickIndices = useMemo(() => {
    if (chartTrend.length <= X_TICK_COUNT) return chartTrend.map((_, i) => i);
    const step = (chartTrend.length - 1) / (X_TICK_COUNT - 1);
    return Array.from(new Set(Array.from({ length: X_TICK_COUNT }, (_, i) => Math.round(i * step))));
  }, [chartTrend.length]);
```

(`endLabels` bleibt unverändert — hängt nur von `paths` ab, das bereits über `chartTrend` läuft. Der `if (!trend.length)`-Guard direkt danach bleibt ebenfalls unverändert — prüft die volle, ungekürzte Historie auf "keine Daten vorhanden", unabhängig von der Mobile-Kürzung.)

- [ ] **Step 4: `onMouseMove` auf `nearestTrendIndex` umstellen**

Aktueller Code:

```tsx
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const relX = ((e.clientX - rect.left) / rect.width) * CHART_WIDTH;
              const i = Math.round(((relX - PAD.left) / plotW) * (trend.length - 1));
              setHoverIndex(Math.min(Math.max(i, 0), trend.length - 1));
            }}
            onMouseLeave={() => setHoverIndex(null)}
```

Ersetzen durch:

```tsx
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const relX = ((e.clientX - rect.left) / rect.width) * CHART_WIDTH;
              setHoverIndex(nearestTrendIndex(relX, plotW, PAD.left, chartTrend.length));
            }}
            onMouseLeave={() => setHoverIndex(null)}
```

- [ ] **Step 5: Tick-Label und Tooltip-Inhalt auf `chartTrend` umstellen**

Aktueller Code (Tick-Label im SVG):

```tsx
            {tickIndices.map((i) => (
              <text
                key={i}
                x={xFor(i)}
                y={CHART_HEIGHT - PAD.bottom + 16}
                textAnchor="middle"
                className="fill-slate-400 text-[10px] dark:fill-slate-500"
              >
                {shortDate(trend[i].date)}
              </text>
            ))}
```

Ersetzen durch (nur `trend[i]` → `chartTrend[i]`):

```tsx
            {tickIndices.map((i) => (
              <text
                key={i}
                x={xFor(i)}
                y={CHART_HEIGHT - PAD.bottom + 16}
                textAnchor="middle"
                className="fill-slate-400 text-[10px] dark:fill-slate-500"
              >
                {shortDate(chartTrend[i].date)}
              </text>
            ))}
```

Aktueller Code (Tooltip-Inhalt):

```tsx
              <div className="font-medium text-slate-900 dark:text-slate-50">{trend[hoverIndex].date}</div>
              {MODEL_ORDER.map((name) => (
                <div key={name} className="text-slate-600 dark:text-slate-300">
                  {MODEL_LABELS[name]}: {fmtAccPct(trend[hoverIndex][name])}
                </div>
              ))}
```

Ersetzen durch (`trend[hoverIndex]` → `chartTrend[hoverIndex]`):

```tsx
              <div className="font-medium text-slate-900 dark:text-slate-50">{chartTrend[hoverIndex].date}</div>
              {MODEL_ORDER.map((name) => (
                <div key={name} className="text-slate-600 dark:text-slate-300">
                  {MODEL_LABELS[name]}: {fmtAccPct(chartTrend[hoverIndex][name])}
                </div>
              ))}
```

(Die `SortableTable`-Zeile im `showTable`-Zweig — `rows={trend}` — bleibt unverändert, zeigt weiterhin die volle Historie.)

- [ ] **Step 6: Typecheck ausführen**

Run: `cd frontend && npm run typecheck`
Expected: keine Fehler.

- [ ] **Step 7: Build ausführen**

Run: `cd frontend && npm run build`
Expected: Build erfolgreich, keine Fehler.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "ML-Charts Mobile: Chart zeigt auf Mobile nur die letzten 14 Trend-Eintraege"
```

---

### Task 4: Touch-Interaktion (Tap + Drag) für den Chart

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx`

**Interfaces:**
- Consumes: `nearestTrendIndex` (Task 1), `chartTrend` und `plotW` (Task 3, lokale Variablen in `TrendChart`).
- Produces: `handleTouch` (lokale Funktion in `TrendChart`, konsumiert nur innerhalb dieser Komponente, kein Export nötig).

- [ ] **Step 1: React-Import um `TouchEvent`-Typ erweitern**

Aktueller Code (erste Zeile der Datei):

```tsx
import { useMemo, useState } from "react";
```

Ersetzen durch (gleiches Alias-Muster wie in `App.tsx`s `useSwipeTabs`):

```tsx
import { useMemo, useState, type TouchEvent as ReactTouchEvent } from "react";
```

- [ ] **Step 2: `handleTouch` einführen und auf dem `<svg>` verdrahten**

Aktueller Code (direkt vor dem `return (` von `TrendChart`, nach dem `columns`-Array):

```tsx
  const columns: TableColumn<MlAccuracyTrendEntry>[] = [
    { key: "date", label: "Datum", sortValue: (e) => e.date, render: (e) => e.date },
    { key: "rf", label: "Random Forest", align: "right", sortValue: (e) => e.RandomForest, render: (e) => fmtAccPct(e.RandomForest) },
    {
      key: "hgb",
      label: "Hist Gradient Boosting",
      align: "right",
      sortValue: (e) => e.HistGradientBoosting,
      render: (e) => fmtAccPct(e.HistGradientBoosting),
    },
  ];

  return (
```

Ersetzen durch (Funktion `handleTouch` davor einfügen):

```tsx
  const columns: TableColumn<MlAccuracyTrendEntry>[] = [
    { key: "date", label: "Datum", sortValue: (e) => e.date, render: (e) => e.date },
    { key: "rf", label: "Random Forest", align: "right", sortValue: (e) => e.RandomForest, render: (e) => fmtAccPct(e.RandomForest) },
    {
      key: "hgb",
      label: "Hist Gradient Boosting",
      align: "right",
      sortValue: (e) => e.HistGradientBoosting,
      render: (e) => fmtAccPct(e.HistGradientBoosting),
    },
  ];

  // Mobile: Tippen setzt den Tooltip fest, Ziehen scrubbt live wie der
  // Maus-Hover - kein onTouchEnd-Handler, damit der Tooltip nach dem
  // Loslassen sichtbar bleibt (Lock), bis anderswo im SVG getippt wird.
  function handleTouch(e: ReactTouchEvent<SVGSVGElement>) {
    const touch = e.touches[0];
    if (!touch) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = ((touch.clientX - rect.left) / rect.width) * CHART_WIDTH;
    setHoverIndex(nearestTrendIndex(relX, plotW, PAD.left, chartTrend.length));
  }

  return (
```

Aktueller Code (`<svg>`-Öffnung):

```tsx
          <svg
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            className="w-full"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const relX = ((e.clientX - rect.left) / rect.width) * CHART_WIDTH;
              setHoverIndex(nearestTrendIndex(relX, plotW, PAD.left, chartTrend.length));
            }}
            onMouseLeave={() => setHoverIndex(null)}
          >
```

Ersetzen durch:

```tsx
          <svg
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            className="w-full"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const relX = ((e.clientX - rect.left) / rect.width) * CHART_WIDTH;
              setHoverIndex(nearestTrendIndex(relX, plotW, PAD.left, chartTrend.length));
            }}
            onMouseLeave={() => setHoverIndex(null)}
            onTouchStart={handleTouch}
            onTouchMove={handleTouch}
          >
```

- [ ] **Step 3: `data-swipe-ignore` auf den Chart-Container setzen**

Ohne diesen Schritt bubbelt jedes Touch-Drag auf dem Chart zum App-weiten Swipe-Tab-Handler in `App.tsx` (`<main onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>`, siehe `useSwipeTabs`) und würde beim Scrubben zusätzlich versehentlich den Tab wechseln — exakt das gleiche Problem, das `components/table.tsx` für horizontal scrollende Tabellen bereits mit `data-swipe-ignore` löst (`useSwipeTabs`' `onTouchStart` bricht per `target.closest("[data-swipe-ignore]")` ab).

Aktueller Code (öffnendes Chart-Container-`<div>`):

```tsx
        <div className="relative rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900">
```

Ersetzen durch:

```tsx
        <div
          data-swipe-ignore
          className="relative rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900"
        >
```

- [ ] **Step 4: Typecheck ausführen**

Run: `cd frontend && npm run typecheck`
Expected: keine Fehler.

- [ ] **Step 5: Build ausführen**

Run: `cd frontend && npm run build`
Expected: Build erfolgreich, keine Fehler.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "ML-Charts Mobile: Tap-und-Drag-Touch-Interaktion fuer TrendChart"
```

---

### Task 5: Tooltip-Randklemmung mit gemessener Container-Breite

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx`

**Interfaces:**
- Consumes: `clampTooltipLeftPercent` (Task 2), `chartTrend`/`xFor`/`hoverIndex` (Task 3).
- Produces: keine neuen Exports — rein interne Render-Logik innerhalb `TrendChart`.

- [ ] **Step 1: React- und lib-Import um `useRef`/`clampTooltipLeftPercent` erweitern**

Aktueller Code (nach Task 4):

```tsx
import { useMemo, useState, type TouchEvent as ReactTouchEvent } from "react";
import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlMetrics, MlModelType } from "../types";
import { POSITIONS } from "../lib/formations";
import { nearestTrendIndex } from "../lib/mlChartMobile";
```

Ersetzen durch:

```tsx
import { useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from "react";
import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlMetrics, MlModelType } from "../types";
import { POSITIONS } from "../lib/formations";
import { clampTooltipLeftPercent, nearestTrendIndex } from "../lib/mlChartMobile";
```

- [ ] **Step 2: `TOOLTIP_WIDTH_PX`-Konstante ergänzen**

Aktueller Code:

```tsx
const CHART_WIDTH = 760;
const CHART_HEIGHT = 240;
const PAD = { top: 16, right: 88, bottom: 28, left: 36 };
```

Ersetzen durch:

```tsx
const CHART_WIDTH = 760;
const CHART_HEIGHT = 240;
// Fester Schaetzwert statt dynamischer Messung - deckt Datum + bis zu 2
// Modell-Zeilen in text-xs ab (siehe Tooltip-Inhalt weiter unten).
const TOOLTIP_WIDTH_PX = 140;
const PAD = { top: 16, right: 88, bottom: 28, left: 36 };
```

- [ ] **Step 3: `containerRef` anlegen und am Chart-Container anhängen**

Aktueller Code (Anfang von `TrendChart`, nach Task 3):

```tsx
function TrendChart({ trend }: { trend: MlAccuracyTrendEntry[] }) {
  const [showTable, setShowTable] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [isMobile] = useState(isMobileViewport);
```

Ersetzen durch:

```tsx
function TrendChart({ trend }: { trend: MlAccuracyTrendEntry[] }) {
  const [showTable, setShowTable] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [isMobile] = useState(isMobileViewport);
  const containerRef = useRef<HTMLDivElement>(null);
```

Aktueller Code (Chart-Container-`<div>`, nach Task 4):

```tsx
        <div
          data-swipe-ignore
          className="relative rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900"
        >
```

Ersetzen durch:

```tsx
        <div
          ref={containerRef}
          data-swipe-ignore
          className="relative rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900"
        >
```

- [ ] **Step 4: `tooltipLeftPercent` berechnen und im Tooltip-Style verwenden**

Aktueller Code (direkt vor `const columns`, nach dem `if (!trend.length)`-Guard):

```tsx
  if (!trend.length) {
    return <p className="text-xs text-slate-400 dark:text-slate-500">Noch keine Trend-Daten vorhanden…</p>;
  }

  const columns: TableColumn<MlAccuracyTrendEntry>[] = [
```

Ersetzen durch:

```tsx
  if (!trend.length) {
    return <p className="text-xs text-slate-400 dark:text-slate-500">Noch keine Trend-Daten vorhanden…</p>;
  }

  // Klemmt die Tooltip-Position an der tatsaechlich gemessenen
  // Container-Breite, damit er auf schmalen Mobile-Viewports nie ueber den
  // rechten Rand hinausragt (kein ResizeObserver - Breite wird nur beim
  // Render gelesen, Fenster-Resize ist ein akzeptiertes Nicht-Ziel).
  const tooltipLeftPercent =
    hoverIndex !== null
      ? clampTooltipLeftPercent(
          (xFor(hoverIndex) / CHART_WIDTH) * 100,
          (TOOLTIP_WIDTH_PX / (containerRef.current?.getBoundingClientRect().width ?? CHART_WIDTH)) * 100
        )
      : 0;

  const columns: TableColumn<MlAccuracyTrendEntry>[] = [
```

Aktueller Code (Tooltip-`<div>`-Style):

```tsx
            <div
              className="pointer-events-none absolute top-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800"
              style={{ left: `${(xFor(hoverIndex) / CHART_WIDTH) * 100}%` }}
            >
```

Ersetzen durch:

```tsx
            <div
              className="pointer-events-none absolute top-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800"
              style={{ left: `${tooltipLeftPercent}%` }}
            >
```

- [ ] **Step 5: Typecheck ausführen**

Run: `cd frontend && npm run typecheck`
Expected: keine Fehler.

- [ ] **Step 6: Build ausführen**

Run: `cd frontend && npm run build`
Expected: Build erfolgreich, keine Fehler.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "ML-Charts Mobile: Tooltip an Container-Rand geklemmt statt reiner Prozent-Position"
```
