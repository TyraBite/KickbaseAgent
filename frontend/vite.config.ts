import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Wird von GitHub Pages unter https://tyrabite.github.io/KickbaseAgent/
// als Standard-UI ausgeliefert (Cutover 2026-07-29, Phase 6 Sub-Projekt 4).
// Die alte index.html bleibt separat unter .../KickbaseAgent/old/ erreichbar.
// `vitest/config` ist ein Drop-in-Superset von "vite" (unterstuetzt zusaetzlich
// den `test`-Key) - Build/Dev-Verhalten bleibt unveraendert. War vorher in
// vitest.config.ts dupliziert, das Vitest-eigenstaendig gelesen und dabei
// diese Datei (Plugin + base) komplett ignoriert hat.
export default defineConfig({
  base: "/KickbaseAgent/",
  plugins: [react()],
  test: {
    environment: "node",
    // tests-e2e/ (Playwright E2E, eigener Runner: `npm run test:e2e`) matcht
    // sonst zusaetzlich Vitests eigenen Default-Include ("**/*.spec.ts") und
    // crasht dort mit "Playwright Test did not expect test.describe() to be
    // called here" (Lueckenfund beim Tages-Dashboard-Merge 2026-08-03, siehe
    // HEAD-Merge-Commit). tests-ct/ kollidiert bereits nicht (nutzt ".ct.tsx",
    // matcht Vitests Default-Include gar nicht erst), aber explizit
    // ausgeschlossen fuer Robustheit gegen kuenftige Konventionsaenderungen.
    exclude: [...configDefaults.exclude, "tests-e2e/**", "tests-ct/**"],
  },
});
