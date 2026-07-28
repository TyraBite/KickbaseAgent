import { useEffect, useState } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db } from "./firebase";
import Login from "./components/Login";
import SpekulationTab from "./components/SpekulationTab";
import type { DashboardSnapshot } from "./types";

type LoadState = "loading" | "error" | "ready";

const TABS = [
  { key: "transfermarkt", label: "Transfermarkt" },
  { key: "spekulation", label: "Spekulation" },
  { key: "team", label: "Eigenes Team" },
  { key: "wunschkader", label: "Wunschkader" },
  { key: "alle-spieler", label: "Alle Spieler" },
  { key: "liga", label: "Ligaanalyse" },
  { key: "ml-genauigkeit", label: "ML-Genauigkeit" },
];

// Sub-Projekt 1 (Pilot): nur Spekulation ist migriert, alle anderen Tabs
// bleiben bis zu ihrem eigenen Sub-Projekt (siehe Phase-6-Plan) deaktiviert.
const ACTIVE_TAB = "spekulation";

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [data, setData] = useState<DashboardSnapshot | null>(null);

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), []);

  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then((snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte spaeter erneut versuchen.");
          setLoadState("error");
          return;
        }
        setData(snap.data() as DashboardSnapshot);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, [user]);

  // Erster Auth-Check laeuft noch (verhindert Login-Formular-Aufflackern).
  if (user === undefined) return null;
  if (!user) return <Login />;

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950">
      <header className="border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          KickbaseAgent Dashboard{" "}
          <span className="text-sm font-normal text-neutral-500 dark:text-neutral-400">(Preview)</span>
        </h1>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-neutral-200 px-6 dark:border-neutral-800">
        {TABS.map((tab) => {
          const isActive = tab.key === ACTIVE_TAB;
          return (
            <button
              key={tab.key}
              type="button"
              disabled={!isActive}
              className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm ${
                isActive
                  ? "border-blue-600 font-semibold text-neutral-900 dark:text-neutral-100"
                  : "cursor-not-allowed border-transparent text-neutral-400 dark:text-neutral-600"
              }`}
            >
              {tab.label}
              {!isActive && <span className="ml-1 text-xs">(bald)</span>}
            </button>
          );
        })}
      </nav>
      <main className="px-6 py-6">
        {loadState === "loading" && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Lade Daten...</p>
        )}
        {loadState === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        )}
        {loadState === "ready" && data && <SpekulationTab rows={data.spekulation ?? []} />}
      </main>
    </div>
  );
}
