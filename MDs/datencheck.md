# Datencheck — bekannte Probleme im Dump

Diese Liste gegen jeden neuen Dump prüfen. Behobene Punkte in den Abschnitt
`Behoben` verschieben, damit sie nicht mehr erwähnt werden.

Stand: 2026-07-25, geprüft gegen den Dump vom 2026-07-25 (Saison 26/27,
vor Spieltag 1).

**Hinweis zur Nummerierung:** Beim Stand 2026-07-25 wurde neu durchnummeriert,
weil drei Punkte behoben waren. Alte Verweise auf „Punkt 5" (Spieltagspunkte)
zeigen jetzt auf Punkt 4.

## Offen

### 1. Anbieterfeld liefert Namen, das Preis-Delta erkennt nichts mehr
Die Anbieter-Erkennung funktioniert: Managernamen kommen korrekt durch
(beobachtet: Fassii, Bobetinho, Fleischmanns, Thommi Kessler, senf). Aber alle
Mitspieler-Angebote außer denen von *senf* stehen exakt auf dem Marktwert.
Nur senf setzt manuelle Preise, beobachtet +11,1 %, +12,2 %, +26,3 %, +45,8 %.

**Konsequenz:** Für die Unterscheidung „Systemangebot vs. Mitspieler" jetzt das
Anbieterfeld verwenden, nicht mehr das Delta. Ein Delta von 0 % bei einem
Mitspieler-Angebot heißt **nicht** „kein Verhandlungsspielraum", sondern nur
„kein Aufschlag gesetzt". Das Delta bleibt nützlich, um überteuerte Angebote zu
erkennen.

### 2. Einsatzquote um Faktor 34 zu hoch
Die Division durch die Zahl der Spieltage fehlt. Beobachtet: „Chaves
Einsatzquote ~1507 %" entspricht 15,07 Einsätzen, also 44 %.

**Konsequenz:** Ausgabewert durch 34 teilen, bevor die Schwellen aus
`methodik.md` angewendet werden. Ohne diese Korrektur landet jeder Spieler
oberhalb jeder Schwelle und die Metrik ist wertlos.

### 3. Kosten pro Punkt gegen falschen Divisor
Der Dump rechnet `Marktwert / Punkte gesamt`, `methodik.md` definiert
`Marktwert / Punkteschnitt`. Beispiel Chaves: Dump 4.110, korrekt 61.900.

**Konsequenz:** Die Dump-Werte sind um den Faktor „Einsatzzahl" zu niedrig und
mit den Schwellen 100k/150k nicht vergleichbar. Selbst nachrechnen. Wenn im
Skript eine der beiden Definitionen bleiben soll, dann die aus `methodik.md` —
sonst müssen dort die Schwellen neu kalibriert werden.

### 4. Flag „im Preisverfall" ist unbrauchbar
Es korreliert nicht mit der Wertentwicklung, teilweise invers. Beobachtet im
Dump vom 2026-07-25:

| Spieler | 7-Tage-Änderung | Lage | Flag |
|---|---|---|---|
| Baumgartner | −2.331.501 | auf dem 92-Tage-Tief | **nicht** gesetzt |
| Stange | +1.597.646 | auf dem 92-Tage-Hoch | gesetzt |
| Suleiman | +1.907.570 | auf dem 92-Tage-Hoch | gesetzt |
| Funk | ±0 | konstant auf 500.000 | gesetzt |

**Konsequenz:** Feld ignorieren. Stattdessen 7-Tage-Veränderung plus
Tiefst/Höchst über 92 Tage verwenden — die beiden Felder sind plausibel und
reichen für die Trendaussage vollständig aus.

### 5. Tiefstwert `0 €` statt 500.000
Beobachtet bei Becker, Rohr, Lerma, Petkov, Schmahl, Stalmach, Suso,
Zimmerschied, Pruhs. 500.000 ist der Kickbase-Mindestmarktwert, ein echter
Tiefstwert von 0 ist unmöglich.

**Konsequenz:** `0` heißt fehlende Historie im 92-Tage-Fenster, typisch bei
Aufsteiger-Spielern und Neuzugängen. Nicht als Absturz interpretieren und nicht
als „Untergrenze erreicht" im Sinne von `methodik.md` lesen.

