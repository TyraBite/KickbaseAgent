# PR-Workflow + Branch-Protection für main — Design

## Kontext

Bisherige Konvention: Claude pusht direkt auf `main`, sobald Tests lokal grün sind — kein PR-Umweg. Nach Abschluss der Playwright-Regressionstests-Session (`docs/superpowers/plans/2026-08-03-playwright-regression-coverage.md`) existieren jetzt erstmals aussagekräftige, echte Test-Gates (Backend-pytest, Frontend-Unit-Tests, Playwright Component+E2E). User möchte das jetzt als echtes Merge-Gate nutzen statt nur lokal/manuell laufen zu lassen.

**Wichtiger Fund während der Recherche:** aktuell läuft `pytest` in KEINEM CI-Workflow — die 290 Backend-Tests laufen nur lokal in Sandbox-Sessions, nie automatisiert. `frontend-pilot.yml` triggert nur auf `push` zu main (kein `pull_request`) und macht zusätzlich den GitHub-Pages-Deploy. Branch-Protection für `main` existiert aktuell nicht (`404 Branch not protected`). `allow_auto_merge` ist im Repo aus (`false`).

## Ziel

PR-basierter Workflow für main mit 4 echten Required-Status-Checks, Auto-Merge sobald alle grün, Bypass für Repo-Admin (Owner/Claude) bei trivialen Änderungen, Doku-Änderungen weiterhin per Direkt-Push.

## Architektur

### Neue/geänderte CI-Workflows

**Neu: `.github/workflows/backend-tests.yml`**
- Trigger: `push` (main) + `pull_request`, `workflow_dispatch`.
- `actions/setup-python@v5`, Python `3.11` (wie bestehende Cron-Workflows).
- Installiert `requirements.txt` UND `requirements-news.txt` (inkl. CPU-only-Torch-Vorinstallation: `pip install torch --index-url https://download.pytorch.org/whl/cpu` VOR `pip install -r requirements-news.txt`, exakt das Muster aus `.github/workflows/player-news-sentiment.yml`). Notwendig, weil `src/news_sentiment.py` `germansentiment` unconditional importiert — ohne diesen Schritt würden 28 von 290 Tests (`tests/test_news_sentiment.py`) beim Import scheitern.
- Kein Firebase-Secret nötig — `pytest` läuft komplett gegen Mocks (bestehende Testkonvention, kein `FIRESTORE_ENABLED`).
- Step: `pytest tests/ -v`.
- Job-Name (für Required-Check-Referenz): `pytest`.

**Neu: `.github/workflows/frontend-tests.yml`**
- Trigger: `push` (main) + `pull_request`, `workflow_dispatch`.
- Steps: `npm ci`, `npm run typecheck`, `npm test` (Vitest).
- KEIN Build/Deploy-Schritt — das bleibt exklusiv in `frontend-pilot.yml` (unverändert, weiterhin nur `push` zu main).
- Job-Name: `typecheck-and-unit-tests`.

**Unverändert: `.github/workflows/frontend-playwright-tests.yml`**
- Hat bereits `pull_request`-Trigger. Job-Namen bleiben `component-tests`/`e2e-touch-swipe`.

### Branch-Protection für `main`

Per `gh api -X PUT repos/{owner}/{repo}/branches/main/protection`:
- `required_status_checks`: `strict: true` (Branch muss aktuell zu main sein — erzwingt "Update branch" bei veraltetem PR), `checks`: die 4 Job-Kontexte (`pytest`, `typecheck-and-unit-tests`, `component-tests`, `e2e-touch-swipe`).
- `enforce_admins: false` — Repo-Admins (Owner, und Claude beim Committen als Owner) können weiterhin direkt auf main pushen. Das ist der einzige Bypass-Mechanismus, kein separates Setup nötig.
- `required_pull_request_reviews`: `required_approving_review_count: 0` — PR ist Pflicht, aber keine menschliche Freigabe nötig (Solo-Repo, kein Team-Reviewer verfügbar).
- `restrictions: null` — keine Einschränkung, WER pushen darf (nur WIE — über PR).
- `allow_force_pushes: false`, `allow_deletions: false`.

