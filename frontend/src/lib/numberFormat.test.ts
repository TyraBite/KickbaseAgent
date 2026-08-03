import { describe, expect, it } from "vitest";
import { cursorIndexForDigitCount, digitCountBefore, formatThousands, parseThousands } from "./numberFormat";

describe("formatThousands", () => {
  it("returns an empty string for empty input", () => {
    expect(formatThousands("")).toBe("");
  });

  it("inserts German thousands separators", () => {
    expect(formatThousands("500000")).toBe("500.000");
    expect(formatThousands("5000000")).toBe("5.000.000");
  });

  it("leaves small numbers without a separator", () => {
    expect(formatThousands("12")).toBe("12");
  });

  it("strips non-digit characters before formatting (idempotent on already-formatted input)", () => {
    expect(formatThousands("500.000")).toBe("500.000");
  });

  it("returns an empty string when there are no digits at all", () => {
    expect(formatThousands("abc")).toBe("");
  });
});

describe("parseThousands", () => {
  it("parses a formatted value back to a plain number", () => {
    expect(parseThousands("500.000")).toBe(500_000);
    expect(parseThousands("5.000.000")).toBe(5_000_000);
  });

  it("returns NaN for an empty string", () => {
    expect(parseThousands("")).toBeNaN();
  });

  it("returns NaN when there are no digits", () => {
    expect(parseThousands("abc")).toBeNaN();
  });
});

describe("digitCountBefore", () => {
  it("counts only digit characters before the given index", () => {
    expect(digitCountBefore("500.000", 0)).toBe(0);
    expect(digitCountBefore("500.000", 3)).toBe(3);
    expect(digitCountBefore("500.000", 4)).toBe(3);
  });
});

describe("cursorIndexForDigitCount", () => {
  it("returns 0 for a digit count of 0 or less", () => {
    expect(cursorIndexForDigitCount("500.000", 0)).toBe(0);
  });

  it("places the cursor right after the nth digit, skipping over separators", () => {
    expect(cursorIndexForDigitCount("500.000", 3)).toBe(3);
    expect(cursorIndexForDigitCount("500.000", 4)).toBe(5);
  });

  it("returns the string length when the digit count matches the total available digits", () => {
    expect(cursorIndexForDigitCount("500.000", 6)).toBe(7);
  });

  it("falls back to the string end if there are fewer digits than requested", () => {
    expect(cursorIndexForDigitCount("50", 6)).toBe(2);
  });
});
