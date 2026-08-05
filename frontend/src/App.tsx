import { useEffect, useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { AnimatePresence, motion, MotionConfig, type Variants } from "framer-motion";
import { backdropVariants, fadeVariants, panelVariants, slideFadeVariants } from "./lib/motionVariants";
import { auth, db } from "./firebase";
import AlleSpielerTab from "./components/AlleSpielerTab";
import DashboardTab from "./components/DashboardTab";
import Login from "./components/Login";
import EigenesTeamTab from "./components/EigenesTeamTab";
import LigaanalyseTab from "./components/LigaanalyseTab";
import MlGenauigkeitTab from "./components/MlGenauigkeitTab";
import SpekulationTab from "./components/SpekulationTab";
import TransfermarktTab from "./components/TransfermarktTab";
import WunschkaderTab from "./components/WunschkaderTab";
import FeedbackTab from "./components/FeedbackTab";
import {
  IconMenu,
  IconTabDashboard,
  IconTabTeam,
  IconTabSpekulation,
  IconTabWunschkader,
  IconTabTransfermarkt,
  IconTabLiga,
  IconTabAlleSpieler,
  IconTabMlGenauigkeit,
  IconTabFeedback,
} from "./components/icons";
import { buildSpekulationRows, buildTransfermarktRows, formatRelativeTime } from "./lib/derive";
import { useHideOnScroll } from "./lib/useHideOnScroll";
import { isAnyModalOpen, useModalOpenTracking } from "./lib/modalOpenTracker";
import type { DashboardSnapshot, RawWunschkaderTarget } from "./types";

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

type TabTransition = { kind: "fade" } | { kind: "slide"; direction: 1 | -1 };

type WunschkaderPhase = "active" | "exiting" | "hidden";
// Rein optische Exit-Dauer fuer den WunschkaderTab-Wrapper unten (nicht das
// geteilte fadeVariants aus motionVariants.ts, das bleibt fuer alle anderen
// Fades bei FADE_EXIT_S) - NICHT sicherheitskritisch: WunschkaderTab wird nie
// unmounted, solange Daten geladen sind (siehe wunschkaderPhase-Kommentar bei
// der Render-Stelle unten), sein React-State (Notiz, offenes Detail-Modal)
// ueberlebt deshalb JEDE Verweildauer auf einem anderen Tab, unabhaengig von
// dieser Zahl. Diese Dauer bestimmt nur, wie lange der sichtbare Opacity-Fade
// beim Wegwechseln dauert, bevor der Wrapper per display:none aus dem
// CSS-Grid-Stack (Layout/Hit-Testing) verschwindet.
const WUNSCHKADER_FADE_EXIT_S = 0.45;
const wunschkaderFadeVariants: Variants = {
  initial: fadeVariants.initial,
  animate: fadeVariants.animate,
  exit: { opacity: 0, transition: { duration: WUNSCHKADER_FADE_EXIT_S } },
};
// Rein kosmetischer Nachlauf, bevor der (unveraendert gemountete) Wrapper per
// display:none aus dem Grid-Stack genommen wird, falls onAnimationComplete
// mal nicht zuverlaessig feuert (siehe Kommentar beim Fallback-Effect unten) -
// betrifft nur Layout-Sauberkeit/Klick-Durchlaessigkeit, keine State-Erhaltung.
const WUNSCHKADER_EXIT_FALLBACK_MS = 700;

const TABS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "team", label: "Eigenes Team" },
  { key: "spekulation", label: "Spekulation" },
  { key: "wunschkader", label: "Wunschkader" },
  { key: "transfermarkt", label: "Transfermarkt" },
  { key: "liga", label: "Ligaanalyse" },
  { key: "alle-spieler", label: "Alle Spieler" },
  { key: "ml-genauigkeit", label: "Modell-Tracking" },
  { key: "feedback", label: "Bugs & Ideen" },
];

// Sub-Projekt 3: Tabs werden nach und nach aktiviert, sobald migriert.
const ACTIVE_TABS = new Set([
  "dashboard",
  "spekulation",
  "wunschkader",
  "team",
  "alle-spieler",
  "transfermarkt",
  "liga",
  "ml-genauigkeit",
  "feedback",
]);

