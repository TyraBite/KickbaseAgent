import { describe, expect, it } from "vitest";
import { budgetTone, fmtNum, fmtSigned, fmtPct, trendClass, formatDurationMs, trendArrow } from "./format";

describe("budgetTone", () => {
  it("returns red classes for a negative value", () => {
    expect(budgetTone(-100)).toBe("text-red-600 dark:text-red-400");
  });

  it("returns neutral classes for 0", () => {
    expect(budgetTone(0)).toBe("text-slate-900 dark:text-slate-100");
  });

  it("returns neutral classes for a positive value", () => {
    expect(budgetTone(100)).toBe("text-slate-900 dark:text-slate-100");
  });

  it("returns neutral classes for null", () => {
    expect(budgetTone(null)).toBe("text-slate-900 dark:text-slate-100");
  });

  it("returns neutral classes for undefined", () => {
    expect(budgetTone(undefined)).toBe("text-slate-900 dark:text-slate-100");
  });
});

describe("fmtNum", () => {
  it("rounds and formats with German thousands separators", () => {
    expect(fmtNum(1_234_567.6)).toBe("1.234.568");
  });

  it("keeps the minus sign for negative numbers", () => {
    expect(fmtNum(-500)).toBe("-500");
  });

  it("returns '–' for null/undefined", () => {
    expect(fmtNum(null)).toBe("–");
    expect(fmtNum(undefined)).toBe("–");
  });
});

describe("fmtSigned", () => {
  it("prefixes a '+' for positive numbers", () => {
    expect(fmtSigned(500)).toBe("+500");
  });

  it("does not double up the minus sign for negative numbers (fmtNum already adds it)", () => {
    expect(fmtSigned(-500)).toBe("-500");
  });

  it("shows no sign for exactly 0, and '–' for null/undefined", () => {
    expect(fmtSigned(0)).toBe("0");
    expect(fmtSigned(null)).toBe("–");
    expect(fmtSigned(undefined)).toBe("–");
  });
});

describe("fmtPct", () => {
  it("formats with the default 1 digit and a '%' suffix", () => {
    expect(fmtPct(5)).toBe("5.0%");
  });

  it("respects a custom digits count", () => {
    expect(fmtPct(5, 0)).toBe("5%");
  });

  it("keeps the sign for negative percentages, and returns '–' for null/undefined", () => {
    expect(fmtPct(-2.5)).toBe("-2.5%");
    expect(fmtPct(null)).toBe("–");
    expect(fmtPct(undefined)).toBe("–");
  });
});

describe("trendClass", () => {
  it("returns brand color classes for a positive value", () => {
    expect(trendClass(5)).toBe("text-brand-600 dark:text-brand-400");
  });

  it("returns red classes for a negative value", () => {
    expect(trendClass(-5)).toBe("text-red-600 dark:text-red-400");
  });

  it("returns slate/neutral classes for 0, null, and undefined", () => {
    expect(trendClass(0)).toBe("text-slate-400 dark:text-slate-500");
    expect(trendClass(null)).toBe("text-slate-400 dark:text-slate-500");
    expect(trendClass(undefined)).toBe("text-slate-400 dark:text-slate-500");
  });
});

describe("formatDurationMs", () => {
  it("formats under 24h as 'Xh Ym'", () => {
    expect(formatDurationMs(90 * 60 * 1000)).toBe("1h 30m");
  });

  it("formats 24h and beyond as 'Dd Rh'", () => {
    expect(formatDurationMs(25 * 3600 * 1000)).toBe("1d 1h");
  });

  it("clamps negative durations to '0h 0m' instead of going negative", () => {
    expect(formatDurationMs(-5_000)).toBe("0h 0m");
  });
});

describe("trendArrow", () => {
  const thresholds = { flat: 10_000, strong: 100_000 };

  it("returns the flat arrow for null, undefined, and exactly 0", () => {
    expect(trendArrow(null, thresholds)).toBe("➡️");
    expect(trendArrow(undefined, thresholds)).toBe("➡️");
    expect(trendArrow(0, thresholds)).toBe("➡️");
  });

  it("returns the flat arrow for a nonzero value below the flat threshold, regardless of sign", () => {
    expect(trendArrow(5_000, thresholds)).toBe("➡️");
    expect(trendArrow(-5_000, thresholds)).toBe("➡️");
  });

  it("returns a diagonal arrow for values between flat and strong, direction depends on sign", () => {
    expect(trendArrow(50_000, thresholds)).toBe("↗️");
    expect(trendArrow(-50_000, thresholds)).toBe("↘️");
  });

  it("returns a full vertical arrow for values beyond the strong threshold, direction depends on sign", () => {
    expect(trendArrow(200_000, thresholds)).toBe("⬆️");
    expect(trendArrow(-200_000, thresholds)).toBe("⬇️");
  });
});
