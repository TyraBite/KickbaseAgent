import { describe, expect, it } from "vitest";
import { normalizeSearchText } from "./derive";

describe("normalizeSearchText", () => {
  it("lowercases plain ASCII", () => {
    expect(normalizeSearchText("Diaz")).toBe("diaz");
  });

  it("strips diacritics so accented names match plain queries", () => {
    expect(normalizeSearchText("Luis Díaz")).toBe("luis diaz");
    expect(normalizeSearchText("Díaz")).toBe(normalizeSearchText("Diaz"));
  });

  it("strips apostrophe variants", () => {
    expect(normalizeSearchText("N'Guessan")).toBe("nguessan");
    expect(normalizeSearchText("N’Guessan")).toBe("nguessan");
  });

  it("handles German umlauts", () => {
    expect(normalizeSearchText("Müller")).toBe("muller");
  });
});
