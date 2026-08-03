# KickbaseAgent — Hinweise für KI-Agenten

Architektur/Setup: siehe `README.md`. Laufender Session-Status/Historie: siehe `HANDOFF.md` — dort lesen, bevor eine
neue Session hier startet.

## Verbindliche Regel: Testabdeckung (seit 2026-08-03)

**Jedes neue Frontend-Feature UND jeder Bugfix muss durch einen automatisierten Test abgedeckt sein, bevor er als
fertig gilt.** Wähler die Test-Ebene passend zum Szenario:

- **Reine Logik/Ableitungsfunktionen** (`frontend/src/lib/derive.ts`, `format.ts`, etc.) → Vitest-Unit-Test
  (`frontend/src/**/*.test.ts`), TDD (Test zuerst, rot, dann grün).
- **Komponenten-Interaktion** (Formular-Verhalten, State-Uebergaenge innerhalb einer Komponente, ohne echten
  Firebase-Zugriff) → Playwright Component Test (`frontend/tests-ct/*.ct.tsx`).
- **App-weites Verhalten** (Tab-Wechsel, Touch-Gesten, Interaktion zwischen mehreren Komponenten) → Playwright E2E
  (`frontend/tests-e2e/*.spec.ts`).
- **Backend** (`src/`) folgt der bereits etablierten Konvention: `unittest`, TDD, siehe bestehende `tests/*.py`.

Ein Bugfix ohne Regressionstest gilt als unvollstaendig — der Test soll den Bug reproduzieren (rot), dann den Fix
verifizieren (gruen). Ausnahme nur bei echter, im PR explizit begruendeter Unmoeglichkeit (z.B. reiner
Text-/Copy-Fix ohne Verhaltensaenderung).

**Wie das durchgesetzt wird:**
1. Diese Datei wird bei jeder neuen Claude-Code-Session automatisch geladen — die Regel ist also nicht nur hier
   dokumentiert, sondern aktiver Kontext von Anfang an.
2. `.github/pull_request_template.md` fragt bei jedem `gh pr create` explizit nach der Testabdeckung — ein PR ohne
   beantwortete Checkliste faellt beim Review auf.
3. Test-Coverage-Luecken werden im laufenden Audit (`docs/superpowers/plans/2026-08-03-test-coverage-audit.md`,
   falls vorhanden — sonst `HANDOFF.md` nach dem aktuellen Stand durchsuchen) priorisiert nachgezogen, nicht nur bei
   neuen Features.

Dies ist eine **Regel, kein CI-Gate** — es gibt (bewusst) keinen automatisierten Check, der einen PR ohne Test hart
blockiert (zu viele legitime Ausnahmen: reine Copy-Fixes, Refactorings ohne Verhaltensaenderung, Doku-PRs). Die
Durchsetzung passiert ueber Review-Disziplin (Punkt 2) und darüber, dass diese Regel jeder Session von Anfang an
bekannt ist (Punkt 1) — nicht über einen harten Gate.

## PR-Workflow (seit 2026-08-03)

Jede funktionale Aenderung (Backend `src/`+`tests/`, Frontend `frontend/src/`+`frontend/tests-*`, CI
`.github/workflows/`) laeuft ueber einen echten PR: `gh pr create` + `gh pr merge --auto --squash` (kein `--admin`
noetig, Auto-Merge funktioniert). Direkt-Push auf `main` bleibt nur fuer reine Doku-/Planungs-Commits (Specs,
Plaene, `HANDOFF.md`, dieses Dokument, Memory-Notizen) ohne Code-Auswirkung. Details/Hintergrund:
`HANDOFF.md` (Abschnitt "PR-Workflow + Branch-Protection").
