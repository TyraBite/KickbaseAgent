# PR-Workflow + Branch-Protection für main Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `main` durch einen echten PR-Workflow mit 4 Required-Status-Checks absichern (Backend-pytest, Frontend-Typecheck+Unit-Tests, Playwright-Component-Tests, Playwright-E2E), mit Admin-Bypass für triviale/Doku-Änderungen und Auto-Merge sobald alle Checks grün sind.

**Architecture:** Zwei neue, schlanke CI-Workflows (`backend-tests.yml`, `frontend-tests.yml`) ergänzen die bestehende `frontend-playwright-tests.yml` (hat `pull_request`-Trigger bereits). Danach Branch-Protection + Repo-Settings per `gh api` gesetzt, jeweils sofort re-verifiziert. Abschließend ein echter End-to-End-Test mit einem Wegwerf-PR, der beweist, dass Merge vor grünen Checks blockiert ist, Auto-Merge danach greift, und der Admin-Bypass für Direkt-Push weiterhin funktioniert.

**Tech Stack:** GitHub Actions, `gh` CLI (bereits authentifiziert in dieser Session), GitHub REST API (Branch-Protection + Repo-Settings-Endpunkte).

## Global Constraints

- Repo: `TyraBite/KickbaseAgent`, Default-Branch `main`.
- Backend-Tests brauchen `requirements.txt` UND `requirements-news.txt` (inkl. CPU-only-Torch-Vorinstallation VOR `requirements-news.txt`) — sonst scheitern 28 von 290 Tests (`tests/test_news_sentiment.py`) am Import von `germansentiment`.
- Kein Firebase-Secret in den neuen Test-Workflows nötig — alle Backend-Tests laufen gegen Mocks.
- Frontend-Test-Workflow macht KEINEN Build/Deploy — das bleibt exklusiv `frontend-pilot.yml` vorbehalten (unverändert).
- Required-Check-Kontext-Namen müssen exakt den Job-IDs in den YAML-Dateien entsprechen: `pytest`, `typecheck-and-unit-tests`, `component-tests`, `e2e-touch-swipe`.
- `enforce_admins: false` ist der EINZIGE Bypass-Mechanismus (Repo-Admin kann direkt pushen) — kein separates Setup.
- Jede API-Änderung (Branch-Protection, Repo-Settings) MUSS sofort per GET re-verifiziert werden, bevor der nächste Task startet.
- Kein Force-Push, keine Branch-Löschung auf main erlauben (`allow_force_pushes: false`, `allow_deletions: false`).

---

## Task 1: Backend-Test-Workflow (`backend-tests.yml`)

**Files:**
- Create: `.github/workflows/backend-tests.yml`

**Interfaces:**
- Produces: CI-Check-Kontext `pytest` (Job-ID) — konsumiert von Task 3 (Required-Status-Check-Liste).

- [ ] **Step 1: Aktuelle pytest-Version ermitteln**

Run: `python3 -m venv /tmp/pytest-version-check && /tmp/pytest-version-check/bin/pip install pytest 2>&1 | tail -5`
Expected: Installation läuft durch, letzte Zeile nennt die installierte Version (z.B. `Successfully installed pytest-8.x.x ...`). Notiere die exakte Version für Step 2.

Danach aufräumen: `rm -rf /tmp/pytest-version-check`

- [ ] **Step 2: Workflow-Datei schreiben**

Neue Datei `.github/workflows/backend-tests.yml` (ersetze `<PYTEST_VERSION>` mit der in Step 1 ermittelten exakten Version, z.B. `8.3.5`):

