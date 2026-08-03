import { defineConfig, devices } from "@playwright/experimental-ct-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests-ct",
  // Muss aus Task 2 erhalten bleiben - siehe Kommentar dort. Ohne diese
  // Zeile findet "npm run test:ct" 0 Tests.
  testMatch: /.*\.ct\.tsx$/,
  timeout: 10_000,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : "html",
  use: {
    trace: "on-first-retry",
    ctViteConfig: {
      resolve: {
        alias: [
          {
            find: /^(\.\.\/)+firebase$/,
            replacement: path.resolve(__dirname, "src/test-fixtures/firebase.mock.ts"),
          },
          {
            find: "firebase/firestore",
            replacement: path.resolve(__dirname, "src/test-fixtures/firestore.mock.ts"),
          },
        ],
      },
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
