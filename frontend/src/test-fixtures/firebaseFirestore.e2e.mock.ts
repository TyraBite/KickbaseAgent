// Aliased an Stelle des echten "firebase/firestore"-npm-Pakets fuer das
// E2E-Projekt - siehe firebaseAuth.e2e.mock.ts fuer die Begruendung.
// Unterlegt App.tsx's zwei getDoc()-Reads mit einem In-Memory-Fixture statt
// einem echten Firestore-Roundtrip. Writes (setDoc) werden akzeptiert und
// In-Memory gemergt, nie persistiert, nie ueber Netzwerk.

import { buildFixtureSnapshot, FIXTURE_ML_METRICS, FIXTURE_ML_TREND } from "./dashboardSnapshot.fixture";

const store = new Map<string, unknown>();
const fixture = buildFixtureSnapshot({ ml_metrics: FIXTURE_ML_METRICS, ml_accuracy_trend: FIXTURE_ML_TREND });
store.set("dashboard_snapshot/latest", fixture);
store.set("wunschkader/current", { targets: fixture.wunschkader_targets });

export function getFirestore(_app: unknown) {
  return {};
}

export function doc(_db: unknown, ...pathSegments: string[]) {
  return { __e2eDocPath: pathSegments.join("/") };
}

export async function getDoc(ref: { __e2eDocPath: string }) {
  const data = store.get(ref.__e2eDocPath);
  return { exists: () => data !== undefined, data: () => data };
}

export async function setDoc(
  ref: { __e2eDocPath: string },
  data: Record<string, unknown>,
  options?: { merge?: boolean }
): Promise<void> {
  const existing = (store.get(ref.__e2eDocPath) as Record<string, unknown> | undefined) ?? {};
  store.set(ref.__e2eDocPath, options?.merge ? { ...existing, ...data } : data);
}

export function arrayUnion(...items: unknown[]) {
  return { __e2eArrayUnion: items };
}