```yaml
name: Backend Tests (pytest)

# Erster CI-Lauf ueberhaupt fuer die 290 Backend-Tests (tests/*.py) - vorher
# liefen sie nur lokal in Sandbox-Sessions, nie automatisiert. Kein
# Firebase-Secret noetig: alle Tests laufen gegen Mocks. requirements-news.txt
# (inkl. CPU-only-Torch) ist noetig, weil src/news_sentiment.py germansentiment
# unconditional importiert - ohne diesen Schritt wuerden 28 von 290 Tests
# (tests/test_news_sentiment.py) schon beim Import scheitern.

on:
  push:
    branches: [main]
  pull_request: {}
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install torch (CPU-only, vermeidet ~5GB CUDA-Download von germansentiment)
        run: pip install torch --index-url https://download.pytorch.org/whl/cpu

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-news.txt
          pip install pytest==<PYTEST_VERSION>

      - name: Run tests
        # "python -m pytest" statt bloss "pytest": tests/ hat kein __init__.py,
        # daher fuegt der bare pytest-Befehl nur tests/ selbst zu sys.path
        # hinzu, nicht das Repo-Root - "from src.xxx import ..." schlaegt dann
        # mit ModuleNotFoundError fehl (live in CI verifiziert, urspruenglich
        # als bare "pytest" ausgefuehrt gewesen und live gefixt). "python -m"
        # stellt sicher, dass das CWD (Repo-Root) auf sys.path[0] landet.
        run: python -m pytest tests/ -v
```

- [ ] **Step 3: Lokal gegenchecken, dass die Tests mit dieser pytest-Version durchlaufen**

Run: `python3 -m venv /tmp/backend-ci-check && /tmp/backend-ci-check/bin/pip install -r requirements.txt -r requirements-news.txt pytest==<PYTEST_VERSION> 2>&1 | tail -5 && /tmp/backend-ci-check/bin/python -m pytest tests/ -v 2>&1 | tail -20`

(Torch-CPU-Install lokal nicht nötig zu erzwingen — die Sandbox hat ausreichend Platz, ein normaler `pip install -r requirements-news.txt` funktioniert hier auch ohne den CI-spezifischen CPU-only-Trick, der nur in CI wegen Download-Zeit/Kosten relevant ist.)

Expected: `290 passed` (oder die zu diesem Zeitpunkt aktuelle Gesamtzahl — prüfe `grep -rc "def test_" tests/*.py` vorher, falls sich die Zahl seit Planerstellung geändert hat).

Danach aufräumen: `rm -rf /tmp/backend-ci-check`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/backend-tests.yml
git commit -m "CI: Backend-pytest-Workflow (erster automatisierter Lauf der 290 Tests)"
```

- [ ] **Step 5: Push und ersten CI-Lauf abwarten (Voraussetzung für Task 3)**

Run: `git push` (auf dem aktuellen Arbeits-Branch, NICHT direkt main — dieser Task läuft im Rahmen der subagent-driven-development-Ausführung, die eigene Branch-Konventionen hat).

Nach dem finalen Merge dieses Plans nach main (letzter Schritt der gesamten Ausführung) MUSS mindestens ein `push`-Lauf auf main existieren, damit GitHub den Kontext `pytest` überhaupt als Required-Check-Kandidat kennt (Task 3 hängt davon ab). Vermerke das explizit im Ledger, falls die Reihenfolge nicht sofort so passt.

---

## Task 2: Frontend-Test-Workflow (`frontend-tests.yml`)

**Files:**
- Create: `.github/workflows/frontend-tests.yml`

**Interfaces:**
- Produces: CI-Check-Kontext `typecheck-and-unit-tests` — konsumiert von Task 3.

- [ ] **Step 1: Workflow-Datei schreiben**

Neue Datei `.github/workflows/frontend-tests.yml`:

```yaml
name: Frontend Tests (Typecheck + Unit)

# Bewusst getrennt von frontend-pilot.yml (das bleibt push-only zu main und
# macht zusaetzlich den GitHub-Pages-Deploy, den wir nicht auf jedem PR
# wollen). Dieser Workflow deckt NUR Typecheck+Vitest ab, kein Build/Deploy.

on:
  push:
    branches: [main]
  pull_request: {}
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  typecheck-and-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci

      - name: Typecheck
        working-directory: frontend
        run: npm run typecheck

      - name: Unit tests
        working-directory: frontend
        run: npm test
