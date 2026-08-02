# Methodik — Kennzahlen und Schwellenwerte

## Einsatzzahl und Einsatzquote

```
Einsätze     ≈ Punkte gesamt / Punkteschnitt
Einsatzquote  = Einsätze / 34
```

Der zentrale Wert für die Stammspieler-Frage. Ein Punkteschnitt allein sagt
nichts: 103 aus 16 Spielen ist etwas völlig anderes als 103 aus 32.

**Achtung, der Dump rechnet beides falsch aus.** Die ausgegebene Einsatzquote
ist um den Faktor 34 zu hoch (die Division fehlt), und `Kosten/Punkt` wird gegen
`Punkte gesamt` statt gegen den Punkteschnitt gerechnet. Details in
`datencheck.md`, Punkte 2 und 3. Beide Werte selbst nachrechnen.

### Stand der Validierung (2026-07-25)

Die Formel wurde gegen externe Einsatzzahlen geprüft. Ergebnis gemischt:

| Spieler | Formel ergibt | Externe Quelle | Treffer? |
|---|---|---|---|
| Ogbus | 18,08 Einsätze | 18 BL-Einsätze 25/26 (Wikipedia) | ja, exakt |
| Chaves | 15,07 Einsätze | 15 BL-Einsätze 25/26 (Ligainsider) | ja, exakt |
| Scherhant | 30,98 Einsätze | 24 BL-Einsätze 25/26 (soccerway) | **nein, +29 %** |
| Urbig (Vorsaison) | ~14 Einsätze | 16 Pflichtspiele (Sky), 405 BL-Minuten (FotMob) | **nein** |

Zwei exakte Treffer sind mehr, als nach dem Urbig-Fall zu erwarten war — die
Formel ist also nicht grundsätzlich kaputt. Aber die Abweichung bei Scherhant
lässt sich nicht wegrechnen: 24 BL-Spiele, dazu Pokal und Europa League ergeben
37 Gesamteinsätze, keine der beiden Zahlen ist 31. Kickbase zählt in manchen
Fällen anders, als die Formel unterstellt, und es ist unklar in welchen.

**Als Ranking-Signal brauchbar, als absolute Zahl nicht belastbar.**
Nie als „der Spieler hat X Spiele gemacht" formulieren, sondern als
„die Daten deuten auf eine Einsatzquote um X % hin". Bei einer Kaufentscheidung
über mehreren Millionen nie allein auf diesen Wert stützen.

**Besser, wo verfügbar:** Ligainsider führt `Einsätze`, `Startelf`,
`Einwechslungen` und `Bank` getrennt. `Startelf / 34` ist die Metrik, die die
Frage tatsächlich beantwortet — Einwechslungen bringen in Kickbase
Minutenpunkte, aber keinen planbaren Startplatz.

### Interpretation

| Quote | Bedeutung |
|---|---|
| über 80 % | echter Stammspieler — **aber siehe Warnung unten** |
| 50–80 % | Rotation, nicht planbar |
| unter 50 % | Ersatzspieler, Wintertransfer oder Verletzung — recherchieren |

Niedrige Quote ist **nicht automatisch** schlecht. Ein Wintertransfer kann
maximal ~17 Spiele haben. Deshalb ist bei jeder Quote unter 70 % mit gutem
Schnitt Recherche Pflicht, statt den Spieler abzuwerten.

**Hohe Quote ist ebenfalls nicht automatisch gut.** Eine Quote über 80 % bei
einem Punkteschnitt unter 55 bedeutet in der Praxis „Dauer-Einwechselspieler",
nicht „Stammspieler". Belegte Fälle vom 2026-07-25:

- Scherhant: 91 % Quote, Schnitt 48 — Ligainsider führt ihn ausdrücklich nur
  als *Alternative* zu Grifo.
- Machino: 95 % Quote, Schnitt 23.
- Mwene: 86 % Quote, Schnitt 49.
- Chukwuemeka: 82 % Quote, Schnitt 47.

Faustregel: **Quote und Schnitt immer zusammen lesen.** Hohe Quote plus
niedriger Schnitt heißt „spielt viel, punktet nicht" — das ist in Kickbase
fast so wertlos wie ein Ersatzspieler und obendrein teurer, weil die hohe
Einsatzzahl den Marktwert stützt.

## Kosten pro Punkt

```
k/Punkt = Marktwert / Punkteschnitt
```

| Wert | Einordnung |
|---|---|
| unter 100k | gut |
| 100–150k | mittel |
| über 150k | teuer |

**Nicht als Hauptkriterium verwenden.** Sehr gute Werte entstehen typischerweise
bei billigen Ersatzspielern (Beispiel: 55er Schnitt bei 622k = 11k/Punkt — der
Spieler ist billig, weil er nicht spielt). Die Metrik taugt zum Vergleich
*innerhalb* einer Gruppe von Spielern mit ähnlicher Einsatzquote.

