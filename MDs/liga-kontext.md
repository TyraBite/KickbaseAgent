# Kontext Saison 2026/27

Stand: 2026-07-25

## Termine

- **1. Spieltag: 28.–30. August 2026.** Eröffnungsspiel FC Bayern gegen VfB Stuttgart.
- Saisonende: 22. Mai 2027, 34 Spieltage.
- Der Start liegt eine Woche später als üblich, weil die WM 2026 im Sommer stattfand.

Der Dump vom 2026-07-25 meldete „Spieltag 1, nächster Termin in 34 Tagen", was
genau den 28.08.2026 ergibt. Die Termin-Semantik des Skripts ist damit
bestätigt, siehe `datencheck.md`, Abschnitt Behoben.

## Der WM-Effekt — relevant für die ersten Spieltage

Spieler, die bei der WM 2026 weit gekommen sind, hatten kaum Pause und
verspäteten Vorbereitungsstart. Beispiel: der VfB begann am 16. Juli, die
WM-Fahrer Undav, Leweling und Stiller fehlten beim Trainingsauftakt.

**Konsequenz für Spieltag 1 bis 3:** WM-Rückkehrer werden überproportional
geschont, unabhängig von ihrem Stammspielerstatus. Spieler ohne WM-Teilnahme
sind für den Saisonstart systematisch die verlässlichere Wahl, auch wenn sie
langfristig die schwächeren sind.

**Abstufung nach Turnierrolle.** Der Effekt hängt an den gespielten Minuten,
nicht an der Nominierung. Baumann war im deutschen WM-Kader, laut Berichten aber
als Ersatz hinter Neuer — bei ihm ist kaum Belastung entstanden und das
Schonungsrisiko entsprechend klein. Bei Leweling, der als Stammspieler
mitgefahren ist, ist es real. Vor dem Anwenden des Effekts also prüfen: war er
Stammspieler beim Turnier oder Kaderfüller?

Das ist eine einmalige Verzerrung dieser Saison und läuft nach etwa vier
Spieltagen aus.

## Transferfenster

Offen bis etwa 1. September 2026, also über den 1. Spieltag hinaus. Bis dahin
kann sich jede Hierarchie ändern. Jede Einschätzung ist ein Stand von heute,
keine Prognose für Spieltag 5.

Konkrete offene Fälle mit direkter Auswirkung auf eigene Spieler (Stand
2026-07-25): Asllani-Interesse von RB Leipzig würde Harders Stammplatz treffen;
Augsburg hält eine Kaufoption auf Chaves.

## Aufsteiger und Absteiger

**Aufsteiger:** Schalke 04, SV Elversberg, SC Paderborn
**Absteiger:** VfL Wolfsburg, 1. FC Heidenheim, FC St. Pauli

Wichtig für die Dateninterpretation: Spieler der drei Aufsteiger haben oft
keinen Bundesliga-Punkteschnitt, obwohl sie Stammspieler sind. Ein fehlender
Schnitt ist bei ihnen kein Warnsignal, sondern erwartbar.

**Umgekehrt gilt aber:** die Kickbase-Nutzerschaft bewertet Aufsteiger-Spieler
hoch, obwohl keine Datenbasis existiert. Am 2026-07-25 standen drei projizierte
Elversberg-Stammspieler bei 8,4 bis 10,3 Mio. ohne jede BL-Historie. Siehe
`methodik.md`, Abschnitt „Aufsteiger-Prämie". Startplatz ja, Preis fragwürdig.

Titelverteidiger ist der FC Bayern München.

## Meine Liga (8 Manager)

Eigener Manager-Name: **Tyra**.

### Tabelle — Stand Ende Saison 2025/26

