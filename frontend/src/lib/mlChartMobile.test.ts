import { describe, expect, it } from "vitest";
import { clampTooltipLeftPercent, nearestTrendIndex } from "./mlChartMobile";

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
