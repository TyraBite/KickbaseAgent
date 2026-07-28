import { useEffect, useState } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db } from "./firebase";
import Login from "./components/Login";
import SpekulationTab from "./components/SpekulationTab";
import WunschkaderTab from "./components/WunschkaderTab";
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

// Sub-Projekt 1+2: Spekulation und Wunschkader sind migriert, alle anderen
// Tabs bleiben bis zu ihrem eigenen Sub-Projekt (siehe Phase-6-Plan) deaktiviert.
const ACTIVE_TABS = new Set(["spekulation", "wunschkader"]);

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState("spekulation");

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), []);

  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then((snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte später erneut versuchen.");
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

  // Erster Auth-Check läuft noch (verhindert Login-Formular-Aufflackern).
  if (user === undefined) return null;
  if (!user) return <Login />;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-800 dark:bg-slate-950">
        <h1 className="flex items-center gap-2.5 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="inline-block h-3 w-3 rounded-full bg-brand-500 shadow-md shadow-brand-500/50" />
          KickbaseAgent
          <span className="font-normal text-slate-400 dark:text-slate-500">Dashboard</span>
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300">
            Preview
          </span>
        </h1>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-6 dark:border-slate-800 dark:bg-slate-950">
        {TABS.map((tab) => {
          const isActive = ACTIVE_TABS.has(tab.key);
          const isSelected = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              type="button"
              disabled={!isActive}
              onClick={() => isActive && setActiveTab(tab.key)}
              className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm transition-colors ${
                isSelected
                  ? "border-brand-500 font-semibold text-slate-900 dark:text-slate-50"
                  : isActive
                    ? "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-50"
                    : "cursor-not-allowed border-transparent text-slate-400 dark:text-slate-600"
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
          <p className="text-sm text-slate-500 dark:text-slate-400">Lade Daten…</p>
        )}
        {loadState === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "spekulation" ? "" : "hidden"}>
            <SpekulationTab rows={data.spekulation ?? []} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "wunschkader" ? "" : "hidden"}>
            <WunschkaderTab data={data} />
          </div>
        )}
      </main>
    </div>
  );
}
