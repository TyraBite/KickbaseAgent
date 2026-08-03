import { test, expect } from "@playwright/experimental-ct-react";

test("Playwright-CT-Toolchain funktioniert", async ({ mount }) => {
  const component = await mount(<div>Playwright CT funktioniert</div>);
  await expect(component).toContainText("Playwright CT funktioniert");
});
