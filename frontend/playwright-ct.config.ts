import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
      resolve: {
        alias: [
          {
            find: /^(\.\.\/)+firebase$/,
            replacement: path.resolve(__dirname, "src/test-fixtures/firebase.mock.ts"),
          },
        ],
      },
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
