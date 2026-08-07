# HANDOFF: KickbaseAgent Dashboard

Zustand nach der letzten Session: was zuletzt gemacht wurde und was die nächste Session ggf. aufgreifen sollte. Kein
Backlog — offene Ideen/Schulden ohne aktuellen Auftrag stehen in `BACKLOG.md`. Kein Änderungsprotokoll vergangener
Arbeit (das steht in der Git-Historie, `git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## Zuletzt gemacht (2026-08-07)

- **Feedback-Log geprüft** (`feedback/current`, alle 27 Items durchgesehen): 4 offene (`status:"open"`). Zwei bereits
  bekannt und dokumentiert (Sentiment-Turningpoints `6b08e2cf`, Public-Domain-DB-Idee `f686c8db`). Zwei neu, jetzt in
  `BACKLOG.md` nachgetragen: Achievements/Login-Boni in die Budget-Schätzung einbeziehen (`84ad6dff`) und
  Light/Heavy-Workflows über einen Raspberry Pi laufen lassen statt/zusätzlich zu GitHub Actions (`306066b2`).
- **Manager-Budgets: exakte Achievement-Erkennung statt Punkte-Verhältnis-Skalierung** (PR #19 + Follow-up PR #20,
  beide gemergt) — Umsetzung von `84ad6dff`, Teil 1. Für ANDERE Liga-Manager (nicht das eigene, ohnehin exakte
  Kapital) wird der Achievement-Bonus-Anteil für 5 live verifizierte, exakt prüfbare Achievement-Ids (Teamwert-,
  Trade-Count-, Liga-Größe-Schwellen) jetzt exakt statt per Saisonpunkte-Verhältnis geschätzt. Plan:
  `docs/superpowers/plans/2026-08-07-manager-budgets-exact-achievements.md`, subagent-driven umgesetzt (3
  Code-Tasks + PR + finale Whole-Branch-Review + eine Fix-Welle).
  - Live-Recherche vor der Umsetzung ergab: Login-Bonus ist ein Streak (10k→20k→…→100k gedeckelt ab Tag 10, Reset
    vermutlich bei Lücke), nicht der bislang angenommene feste Betrag. Login-Bonus- und Achievement-Feed-Einträge
    sind strikt auf den Token-Owner beschränkt (ein `managerId`-Query-Param wird stillschweigend ignoriert). Die
    "Jackpot"-Idee (Achievements anderer Manager direkt/season-weit auslesen) wurde deshalb live getestet und
    verworfen — kein Manager-scoped Achievement-Endpoint. Beides in `BACKLOG.md` dokumentiert; die
    Login-Bonus-Aktivitätserkennung (Teil 2 der Idee) ist auf User-Wunsch bewusst zurückgestellt, nicht Teil dieser
    Umsetzung.
  - Die finale Whole-Branch-Review (dispatcht auf dem leistungsfähigsten verfügbaren Modell) fand einen
    mutation-verifizierten Coverage-Gap: die `trade_count`/`league_size`-Verdrahtung in `estimate_all()` hatte keine
    Integrationstests (nur `team_value` war abgedeckt) — der Code selbst war korrekt. Per Follow-up-PR #20
    geschlossen (2 neue, mutation-verifizierte Integrationstests + 2 kleine Doku-Fixes).
  - **Prozess-Lehre, in `CLAUDE.md` nachgetragen**: Task 4 (PR + Auto-Merge) lief parallel zur finalen
    Whole-Branch-Review statt danach — PR #19 merged, bevor die Review fertig war. Künftig: bei
    Subagent-Driven-Development-Ausführung die finale Review abwarten, bevor Auto-Merge für den letzten Code-Task
    gesetzt wird.
  - Live-Produktions-Delta heute: exakt 0 € für alle 8 Manager (alle bereits über jeder Schwelle, `season_points=0`
    aktuell macht auch den alten Skalierungs-Pfad wirkungslos) — kein erzwungener Heavy-Lauf nötig, kein
    Firestore-Schema- oder Output-Change.
  - E2E-Flaky-Test (`WunschkaderDragAndDrop.spec.ts`, `maxScroll`-Sanity-Check) trat auf PR #20 erneut auf, per
    Job-Log bestätigt unabhängig vom (reinen Backend-)Diff, nach Rerun grün — zweiter Beleg für den in
    `BACKLOG.md` bereits vermerkten, noch nicht root-caused Flake.

## Aufzugreifen

- **Raspi-Workflow-Idee** (`306066b2`, `BACKLOG.md`) — sollte laut User als Nächstes im Dialog geplant werden
  (parallel zur Achievement-Umsetzung angestoßen). Noch keine Antwort zu Hardware/OS/Docker-Status erhalten, noch
  nicht begonnen.
