// Hilfsfunktionen fuer Tausenderpunkte in Zahlen-Eingabefeldern (die
// Marktwert-Min/Max-Filter in AlleSpielerTab.tsx). <input type="number">
// lehnt Punkte als Tausendertrennzeichen als ungueltiges Zeichen ab -
// deshalb formatieren wir hier reine Ziffern-Strings manuell fuer ein
// type="text"-Feld mit inputMode="numeric" (behaelt die numerische
// Mobil-Tastatur, User-Feedback d390f441).

// Entfernt alles Nicht-Ziffern und formatiert das Ergebnis mit
// de-DE-Tausenderpunkten (z.B. "500000" -> "500.000"). Leerer String bleibt
// leer, damit ein Feld waehrend des Tippens leer sein darf (siehe
// AlleSpielerTab.tsx - marketValueMinInput/marketValueMaxInput haelt
// genau deshalb einen String statt einer Number).
export function formatThousands(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits === "") return "";
  return Number(digits).toLocaleString("de-DE");
}

// Kehrt formatThousands() um: entfernt die Punkte (und jedes andere
// Nicht-Ziffern-Zeichen) wieder und liefert die reine Zahl. Leerer/
// ungueltiger Input liefert NaN, damit bestehende "Number(x) || default"-
// Fallback-Stellen unveraendert weiterfunktionieren (NaN ist falsy).
export function parseThousands(value: string): number {
  const digits = value.replace(/\D/g, "");
  return digits === "" ? NaN : Number(digits);
}

// Zaehlt Ziffern vor `index` in `value` - die "logische" Cursor-Position
// unabhaengig von eingestreuten Formatierungspunkten. Wird zusammen mit
// cursorIndexForDigitCount() genutzt, um den Cursor nach dem Neu-Formatieren
// an derselben logischen Stelle zu halten (sonst springt er beim Tippen ans
// Feldende).
export function digitCountBefore(value: string, index: number): number {
  let count = 0;
  for (let i = 0; i < index && i < value.length; i++) {
    if (/\d/.test(value[i])) count++;
  }
  return count;
}

// Kehrt digitCountBefore() um: findet die Zeichen-Position in `formatted`
// direkt nach der `digitCount`-ten Ziffer. Faellt auf das Stringende zurueck,
// falls `formatted` weniger Ziffern enthaelt als `digitCount` (z.B. wenn der
// Nutzer eine Ziffer geloescht hat).
export function cursorIndexForDigitCount(formatted: string, digitCount: number): number {
  if (digitCount <= 0) return 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) {
      seen++;
      if (seen >= digitCount) return i + 1;
    }
  }
  return formatted.length;
}