Umgekehrt gilt: bei einem belegten Stammspieler ist ein Wert über 150k kein
Ausschlussgrund. Leweling liegt bei 252k, Raum bei 211k, Baumann bei 193k —
das ist der Preis für Planbarkeit, und Planbarkeit ist die Zielsetzung. Ein
teurer Stammspieler schlägt einen billigen Rotationsspieler auch dann, wenn die
Metrik das Gegenteil suggeriert.

Für eine positionsrelative, gegen den vollen Live-Datensatz kalibrierte
Fassung dieser Kennzahl siehe den nächsten Abschnitt „Fairwert und Signal".

## Fairwert und Signal (Kosten pro Punkt, positionsrelativ)

Erweitert die Schwellentabelle oben um einen Bezugspunkt: was zahlt die Liga
aktuell für einen Punkt bei einem belegten Stammspieler. Entwickelt in einer
separaten Recherche-Session ohne Live-API-Zugriff, am 2026-07-27 gegen den
vollen Live-Datensatz kalibriert und validiert (nicht nur den ursprünglichen
68-Spieler-Dump) — Skript: `src/player_valuation.py`
(`python -m src.player_valuation`).

```
Referenzmenge = Spieler mit Punkteschnitt > 70, Einsatzquote > 85 %,
                 Marktwert > 500.000, Punkteschnitt vorhanden
K             = Median(Marktwert / Punkteschnitt) über die Referenzmenge
Signal        = K / (Marktwert_Kandidat / Punkteschnitt_Kandidat)
Fairwert      = Punkteschnitt_Kandidat × K   (= Preisobergrenze)
```

**Gültig nur für Spieler, die das Gate bestanden haben**: Startelf-
Erstkandidat laut Ligainsider, keine offene Verfügbarkeitsfrage, letzte
Saison überwiegend Startelf (siehe „Reihenfolge der Prüfung" unten). Ohne
diese drei ist der Punkteschnitt kein Prädiktor und die Zahl bedeutungslos.
Die Einsatzquote hier ist die echte Einsatzzahl aus der Performance-Historie
(letzte abgeschlossene Saison, gespielte Spieltage gezählt), nicht die oben
dokumentierte Näherungsformel aus `datencheck.md` Punkt 2.

### Kalibrierung (Stand 2026-07-27, 453 gescannte Spieler, Referenzmenge n=70)

**Wichtigster Befund: mit K positionsspezifisch rechnen, nicht global.** Die
ursprüngliche Schätzung (3 Datenpunkte, Median 211k) unterschätzte die
Positionsspreizung massiv und hatte sogar die falsche Richtung — die
Hypothese war „Torhüter teuer, Stürmer billig" (aus Baumann/Raum/Leweling
abgeleitet). Der volle Datensatz zeigt das Gegenteil, und die Spreizung ist
kein Rauschen von ±15 %, sondern Faktor ~1,9 zwischen teuerster und
billigster Position:

| Position | K (Median) | n |
|---|---|---|
| Sturm | 282.750 | 9 |
| Abwehr | 192.567 | 23 |
| Mittelfeld | 157.756 | 29 |
| Torwart | 150.802 | 9 |
| **Global (alle Positionen)** | 171.540 | 70 |

Alle vier Positionen haben genug Datenpunkte (Minimum 4, hier 9–29) für einen
eigenen Median — **Positions-K verwenden, nicht global.** Global-K nur als
Fallback, falls eine Position bei einer späteren Kalibrierung unter 4
Datenpunkte fällt.

**Konsistenz-Check bestanden**: Baumann/Raum/Leweling (die 3
Ursprungs-Datenpunkte aus dem 68-Spieler-Dump) tauchen im vollen
Live-Datensatz mit identischem Punkteschnitt und nahezu identischem k/Punkt
wieder auf (Baumann 193.734 vs. 193.000, Raum 211.725 vs. 211.000, Leweling
252.640 vs. 252.000) — die Datenpipeline ist verlässlich, nur die Stichprobe
von 3 Punkten war zu klein, um die Positionsspreizung zu sehen.

### Toleranzband (vorläufig, per Position anwenden)

| Signal | Lesart |
|---|---|
| > 1,25 | Markt bewertet ihn deutlich unter seinem (positionsrelativen) Schnitt — Kandidat, Ursache recherchieren |
| 0,80–1,25 | im Rauschen. Kaufentscheidung allein über Positionsbedarf und Startelf-Beleg |
| < 0,80 | Prämie für etwas, das nicht im Schnitt steckt |

Das Band selbst ist noch nicht gegen den vollen Datensatz neu kalibriert (nur
die Median-Werte oben sind es) — vor einer echten Kaufentscheidung im
Grenzbereich mit Vorsicht behandeln und die Streuung *innerhalb* der
jeweiligen Positions-Referenzmenge prüfen, nicht nur den Median.

