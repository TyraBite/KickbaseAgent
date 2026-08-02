# Status- und Trend-Codes (Kickbase v4)

Diese Datei ist ein Arbeitsdokument. Bedeutungen selbst im Kickbase-Client
gegenprüfen und hier eintragen. Nichts in die Verifiziert-Tabelle eintragen,
was nicht verifiziert ist.

Solange ein Code nicht in der Verifiziert-Tabelle steht, gilt er als
**unbekannt** — dann in der Antwort darauf hinweisen, dass ich ihn im Client
gegenchecken sollte, und keine Bedeutung annehmen.

Stand: 2026-07-25

## Status-Codes

| Code | Bedeutung | Verifiziert am |
|---|---|---|
| kein Code / 0 | unauffällig / einsatzfähig | — |
| 1 | Verletzt (rotes Kreuz, Tooltip "Injured"/"out for the time being") | 2026-07-29, direkt in der App gegengecheckt (Ben Seghir) |
| 2 | Angeschlagen (Pillen-Symbol, Tooltip "Sick: Adductor problems - misses team training" - Kickbase nennt es "Sick", gemeint ist ein day-to-day-Wehwehchen ohne echten Ausfall) | 2026-07-29, direkt in der App gegengecheckt (Matsima) |
| 4 | Im Aufbau (Hantel-Symbol, Tooltip "Rehab") | 2026-07-29, direkt in der App gegengecheckt (Hollerbach, Ben Seghir) |
| 8 | ? | |

Alle 3 beobachteten Codes (1, 2, 4) sind jetzt verifiziert. Nur Code 8 (nie
beobachtet) bleibt offen.

**Korrektur-Verlauf (2026-07-29)**: erster Check ergab fälschlich "2 =
Verletzt, 4 = Im Aufbau" (Icon richtig zugeordnet, aber am falschen Spieler
verglichen). Zweiter Check an einem konkreten Code-1-Spieler (Ben Seghir,
rotes Kreuz, "Injured"/"out for the time being") zeigte: 1 ist "Verletzt".
Dritter Check an Matsima (Code 2, Pillen-Symbol, Tooltip explizit gelesen:
"Sick: Adductor problems - misses team training") bestätigte 2 = "Angeschlagen"
und Hollerbach (Code 4, Hantel-Symbol, "Rehab") bestätigte 4 = "Im Aufbau"
endgültig. Kurz erwogene Gegentheorie "4 = fit, weil Großteil der Spieler
diesen Status hat" wurde anhand echter Daten verworfen: im lokalen Snapshot
vom 25.-28.07. hat Code 0 (kein Status) 135 Treffer in market_listings,
Code 4 nur 6 - Code 4 ist eine kleine Minderheit, nicht der Großteil. Alte
Arbeitshypothese unten (1 = verletzt, 2 = angeschlagen, nur aus Presse-
Korrelation) war in der Grundtendenz richtig, aber nie direkt bestätigt -
jetzt durch echte App-Beobachtung ersetzt.

### Beobachtungen — noch nicht verifiziert, nicht darauf bauen

Im Dump vom 2026-07-25 tragen zehn Spieler einen Status-Code. Für sechs davon
ließ sich der Zustand am selben Tag über Vereins- und Presseberichte
recherchieren. Ergebnis:

| Code | Spieler | Recherchierter Zustand am 2026-07-25 |
|---|---|---|
| 1 | Ben Seghir | Muskelverletzung rechter Oberschenkel, MRT-Bestätigung durch Leverkusen 19./20.07.2026, Ausfalldauer offen |
| 1 | Baumgartner | Sehnenriss am Hüfteinsatz, Operation Anfang Juni 2026, WM verpasst |
| 1 | Nsoki | nichts gefunden |
| 2 | Stange | fehlte beim HSV-Testspiel |
| 2 | Baldé | fehlte beim HSV-Testspiel |
| 2 | Giannoulis | musste die Trainingseinheit am 21.07.2026 vorzeitig abbrechen |
| 2 | Matsima | fehlte am 21.07.2026 komplett im Training (Adduktorenprobleme) |
| 2 | Pauli, Castrop, Zimmerschied | nichts gefunden |
| 4 | Rönnow | nichts Aktuelles gefunden |
| 4 | Røssing-Lelesiit | nichts gefunden |

