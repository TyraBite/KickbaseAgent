# Spieler-Vergleichsansicht — Design

## Kontext

Beim Wunschkader-Ziel-Wechsel (WunschkaderTab.tsx, bestehende Ersatzspieler-Suche via `scoreReplacementPool()`/`searchReplacementPool()`) möchte der User zwei Spieler im Detail nebeneinander vergleichen können, bevor er sich entscheidet. Dieselbe Entscheidungssituation (Spieler A gegen Spieler B tauschen) tritt auch in "Alle Spieler" (allgemeines Scouting) und "Eigenes Team" (Verkaufskandidat vs. Watchlist-Ziel) auf.

## Architektur

Eine geteilte Komponente `PlayerCompareModal` (neue Datei `frontend/src/components/PlayerCompareModal.tsx`) nimmt zwei `player_id`s + den vollen `data: DashboardSnapshot`-Snapshot als Props. Löst beide Spieler intern über `data.players` auf und baut für beide über die bereits bestehende `buildPlayerRow()` (`frontend/src/lib/derive.ts`) dieselben Felder — unabhängig davon, aus welchem Tab der Vergleich gestartet wurde. Zwei-Spalten-Layout (ein Feld pro Zeile, ein Spieler pro Spalte), Feld-Set: ML-Prognose, Signal, Marktwert, Startelf-Rang, Fitness, Schnitt (gleiche Reihenfolge/Relevanz wie das aktuelle EigenesTeamTab-Detail).

## Einstiegspunkte (3 Tabs)

- **Wunschkader** (`WunschkaderTab.tsx`): Klick auf einen vorgeschlagenen Ersatz in der bestehenden Ersatzspieler-Suche öffnet direkt `PlayerCompareModal(aktuelles Ziel, Vorschlag)` — keine weitere Auswahl nötig, beide IDs sind schon bekannt.
- **Alle Spieler** (`AlleSpielerTab.tsx`) / **Eigenes Team** (`EigenesTeamTab.tsx`): das jeweils bestehende Detail-Modal bekommt einen neuen Button "Vergleichen mit…", öffnet einen kleinen Namens-Picker (gleiches Suchmuster wie die bestehende Ersatzspieler-Suche) → `PlayerCompareModal(aktueller Spieler, ausgewählter Spieler)`.
- Transfermarkt/Spekulation sind bewusst NICHT Teil dieses Plans (siehe Out of Scope) — die geteilte Komponente ist so gebaut, dass eine spätere Erweiterung dort nur eine zusätzliche Wiring-Stelle braucht, kein Umbau der Komponente selbst.

## Spieler-Wechsel innerhalb des offenen Modals

Beide Seiten (nicht nur eine) bekommen einen kleinen "Wechseln"-Button direkt neben dem Spielernamen. Öffnet denselben Namens-Picker wie Einstiegspunkt 2 und tauscht NUR diese eine Seite aus, ohne das Modal zu schließen — z.B. Ziel A vs. Kandidat 1 vergleichen, dann rechts auf Kandidat 2 wechseln. Symmetrisch für beide Seiten, keine Sonderregel (z.B. "linke Seite ist der fixe Anker") — auch beim Wunschkader-Einstiegspunkt kann das aktuelle Ziel selbst ausgetauscht werden, wenn gewünscht.

## Tausch-Auslöser (nur Wunschkader)

Klick auf einen Ersatzspieler-Vorschlag öffnet jetzt den Vergleich statt sofort zu tauschen (bisheriges `onReplace(s)` direkt am Chip entfällt). `PlayerCompareModal` bekommt einen OPTIONALEN Callback-Prop `onSelectSide?: (playerId: string) => void` — nur wenn übergeben, zeigt die Komponente einen kleinen Button "Diesen als Ersatz wählen" unter der jeweiligen Seite. Der Wunschkader-Einstiegspunkt übergibt diesen Callback (ruft intern das bestehende `onReplace()` auf und schließt beide Modals); Alle Spieler/Eigenes Team übergeben ihn NICHT — dort bleibt der Vergleich rein informativ, kein Handlungs-Button.

## "Wer ist besser"-Markierung pro Zeile

Farbliche Hervorhebung (grün, wie die bestehenden Signal-/Trend-Badges) auf der Seite mit dem besseren Wert:

| Feld | Besser = |
|---|---|
| ML-Prognose | höher |
| Signal | höher |
| Schnitt | höher |
| Startelf-Rang | niedriger (Rang 1 = wahrscheinlichster Stammplatz) |
| Fitness | "Fit" (kein `status_label`) schlägt jede Verletzt/Angeschlagen-Markierung |
| Marktwert | niedriger (günstiger bei vergleichbarer Qualität ist besser) |

## Edge Cases

- Fehlt ein Feld bei einem der beiden Spieler (z.B. `starting_rank: null`) → "n/v" auf der betroffenen Seite, keine Hervorhebung auf beiden Seiten für diese Zeile.
- Beide Seiten zeigen (versehentlich oder bewusst) denselben Spieler → keine Hervorhebung irgendwo, kein Crash (Gleichstand ist kein Fehlerfall).
- Namens-Picker findet keinen Treffer → normaler leerer Zustand (gleiches Verhalten wie die bestehende Ersatzspieler-Suche bei keinem Treffer).

## Out of Scope

- Transfermarkt/Spekulation als weitere Einstiegspunkte — spätere Erweiterung möglich, hier nicht eingeplant.
- Mehr als 2 Spieler gleichzeitig vergleichen — deckt den eigentlichen Anwendungsfall (A-gegen-B-Tausch-Entscheidung) nicht ab, bewusst nicht gebaut.
- Keine Persistierung/Speicherung eines Vergleichs — rein transientes UI-Fenster, schließt sich ohne Spuren.

## Self-Review

- **Platzhalter-Scan**: keine TBD/offenen Stellen.
- **Konsistenz**: `PlayerCompareModal` durchgängig gleich benannt zwischen Architektur- und Einstiegspunkt-Abschnitt. Die "besser"-Tabelle deckt exakt das im Architektur-Abschnitt genannte Feld-Set ab (6 Felder, 6 Zeilen in der Tabelle).
- **Scope**: fokussiert genug für einen einzelnen Implementierungsplan (eine neue geteilte Komponente + 3 Wiring-Stellen, kein Umbau bestehender Tabs nötig).
- **Wiederverwendung**: nutzt bestehende Funktionen (`buildPlayerRow()`) und bestehende UI-Muster (Namens-Picker analog zur Ersatzspieler-Suche) statt neuer Paralleler Implementierungen.
