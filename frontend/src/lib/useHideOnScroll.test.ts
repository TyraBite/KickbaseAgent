import { describe, expect, it } from "vitest";
import { nextHeaderVisible } from "./useHideOnScroll";

describe("nextHeaderVisible", () => {
  it("is always visible at the very top of the page", () => {
    expect(nextHeaderVisible(120, 0, false)).toBe(true);
  });

  it("hides when scrolling down past the threshold", () => {
    expect(nextHeaderVisible(100, 140, true)).toBe(false);
  });

  it("shows when scrolling up past the threshold", () => {
    expect(nextHeaderVisible(140, 100, false)).toBe(true);
  });

  it("keeps the previous state on small jitter deltas", () => {
    expect(nextHeaderVisible(100, 102, true)).toBe(true);
    expect(nextHeaderVisible(100, 102, false)).toBe(false);
  });
});
