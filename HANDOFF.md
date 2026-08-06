# HANDOFF: KickbaseAgent Dashboard

Zustand nach der letzten Session: was zuletzt gemacht wurde und was die nächste Session ggf. aufgreifen sollte. Kein
Backlog — offene Ideen/Schulden ohne aktuellen Auftrag stehen in `BACKLOG.md`. Kein Änderungsprotokoll vergangener
Arbeit (das steht in der Git-Historie, `git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## Zuletzt gemacht (2026-08-06)

- **Stale Worktrees aufgeräumt**: alle 5 Worktrees unter `.claude/worktrees/` entsprachen bereits gemergten PRs
  (#10, #12, #13, #14, #15) und wurden inkl. ihrer lokalen `worktree-*`-Branches entfernt. Kein Datenverlust (alles
  bereits in `main`).
- **`HANDOFF.md`/`BACKLOG.md` getrennt** (dieser Commit, auf Wunsch des Users): `HANDOFF.md` beschreibt ab jetzt nur
  noch den Session-Übergang, `BACKLOG.md` trägt die alte Backlog-Rolle. `CLAUDE.md` entsprechend angepasst
  (Abschnitt am Anfang + Direkt-Push-Liste im Git-Workflow-Abschnitt + ein neuer Sandbox-Hinweis, siehe unten).
- **Sandbox-Fähigkeit getestet und dokumentiert**: Playwright-Browserausführung (CT/E2E) läuft in dieser Sandbox
  NICHT lokal (`chrome-headless-shell` fehlen mehrere System-Shared-Libraries, kein root für `apt-get`/
  `playwright install-deps`) — jetzt in `CLAUDE.md` unter „Sandbox- und Ausführungshinweise" festgehalten, damit
  das nicht jede Session neu herausfinden muss. Vitest läuft lokal problemlos (jsdom, kein echter Browser nötig).

## Aufzugreifen: Wunschkader-Kartenkopf wrap-Bug (NICHT fertig)

User-Report: seit dem Drag-and-Drop (PR #16) sehen Wunschkader-Karten in derselben Positionsgruppe/Bank
unterschiedlich hoch aus — längere Spielernamen laufen in eine zweite Zeile, kürzere bleiben einzeilig.

**Root Cause identifiziert** (`frontend/src/components/WunschkaderTab.tsx`, Kartenkopfzeile um Zeile 769):
`<div className="mb-3 flex flex-wrap items-center gap-2 pr-10">` — `pr-10` wurde in PR #16 hinzugefügt, um die
Kopfzeile vom neuen Drag-Handle (rechts oben, absolut positioniert) freizuhalten. Die Zeile ist aber weiterhin
`flex-wrap` — bei ausreichend langem Namen und knapper Spaltenbreite (Grid-Minimum 220px minus `pr-10` minus
Karten-Padding) läuft der Name in eine zweite Zeile, kürzere Namen nicht. Dadurch unterschiedliche Kartenhöhen
innerhalb derselben Grid-Reihe.

**Geplanter (noch NICHT umgesetzter) Fix**: Kopfzeile nicht mehr wrappen lassen, stattdessen nur den Namen selbst
schrumpfen/truncaten (`flex-1 min-w-0 truncate` auf den `<span className="font-semibold ...">{computed.name}</span>`,
`flex-wrap` aus dem Container entfernen). Crest/PositionBadge/Tone-Badges behalten ihre natürliche Größe (kein
`min-w-0`, schrumpfen deshalb nicht spürbar). Der volle Name bleibt über das Detail-Modal (Klick auf die Karte)
weiterhin sichtbar — keine dauerhaft verlorene Information.

**Stand der Umsetzung**: PR #17 (`https://github.com/TyraBite/KickbaseAgent/pull/17`,
Branch `worktree-wunschkader-card-header-wrap`) ist offen und enthält bisher NUR Test + Fixture, bewusst OHNE Fix:
- Neuer Fixture-Spieler `FIXTURE_PLAYERS.longName` (`frontend/src/test-fixtures/dashboardSnapshot.fixture.ts`,
  Name "Maximilian Langername", Position Abwehr) — deutlich länger als die übrigen Fixtures.
- Neuer Test `frontend/tests-ct/WunschkaderTabCardHeaderWrap.ct.tsx` — mountet zwei Abwehr-Ziele (kurzer + langer
  Name) bei 480px Viewport (erzwingt zwei ~220px-Spalten) und erwartet gleiche `getBoundingClientRect().height`
  für beide Karten.
- Commit `fe8dd7e`, gepusht. CI (`component-tests` u.a.) war beim Session-Abbruch noch `pending` — **nicht
  verifiziert, ob der Test tatsächlich rot ist**, das ist der erste Schritt der nächsten Session.

**Warum kein Fix + kein lokaler Test-Lauf in dieser Session**: Playwright-Browserausführung ist in der Sandbox
nicht möglich (siehe oben) — Rot/Grün-Verifikation muss über CI laufen, nicht lokal. Test+Fixture wurden deshalb
bewusst zuerst OHNE Fix committet, damit CI den Fehlschlag zeigt, bevor der Fix kommt.

**Nächste Schritte**:
1. `gh pr checks 17` — bestätigen, dass `component-tests` auf Commit `fe8dd7e` tatsächlich rot war. Falls nicht:
   Repro-Annahme (Viewport-Breite, Fixture-Namenslänge) neu prüfen, nicht blind den geplanten Fix übernehmen.
2. In den bestehenden Worktree wechseln (`.claude/worktrees/wunschkader-card-header-wrap`,
   Branch `worktree-wunschkader-card-header-wrap`) — nicht neu anlegen, `npm install` ist dort bereits gelaufen.
3. Fix wie oben beschrieben umsetzen.
4. Lokal `npm test` (Vitest) + `npm run build` prüfen (beide laufen lokal problemlos). Vor dem Commit
   `git diff frontend/package-lock.json` checken — lokales `npm install` kann die Lockfile durch eine andere
   npm-Version umschreiben (großer Diff durch entfernte optionale Plattform-Pakete); das ist reines
   Versions-Rauschen und darf nicht mitcommittet werden (schon einmal in PR #14 zu `EBADPLATFORM` in CI geführt).
5. Committen, pushen, PR-CI grün abwarten. Der Rot-auf-`fe8dd7e` → Grün-auf-dem-Fix-Commit-Übergang erfüllt die
   Projekt-Pflicht „Test zuerst rot, dann grün" + Mutation-Check — ein zusätzlicher dritter Lauf ist dafür nicht
   nötig, da lokale Playwright-Ausführung ohnehin nicht möglich ist.
6. `gh pr merge --auto --squash`.
7. Nach dem Merge: Worktree entfernen (`rm -rf` auf `node_modules` dauert auf diesem Mount ca. 10 Minuten —
   im Hintergrund laufen lassen, nicht synchron warten) und die lokale Branch löschen.