```

- [ ] **Step 2: Lokal gegenchecken**

Run: `cd frontend && npm run typecheck && npm test`
Expected: Typecheck 0 Fehler, alle Vitest-Tests grün.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/frontend-tests.yml
git commit -m "CI: Frontend-Typecheck+Unit-Test-Workflow (getrennt vom Deploy)"
```

---

## Task 3: Branch-Protection für `main` setzen

**Files:**
- Keine Code-Dateien — reine GitHub-API-Konfiguration.

**Interfaces:**
- Consumes: die 4 Check-Kontexte (`pytest`, `typecheck-and-unit-tests` aus Task 1/2; `component-tests`, `e2e-touch-swipe` bereits aus der bestehenden `frontend-playwright-tests.yml`).

**Voraussetzung:** Task 1 und Task 2 müssen bereits mindestens einmal erfolgreich (oder zumindest einmal überhaupt) auf `main` oder einem PR gelaufen sein — GitHub lässt einen Kontext nur als Required Check registrieren, wenn er in den letzten Check-Runs des Repos aufgetaucht ist. Falls das noch nicht der Fall ist: `gh workflow run backend-tests.yml`, `gh workflow run frontend-tests.yml`, dann `gh run watch <id> --exit-status` für beide, BEVOR dieser Task fortfährt.

- [ ] **Step 1: Aktuellen (fehlenden) Schutzstatus dokumentieren**

Run: `gh api repos/TyraBite/KickbaseAgent/branches/main/protection 2>&1`
Expected: `404 Branch not protected` (Ausgangszustand, zur Doku im Report).

- [ ] **Step 2: Branch-Protection setzen**

Run:
```bash
gh api -X PUT repos/TyraBite/KickbaseAgent/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "pytest"},
      {"context": "typecheck-and-unit-tests"},
      {"context": "component-tests"},
      {"context": "e2e-touch-swipe"}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

**Falls dieser Call mit einem 4xx-Fehler zu `required_approving_review_count: 0` fehlschlägt** (die klassische Branch-Protection-API akzeptiert das je nach GitHub-Plan/Version ggf. nicht): auf die Repository-Rulesets-API ausweichen:

```bash
gh api -X POST repos/TyraBite/KickbaseAgent/rulesets \
  --input - <<'EOF'
{
  "name": "main-pr-required",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {"include": ["refs/heads/main"], "exclude": []}
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false}
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "pytest"},
          {"context": "typecheck-and-unit-tests"},
          {"context": "component-tests"},
          {"context": "e2e-touch-swipe"}
        ]
      }
    },
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ],
  "bypass_actors": [
    {"actor_type": "OrganizationAdmin", "bypass_mode": "always"}
  ]
}
EOF
```

(Falls `bypass_actors` mit `OrganizationAdmin` bei einem persönlichen, nicht-Org-Repo fehlschlägt: stattdessen den eigenen User-Account als `actor_type: "RepositoryRole", actor_id: 5` — die Rolle-ID für "Admin" — eintragen, oder ganz weglassen und stattdessen `enforce_admins`-Äquivalent über die Ruleset-UI im Browser einmalig nachjustieren. Dokumentiere im Report, welcher Pfad (klassische Branch-Protection oder Ruleset) tatsächlich funktioniert hat.)

- [ ] **Step 3: Sofort re-verifizieren**

Run: `gh api repos/TyraBite/KickbaseAgent/branches/main/protection` (bei klassischer Branch-Protection) ODER `gh api repos/TyraBite/KickbaseAgent/rulesets` (bei Ruleset-Pfad).

Expected: die Antwort spiegelt exakt die 4 Kontexte, `enforce_admins: {"enabled": false}`, `required_pull_request_reviews.required_approving_review_count: 0`, `allow_force_pushes: {"enabled": false}`, `allow_deletions: {"enabled": false}` wider (Feldnamen bei Ruleset-Pfad leicht anders, aber inhaltlich äquivalent — prüfe gegen die gesendete Payload).

- [ ] **Step 4: Rollback-Befehl dokumentieren (nicht ausführen, nur für den Report)**

Klassische Branch-Protection entfernen: `gh api -X DELETE repos/TyraBite/KickbaseAgent/branches/main/protection`
Ruleset entfernen: `gh api -X DELETE repos/TyraBite/KickbaseAgent/rulesets/<ruleset_id>` (die `<ruleset_id>` steht in der Antwort von Step 2/3).

- [ ] **Step 5: Commit**

Keine Code-Änderung in diesem Task — stattdessen im SDD-Ledger UND im finalen Report exakt dokumentieren: welcher API-Pfad (klassisch oder Ruleset) tatsächlich verwendet wurde, mit der vollen Response aus Step 3.

---

## Task 4: Repo-Settings anpassen (Auto-Merge + Merge-Methoden)

**Files:**
- Keine Code-Dateien — reine GitHub-API-Konfiguration.

- [ ] **Step 1: Aktuellen Zustand dokumentieren**

Run: `gh api repos/TyraBite/KickbaseAgent | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({k:d[k] for k in ['allow_auto_merge','allow_squash_merge','allow_merge_commit','allow_rebase_merge']}, indent=2))"`
Expected (Ausgangszustand, zur Doku): `allow_auto_merge: false`, die drei Merge-Methoden alle `true`.

