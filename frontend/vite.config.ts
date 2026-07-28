import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Wird von GitHub Pages unter https://tyrabite.github.io/KickbaseAgent/preview/
// ausgeliefert, waehrend die alte index.html am Repo-Root parallel weiterlaeuft
// (Phase 6 Sub-Projekt 1: Parallelbetrieb bis Cutover).
export default defineConfig({
  base: "/KickbaseAgent/preview/",
  plugins: [react()],
});