**Arbeitshypothese:** `1` = längerer Ausfall / verletzt, `2` = angeschlagen /
fraglich, `4` = unbekannt.

**Warum das noch kein Beleg ist:** Sechs Korrelationen sind mehr als eine
Vermutung, aber ein Spieler kann ein Testspiel auch aus anderen Gründen
verpassen — Urlaub, Aufbautraining, taktische Schonung. Die Zuordnung von `2`
stützt sich ausschließlich auf Abwesenheiten, nicht auf eine Diagnose. Bei `1`
sind beide Fälle bestätigte Verletzungen mit offener Dauer, das ist die
stärkere Evidenz.

Die frühere Beobachtung passt dazu: ein Spieler mit Status 2 hatte
gleichzeitig einen Punkteschnitt von 5 bei 4,07 Mio. Marktwert. Das war Stange —
der niedrige Schnitt kommt aber von seiner Rolle als Talent ohne
Startelfeinsätze, nicht von einem Langzeitausfall. **Die alte Deutung
„Muster hoher Marktwert, kaum Punkte passt zu einem Langzeitausfall" war bei
diesem Spieler falsch und ist damit erledigt.**

### So lässt sich das in zehn Minuten auflösen

Diese fünf Spieler im Kickbase-Client aufrufen und notieren, welches Symbol
oder welcher Text dort steht:

- Ben Seghir (Leverkusen) und Baumgartner (Leipzig) — beide Code 1
- Stange (HSV), Giannoulis und Matsima (Augsburg) — alle Code 2
- Rönnow (Union Berlin) — Code 4, der einzige völlig offene Fall, und
  gleichzeitig ein Kaufkandidat. Deshalb der wichtigste von den sechs.

Wenn der Client bei den ersten zwei „verletzt" und bei den nächsten drei
„angeschlagen" oder „fraglich" zeigt, ist die Zuordnung eindeutig und kann in
die Verifiziert-Tabelle. Codes 0 und 8 sind bisher nie aufgetreten und bleiben
offen.

**Falls es eine Bitmaske ist:** Dann müsste ein Spieler mit mehreren
Eigenschaften einen Summenwert wie 3, 5 oder 6 tragen. Solche Werte sind bisher
nie beobachtet worden — bisher immer nur 1, 2 oder 4 einzeln. Das spricht eher
für einen einfachen Enum, ist aber bei nur zehn Datenpunkten kein Beweis. Wenn
irgendwann ein Wert wie 3 oder 6 auftaucht, ist die Bitmasken-Frage damit
beantwortet und dieser Abschnitt gehört überarbeitet.

## Trend-Codes — erledigt, nur zur Dokumentation

**Der Dump liefert seit 2026-07-25 keine Trend-Codes mehr, sondern die
Marktwertveränderung der letzten 7 Tage in Euro.** Das ist die bessere
Information: sie enthält Richtung *und* Größe, statt nur eine Richtung
anzudeuten. Die Auflösungsarbeit an den Trend-Codes ist damit unnötig geworden.

Falls die Codes in einem künftigen Dump wieder auftauchen, hier der letzte
Stand: Verteilung war 7× `1`, 7× `2`, 1× `0`. Anhaltspunkt für `0` =
unverändert: der einzige Spieler mit `0` saß exakt auf dem Mindestmarktwert von
500.000 und konnte sich nicht bewegen. Bei 1 vs. 2 war die Datenlage
widersprüchlich und die Hypothese „1 = fallend" stützte sich auf zwei
Datenpunkte.

Die damals vorgeschlagene Methode zur Auflösung — Marktwerte täglich pro
Spieler speichern und den Code des Vortages gegen die tatsächliche
Wertänderung joinen — lohnt sich trotzdem weiterhin, aber aus einem anderen
Grund: eine eigene Marktwert-Historie macht Trends über mehr als 7 Tage
sichtbar und erlaubt es, Hype-Gipfel wie bei Stange und Suleiman früher zu
erkennen. In der Sommerpause bewegen sich die Werte langsam genug für saubere
Messwerte, ab Saisonstart überlagert die Spieltagsvolatilität das Signal.
