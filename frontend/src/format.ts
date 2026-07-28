// 1:1 uebernommen aus der bestehenden index.html (fmtNum/fmtSigned/mlCell),
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
  if (n === null || n === undefined) return "text-neutral-400 dark:text-neutral-500";
  if (n > 0) return "text-emerald-600 dark:text-emerald-400";
  if (n < 0) return "text-red-600 dark:text-red-400";
  return "text-neutral-400 dark:text-neutral-500";
}
