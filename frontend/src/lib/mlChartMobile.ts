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

// Haelt die linke Tooltip-Position (in % der Container-Breite) innerhalb
// [0, 100 - tooltipWidthPercent], damit der Tooltip nie ueber den rechten
// (oder bei sehr breitem Tooltip: linken) Rand hinausragt.
export function clampTooltipLeftPercent(pointXPercent: number, tooltipWidthPercent: number): number {
  const maxLeft = Math.max(0, 100 - tooltipWidthPercent);
  return Math.min(Math.max(pointXPercent, 0), maxLeft);
}
