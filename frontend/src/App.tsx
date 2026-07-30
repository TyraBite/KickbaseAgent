import { useEffect, useMemo, useState } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db } from "./firebase";
import AlleSpielerTab from "./components/AlleSpielerTab";
import Login from "./components/Login";
import EigenesTeamTab from "./components/EigenesTeamTab";
import LigaanalyseTab from "./components/LigaanalyseTab";
import MlGenauigkeitTab from "./components/MlGenauigkeitTab";
import SpekulationTab from "./components/SpekulationTab";
import TransfermarktTab from "./components/TransfermarktTab";
import WunschkaderTab from "./components/WunschkaderTab";
import { buildSpekulationRows, buildTransfermarktRows } from "./lib/derive";
import type { DashboardSnapshot } from "./types";

// Gemeinsamer Ticker fuer SpekulationTab + TransfermarktTab (vormals in beiden
// Tabs dupliziert, siehe HANDOFF.md Task 17). Restzeiten werden clientseitig
// aus *_expires_at bei jedem Render + alle 60s neu berechnet.
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

type LoadState = "loading" | "error" | "ready";

const TABS = [
  { key: "team", label: "Eigenes Team" },
  { key: "spekulation", label: "Spekulation" },
  { key: "wunschkader", label: "Wunschkader" },
  { key: "transfermarkt", label: "Transfermarkt" },
  { key: "liga", label: "Ligaanalyse" },
  { key: "alle-spieler", label: "Alle Spieler" },
  { key: "ml-genauigkeit", label: "ML-Genauigkeit" },
];

// Sub-Projekt 3: Tabs werden nach und nach aktiviert, sobald migriert.
const ACTIVE_TABS = new Set([
  "spekulation",
  "wunschkader",
  "team",
  "alle-spieler",
  "transfermarkt",
  "liga",
  "ml-genauigkeit",
]);

// Reload ist der einzige Weg an frische Daten zu kommen (Client pollt nicht,
// reiner Pull) - der zuletzt offene Tab soll dabei erhalten bleiben, statt
// immer auf einen festen Tab zurueckzufallen. "team" (Eigenes Team) ist der
// Fallback, wenn noch nichts gespeichert ist oder der gespeicherte Tab nicht
// (mehr) existiert.
const ACTIVE_TAB_STORAGE_KEY = "kickbaseagent_active_tab";

function readStoredActiveTab(): string {
  const stored = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  return stored && ACTIVE_TABS.has(stored) ? stored : "team";
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState(readStoredActiveTab);
  const now = useNow(60_000);
  // data.players kann fehlen, wenn der Firestore-Snapshot noch im alten Schema
  // vorliegt (Deploy-Zeitfenster zwischen Frontend-Push und naechstem Backend-
  // Lauf, siehe Review-Fund 2026-07-29) - dann NICHT buildTransfermarktRows()
  // aufrufen, sonst crasht listings.filter() auf undefined ohne ErrorBoundary.
  const transfermarktRows = useMemo(
    () =>
      data && data.players
        ? buildTransfermarktRows(data.players, data.transfermarkt_listings, data.calibration, data.own_available_budget, new Date(now))
        : [],
    [data, now]
  );
  const spekulationRows = useMemo(() => buildSpekulationRows(transfermarktRows), [transfermarktRows]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

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

  // Snapshot geladen, aber noch im alten Schema (kein "players"-Feld) - kein
  // ErrorBoundary vorhanden, also hier gezielt abfangen statt weiss auf weiss
  // abzustuerzen (siehe Review-Fund 2026-07-29).
  if (data && !data.players) {
    return (
      <p className="p-6 text-sm text-slate-500 dark:text-slate-400">
        Snapshot noch im alten Schema — der nächste Pipeline-Lauf schreibt das neue Format automatisch (bis zu ~2h,
        oder manuell über GitHub Actions anstoßen).
      </p>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-800 dark:bg-slate-950">
        <h1 className="flex items-center gap-2.5 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="inline-block h-3 w-3 rounded-full bg-brand-500 shadow-md shadow-brand-500/50" />
          KickbaseAgent
          <span className="font-normal text-slate-400 dark:text-slate-500">Dashboard</span>
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
            <SpekulationTab rows={spekulationRows} now={now} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "wunschkader" ? "" : "hidden"}>
            <WunschkaderTab data={data} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "team" ? "" : "hidden"}>
            <EigenesTeamTab data={data} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "alle-spieler" ? "" : "hidden"}>
            <AlleSpielerTab data={data} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "transfermarkt" ? "" : "hidden"}>
            <TransfermarktTab data={data} rows={transfermarktRows} now={now} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "liga" ? "" : "hidden"}>
            <LigaanalyseTab data={data} />
          </div>
        )}
        {loadState === "ready" && data && (
          <div className={activeTab === "ml-genauigkeit" ? "" : "hidden"}>
            <MlGenauigkeitTab data={data} />
          </div>
        )}
      </main>
    </div>
  );
}