### Was offen bleibt

- Die Referenzmenge (n=70 aus 453 Spielern) basiert auf der letzten
  abgeschlossenen Saison (2025/26) — vor Saisonstart 2026/27 unvermeidbar,
  nach ein paar Spieltagen 2026/27 neu kalibrieren.
- n=9 bei Sturm und Torwart ist nutzbar (über dem Minimum von 4), aber dünner
  als Abwehr/Mittelfeld — bei einer Neukalibrierung im Saisonverlauf zuerst
  hier prüfen, ob sich der Wert stabilisiert oder noch wandert.

## Preis-Delta (Anbieter-Erkennung)

```
Delta = (Preis - Marktwert) / Marktwert
```

| Delta | Interpretation |
|---|---|
| 0 % | **kein Aufschlag gesetzt.** Bei Systemangeboten heißt das Festpreis ohne Verhandlungsspielraum, aber auch ohne Bieterwettbewerb — Warten bis kurz vor Ablauf kostet nichts. Bei Mitspieler-Angeboten heißt es nur, dass der Anbieter den Marktwert übernommen hat; ein Gebot darunter ist trotzdem möglich. |
| über 0 % | Mitspieler-Angebot mit Aufschlag. Verhandeln lohnt. Beobachtete Aufschläge: 11–46 %. |

**Seit dem Dump vom 2026-07-25 ist das Anbieterfeld zuverlässig** und ersetzt
das Delta für die Frage „System oder Mitspieler". Siehe `datencheck.md`,
Punkt 1. Das Delta bleibt nützlich, um überteuerte Angebote zu erkennen.

Beobachtung, die sich lohnt zu merken: In der Liga setzt bisher nur **ein**
Manager (senf) manuell Preise über dem Marktwert — und er tut es systematisch
bei Spielern mit hohem historischen Punkteschnitt, die ihren Stammplatz
verloren haben (Gulácsi, Blaswich: beide Ersatztorhüter mit Schnitt über 100).
Das ist ein gezielter Köder für jemanden, der nur auf den Schnitt schaut.

## Der Bayern-Effekt (Mustererkennung)

Wiederkehrendes Muster: hoher Punkteschnitt bei niedriger Einsatzquote und
hohem Marktwert = Rotationsspieler bei einem Spitzenklub. Solche Spieler
punkten stark, wenn sie spielen (starkes Team, viele Siege, Zu-null-Spiele),
sind aber nicht planbar aufstellbar.

In den Daten sieht das wie ein Topspieler aus. Für die Zielsetzung
„jede Position mit Stammspielern besetzen" ist es das Gegenteil.

Bisher beobachtet bei Urbig und H. Ito (Bayern), Tella (Leverkusen, 50 % Quote
bei Schnitt 68) und Matsima (Augsburg, 53 % bei Schnitt 82). Der Effekt ist
also nicht auf Bayern beschränkt — er tritt bei jedem Klub mit tiefem Kader
auf. Der Name kann bleiben, die Prüfung muss breiter laufen.

## Der Hype-Gipfel (Mustererkennung, neu 2026-07-25)

Drei Merkmale gleichzeitig:

1. Marktwertsprung von über 1,5 Mio. in 7 Tagen
2. Marktwert steht exakt auf dem 92-Tage-Höchstwert
3. Punkteschnitt niedrig oder gar nicht vorhanden

Das ist kein Leistungssignal, sondern eine Nachrichtenlage: ein Turniererfolg,
ein Transfergerücht, eine Beförderungsmeldung. Kickbase-Marktwerte reagieren
auf Kaufnachfrage, und die reagiert auf Schlagzeilen.

Belegte Fälle: **Stange** (+1,60 Mio. in 7 Tagen, Punkteschnitt 5, Ursache
U19-EM-Torschützenkönig im Juli 2026) und **Suleiman** (+1,91 Mio., keine
Punktehistorie, Ursache Aufmerksamkeit um einen 19-jährigen Neuzugang).

**Handlungsregel:** Verkaufen, solange alle drei Merkmale zusammen zutreffen.
Der Punkteschnitt liefert keinen Boden für den Wert, also fällt er zurück,
sobald die Nachricht durch ist. Umgekehrt: einen solchen Spieler nie kaufen.

Abgrenzung zum echten Aufwärtstrend: bei einem Stammspieler steigt der Wert in
kleineren Schritten und der Punkteschnitt stützt ihn (Leweling: +275k in 7
Tagen bei Schnitt 103, Wert seit 92 Tagen in einem engen Band).

## Die Aufsteiger-Prämie (Mustererkennung, neu 2026-07-25)

