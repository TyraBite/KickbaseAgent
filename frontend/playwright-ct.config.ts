import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";

export default defineConfig({
  testDir: "./tests-ct",
  testMatch: /.*\.ct\.tsx$/,
  timeout: 10_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    trace: "on-first-retry",
    ctViteConfig: {
      plugins: [react()],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
