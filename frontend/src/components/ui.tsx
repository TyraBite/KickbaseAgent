import { useState, type ReactNode } from "react";

export const POSITION_ABBR: Record<string, string> = {
  Torwart: "TW",
  Abwehr: "ABW",
  Mittelfeld: "MF",
  Sturm: "ST",
};

// Offizielle 3-Buchstaben-Kuerzel (DFL/TV-Uebertragung, z.B. Sky/Kicker),
// per WebSearch gegengecheckt (siehe Konversation, 2026-07-28). Nach
// team_name geschluesselt (steht schon seit Phase 1 in jeder Zeile, reines
// FE-Mapping ohne Firestore-Push/Cron-Abhaengigkeit) - dient sowohl als
// Fallback-Badge-Text als auch als Wappen-Dateiname (kein team_id noetig,
// das Kuerzel selbst ist schon ASCII-sicher, robuster als der Vereinsname
// mit Sonderzeichen wie "M'gladbach"). Unbekannter Vereinsname faellt auf
// die ersten 3 Buchstaben zurueck.
export const TEAM_ABBR: Record<string, string> = {
  Bayern: "FCB",
  Augsburg: "FCA",
  Bremen: "SVW",
  Dortmund: "BVB",
  Elversberg: "SVE",
  Frankfurt: "SGE",
  Freiburg: "SCF",
  Hamburg: "HSV",
  Hoffenheim: "TSG",
  Köln: "KOE",
  Leipzig: "RBL",
  Leverkusen: "B04",
  "M'gladbach": "BMG",
  Mainz: "M05",
  Paderborn: "SCP",
  Schalke: "S04",
  Stuttgart: "VFB",
  "Union Berlin": "FCU",
};

export function teamAbbr(teamName: string | null): string {
  if (teamName && TEAM_ABBR[teamName]) return TEAM_ABBR[teamName];
  return (teamName ?? "???").slice(0, 3).toUpperCase();
}

// Kickbase liefert selbst keine Logo-URL - Wappen liegen self-hosted unter
// public/crests/{TEAM_ABBR}.svg (vom User zu besorgen). Fehlt eine Datei
// (noch) oder ist der Vereinsname unbekannt, faellt die Kachel auf das
// TV-Kuerzel-Badge zurueck statt ein kaputtes Bild-Icon zu zeigen - Wappen
// koennen nach und nach ergaenzt werden.
export function TeamCrest({ teamName }: { teamName: string | null }) {
  const [failed, setFailed] = useState(false);
  const abbr = teamAbbr(teamName);
  if (!teamName || failed) {
    return (
      <span className="flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md bg-slate-200 px-1 text-[9px] font-semibold tracking-tight text-slate-600 dark:bg-slate-700 dark:text-slate-300">
        {abbr}
      </span>
    );
  }
  return (
    <img
      src={`${import.meta.env.BASE_URL}crests/${abbr}.svg`}
      alt={teamName}
      onError={() => setFailed(true)}
      className="h-6 w-6 shrink-0 rounded-full object-contain"
    />
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right font-medium tabular-nums text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}

export function Badge({ tone, children }: { tone: "good" | "warn" | "crit"; children: ReactNode }) {
  const toneClass = {
    good: "bg-brand-100 text-brand-800 dark:bg-brand-950 dark:text-brand-300",
    warn: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    crit: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  }[tone];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>;
}

// 1:1 Portierung von signalPill() aus der bestehenden index.html - gleiche
// Schwellen (DATA.signal_thresholds), gleiche 3 Zustaende.
export function SignalBadge({
  signal,
  thresholds,
}: {
  signal: number | null | undefined;
  thresholds: { good: number; critical: number };
}) {
  if (signal === null || signal === undefined) {
    return <span className="text-slate-400 dark:text-slate-500">nicht kalibriert</span>;
  }
  const tone = signal > thresholds.good ? "good" : signal < thresholds.critical ? "crit" : "warn";
  const label = signal > thresholds.good ? "unter Fairwert" : signal < thresholds.critical ? "Prämie" : "im Rauschen";
  return (
    <Badge tone={tone}>
      {signal.toFixed(2)} · {label}
    </Badge>
  );
}
