import { defineConfig } from "vitest/config";
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
  },
});
