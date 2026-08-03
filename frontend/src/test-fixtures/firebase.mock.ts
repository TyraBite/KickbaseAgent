// Test-only Stub fuer "../firebase" - wird per Vite-Alias in
// playwright-ct.config.ts eingehaengt, damit z.B. WunschkaderTab.tsx's
// `import { db } from "../firebase"` in Component-Tests NIEMALS das echte
// Firebase-SDK laedt. Bewusst KEIN Import aus dem echten "firebase"-Paket -
// das macht es strukturell unmoeglich (nicht nur "wahrscheinlich harmlos"),
// dass initializeApp/getAuth/getFirestore in einem CT-Lauf ausgefuehrt
// werden.
export const auth = {};
export const db = {};
