// Aliased (Vite resolve.alias, playwright-ct.config.ts) an Stelle des echten
// "firebase/firestore"-npm-Pakets fuer ALLE Playwright Component Tests - kein
// Import aus "firebase"/"firebase/firestore" hier, damit es strukturell
// unmoeglich ist, dass die echte SDK in einem CT-gemounteten Baum laeuft.
// Calls werden auf `window.__ctFirestoreCalls` aufgezeichnet (NICHT ein
// simples Modul-Array), weil dieses Modul im gemounteten Page-Kontext
// ausgefuehrt wird - einem GETRENNTEN Modul-Graph vom Node-seitigen
// Test-Code. Nur ein window-Global ueberlebt die Node<->Browser-Grenze
// via page.evaluate().

export interface RecordedSetDocCall {
  path: string;
  data: unknown;
  options: unknown;
}

function callLog(): RecordedSetDocCall[] {
  const w = window as unknown as { __ctFirestoreCalls?: RecordedSetDocCall[] };
  if (!w.__ctFirestoreCalls) w.__ctFirestoreCalls = [];
  return w.__ctFirestoreCalls;
}

export function doc(_db: unknown, ...pathSegments: string[]) {
  return { __ctDocPath: pathSegments.join("/") };
}

export async function setDoc(ref: { __ctDocPath: string }, data: unknown, options?: unknown): Promise<void> {
  callLog().push({ path: ref.__ctDocPath, data, options });
}

// Nicht von den aktuellen CT-Tests genutzt - reiner Vorsorge-Stub, falls
// kuenftig eine weitere Komponente (z.B. FeedbackTab.tsx) ebenfalls per CT
// gemountet wird und "firebase/firestore" importiert.
export async function getDoc(_ref: unknown) {
  return { exists: () => false, data: () => undefined };
}
export function arrayUnion(...items: unknown[]) {
  return { __ctArrayUnion: items };
}
