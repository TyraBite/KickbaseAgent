import { defineConfig, devices } from "@playwright/test";

const PORT = 4300;

export default defineConfig({
  testDir: "./tests-e2e",
  timeout: 15_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
  },
  webServer: {
    command: `npx vite --config vite.e2e.config.ts --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    // Pixel 5 statt eines iPhone-Presets, weil dessen defaultBrowserType
    // chromium ist (konsistent mit dem CT-Projekt) - liefert hasTouch:true,
    // isMobile:true und einen Viewport <640px (MlGenauigkeitTab's
    // isMobileViewport()-matchMedia-Schwelle).
    { name: "mobile-chromium-touch", use: { ...devices["Pixel 5"] } },
  ],
});
