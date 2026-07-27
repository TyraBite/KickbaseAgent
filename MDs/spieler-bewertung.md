# Spieler-Bewertungen (Recherche-Cache)

Ersetzt die frühere Datei `spieler-vereine.md`. Diese kann gelöscht werden —
seit dem Dump vom 2026-07-25 liefert die API das Vereinsfeld, damit ist der
einzige Zweck jener Datei entfallen.

## Zweck

Diese Datei cacht **nicht** die Vereinszugehörigkeit — die kommt aus dem
Kickbase-Dump. Sie cacht das, was die Kickbase-API nicht liefert und was teuer
zu recherchieren ist: Startelf-Sicherheit, Vertragslage und
Konkurrenzsituation.

Nur eintragen, was tatsächlich recherchiert wurde. Nichts aus dem Gedächtnis
ergänzen — der einzige Wert dieser Datei ist, dass ihr Inhalt verlässlich ist.
Das gilt auch für aus dem Dump abgeleitete Werte: Einsatzquote und Kosten pro
Punkt gehören **nicht** hierher, sie sind bei jedem Dump neu berechenbar und
laut `methodik.md` ohnehin nur Rangsignale.

Das Feld `Verein` bleibt trotzdem in der Tabelle, aber nur als Lesehilfe zur
Identifikation. Bei Widerspruch gilt immer der Dump.

## Regeln zur Aktualität

Der Eintrag `geprüft am` entscheidet, ob ein Eintrag noch verwendbar ist:

| Alter | Umgang |
|---|---|
| während offenem Transferfenster | maximal 14 Tage vertrauen, danach neu prüfen |
| Fenster geschlossen, laufende Saison | 6–8 Wochen vertrauen |
| über eine Winterpause hinweg | immer neu prüfen |

Bei einem Spieler mit Status-Code oder Verletzungsmeldung im Dump gilt der
Eintrag unabhängig vom Alter als überholt.

Wird ein Eintrag durch neue Recherche widerlegt: alten Stand überschreiben und
in der Antwort explizit sagen, dass sich die Einschätzung gedreht hat.

## Bewertungen — eigener Kader