// Grafische Tab-Indikatoren (siehe docs/superpowers/plans/2026-08-03-tab-icons.md).
// "dashboard" hat hier bewusst schon einen Eintrag, obwohl der Tab-Key selbst
// noch nicht in TABS/ACTIVE_TABS existiert (der kommt separat mit dem
// Tages-Dashboard-Feature) - schadet nicht, TAB_ICON wird generisch ueber
// TABS.map() aufgeloest, ein ueberzaehliger Key bleibt einfach ungenutzt.
const TAB_ICON: Record<string, (props: import("react").SVGProps<SVGSVGElement>) => JSX.Element> = {
  dashboard: IconTabDashboard,
  team: IconTabTeam,
  spekulation: IconTabSpekulation,
  wunschkader: IconTabWunschkader,
  transfermarkt: IconTabTransfermarkt,
  liga: IconTabLiga,
  "alle-spieler": IconTabAlleSpieler,
  "ml-genauigkeit": IconTabMlGenauigkeit,
  feedback: IconTabFeedback,
};

// Reload ist der einzige Weg an frische Daten zu kommen (Client pollt nicht,
// reiner Pull) - der zuletzt offene Tab soll dabei erhalten bleiben, statt
// immer auf einen festen Tab zurueckzufallen. "dashboard" ist der
// Fallback, wenn noch nichts gespeichert ist oder der gespeicherte Tab nicht
// (mehr) existiert.
const ACTIVE_TAB_STORAGE_KEY = "kickbaseagent_active_tab";

function readStoredActiveTab(): string {
  const stored = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  return stored && ACTIVE_TABS.has(stored) ? stored : "dashboard";
}

// Wischen wechselt auf dem Handy schneller zwischen Tabs als die Tab-Leiste.
// Reine Touch-Events, kein neues Package. Zwei Ausschluss-Faelle: ein Wisch,
// der in einer horizontal scrollenden Tabelle beginnt (data-swipe-ignore auf
// dem Wrapper in table.tsx), und jeder offene Detail-Modal (siehe
// modalOpenTracker.ts) - sonst wechselt ein Wisch im Modal versehentlich den
// Hintergrund-Tab.
const SWIPE_THRESHOLD_PX = 60;
const SWIPE_MAX_VERTICAL_PX = 50;

function useSwipeTabs(
  activeTab: string,
  setActiveTab: (key: string) => void,
  setTabTransition: (t: TabTransition) => void
) {
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  function onTouchStart(e: ReactTouchEvent<HTMLElement>) {
    touchStart.current = null;
    if (isAnyModalOpen()) return;
    const target = e.target as HTMLElement;
    if (target.closest("[data-swipe-ignore]")) return;
    touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }

  function onTouchEnd(e: ReactTouchEvent<HTMLElement>) {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || isAnyModalOpen()) return;

    const dx = e.changedTouches[0].clientX - start.x;
    const dy = e.changedTouches[0].clientY - start.y;
    if (Math.abs(dy) > SWIPE_MAX_VERTICAL_PX || Math.abs(dx) < SWIPE_THRESHOLD_PX) return;

    // "Inhalt folgt dem Finger": rechts wischen schiebt den aktuellen Tab nach
    // rechts raus, der VORHERIGE (linke) Tab rutscht rein - wie bei
    // Foto-Galerien/iOS-Seitenwischen, nicht wie ein Cursor-Sprung.
    const activeKeys = TABS.filter((t) => ACTIVE_TABS.has(t.key)).map((t) => t.key);
    const i = activeKeys.indexOf(activeTab);
    const next = dx < 0 ? activeKeys[i + 1] : activeKeys[i - 1];
    if (next) {
      setTabTransition({ kind: "slide", direction: dx < 0 ? 1 : -1 });
      setActiveTab(next);
    }
  }

  return { onTouchStart, onTouchEnd };
}

