// Aliased (Vite resolve.alias, vite.e2e.config.ts) an Stelle des echten
// "firebase/auth"-npm-Pakets fuer das E2E-Projekt. Kein Import aus
// "firebase"/"firebase/auth" hier - strukturell unmoeglich, dass die echte
// Auth-SDK (oder irgendein Netzwerk-Call) laeuft.

const FAKE_UID = "e2e-fake-uid";

export function getAuth(_app: unknown) {
  return { currentUser: { uid: FAKE_UID } };
}

// App.tsx: useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])
// Feuert SYNCHRON mit einem eingeloggten Fake-User - App.tsx's
// `if (user === undefined) return null;`-Gate loest sich sofort auf, kein
// Login-Formular-Aufblitzen, kein echtes Warten.
export function onAuthStateChanged(
  _auth: unknown,
  callback: (user: { uid: string } | null) => void
): () => void {
  callback({ uid: FAKE_UID });
  return () => {};
}

// Wird nie aufgerufen (Login.tsx wird dank des sofort feuernden
// onAuthStateChanged oben nie gemountet) - Stub trotzdem vorhanden, damit
// der benannte Import in Login.tsx nicht ins Leere zeigt.
export async function signInWithEmailAndPassword(): Promise<never> {
  throw new Error("signInWithEmailAndPassword ist im E2E-Fake nicht implementiert.");
}