| Spieler | Verein | Startelf Vorsaison | Vertrag bis | Konkurrenz / Lage | Urteil | geprüft am |
|---|---|---|---|---|---|---|
| Jamie Leweling | VfB Stuttgart | ~94 % Einsatzquote, 7 Tore / 9 Vorlagen | 30.06.2029 | gesetzt. WM-2026-Teilnehmer, verspäteter Vorbereitungsstart. Januar 2026 Bournemouth-Gerüchte | **Stammspieler**, Startrisiko Spieltag 1–3 | 2026-07-25 |
| Lasse Günther | SV Elversberg | 21 Startelf bei 27 Einsätzen (2. BL), 7 Vorlagen | 2030 | Linksverteidiger. Vertrag im Juni 2026 verlängert, nachdem ein Werder-Wechsel platzte. In Ligainsiders Top-Elf-Prognose 26/27 eingeplant | **Stammspieler** | 2026-07-25 |
| Conrad Harder | RB Leipzig | Startelfeinsätze als Mittelstürmer (u. a. 31.01.2026 vs. Mainz) | nicht ermittelt | in Ligainsiders Top-Elf-Prognose 26/27 eingeplant. Ligainsider meldet am 20.07.2026 Asllani-Interesse → direkte Konkurrenz im Sturmzentrum. Neuer Trainer | **Stammspieler auf Widerruf.** Auslöser für Verkauf: Asllani-Verpflichtung | 2026-07-25 |
| Bruno Ogbus | SC Freiburg | 18 BL-Einsätze, ab dem 17. Spieltag durchgehend im Einsatz | nicht ermittelt | Trainer Schuster hat den offenen Konkurrenzkampf mit Lienhart ausgerufen; dazu Ginter, Rosenfelder, Jung, Treu, Makengo. Freiburg mit Europapokal-Belastung | **Rotation, nicht planbar.** Auslöser: kein Startelfplatz an Spieltag 1 | 2026-07-25 |
| Arthur Chaves | TSG Hoffenheim | 11 Startelf bei 16 Einsätzen (inkl. Augsburg-Leihe) | 2029 | Januar bis Juni 2026 an Augsburg verliehen, weil er in der Hinrunde nur 4 BL-Spiele hatte; Augsburg hält eine Kaufoption. IV-Konkurrenz: Hranáč, Dulic, Kabak, Bernardo, Hajdari, Machida, Szalai | **kein gesicherter Stammplatz.** Auslöser: sobald ein Stamm-Verteidiger nachgerückt ist | 2026-07-25 |
| Derry Scherhant | SC Freiburg | 24 BL-Einsätze, überwiegend Einwechslungen | 30.06.2027 | Ligainsiders Top-Elf-Prognose vom 22.07.2026 führt ihn nur als *Alternative* zu Grifo auf dem linken Flügel | **kein Stammspieler** | 2026-07-25 |
| Nathan Tella | Bayer 04 Leverkusen | ~50 % Einsatzquote bei Schnitt 68 | 30.06.2028 | Rotationsspieler in tiefem Kader. Flügelkonkurrenz: Poku, Tillman, Maza, Hofmann, Vázquez. Verletzungseintrag ab 18.01.2026 ohne dokumentiertes Ende, davor Knie 17.09.–21.11.2025 | **Rotationsspieler, verkaufen** | 2026-07-25 |
| Eliesse Ben Seghir | Bayer 04 Leverkusen | 25/26 nach Rückkehr nur drei Kurzeinsätze | 30.06.2027 | Muskelverletzung rechter Oberschenkel, MRT-Bestätigung durch den Verein 20.07.2026, Ausfalldauer offen. Davor Sprunggelenksverletzung ab Januar 2026 mit 10 verpassten BL-Spielen. Status-Code 1 im Dump | **Ausfall, verkaufen** | 2026-07-25 |
| Otto Stange | Hamburger SV | keine BL-Startelfeinsätze; 1. Halbserie 25/26 an Elversberg verliehen | nicht ermittelt | 19 Jahre. U19-EM-Torschützenkönig Juli 2026 → reiner Marktwert-Hype. Status-Code 2, fehlte beim HSV-Testspiel | **kein Stammspieler, Hype-Gipfel** | 2026-07-25 |
| Suleman Sani (Dump: „Suleiman") | RB Leipzig | keine BL-Historie | 2031 | seit 13.01.2026 in Leipzig (5 Mio. von Trenčín). Sprunggelenk 26.01.–05.03.2026, Hüftverletzung ab 02.04.2026 mit offenem Ende. Linksaußen hinter Nusa, Bakayoko, Gruda, Diomande | **kein Stammspieler** | 2026-07-25 |
| Marius Funk | VfB Stuttgart | keine Einsätze | — | vierter von vier Torhütern (Bredlow, Drljaca, Seimen) | **irrelevant**, taugt nur als Mindestpreis-Platzhalter | 2026-07-25 |
| Jonas Urbig | FC Bayern | niedrig, Rotationseinsätze | 30.06.2029 | Neuer und Ulreich beide bis 30.06.2027 verlängert, Verein hat Dreier-Torwartteam für 2026/27 offiziell kommuniziert | **kein Stammspieler** | 2026-07-25 |

## Bewertungen — Kaufen

| Spieler | Verein | Startelf Vorsaison | Vertrag bis | Konkurrenz / Lage | Urteil | geprüft am |
|---|---|---|---|---|---|---|
| David Raum | RB Leipzig | ~88 % Einsatzquote bei Schnitt 148 (Höchstwert des Marktes) | nicht ermittelt | steht in Leipzigs Startformation (Vandevoordt – Baku, Orbán, Lukeba, Raum), in Ligainsiders Top-Elf 26/27 eingeplant | **Stammspieler, höchste Priorität** | 2026-07-25 |
| Oliver Baumann | TSG Hoffenheim | 27 BL-Einsätze, 100 % Einsatzquote | 30.06.2028 | Kapitän, 523 BL-Spiele, unumstrittene Nummer eins. WM-2026-Teilnehmer, aber laut Berichten als Ersatz hinter Neuer → geringes Schonungsrisiko | **Stammspieler, sicherster Startplatz im Angebot** | 2026-07-25 |
| Ridle Baku | RB Leipzig | 17 Startelf bei 20 Spielen (Stand Mitte Februar) | 30.06.2027 | Ligainsiders Top-Elf 26/27: „der gesetzte Mann auf der rechten Abwehrseite". Rotation im Saisonverlauf angekündigt | **Stammspieler** | 2026-07-25 |
| Jens Stage | Werder Bremen | 29 Startelf bei 29 Einsätzen, 10 Tore | 2028 | gesetzt, erster Kapitänsvertreter | **Stammspieler, höchste geprüfte Startplatzsicherheit** | 2026-07-25 |
| Vincenzo Grifo | SC Freiburg | ~97 % Einsatzquote bei Schnitt 71 | Verlängerung deutet sich an (nicht bestätigt) | Ligainsider 22.07.2026: „Fixpunkt", gesetzt auf dem linken Flügel. 33 Jahre, Scherhant baut Druck auf | **Stammspieler**, Altersrisiko | 2026-07-25 |
| Frederik Rønnow | 1. FC Union Berlin | 22–26 BL-Einsätze, in jeder der letzten vier Saisons 25–33 | nicht ermittelt | Stammkeeper. Saison 25/26 endete am 24.04.2026 mit Adduktorenverletzung. Raabs Vertrag lief 30.06.2026 aus, Klaus ist Nummer drei. **Status-Code 4 im Dump ungeklärt** | **Stammspieler**, Status vor Kauf im Client prüfen | 2026-07-25 |

## Bewertungen — Watchlist und beobachten

| Spieler | Verein | Startelf Vorsaison | Vertrag bis | Konkurrenz / Lage | Urteil | geprüft am |
|---|---|---|---|---|---|---|
| Christoph Baumgartner | RB Leipzig | ~97 % Einsatzquote bei Schnitt 117 | 30.06.2028 | Sehnenriss am Hüfteinsatz, Operation in Finnland Anfang Juni 2026, WM dadurch verpasst. Status-Code 1, Marktwert auf dem 92-Tage-Tief | **Watchlist.** Kaufen erst bei bestätigter Rückkehr ins Mannschaftstraining — dann bestes Preis-Leistungs-Verhältnis am Markt | 2026-07-25 |
| Dimitrios Giannoulis | FC Augsburg | ~80 % Einsatzquote bei Schnitt 73 | nicht ermittelt | Status-Code 2. Musste Training am 21.07.2026 vorzeitig abbrechen (Zeh). Abgangsspekulationen in der Ligainsider-Kommentarspalte | **Watchlist.** Nach geklärter Fitness bester Preis-Leistungs-Verteidiger | 2026-07-25 |
| Maximilian Rohr | SV Elversberg | keine BL-Historie (Aufsteiger) | nicht ermittelt | projizierter Stamm-Innenverteidiger laut Ligainsiders Top-Elf-Prognose | **Startplatz belegt, Preis zu hoch.** Unter 6 Mio. neu prüfen | 2026-07-25 |
| Lukas Petkov | SV Elversberg | keine BL-Historie (Aufsteiger), 7 Tore / 6 Vorlagen in der 2. BL | nicht ermittelt | „weiterhin Stammspieler auf der rechten Außenbahn" laut Ligainsider | **Startplatz belegt, Aufsteiger-Hype-Preis** | 2026-07-25 |
| Tom Zimmerschied | SV Elversberg | keine BL-Historie (Aufsteiger), 9 Vorlagen in der 2. BL | nicht ermittelt | projizierter Stamm-Linksaußen, „kein Anlass für Veränderungen" laut Ligainsider. Status-Code 2 im Dump | **Startplatz belegt, Status offen, Preis zu hoch** | 2026-07-25 |
| Raphael Obermair | SC Paderborn 07 | keine BL-Historie (Aufsteiger) | nicht ermittelt | projizierter Stammspieler linke Schiene, 30, Vizekapitän | **Startplatz belegt**, preislich vernünftigster Aufsteiger | 2026-07-25 |
| Tiago Tomás | VfB Stuttgart | ~80 % Einsatzquote bei Schnitt 59 | nicht ermittelt | **Startelf-Status 26/27 nicht recherchiert** | **vor Kauf prüfen.** Bestes Stürmer-Profil des Angebots, aber unbelegt | 2026-07-25 |
| José María Andrés Baixauli | VfB Stuttgart | ~74 % Einsatzquote bei Schnitt 77 | nicht ermittelt | dichtes Mittelfeld: El Khannouss, Führich, Karazor, Prömel, Stiller, Ulrich, Nartey, Malanga | **unklar**, nur mit Startelf-Beleg kaufen | 2026-07-25 |
| Finn Jeltsch | VfB Stuttgart | nicht ermittelt | nicht ermittelt | Abwehr | nicht bewertet | 2026-07-25 |
| Jovan Milosevic | VfB Stuttgart | nicht ermittelt | nicht ermittelt | Sturm | nicht bewertet | 2026-07-25 |
| Lazar Jovanovic | VfB Stuttgart | nicht ermittelt | nicht ermittelt | Mittelfeld | nicht bewertet | 2026-07-25 |
| Dariusz Stalmach | Werder Bremen | nicht ermittelt | nicht ermittelt | Mittelfeld | nicht bewertet | 2026-07-25 |
| Hiroki Ito | FC Bayern | ~47 % Einsatzquote | 30.06.2028 | Upamecano (2030), Tah (2029), Kim (2028) — vier IV für zwei Plätze. **Steht seit dem Dump vom 2026-07-25 nicht mehr im eigenen Kader** | **wahrscheinlich kein Stammspieler**, Rangfolge nicht direkt belegt | 2026-07-25 |

## Bewertungen — Nicht kaufen

| Spieler | Verein | Grund | Urteil | geprüft am |
|---|---|---|---|---|
| Mika Baur | SC Paderborn 07 | Ligainsider meldet eine Einigung mit einem Glasgower Klub. Projizierter Stammspieler, aber Abgang wahrscheinlich | **Abgangsrisiko** | 2026-07-25 |
| Péter Gulácsi | RB Leipzig | hat den Stammplatz verletzungsbedingt an Vandevoordt verloren, laut Ligainsider künftig dauerhaft Bank. Schnitt 103 ist historisch, nicht prognostisch | **Ersatztorwart** | 2026-07-25 |
| Janis Blaswich | Bayer 04 Leverkusen | ~32 % Einsatzquote bei Schnitt 111. Konkurrenz Flekken, Lomb, Omlin | **Ersatztorwart** | 2026-07-25 |
| Chrislain Matsima | FC Augsburg | Status-Code 2, fehlte am 21.07.2026 komplett im Training (Adduktoren), Verletzungseintrag ab 09.01.2026. ~53 % Quote bei Schnitt 82 = Rotationsmuster. Abgangsspekulation | **Ausfall + Rotation** | 2026-07-25 |
| Tomáš Kalas | FC Schalke 04 | RevierSport aus dem Trainingslager (22.07.2026): gehört zum Quintett, das die Einheiten von hinter dem Tor verfolgte | **aussortiert** | 2026-07-25 |
| Anton Donkor | FC Schalke 04 | seit einem Jahr auf der Abgabeliste, „weiter ohne jegliche Einsatzchance". Gosens und V. Becker links davor | **aussortiert** | 2026-07-25 |
| Maximilian Wöber | FC Schalke 04 | neu verpflichtet, laut Ligainsider-Redaktion nicht direkt gesetzt. 66 Punkte gesamt | **unklar, kein Startplatz belegt** | 2026-07-25 |
| Daniel Svensson | Borussia Dortmund | gesetzt auf der linken Schiene (Vertrag 2029), aber laut Ligainsider in der Rückrunde abgebaut und Platz teils an Beier verloren; laut Bild Verkaufsbereitschaft ab 30 Mio. (Leeds, Arsenal, Inter) | **Stammspieler mit Abgangsrisiko, zu teuer pro Punkt** | 2026-07-25 |
| Albert Grønbæk | Hamburger SV | Schnitt 74 bei nur ~21 % Einsatzquote. Ligainsider: kam spät aus Verletzung zurück, Potenzial 150+ Punkte „wenn er fit bleibt" | **Hochrisiko** | 2026-07-25 |
| Fabio Baldé | Hamburger SV | Status-Code 2, fehlte beim HSV-Testspiel, Schnitt 22 | **kein Stammspieler** | 2026-07-25 |
| Frederik Schmahl | SV Elversberg | nicht in der Top-Elf-Prognose, Marktwert −566k in 7 Tagen | **Platz verloren** | 2026-07-25 |
| Luca Schnellbacher | SV Elversberg | nicht in der Top-Elf-Prognose (Mokwa davor); Ligainsider nennt das Sturmzentrum als offene Baustelle | **kein Stammspieler** | 2026-07-25 |
| Tom Baack | SC Paderborn 07 | nicht in der Top-Elf-Prognose | **kein Stammspieler** | 2026-07-25 |
| Florian Pruhs | SC Paderborn 07 | „fehlt schlicht die Profierfahrung", Torwartposten geht laut Ligainsider wohl an einen Neuzugang | **irrelevant**, nur als 500k-Platzhalter | 2026-07-25 |

## Nicht eindeutig identifizierbar

Seit dem Vereinsfeld im Dump ist diese Liste fast leer. Es bleiben Fälle, in
denen ein Verein zwei Spieler mit demselben Nachnamen hat.

| Name im Dump | Verein | Problem | Fehlende Information |
|---|---|---|---|
| Becker | FC Schalke 04 | Schalke hat **Timo Becker** (von Ligainsider in der rechten Innenverteidigung eingeplant) und **Vitalie Becker** (Talent, linke Seite, vor Donkor). Der fehlende Punkteschnitt spricht für Vitalie, belegen lässt sich das nicht | Vorname oder Trikotnummer im Dump |

Aus der früheren Liste aufgelöst: Tella, Günther, Harder, Scherhant, Ben
Seghir, Ogbus, Chaves, Suleiman. Nicht mehr im Dump vorhanden und daher
gestrichen: Chuki, Stange (als unidentifiziert), Götze.

## Quellen, die sich bewährt haben

- **ligainsider.de „Top-Elf-Prognose" und „Voraussichtliche Aufstellung"** pro
  Verein. Das ist die stärkste Einzelquelle für die Startelf-Frage: sie nennt
  je Position einen Erstkandidaten und explizit eine *Alternative*. Genau diese
  Unterscheidung fehlt in Kickbase. Beide Seiten tragen ein
  Aktualisierungsdatum — immer mitlesen.
- **ligainsider.de Spielerprofile** führen `Einsätze`, `Startelf`,
  `Einwechslungen` und `Bank` getrennt aus. Belastbarste Quelle für die
  Startelf-Quote.
- **Vereinsseiten** für offizielle Aussagen zu Verletzungen, Hierarchien und
  Vertragslagen. Verletzungsmeldungen des Vereins sind die einzige Quelle, der
  man die Formulierung „Dauer offen" glauben sollte.
- **soccerway.com Verletzungshistorie** zeigt Einträge mit offenem Ende (`?`).
  Ein offener Eintrag aus der Vorsaison ist ein Warnsignal, das in Kickbase
  nirgends auftaucht.
- **kicker.de Spielerprofile** listen den kompletten Vereinskader mit
  Klarnamen. Nützlich zur Identifikation, nicht zur Hierarchie.
- **Regionale Vereinsberichterstattung** (z. B. RevierSport zu Schalke,
  „Nur die Raute" zum HSV) liefert Trainingslager-Beobachtungen, die
  aussortierte Spieler früher sichtbar machen als jede Statistik.
- **Nicht belastbar:** Testspiel-Aufstellungen. Trainer rotieren in der
  Vorbereitung absichtlich. Ein *Fehlen* im Testspiel ist trotzdem ein
  Signal — nicht für die Hierarchie, aber für die Fitness.
- **Nicht belastbar:** Marktwerte auf Transfermarkt/soccerway. Sie haben mit
  Kickbase-Marktwerten nichts zu tun und stiften nur Verwirrung.
