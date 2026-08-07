# HANDOFF: KickbaseAgent Dashboard

Zustand nach der letzten Session: was zuletzt gemacht wurde und was die nächste Session ggf. aufgreifen sollte. Kein
Backlog — offene Ideen/Schulden ohne aktuellen Auftrag stehen in `BACKLOG.md`. Kein Änderungsprotokoll vergangener
Arbeit (das steht in der Git-Historie, `git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## Zuletzt gemacht (2026-08-07)

- **Wunschkader-Kartenkopf wrap-Bug behoben** (PR #17, gemergt): `flex-wrap` auf der Kartenkopfzeile
  (`WunschkaderTab.tsx`) ließ einen zu langen Namen als eigenes Flex-Item in eine zweite Zeile kippen, kürzere Namen
  blieben einzeilig — macht Karten derselben Positionsgruppe/Bank unterschiedlich hoch. Fix: `flex-wrap` entfernt,
  `flex-1 min-w-0 truncate` auf den Namen-Span, Crest/Badges behalten ihre Größe. Volle Namen bleiben über das
  Detail-Modal erreichbar.
  - Wichtiger Nebenfund beim Verifizieren: der ursprüngliche Test (aus der Vorsession) maß die Höhe des
    `motion.div`-Wrappers (CSS-Grid-Item) statt der sichtbaren, umrandeten Karte darunter — CSS Grids
    `align-items: stretch` gleicht das Grid-Item IMMER an, unabhängig vom Bug, daher war der Test grün, obwohl der
    Bug noch da war. Live per Diagnose-Commit bestätigt (Grid-Item 224px beide, sichtbare Karte 200px vs. 224px).
    Test korrigiert, misst jetzt `div[role="button"]` eine Ebene tiefer.
- **Zweiter, unabhängig gefundener Bug behoben** (PR #18, gemergt): `db.py::connect()`-Migration hatte keinen
  `_ensure_column()`-Eintrag für `purchase_price` — eine bereits bestehende, ältere `data/kickbase.db` crasht beim
  Export mit `sqlite3.OperationalError`. Live in der Sandbox reproduziert (beim manuellen Heavy-Lauf, siehe unten).
  Betrifft nur langlebige lokale/Windows-seitige DB-Dateien, nicht CI (immer frischer Checkout).
- **Manueller Heavy-Dashboard-Lauf**: während eines mehrstündigen GitHub-Actions-Gesamtausfalls (bestätigt über
  githubstatus.com, 2026-08-06 ~18:46 UTC bis ins Deployment-Fenster von PR #17/#18 hinein) lief weder der
  stündliche Light- noch der tägliche Heavy-Cron. Auf Nutzerwunsch wurde `python -m src.dashboard_export`
  (Heavy-Äquivalent zu `dashboard-marktwerte.yml`) direkt in der Sandbox gegen die echte Kickbase-API/Firestore
  ausgeführt, `dashboard_snapshot/latest` ist seitdem wieder aktuell (Stand 2026-08-06/07). Dabei kam der
  `purchase_price`-Bug oben ans Licht.
- Beide PRs liefen über den normalen Workflow (Branch, PR, `--auto --squash`), verzögert durch den Actions-Ausfall
  (Checks blieben teils stundenlang `pending`/`queued`, ein Re-Trigger durch einen `main`-Merge-Commit auf dem
  PR-#17-Branch half, sobald GitHub wieder lief). Kein offener PR, kein offener Worktree mehr — beide Worktrees
  (`.claude/worktrees/wunschkader-card-header-wrap`, Branch für PR #18) inkl. lokaler Branches entfernt.

## Aufzugreifen

Nichts Offenes aus dieser Session. Ein live beobachteter, wahrscheinlich vorbestehender Flaky-Test
(`WunschkaderDragAndDrop.spec.ts`, `maxScroll`-Sanity-Check) ist als technische Schuld in `BACKLOG.md` vermerkt,
nicht hier — kein aktueller Auftrag.
