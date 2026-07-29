import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Wird von GitHub Pages unter https://tyrabite.github.io/KickbaseAgent/
// als Standard-UI ausgeliefert (Cutover 2026-07-29, Phase 6 Sub-Projekt 4).
// Die alte index.html bleibt separat unter .../KickbaseAgent/old/ erreichbar.
export default defineConfig({
  base: "/KickbaseAgent/",
  plugins: [react()],
});
