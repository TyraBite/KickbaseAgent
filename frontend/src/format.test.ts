import { describe, expect, it } from "vitest";
import { budgetTone } from "./format";

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
