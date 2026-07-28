// 1:1 übernommen aus der bestehenden index.html (fmtNum/fmtSigned/mlCell),
// nur als benannte Exporte statt globaler Funktionen.

export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return Math.round(n).toLocaleString("de-DE");
}

export function fmtSigned(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return (n > 0 ? "+" : "") + fmtNum(n);
}

export function trendClass(n: number | null | undefined): string {
  if (n === null || n === undefined) return "text-slate-400 dark:text-slate-500";
  if (n > 0) return "text-brand-600 dark:text-brand-400";
  if (n < 0) return "text-red-600 dark:text-red-400";
  return "text-slate-400 dark:text-slate-500";
}

// Analog zu _format_duration() in src/dashboard_export.py, fuer den
// client-seitig live nachgerechneten Auktions-Countdown (auction_expires_at).
export function formatDurationMs(ms: number): string {
  const totalMinutes = Math.max(Math.round(ms / 60_000), 0);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const restHours = hours % 24;
    return `${days}d ${restHours}h`;
  }
  return `${hours}h ${minutes}m`;
}

// 5-stufiger Pfeil: Vorzeichen = Richtung, Betrag ueber `flat`/`strong` = Stufe.
// Aufrufer uebergeben feldspezifische Schwellen (siehe SpekulationTab), keine
// hartkodierte Zahlendopplung hier. Bewusst alle 5 Glyphen aus dem gleichen
// Unicode-Arrows-Block (U+2190-2199) statt der Geometric-Shapes-Dreiecke
// (▲/▼) - Dreiecke rendern auf manchen Systemfonts fest-farbig statt der
// CSS-Textfarbe zu folgen (User-Feedback: ▲/▼ blieben immer gruen).
export function trendArrow(
  n: number | null | undefined,
  { flat, strong }: { flat: number; strong: number }
): string {
  if (n === null || n === undefined || n === 0) return "→";
  const abs = Math.abs(n);
  const up = n > 0;
  if (abs < flat) return "→";
  if (abs > strong) return up ? "↑" : "↓";
  return up ? "↗" : "↘";
}
