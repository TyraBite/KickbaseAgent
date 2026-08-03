import { useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from "react";
import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlMetrics, MlModelType } from "../types";
import { POSITIONS } from "../lib/formations";
import { clampTooltipLeftPercent, nearestTrendIndex } from "../lib/mlChartMobile";
import { Badge } from "./ui";
import { SortableTable, type TableColumn } from "./table";
import { fmtNum } from "../format";

const MODEL_ORDER: MlModelType[] = ["RandomForest", "HistGradientBoosting"];
const MODEL_LABELS: Record<MlModelType, string> = {
  RandomForest: "Random Forest",
  HistGradientBoosting: "Hist Gradient Boosting",
};
// Kategorial, feste Zuordnung (siehe dataviz-Skill) - beide Farben per
// scripts/validate_palette.js gegen Light- UND Dark-Chart-Flaeche
// gegengecheckt (ALL CHECKS PASS), Text/Legende tragen trotzdem den Namen
// direkt statt sich allein auf Farbe zu verlassen (CVD-Sicherheitsnetz).
const MODEL_COLORS: Record<MlModelType, { light: string; dark: string }> = {
  RandomForest: { light: "#0a9d55", dark: "#0a9d55" },
  HistGradientBoosting: { light: "#2563eb", dark: "#3b82f6" },
};
const SELECTION_REASON_LABELS: Record<string, string> = {
  realized_trailing_30d: "Trailing-30-Tage-Realwerte",
  synthetic_split_fallback: "Synthetischer Split (noch zu wenig Realdaten)",
};

function fmtAccPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/v";
  return `${v.toFixed(1)}%`;
}

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
      <div className={`mb-6 grid gap-4 ${metrics3d ? "lg:grid-cols-2" : ""}`}>
        <HeadToHeadBlock metrics={metrics} heading="Kopf-an-Kopf (1-Tages-Horizont)" />
        {metrics3d && <HeadToHeadBlock metrics={metrics3d} heading="Kopf-an-Kopf (3-Tages-Horizont)" />}
      </div>

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
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
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

const CHART_WIDTH = 760;
const CHART_HEIGHT = 240;
// Fester Schaetzwert statt dynamischer Messung - deckt Datum + bis zu 2
// Modell-Zeilen in text-xs ab (siehe Tooltip-Inhalt weiter unten).
const TOOLTIP_WIDTH_PX = 140;
const PAD = { top: 16, right: 88, bottom: 28, left: 36 };
const X_TICK_COUNT = 6;
// Vertikaler Mindestabstand zwischen zwei Modell-Endlabels (px) - verhindert
// Ueberlappung, wenn beide Modelle am aktuellen Rand nah beieinander liegen
// (User-Fund 2026-07-30: bei Kopf-an-Kopf-Werten waren die Labels sonst
// nicht mehr lesbar).
const MIN_LABEL_GAP = 13;