**Offener Implementierungspunkt:** ob die klassische Branch-Protection-API `required_approving_review_count: 0` tatsächlich akzeptiert, muss beim Umsetzen live gegen die echte GitHub-API verifiziert werden (per `gh api ... | gh api ...` Round-Trip: setzen, dann GET zum Bestätigen). Falls nicht: auf die neuere **Repository-Rulesets-API** (`gh api repos/{owner}/{repo}/rulesets`) ausweichen, die `pull_request`-Regeln mit `required_approving_review_count: 0` sowie eine explizite Bypass-Actors-Liste (Owner-Account) unterstützt — funktional identisches Ergebnis, moderneres Mechanismus. Die Absicht (PR Pflicht, 0 Approvals, Admin-Bypass) ist in jedem Fall bindend, nur der konkrete API-Weg ist Implementierungsdetail.

### Repo-Settings

- `allow_auto_merge`: `false` → `true` (Voraussetzung für `gh pr merge --auto`).
- `allow_merge_commit`: `true` → `false`, `allow_rebase_merge`: `true` → `false` — nur Squash bleibt als Merge-Methode wählbar (verhindert versehentliches Merge-Commit/Rebase über die UI).
- `allow_squash_merge`: bleibt `true`.

## Alltags-Workflow (nach Umsetzung)

**Code-Änderungen** (Backend/Frontend/Tests): `git checkout -b <branch>` → Commits → `git push -u origin <branch>` → `gh pr create` → `gh pr merge --auto --squash`. GitHub merged automatisch, sobald alle 4 Required Checks grün sind. Kein manueller Klick nötig, kein Warten im Chat.

**Doku-Änderungen** (Specs, Pläne, `HANDOFF.md`, `.superpowers/`-Inhalte): weiterhin Direkt-Push auf main — nutzt den Admin-Bypass, deckungsgleich mit der bestehenden "Specs/Pläne sofort auf main"-Präferenz. Keine Tests betroffen, kein PR-Umweg nötig.

**Mischfälle** (Code + Doku im selben Change, z.B. ein Implementierungsplan mit Code-Umsetzung): PR-Pflicht, da Code enthalten ist.

## Testing / Verifikation

- Nach Anlegen der beiden neuen Workflow-Dateien: `gh workflow run backend-tests.yml` und `gh workflow run frontend-tests.yml` (bzw. abwarten bis ein Push/PR sie automatisch triggert), `gh run watch <id> --exit-status` — beide müssen grün laufen, BEVOR die Branch-Protection sie als Required Check eintragen kann (GitHub verlangt, dass ein Check-Name mindestens einmal in den letzten Läufen aufgetaucht ist, sonst lässt sich der Kontext nicht als Required registrieren).
- End-to-End-Test der neuen Regel: einen trivialen Test-PR öffnen (z.B. Kommentar-Änderung im Code, kein Doku-only), prüfen dass (a) Merge über die UI/`gh pr merge` ohne `--admin`-Flag VERWEIGERT wird, solange Checks laufen, (b) nach grünen Checks Auto-Merge tatsächlich durchläuft, (c) ein Direkt-Push auf main als Admin weiterhin funktioniert (Bypass-Test).
- Danach den Test-PR/Branch wieder aufräumen.

## Bewusst außen vor

- Kein Team-Review-Zwang (Solo-Repo).
- Keine Required-Check für die Cron-Workflows (`dashboard.yml`, `dashboard-marktwerte.yml`, `player-news-sentiment.yml`) — die sind Daten-Pipelines, kein Code-Gate.
- Kein PR-Template (`.github/pull_request_template.md`) — nicht angefragt, YAGNI für ein Solo-Repo ohne externe Contributor.