Spieler der drei Aufsteiger haben systematisch keinen Bundesliga-Punkteschnitt,
werden aber trotzdem hoch bewertet, weil die Nutzerschaft auf Stammplätze in
einer neuen Mannschaft wettet. Beobachtet am 2026-07-25 bei Elversberg: Rohr
8,43 Mio., Zimmerschied 9,00 Mio., Petkov 10,25 Mio. — alle drei projizierte
Stammspieler, alle drei ohne jede BL-Datenbasis.

**Konsequenz:** Der Startplatz kann belegt sein und der Preis trotzdem falsch.
Bei diesen Spielern ist die Frage nicht „spielt er?", sondern „wie viele Punkte
bringt ein Stammspieler in einer Mannschaft, die um den Klassenerhalt spielt?".
Für Verteidiger und Torhüter ist das besonders relevant, weil ihre Punkte an
Zu-null-Spielen hängen. Kaufen erst, wenn der Preis den Aufsteiger-Abschlag
enthält, nicht die Aufsteiger-Prämie.

## Marktwert als Indikator

Kickbase-Marktwerte entstehen über Kauf- und Verkaufsnachfrage aller Nutzer
plus Leistung und Nachrichtenlage. Sie sind damit selbst ein Signal für
wahrgenommenen Stammspielerstatus — ein Verteidiger wird nicht auf 17 Mio.
bewertet, wenn die Nutzerschaft ihn für einen Ersatzmann hält.

**Einschränkung:** Das gilt nur bei vorhandener Punktehistorie. Ohne sie
bewertet der Markt Erwartung, nicht Status — siehe Hype-Gipfel und
Aufsteiger-Prämie oben. Stange auf 4,07 Mio. bei einem Punkteschnitt von 5 ist
der Gegenbeweis zur Regel.

Umgekehrt: niedriger Marktwert bei brauchbarem Schnitt heißt meist
begrenzte Spielzeit.

**Nicht prognostizierbar.** Keine Aussagen darüber treffen, welcher Spieler
in den nächsten Wochen im Wert steigt. Was geht: strukturelle Einordnung
(gedeckelt nach oben, Abwärtsrisiko, Untergrenze erreicht).

**Untergrenze:** 500.000 € ist der Kickbase-Mindestmarktwert. Spieler auf
diesem Wert können nicht fallen und sind damit kostenlose Kaderplatzhalter.
Ein ausgewiesener Tiefstwert von `0 €` ist dagegen ein Datenfehler, siehe
`datencheck.md` Punkt 5 — nicht als „Untergrenze erreicht" lesen.

**Verletzungstief als Einstiegspunkt:** Ein Stammspieler mit hoher Quote, der
verletzt ist und dessen Marktwert auf dem 92-Tage-Tief steht, ist der einzige
Fall, in dem sich ein Kauf ohne aktuellen Startplatz rechnet. Beispiel
2026-07-25: Baumgartner, Schnitt 117 bei 97 % Quote, Wert von 34,4 auf 19,0
Mio. gefallen. **Voraussetzung: bestätigte Rückkehr ins Mannschaftstraining.**
Ohne diese Bestätigung ist es eine Wette auf eine Genesung, deren Verlauf
niemand kennt.

## Punkteschnitt fehlt

Kein Punkteschnitt bedeutet keine Bundesliga-Historie in der Datenbank:
Neuzugang aus dem Ausland, Aufsteiger-Spieler oder kein Einsatz.

Bei hohem Marktwert ohne Historie ist das die riskanteste Konstellation
im Kader — Blindkauf ohne Datenbasis, mit dem höchsten Abwärtsrisiko.
Immer recherchieren, nie nach Gefühl beurteilen.

**Ausnahme Aufsteiger:** Bei Spielern von Schalke, Elversberg und Paderborn ist
ein fehlender Schnitt in der Saison 2026/27 erwartbar und kein Warnsignal —
siehe `liga-kontext.md`. Bei einem Spieler eines etablierten Erstligisten ist er
dagegen genau das.

## Reihenfolge der Prüfung

Wenn die Zeit knapp ist, in dieser Reihenfolge arbeiten. Die ersten zwei
Schritte entscheiden fast immer schon.

1. **Startplatz.** Ligainsiders Top-Elf-Prognose für den Verein: steht der
   Spieler als Erstkandidat oder als Alternative? Das ist die einzige Frage,
   die zählt.
2. **Verfügbarkeit.** Status-Code im Dump, Vereinsmeldungen der letzten zwei
   Wochen, offene Verletzungseinträge aus der Vorsaison.
3. **Quote und Schnitt gemeinsam**, mit den korrigierten Werten.
4. **Marktwertlage**: 7-Tage-Änderung plus Position im 92-Tage-Band.
5. **k/Punkt** — zuletzt, und nur innerhalb einer Gruppe mit ähnlicher Quote.