// "YYYY-MM-DD" -> "DD.MM." (kompakt genug fuer Achsen-Ticks).
function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}.${month}.`;
}

// Gleicher Breakpoint wie useViewMode.ts (Tabellen/Karten-Toggle,
// Burger-Menue) - konsistent mit dem Rest der App. Einmalig beim Mount
// ermittelt, kein Resize-Listener (gleiches Muster wie useViewMode.ts).
function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 639px)").matches;
}

function TrendChart({ trend }: { trend: MlAccuracyTrendEntry[] }) {
  const [showTable, setShowTable] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [isMobile] = useState(isMobileViewport);
  const containerRef = useRef<HTMLDivElement>(null);

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

  // Grob skizzierter Zeitraum auf der X-Achse (User-Fund 2026-07-30: bisher
  // komplett unbeschriftet) - ein paar gleichmaessig verteilte Datums-Ticks
  // reichen, keine taggenaue Beschriftung noetig.
  const tickIndices = useMemo(() => {
    if (chartTrend.length <= X_TICK_COUNT) return chartTrend.map((_, i) => i);
    const step = (chartTrend.length - 1) / (X_TICK_COUNT - 1);
    return Array.from(new Set(Array.from({ length: X_TICK_COUNT }, (_, i) => Math.round(i * step))));
  }, [chartTrend.length]);

  // Endlabel-Positionen kollisionsfrei machen: liegen zwei Modelle am
  // rechten Rand vertikal zu nah beieinander, werden ihre TEXT-Labels
  // (nicht die Datenpunkte selbst) auseinandergeschoben.
  const endLabels = useMemo(() => {
    const withEnd = paths
      .filter((p) => p.points.length > 0)
      .map((p) => ({ name: p.name, x: p.points[p.points.length - 1].x, y: p.points[p.points.length - 1].y }));
    const sorted = [...withEnd].sort((a, b) => a.y - b.y);
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].y - sorted[i - 1].y < MIN_LABEL_GAP) {
        sorted[i].y = sorted[i - 1].y + MIN_LABEL_GAP;
      }
    }
    return sorted;
  }, [paths]);

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
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
          {MODEL_ORDER.map((name) => (
            <span key={name} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: MODEL_COLORS[name].light }} />
              {MODEL_LABELS[name]}
            </span>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {showTable ? "Als Chart anzeigen" : "Als Tabelle anzeigen"}
        </button>
      </div>

      {showTable ? (
        <SortableTable columns={columns} rows={trend} rowKey={(e) => e.date} />
      ) : (
        <div
          ref={containerRef}
          data-swipe-ignore
          className="relative rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900"
        >
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
            {[0, 25, 50, 75, 100].map((v) => (
              <g key={v}>
                <line
                  x1={PAD.left}
                  x2={CHART_WIDTH - PAD.right}
                  y1={yFor(v)}
                  y2={yFor(v)}
                  className="stroke-slate-200 dark:stroke-slate-800"
                  strokeWidth={1}
                />
                <text x={PAD.left - 6} y={yFor(v)} textAnchor="end" dominantBaseline="middle" className="fill-slate-400 text-[10px] dark:fill-slate-500">
                  {v}%
                </text>
              </g>
            ))}
            {paths.map(({ name, points, d }) => (
              <g key={name}>
                <path d={d} fill="none" stroke={MODEL_COLORS[name].light} strokeWidth={2} className="dark:hidden" />
                <path d={d} fill="none" stroke={MODEL_COLORS[name].dark} strokeWidth={2} className="hidden dark:inline" />
                {points.map((p, i) => (
                  <circle key={i} cx={p.x} cy={p.y} r={3} fill={MODEL_COLORS[name].light} className="dark:hidden" />
                ))}
                {points.map((p, i) => (
                  <circle key={i} cx={p.x} cy={p.y} r={3} fill={MODEL_COLORS[name].dark} className="hidden dark:inline" />
                ))}
              </g>
            ))}
            {endLabels.map(({ name, x, y }) => (
              <text
                key={name}
                x={x + 6}
                y={y}
                dominantBaseline="middle"
                className="text-[10px] font-medium fill-slate-700 dark:fill-slate-200"
              >
                {MODEL_LABELS[name]}
              </text>
            ))}
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
            {hoverIndex !== null && (
              <line
                x1={xFor(hoverIndex)}
                x2={xFor(hoverIndex)}
                y1={PAD.top}
                y2={CHART_HEIGHT - PAD.bottom}
                className="stroke-slate-300 dark:stroke-slate-700"
                strokeWidth={1}
              />
            )}
          </svg>
          {hoverIndex !== null && (
            <div
              className="pointer-events-none absolute top-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs shadow-md dark:border-slate-700 dark:bg-slate-800"
              style={{ left: `${tooltipLeftPercent}%` }}
            >
              <div className="font-medium text-slate-900 dark:text-slate-50">{chartTrend[hoverIndex].date}</div>
              {MODEL_ORDER.map((name) => (
                <div key={name} className="text-slate-600 dark:text-slate-300">
                  {MODEL_LABELS[name]}: {fmtAccPct(chartTrend[hoverIndex][name])}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