// Mobile Ersatz fuer die horizontale Tab-Leiste (die bleibt ab `sm:` sichtbar,
// siehe <nav> oben) - registriert sich per useModalOpenTracking() wie jedes
// andere Modal, damit isAnyModalOpen() ein Wischen ueber dem offenen Menue
// nicht versehentlich als Tab-Swipe im Hintergrund interpretiert (siehe
// useSwipeTabs oben). Swipe selbst bleibt dadurch unangetastet - Oeffnen
// dieses Menues blockt es nur temporaer, wie bei jedem Detail-Modal.
function MobileTabMenu({
  activeTab,
  onSelect,
  onClose,
}: {
  activeTab: string;
  onSelect: (key: string) => void;
  onClose: () => void;
}) {
  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <motion.div
      variants={backdropVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="fixed inset-0 z-20 bg-slate-950/50 sm:hidden"
      onClick={onClose}
    >
      <motion.nav
        variants={panelVariants("left")}
        initial="initial"
        animate="animate"
        exit="exit"
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-72 max-w-[80vw] flex-col gap-1 overflow-y-auto bg-white p-3 shadow-xl dark:bg-slate-950"
      >
        <div className="mb-2 flex items-center justify-between px-1">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-50">Menü</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        {TABS.map((tab) => {
          const isActive = ACTIVE_TABS.has(tab.key);
          const isSelected = tab.key === activeTab;
          const Icon = TAB_ICON[tab.key];
          const iconTone = !isActive
            ? "text-slate-500"
            : isSelected
              ? "text-brand-600 dark:text-brand-400"
              : "text-slate-500 hover:text-slate-600 dark:hover:text-slate-300";
          return (
            <button
              key={tab.key}
              type="button"
              disabled={!isActive}
              onClick={() => {
                if (!isActive) return;
                onSelect(tab.key);
                onClose();
              }}
              className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                isSelected
                  ? "bg-brand-50 font-semibold text-brand-800 dark:bg-brand-950 dark:text-brand-300"
                  : isActive
                    ? "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                    : "cursor-not-allowed text-slate-400 dark:text-slate-600"
              }`}
            >
              {Icon && <Icon className={`h-6 w-6 shrink-0 ${iconTone}`} aria-hidden="true" />}
              {tab.label}
              {!isActive && <span className="ml-1 text-xs">(bald)</span>}
            </button>
          );
        })}
      </motion.nav>
    </motion.div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [wunschkader, setWunschkader] = useState<{ targets: RawWunschkaderTarget[] } | null>(null);
  const [activeTab, setActiveTab] = useState(readStoredActiveTab);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [tabTransition, setTabTransition] = useState<TabTransition>({ kind: "fade" });
  const [wunschkaderPhase, setWunschkaderPhase] = useState<WunschkaderPhase>(
    activeTab === "wunschkader" ? "active" : "hidden"
  );
  const now = useNow(60_000);
  // data.players kann fehlen, wenn der Firestore-Snapshot noch im alten Schema
  // vorliegt (Deploy-Zeitfenster zwischen Frontend-Push und naechstem Backend-
  // Lauf, siehe Review-Fund 2026-07-29) - dann NICHT buildTransfermarktRows()
  // aufrufen, sonst crasht listings.filter() auf undefined ohne ErrorBoundary.
  const transfermarktRows = useMemo(
    () =>
      data && data.players
        ? buildTransfermarktRows(data.players, data.transfermarkt_listings, data.calibration, new Date(now))
        : [],
    [data, now]
  );
  const spekulationRows = useMemo(() => buildSpekulationRows(transfermarktRows), [transfermarktRows]);
  const { onTouchStart, onTouchEnd } = useSwipeTabs(activeTab, setActiveTab, setTabTransition);
  const headerVisible = useHideOnScroll();

  useEffect(() => {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

  useEffect(() => {
    setWunschkaderPhase((prev) => {
      if (activeTab === "wunschkader") return "active";
      return prev === "hidden" ? "hidden" : "exiting";
    });
  }, [activeTab]);

  // Fallback, falls onAnimationComplete durch schnelles wiederholtes
  // Tab-Wechseln unterbrochen wird und nicht zuverlaessig einmalig feuert
  // (siehe Spec, Abschnitt Fehlerbehandlung) - idempotent, setzt nur das,
  // was der Callback ohnehin setzen wuerde. Rein kosmetisch: "hidden" steuert
  // nur noch display:none am Wrapper (Grid-Hoehe/Klick-Durchlaessigkeit),
  // WunschkaderTab selbst bleibt in jedem Fall gemountet, State geht hier
  // nicht mehr verloren.
  useEffect(() => {
    if (wunschkaderPhase !== "exiting") return;
    const timeoutId = window.setTimeout(() => {
      setWunschkaderPhase((prev) => (prev === "exiting" ? "hidden" : prev));
    }, WUNSCHKADER_EXIT_FALLBACK_MS);
    return () => window.clearTimeout(timeoutId);
  }, [wunschkaderPhase]);

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), []);

  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then(async (snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte später erneut versuchen.");
          setLoadState("error");
          return;
        }
        const snapshotData = snap.data() as DashboardSnapshot;
        setData(snapshotData);

        // Live-Stand bevorzugt (wird von WunschkaderTab per Auto-Save-Effekt
        // ueber saveTargets() sofort beschrieben, ohne auf den naechsten
        // Pipeline-Lauf zu warten) -
        // eigenstaendig abgefangen: ein Wunschkader-Lesefehler darf NICHT den
        // gesamten Dashboard-Ladevorgang scheitern lassen, deshalb kein
        // gemeinsames Promise.all() mit dem Snapshot-Read oben. Fallback auf
        // die Snapshot-Kopie, wenn das Dokument noch nie gespeichert wurde
        // oder der Read fehlschlaegt.
        try {
          const wunschkaderSnap = await getDoc(doc(db, "wunschkader", "current"));
          if (wunschkaderSnap.exists()) {
            const raw = wunschkaderSnap.data() as { targets?: RawWunschkaderTarget[] };
            setWunschkader({ targets: raw.targets ?? [] });
          } else {
            setWunschkader({ targets: snapshotData.wunschkader_targets ?? [] });
          }
        } catch {
          setWunschkader({ targets: snapshotData.wunschkader_targets ?? [] });
        }

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
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        {/* z-30 haelt den Header oberhalb JEDES Tab-Detail-Modals (durchgaengig
            z-10, siehe z.B. WunschkaderTab.tsx) und oberhalb des mobilen
            Menue-Overlays (z-20) - sonst faengt ein offenes Modal Klicks auf
            "Menü öffnen" ab (deckt per fixed inset-0 den ganzen Screen ab,
            gewinnt sonst den Stacking-Tie gegen den Header per DOM-Reihenfolge),
            und Tab-Wechsel waeren bei offenem Modal nicht mehr erreichbar -
            Voraussetzung fuer WunschkaderStatePersistsAcrossTabSwitch.spec.ts. */}
        <header
          className={`sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4 transition-transform duration-200 dark:border-slate-800 dark:bg-slate-950 sm:static sm:!translate-y-0 ${
            headerVisible ? "translate-y-0" : "-translate-y-full"
          }`}
        >
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Menü öffnen"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 sm:hidden dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <IconMenu className="h-5 w-5" />
            </button>
            <h1 className="flex items-center gap-2.5 text-lg font-semibold text-slate-900 dark:text-slate-50">
              <img src={`${import.meta.env.BASE_URL}logo.svg`} alt="" className="h-6 w-6" />
              KickbaseAgent
            </h1>
          </div>
          {data?.generated_at && (
            <p
              className="text-xs text-slate-400 dark:text-slate-500"
              title={data.generated_at}
            >
              Stand: {formatRelativeTime(data.generated_at, new Date(now))}
            </p>
          )}
        </header>
        <nav className="hidden gap-1 overflow-x-auto border-b border-slate-200 bg-white px-6 sm:flex dark:border-slate-800 dark:bg-slate-950">
          {TABS.map((tab) => {
            const isActive = ACTIVE_TABS.has(tab.key);
            const isSelected = tab.key === activeTab;
            const Icon = TAB_ICON[tab.key];
            const iconTone = !isActive
              ? "text-slate-500"
              : isSelected
                ? "text-brand-600 dark:text-brand-400"
                : "text-slate-500 hover:text-slate-600 dark:hover:text-slate-300";
            return (
              <button
                key={tab.key}
                type="button"
                disabled={!isActive}
                onClick={() => {
                  if (!isActive) return;
                  setTabTransition({ kind: "fade" });
                  setActiveTab(tab.key);
                }}
                className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-3 text-sm transition-colors ${
                  isSelected
                    ? "border-brand-500 font-semibold text-slate-900 dark:text-slate-50"
                    : isActive
                      ? "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-50"
                      : "cursor-not-allowed border-transparent text-slate-400 dark:text-slate-600"
                }`}
              >
                {Icon && <Icon className={`h-5 w-5 shrink-0 ${iconTone}`} aria-hidden="true" />}
                {tab.label}
                {!isActive && <span className="ml-1 text-xs">(bald)</span>}
              </button>
            );
          })}
        </nav>
        <AnimatePresence>
          {mobileMenuOpen && (
            <MobileTabMenu
              activeTab={activeTab}
              onSelect={(key) => {
                setTabTransition({ kind: "fade" });
                setActiveTab(key);
              }}
              onClose={() => setMobileMenuOpen(false)}
            />
          )}
        </AnimatePresence>
        <main className="px-6 py-6" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-900 sm:hidden dark:text-slate-100">
            {TAB_ICON[activeTab] &&
              (() => {
                const Icon = TAB_ICON[activeTab];
                return <Icon className="h-6 w-6 shrink-0" aria-hidden="true" />;
              })()}
            {TABS.find((t) => t.key === activeTab)?.label}
          </h2>
          {loadState === "loading" && activeTab !== "feedback" && (
            <p className="text-sm text-slate-500 dark:text-slate-400">Lade Daten…</p>
          )}
          {loadState === "error" && activeTab !== "feedback" && (
            <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
          )}
          {/* Snapshot geladen, aber noch im alten Schema (kein "players"-Feld) - kein
              ErrorBoundary vorhanden, also gezielt abfangen statt weiss auf weiss
              abzustuerzen (siehe Review-Fund 2026-07-29). Bewusst KEIN frueher
              return mehr: sonst waere die Tab-Leiste (und damit der Feedback-Tab)
              in genau diesem Zustand unerreichbar. Alle datenabhaengigen Tabs
              unten pruefen deshalb zusaetzlich auf data.players - "hidden" allein
              wuerde React nicht vom Mounten (und Crashen) abhalten. */}
          {loadState === "ready" && data && !data.players && activeTab !== "feedback" && (
            <p className="p-6 text-sm text-slate-500 dark:text-slate-400">
              Snapshot noch im alten Schema — der nächste Pipeline-Lauf schreibt das neue Format automatisch (bis zu ~2h,
              oder manuell über GitHub Actions anstoßen).
            </p>
          )}
          <div className="grid">
            {/* WunschkaderTab bleibt absichtlich IMMER gemountet, solange Daten
                geladen sind - wunschkaderPhase steuert nur noch display:none
                (nicht mehr, ob die Komponente ueberhaupt im Baum ist). Damit
                ueberlebt ihr lokaler React-State (Notiz, offenes Detail-Modal)
                jede Verweildauer auf einem anderen Tab, unabhaengig von jeder
                Animationsdauer - kein Zeitfenster, keine Race-Condition (siehe
                WunschkaderStatePersistsAcrossTabSwitch.spec.ts, insbesondere
                den kuenstlichen Delay dort). display:none statt Unmount haelt
                trotzdem die urspruengliche Grid-Stack-Absicht ein: eine
                unsichtbare, faktisch verschwundene Karte darf weder Grid-Hoehe
                beanspruchen noch Klicks auf dem jetzt sichtbaren Tab abfangen. */}
            {data && data.players && wunschkader && (
              <motion.div
                style={{ gridArea: "1 / 1", display: wunschkaderPhase === "hidden" ? "none" : undefined }}
                variants={wunschkaderFadeVariants}
                initial="initial"
                animate={wunschkaderPhase === "active" ? "animate" : "exit"}
                onAnimationComplete={() => {
                  setWunschkaderPhase((prev) => (prev === "exiting" ? "hidden" : prev));
                }}
              >
                <WunschkaderTab data={data} wunschkader={wunschkader} onSaved={(targets) => setWunschkader({ targets })} />
              </motion.div>
            )}

            <AnimatePresence mode="wait">
              {(() => {
                if (activeTab === "wunschkader") return null;
                let content: JSX.Element | null = null;
                if (activeTab === "dashboard" && data && data.players && wunschkader) {
                  content = (
                    <DashboardTab data={data} wunschkader={wunschkader} transfermarktRows={transfermarktRows} now={now} />
                  );
                } else if (activeTab === "spekulation" && data && data.players) {
                  content = (
                    <SpekulationTab
                      rows={spekulationRows}
                      now={now}
                      mlMetrics={data.ml_metrics}
                      mlMetrics3d={data.ml_metrics_3d ?? null}
                      bidHistory={data.bid_premium_history ?? []}
                      positionNeed={data.position_need ?? {}}
                    />
                  );
                } else if (activeTab === "team" && data && data.players && wunschkader) {
                  content = <EigenesTeamTab data={data} wunschkader={wunschkader} />;
                } else if (activeTab === "alle-spieler" && data && data.players) {
                  content = <AlleSpielerTab data={data} />;
                } else if (activeTab === "transfermarkt" && data && data.players) {
                  content = <TransfermarktTab data={data} rows={transfermarktRows} now={now} />;
                } else if (activeTab === "liga" && data && data.players) {
                  content = <LigaanalyseTab data={data} />;
                } else if (activeTab === "ml-genauigkeit" && data && data.players) {
                  content = <MlGenauigkeitTab data={data} />;
                } else if (activeTab === "feedback") {
                  content = <FeedbackTab now={now} />;
                }
                return (
                  <motion.div
                    key={activeTab}
                    style={{ gridArea: "1 / 1" }}
                    variants={tabTransition.kind === "fade" ? fadeVariants : slideFadeVariants(tabTransition.direction)}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                  >
                    {content}
                  </motion.div>
                );
              })()}
            </AnimatePresence>
          </div>
        </main>
      </div>
    </MotionConfig>
  );
}
