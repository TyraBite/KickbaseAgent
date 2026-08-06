import { describe, expect, it } from "vitest";
import { panelVariants, slideFadeVariants } from "./motionVariants";

describe("slideFadeVariants", () => {
  it("startet rechts ausserhalb bei Richtung 1 (naechster Tab)", () => {
    const variants = slideFadeVariants(1);
    expect((variants.initial as { x: number }).x).toBeGreaterThan(0);
  });

  it("startet links ausserhalb bei Richtung -1 (vorheriger Tab)", () => {
    const variants = slideFadeVariants(-1);
    expect((variants.initial as { x: number }).x).toBeLessThan(0);
  });

  it("exit-Richtung ist entgegengesetzt zur enter-Richtung", () => {
    const variants = slideFadeVariants(1);
    const enterX = (variants.initial as { x: number }).x;
    const exitX = (variants.exit as { x: number }).x;
    expect(Math.sign(exitX)).not.toBe(Math.sign(enterX));
  });
});

describe("panelVariants", () => {
  it("liefert einen Slide-von-links fuer 'left'", () => {
    const variants = panelVariants("left");
    expect((variants.initial as { x: number }).x).toBeLessThan(0);
  });

  it("liefert einen Scale-Fade fuer 'center', keinen Slide", () => {
    const variants = panelVariants("center");
    expect(variants.initial).not.toHaveProperty("x");
    expect((variants.initial as { scale: number }).scale).toBeLessThan(1);
  });
});