### 6. Eigener Teamwert fehlt, obwohl aus dem Kader berechenbar
`Teamwert: noch keine Saisondaten` bei einem vollen Kader kann nicht stimmen.
Die Summe der Kadermarktwerte lag am 2026-07-25 bei 82.856.923.

**Konsequenz:** Den Wert lokal aus dem Kader aufsummieren, statt auf das
API-Feld zu warten. `Punkte gesamt: noch keine Saisondaten` ist vor Spieltag 1
dagegen plausibel und muss nach dem 1. Spieltag neu geprüft werden.

### 7. „noch keine Saisondaten" bleibt mehrdeutig
Die Beschriftung ist besser als das frühere `None`, aber die drei Ursachen
bleiben ununterscheidbar: Key im Response fehlt, Wert ist echt leer, oder
API-Call fehlgeschlagen.

**Konsequenz:** Bei Ligatabellen-Werten nicht annehmen, dass ein Manager 0
Punkte hat. Vor Spieltag 1 ist ein leerer Wert erwartbar; ab Spieltag 2 ist er
ein Verdachtsfall. Wenn machbar: im Skript zwischen „Key fehlt" und „Wert ist
null" unterscheiden und zwei verschiedene Texte ausgeben.

### 8. Spieltagspunkte in der Ligatabelle — in diesem Dump nicht prüfbar
Früher beobachtet: Werte bis 13.479, während elf Spieler realistisch auf
1.000–2.500 Punkte pro Spieltag kommen. Im Dump vom 2026-07-25 liefert die
Ligatabelle für alle acht Manager gar keine Werte, der Punkt bleibt daher offen
und unbestätigt.

**Konsequenz:** Nach dem 1. Spieltag 2026/27 erneut prüfen. Bis dahin
Spieltagspunkte nur als relative Größen zwischen Managern verwenden, nie als
absolute Punktzahlen.

### 9. Status-Codes ohne verifizierte Bedeutung
Siehe `codes.md`. Beobachtet im Dump vom 2026-07-25: 1, 2, 4.

## Behoben

### Eigene Kaderspieler in der Transfermarkt-Liste (behoben 2026-07-25)
Keiner der 12 Kaderspieler erschien in den 56 Marktangeboten.
**Beim Prüfen aufpassen:** „Stange" (eigener Kader, HSV, Sturm) und „Stage"
(Markt, Bremen, Mittelfeld) sind zwei verschiedene Spieler. Ein
Namensabgleich per Teilstring würde hier falsch anschlagen.

### Kein Vereinsfeld (behoben 2026-07-25)
Jeder Spieler in Kader und Markt hat jetzt einen Verein. Das hat die Gruppe
„nicht identifizierbar" praktisch aufgelöst. Es bleibt der Restfall, dass ein
Verein zwei Spieler mit demselben Nachnamen hat — siehe
`spieler-bewertung.md`, Abschnitt „Nicht eindeutig identifizierbar".

### `Punkte gesamt` fehlte bei Marktspielern (behoben 2026-07-25)
Marktspieler haben jetzt Punkteschnitt **und** Punkte gesamt. Damit ist die
Einsatzquote auch für Kaufkandidaten rechenbar, und der Ausweichweg über den
Marktwert als schwächeren Indikator ist nicht mehr nötig.

### Spieltag-/Termin-Semantik (bestätigt 2026-07-25)
„Spieltag 1, nächster Termin in 34 Tagen" ergibt vom 2026-07-25 aus den
2026-08-28 — exakt der bekannte 1. Spieltag. Die Interpretation „Spieltag-Index
= der nächste anstehende Spieltag, Termin = dessen Datum" ist damit für diesen
Dump bestätigt. Nach dem 1. Spieltag noch einmal gegenprüfen, ob der Index dann
auf 2 springt.

### Trend-Codes ersetzt (behoben 2026-07-25)
Der Dump liefert keine Trend-Codes mehr, sondern die 7-Tage-Veränderung in
Euro. Das ist die bessere Information und macht die Auflösungsarbeit an den
Trend-Codes überflüssig. Siehe `codes.md`.
