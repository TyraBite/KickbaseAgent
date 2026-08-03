import { describe, expect, it } from "vitest";
import { cursorIndexForDigitCount, deleteDigitAt, digitCountBefore, formatThousands, parseThousands } from "./numberFormat";

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

  it("places cursor correctly when a thousands separator is first introduced by reformatting", () => {
    // User types "1000" (4 digits, no separator yet), cursor positioned after 4th digit at index 4
    const digitCount = digitCountBefore("1000", 4);
    expect(digitCount).toBe(4);
    // After reformatting: "1000" → "1.000" (dot now appears at index 1)
    // Cursor should land at index 5 (after 4th digit, which moved from index 3 to index 4)
    expect(cursorIndexForDigitCount("1.000", digitCount)).toBe(5);
  });
});

describe("deleteDigitAt", () => {
  it("removes the digit immediately before a separator (Backspace repro, Critical #2)", () => {
    // "123.456" with caret right after the dot (index 4), Backspace should
    // remove the "3" (the digit before the separator), not the dot itself.
    const result = deleteDigitAt("123.456", 2);
    expect(result.formatted).toBe("12.456");
    // Cursor should land right before the (now earlier) separator, i.e. with
    // exactly 2 digits before it - the same digit count that preceded the
    // deleted digit.
    expect(result.cursorIndex).toBe(2);
  });

  it("removes the digit immediately after a separator (Delete/forward-delete mirror)", () => {
    // "123.456" with caret right before the dot (index 3), Delete should
    // remove the "4" (the digit after the separator) -> "12356" regroups to "12.356".
    const result = deleteDigitAt("123.456", 4);
    expect(result.formatted).toBe("12.356");
    expect(result.cursorIndex).toBe(4);
  });

  it("re-groups thousands separators after the deletion shrinks the digit count", () => {
    // 7 digits -> 6 digits changes the grouping boundary.
    const result = deleteDigitAt("1.234.567", 2); // remove the "2"
    expect(result.formatted).toBe("134.567");
    expect(result.cursorIndex).toBe(1);
  });

  it("collapses to an empty string when deleting the only digit", () => {
    const result = deleteDigitAt("5", 0);
    expect(result.formatted).toBe("");
    expect(result.cursorIndex).toBe(0);
  });
});
