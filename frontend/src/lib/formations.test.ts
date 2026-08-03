import { describe, expect, it } from "vitest";
import { canAddStarter, matchedFormation } from "./formations";
import type { PositionCounts } from "./formations";

describe("canAddStarter", () => {
  it("returns true when at least one of the 10 formations can still be reached after one more starter in the position", () => {
    // 1 Torwart + 3 Abwehr + 3 Mittelfeld + 2 Sturm = 9 Feldspieler belegt.
    // Ein weiterer Mittelfeld-Starter (-> Mittelfeld: 4) passt noch zu
    // "3-4-3" (3/4/3) UND "3-5-2" (3/5/2) - zwei der 10 Formationen bleiben erreichbar.
    const counts: PositionCounts = { Torwart: 1, Abwehr: 3, Mittelfeld: 3, Sturm: 2 };
    expect(canAddStarter(counts, "Mittelfeld")).toBe(true);
  });

  it("returns false when no formation can be reached anymore (e.g. a 2nd Torwart - jede Formation hat Torwart fix 1)", () => {
    const counts: PositionCounts = { Torwart: 1, Abwehr: 0, Mittelfeld: 0, Sturm: 0 };
    expect(canAddStarter(counts, "Torwart")).toBe(false);
  });
});

describe("matchedFormation", () => {
  it("returns the exact formation key when the counts match one of the 10 formations exactly", () => {
    const counts: PositionCounts = { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 };
    expect(matchedFormation(counts)).toBe("4-4-2");
  });

  it("returns null for an invalid 11-Feldspieler-Belegung that matches none of the 10 formations (e.g. 2 Torwaerter)", () => {
    // Summe = 11 (2+4+3+2), aber keine der 10 Formationen hat Torwart: 2.
    const counts: PositionCounts = { Torwart: 2, Abwehr: 4, Mittelfeld: 3, Sturm: 2 };
    expect(matchedFormation(counts)).toBeNull();
  });
});
