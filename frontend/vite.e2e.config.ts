import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: [
      { find: "firebase/auth", replacement: path.resolve(__dirname, "src/test-fixtures/firebaseAuth.e2e.mock.ts") },
      { find: "firebase/firestore", replacement: path.resolve(__dirname, "src/test-fixtures/firebaseFirestore.e2e.mock.ts") },
    ],
  },
});
