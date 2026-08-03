import type { Page } from "@playwright/test";

export interface TouchPoint {
  x: number;
  y: number;
}

// Echte (CDP-vertraute) Touch-Drag-Geste ueber Input.dispatchTouchEvent - JS-
// synthetisierte `el.dispatchEvent(new TouchEvent(...))` werden von Chromium
// als "nicht vertrauenswuerdig" markiert und loesen touch-spezifisches
// Browser-/Framework-Verhalten nicht zuverlaessig aus. CDP-dispatchte Events
// sind fuer die Seite von echten Hardware-Touch-Events nicht unterscheidbar.
// Chromium-only (CDP ist Chromium-spezifisch). WICHTIG: touchEnd/touchCancel
// duerfen laut CDP-Spec KEINE touchPoints enthalten (nur touchStart/
// touchMove).
export async function touchDrag(page: Page, from: TouchPoint, to: TouchPoint, steps = 6): Promise<void> {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: from.x, y: from.y, id: 0 }],
    });
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      await client.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t, id: 0 }],
      });
    }
    await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  } finally {
    await client.detach();
  }
}
