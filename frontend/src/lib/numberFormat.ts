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

// Entfernt genau die Ziffer an Zeichenposition `digitPosition` in `formatted`
// und formatiert das Ergebnis neu - fuer den expliziten Backspace/Delete-
// Tastendruck-Handler in AlleSpielerTab.tsx (MarketValueInput), wenn das
// zu loeschende Zeichen selbst ein Tausenderpunkt ist. Ein simples
// formatThousands(rawDigitsAfterDeletion) reicht dafuer nicht: entfernt man
// nur den Trennpunkt, aendern sich die zugrunde liegenden Ziffern gar nicht -
// React sieht denselben Wert, rendert nicht neu, und der Cursor springt beim
// naechsten Tastendruck ans Feldende (Review-Fund, Critical #2). Diese
// Funktion loescht deshalb stattdessen explizit die dem Trennpunkt
// benachbarte Ziffer (die tatsaechliche Nutzerabsicht bei Backspace/Delete
// neben einem Trennpunkt).
//
// `digitPosition` muss auf eine Ziffer in `formatted` zeigen (nicht auf den
// Trennpunkt selbst) - der Aufrufer waehlt je nach Richtung die Ziffer vor
// (Backspace) bzw. nach (Delete) dem Trennpunkt.
export function deleteDigitAt(formatted: string, digitPosition: number): { formatted: string; cursorIndex: number } {
  const digits = formatted.replace(/\D/g, "");
  const digitOrdinal = digitCountBefore(formatted, digitPosition);
  if (digitOrdinal < 0 || digitOrdinal >= digits.length) {
    return { formatted, cursorIndex: formatted.length };
  }
  const newDigits = digits.slice(0, digitOrdinal) + digits.slice(digitOrdinal + 1);
  const newFormatted = formatThousands(newDigits);
  return { formatted: newFormatted, cursorIndex: cursorIndexForDigitCount(newFormatted, digitOrdinal) };
}