Diese Beobachtungen stammen aus der abgelaufenen Saison. Der Dump vom
2026-07-25 liefert für alle acht Manager keine Werte („noch keine
Saisondaten"), was vor Spieltag 1 erwartbar ist. **Die Platzierungen und
Formkurven haben damit derzeit keinen Informationswert** — auch Platz 8 für mich
selbst ist ein Übertrag, keine Aussage. Ab Spieltag 2 neu bewerten.

| Platz | Manager | Beobachtung 2025/26 |
|---|---|---|
| 1 | Jan | Datenlage zu dünn für eine Einschätzung |
| 2 | Thommi Kessler | Einzige vollständige Datenreihe, konsistent hohe Werte, keine Ausfalltage. Der eigentliche Maßstab. |
| 3 | Mätthi United | Sehr hohe Einzelwerte bei dünner Datenlage. Potenziell der stärkste Manager, unbestätigt. |
| 4 | Bobetinho | Keine Daten |
| 5 | Fassii | Solide, mit einzelnen Ausfalltagen |
| 6 | senf | Vollständige Reihe, aber schwacher Schnitt und ein Spieltag mit fast null Punkten |
| 7 | Fleischmanns | Mehrere Spieltage mit Werten unter 150 |
| 8 | Tyra (ich) | Nur zwei Datenpunkte verfügbar |

**Wichtigste Beobachtung, gilt weiter:** Mehrere Manager haben einzelne
Spieltage mit Werten unter 150, wo sie sonst im vierstelligen Bereich liegen.
Das sind mit hoher Wahrscheinlichkeit vergessene Aufstellungen. In dieser Liga
ist das die häufigste Quelle für Punktverlust — häufiger als schlechte
Transfers.

Alle Zahlen der Ligatabelle sind mit Vorsicht zu behandeln, siehe
`datencheck.md` Punkt 8.

### Marktverhalten als Ersatzindikator (neu 2026-07-25)

Solange die Tabelle leer ist, ist die Zahl der Spieler, die ein Manager auf den
Transfermarkt stellt, die einzige verfügbare Information über seinen Zustand.
Aus dem Dump vom 2026-07-25, 56 Angebote insgesamt:

| Manager | Angebote | Lesart |
|---|---|---|
| Fassii | 10 | Kompletter Umbau, überwiegend Kleinvieh (mehrere 500k-Spieler) |
| Bobetinho | 9 | Umbau, mit echten Werten dabei (Svensson 18,5 Mio., Lerma 8,0 Mio.) |
| Fleischmanns | 9 | Umbau — **und stellt Baumann für 19,1 Mio. rein.** Einen 99er-Schnitt bei 100 % Einsatzquote gibt man nicht ab, wenn man den Kader kennt |
| Thommi Kessler | 7 | Verkauft gezielt die überhitzten Aufsteiger-Werte (Petkov, Rohr, Zimmerschied). Entweder Gewinnmitnahme oder er hält Aufsteiger für zu teuer — bei ihm als Maßstab ein Signal |
| senf | 4 | Der einzige mit manuell gesetzten Preisen (+11 % bis +46 %). Bietet zwei Ersatztorhüter mit hohem historischen Schnitt zu Aufschlägen an |
| Jan | 0 | Nichts auf dem Markt. Fertig aufgestellt oder inaktiv, nicht unterscheidbar |
| Mätthi United | 0 | Ebenso. Passt zu „stärkster Manager mit fertigem Kader", bleibt unbestätigt |

**Praktische Konsequenz:** Fünf von sieben Gegnern räumen ihre Kader. Der Markt
ist entsprechend voll und die Konkurrenz um gute Systemangebote gerade niedrig —
bei acht Angeboten, bei denen ich am 2026-07-25 führte, gab es jeweils genau ein
Gebot, nämlich mein eigenes. Keiner der Gegner bietet aktiv mit. Das ist das
Zeitfenster für Käufe.

**Beim nächsten Dump prüfen:** Bieten Jan und Mätthi United weiterhin nichts an?
Dauerhafte Inaktivität auf dem Transfermarkt bei gleichzeitig guten
Spieltagswerten heißt: fertiger Kader, gefährlich. Bei schlechten
Spieltagswerten heißt es: inaktiver Mitspieler, ungefährlich. Die
Unterscheidung wird ab Spieltag 2 möglich.
