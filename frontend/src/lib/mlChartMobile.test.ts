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