- [ ] **Step 2: Settings ändern**

Run:
```bash
gh api -X PATCH repos/TyraBite/KickbaseAgent \
  -F allow_auto_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F allow_squash_merge=true
```

(`-F` statt `-f` für Boolean-Werte, damit `gh api` sie als JSON `false`/`true` sendet statt als String `"false"` — `-f` würde einen String senden, den die API ggf. als truthy interpretiert.)

- [ ] **Step 3: Sofort re-verifizieren**

Run: dasselbe Kommando wie Step 1.
Expected: `allow_auto_merge: true`, `allow_squash_merge: true`, `allow_merge_commit: false`, `allow_rebase_merge: false`.

- [ ] **Step 4: Rollback-Befehl dokumentieren (nicht ausführen, nur für den Report)**

```bash
gh api -X PATCH repos/TyraBite/KickbaseAgent \
  -F allow_auto_merge=false \
  -F allow_merge_commit=true \
  -F allow_rebase_merge=true \
  -F allow_squash_merge=true
```

- [ ] **Step 5: Commit**

Keine Code-Änderung — im Ledger/Report die Vorher-/Nachher-Werte aus Step 1/3 festhalten.

---

## Task 5: End-to-End-Verifikation mit Wegwerf-PR

**Files:**
- Create (temporär, wird am Ende dieses Tasks wieder gelöscht): `docs/scratch/pr-workflow-e2e-check.md`

**Interfaces:**
- Consumes: die in Task 3/4 gesetzte Branch-Protection + Repo-Settings.

- [ ] **Step 1: Test-Branch anlegen**

Run:
```bash
git checkout -b test/pr-workflow-e2e-check
mkdir -p docs/scratch
echo "Wegwerf-Datei zur End-to-End-Verifikation des PR-Workflows (siehe docs/superpowers/plans/2026-08-03-pr-workflow-branch-protection.md, Task 5). Wird nach dem Test wieder geloescht." > docs/scratch/pr-workflow-e2e-check.md
git add docs/scratch/pr-workflow-e2e-check.md
git commit -m "test: Wegwerf-Commit fuer PR-Workflow-E2E-Check (wird geloescht)"
git push -u origin test/pr-workflow-e2e-check
```

- [ ] **Step 2: PR öffnen und Auto-Merge aktivieren**

```bash
gh pr create --title "test: PR-Workflow E2E-Check (wird geschlossen)" --body "Wegwerf-PR zur Verifikation der neuen Branch-Protection. Wird nach dem Test geschlossen, nicht gemerged in dem Sinne, dass der Inhalt behalten wird."
gh pr merge --auto --squash
```

- [ ] **Step 3: Verifizieren, dass der Merge VOR grünen Checks blockiert ist**

Run: `gh pr view --json mergeStateStatus,autoMergeRequest`
Expected: `mergeStateStatus` zeigt `BLOCKED` oder `UNSTABLE` (nicht `CLEAN`), solange die 4 Checks noch laufen — `autoMergeRequest` ist gesetzt (Auto-Merge ist scharf, wartet aber).

- [ ] **Step 4: Checks abwarten, Auto-Merge-Erfolg verifizieren**

Run: `gh pr checks --watch` (wartet auf alle 4 Checks), danach `gh pr view --json state,mergedAt`
Expected: `state: "MERGED"`, `mergedAt` ist gesetzt — GitHub hat automatisch gemerged, ohne dass hier ein expliziter `gh pr merge`-Zweitaufruf nötig war.

- [ ] **Step 5: Admin-Bypass für Direkt-Push verifizieren**

Run (auf einem NEUEN, kleinen Testcommit direkt auf main, NICHT über PR):
```bash
git checkout main && git pull
echo "" >> docs/scratch/pr-workflow-e2e-check.md
git add docs/scratch/pr-workflow-e2e-check.md
git commit -m "test: Admin-Bypass-Direktpush-Check (wird sofort wieder entfernt)"
git push origin main
```
Expected: Push gelingt (kein `remote rejected` wegen Branch-Protection) — bestätigt, dass `enforce_admins: false` den Admin-Bypass tatsächlich erlaubt.

- [ ] **Step 6: Aufräumen**

```bash
git rm docs/scratch/pr-workflow-e2e-check.md
git commit -m "test: Wegwerf-Datei aus PR-Workflow-E2E-Check wieder entfernt"
git push origin main
git branch -d test/pr-workflow-e2e-check 2>/dev/null
git push origin --delete test/pr-workflow-e2e-check 2>/dev/null
gh pr list --state merged --search "PR-Workflow E2E-Check" --json number --jq '.[0].number' | xargs -I{} gh pr close {} 2>/dev/null || true
```

(Der letzte `gh pr close`-Befehl ist idempotent/best-effort — der PR ist nach Step 4 bereits `MERGED`, nicht mehr offen; falls das Kommando nichts findet, ist das kein Fehler.)

- [ ] **Step 7: Abschlussdokumentation**

Im Report festhalten: vollständige Ausgabe aus Step 3 (blockiert) und Step 4 (gemerged), Bestätigung aus Step 5 (Bypass funktioniert), Bestätigung dass `docs/scratch/` nach Step 6 wieder leer/nicht mehr vorhanden ist (`git log --oneline -5` zur Doku).

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle 4 Architektur-Abschnitte der Spec haben einen Task (Backend-Workflow → Task 1, Frontend-Workflow → Task 2, Branch-Protection → Task 3, Repo-Settings → Task 4), plus der explizit in der Spec verlangte End-to-End-Test → Task 5.
- **Platzhalter-Scan**: `<PYTEST_VERSION>` in Task 1 ist ein bewusster, im selben Task per Step 1 aufgelöster Platzhalter (live ermittelt, nicht geraten) — kein TBD/TODO sonst im Plan.
- **Risiko-Behandlung**: die zwei am schwersten rückgängig zu machenden Schritte (Branch-Protection, Repo-Settings) haben je einen expliziten Rollback-Befehl UND einen sofortigen Re-Verifikations-Schritt, wie vom User/Spec verlangt.
- **Reihenfolge-Abhängigkeit**: Task 3 kann erst wirklich greifen, wenn Task 1/2 mindestens einmal gelaufen sind (GitHub-Anforderung an Required-Check-Kontexte) — explizit als Voraussetzung markiert, nicht stillschweigend angenommen.
- **API-Unsicherheit**: `required_approving_review_count: 0` ist laut Spec ein offener Punkt — Task 3 enthält einen vollständigen, lauffähigen Fallback-Pfad (Rulesets-API), nicht nur einen Hinweis "im Zweifel anders machen".
