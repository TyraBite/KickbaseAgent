# CLAUDE.md — KickbaseAgent

Diese Datei wird zu Beginn jeder Claude-Code-Session geladen. Sie beschreibt,
**wie** in diesem Repo gearbeitet wird — vor jeder neuen Session lesen.

`HANDOFF.md` ist der Gegenpart dazu: offene Aufgaben und Themen, die noch
geplant oder umgesetzt werden müssen — ebenfalls vor jeder neuen Session
lesen. `HANDOFF.md` ist bewusst **kein** fortlaufendes Änderungsprotokoll
vergangener Arbeit (das steht in der Git-Historie, `git log`) — sondern eine
kompakte, aktuell gehaltene Liste dessen, was als Nächstes ansteht. Abgeschlossene
Punkte werden aus `HANDOFF.md` entfernt, nicht dort angehäuft.

Setup-Befehle stehen im `README.md` und werden hier nicht wiederholt — das
README muss deshalb selbst aktuell gehalten werden. Ändert sich Setup,
Architektur oder Modulkarte, gehört die Aktualisierung des `README.md` zum
Task dazu, nicht als separater Nachtrag.

## Was das Projekt ist

Decision-Support für Kickbase: Daten sammeln, aufbereiten, Signale anzeigen.
Der Mensch entscheidet und klickt. Es gibt bewusst **keine** schreibenden
Kickbase-API-Calls (kein Auto-Bidding) — das ist ein anderes Risikoprofil und
wird nicht "nebenbei" eingebaut.

Zweiter, gleichrangiger Arbeitseingang neben dem Chat: das Firestore-Dokument
`feedback/current` (Tab „Bugs & Ideen"). Offene Einträge (`status:"open"`) dort
aktiv prüfen, nicht nur auf Chat-Aufträge reagieren. Nach der Umsetzung auf
`status:"done"` setzen — aber erst, wenn live verifiziert.

## Grundhaltung: ehrliche Daten schlagen vollständige Daten

Das ist die Leitlinie des ganzen Projekts, im Code wie in den `MDs/`:

- Ein unbekannter Wert wird als „–" angezeigt, **nie** als `0`, `–0 €` oder als
  geschätzte Zahl ohne Kennzeichnung. Ein Geldfeld, das „kostenlos" suggeriert,
  ist ein kritischer Bug, kein Schönheitsfehler.
- Wo geschätzt wird, steht die Herkunft dran („(Schätzung)", „(geringe
  Datenbasis, n=X)"). Zahl und Label kommen aus **einer** Funktion, damit sie
  nicht auseinanderlaufen können.
- Keine Bedeutung erfinden, die nicht verifiziert ist — siehe `MDs/codes.md`
  für das Muster (Status-Code 8 ist unbekannt und bleibt unbekannt, bis ein
  In-App-Beleg existiert).
- Lieber eine Lücke im UI als eine plausible Behauptung.

## Architektur — die vier Regeln, die nicht verhandelbar sind

**1. Backend liefert Rohdaten, das Frontend leitet ab.**
Alles, was aus vorhandenen Rohdaten berechenbar ist — Fairwert, Signal,
Status-Text, Trend, Budgetplan, ROI, Auktions-Countdown, Sortierung, Filter —
gehört nach `frontend/src/lib/derive.ts`. Das Backend schreibt nur, was es
nicht selbst errechnen kann (Kickbase-Rohdaten, ML-Prognosen, historische
Aggregate). Bevor ein neues Firestore-Feld entsteht: prüfen, ob es ableitbar
ist. Wenn ja, ist das neue Feld der Fehler.

**2. `player_id` ist der einzige Join-Key.** Niemals über Spielernamen joinen
oder matchen. Der Grund steht in `MDs/datencheck.md` („Stange" vs. „Stage") und
hat schon einmal echten Schaden angerichtet.

**3. Ein Firestore-Snapshot-Dokument.** `dashboard_snapshot/latest` enthält eine
`players`-Map (`player_id -> Rohdaten`) plus dünne Referenzlisten. Keine
parallelen, namensverknüpften Arrays. Ändert sich das Key-Set von `export()`,
muss der Contract-Test (`AssembleSnapshotContractTests.EXPECTED_KEYS`)
mitgezogen werden — der existiert genau deshalb.

**4. Light und Heavy sind getrennt.** `DASHBOARD_MODE=light` (stündlich, günstig)
vs. `heavy` (1×/Tag, teure Kickbase-Calls, ML, Historien-Writes). Beim Ändern
von `dashboard_export.py` immer beide Zweige durchdenken: was der Light-Lauf
stündlich überschreibt, darf keine Diff-Baseline für den Heavy-Lauf sein
(diese Falle hat schon einmal Historie dauerhaft vernichtet — Kickbase liefert
keine Zeitreihen nach). Nach einem großen Schema-Wechsel Frontend-Deploy und
Backend-Cron nicht als synchron annehmen — beide laufen unabhängig
voneinander. Ein Frontend-Push kann live gehen, bevor der nächste Backend-Lauf
das neue Schema geschrieben hat (führte hier schon zu einem echten
Weißer-Bildschirm-Vorfall) — nach jedem größeren Schema-Wechsel sofort einen
Heavy-Lauf erzwingen (`gh workflow run dashboard-marktwerte.yml`), nicht auf
den nächsten planmäßigen Cron warten.

## Modulkarte

**Backend (`src/`, Python)** — Details im `README.md`. Kurz:
`kickbase_client.py` (API-Wrapper, `select_league()` public und von allen
Einstiegspunkten genutzt), `fetcher.py` (ein Abruf-Lauf → SQLite via `db.py`),
`manager_budgets.py`, `player_valuation.py`, `market_predictor.py`,
`bid_premium.py`, `news_sentiment.py`, `firestore_db.py`,
`dashboard_export.py` (Haupt-Einstiegspunkt, baut den Snapshot).

Daneben existiert ein **älterer, paralleler Pfad**: `prompt_builder.py` /
`discord_notify.py` / `main.py` baut einen Text-Prompt für die manuelle
Claude-Konversation. Der nutzt eigene Felder aus SQLite und hat mit dem
Dashboard/Firestore nichts zu tun. Beim Entfernen „toter" Felder dort **nicht**
mitaufräumen, ohne diesen Pfad zu prüfen.

**Frontend (`frontend/`, React + Vite + TypeScript + Tailwind)**
- `lib/derive.ts` — alle Ableitungen, reine Funktionen, das Herz der App
- `types.ts` — Wire-Typen des Snapshots (liegt direkt unter `frontend/src/`,
  nicht unter `lib/`)
- `format.ts` — Formatierung (ebenfalls direkt unter `frontend/src/`); `lib/use*.ts` — Hooks
- `components/ui.tsx` — geteilte Bausteine (`Row`, `Badge`, `PositionBadge`,
  `FitnessBadge`, `TeamCrest`); `components/table.tsx` — `SortableTable`,
  geteilt über mehrere Tabs; `components/icons.tsx` — Inline-SVG-Icons
- Tabs als `*Tab.tsx`-Dateien direkt in `frontend/src/components/` (kein
  eigener `tabs/`-Ordner)

Neue Logik landet in `derive.ts` (testbar), nicht in einer Tab-Komponente.
Ein Muster, das in zwei Tabs auftaucht, wird nach `ui.tsx`/`derive.ts`
konsolidiert, statt kopiert zu werden.

**Wissensspeicher (`MDs/*.md`)** — von Hand gepflegte Recherche-Methodik
(Startelf-Einschätzungen, Verletzungslage, Schwellenwerte, Datenqualität).
**Kein Code-Feature und kein Generierungsziel.** Nie aus Modellwissen
ergänzen. Änderungen daran nur auf ausdrücklichen Wunsch, und dann als reiner
Doku-Commit.

## Code-Style — Python

- Kommentare nur, wo die Logik wirklich nicht-offensichtlich ist (Warum, nicht
  Was). Klare Namen und kleine Funktionen ersetzen Kommentare.
- Modulinterne Funktionen mit führendem Unterstrich (`_build_players_map`,
  `_resolve_is_light`, `_detect_field_changes`). Public nur, was ein anderes
  Modul wirklich braucht.
- **Parametrisieren statt duplizieren.** Zwei Varianten derselben Berechnung
  bekommen einen Parameter (`target_col`, `horizon_days`, `doc_id_fn`), keine
  zweite Kopie. Ein Bugfix muss an einer Stelle passieren. Eine „eigene Kopie
  der Modellparameter" im Backtest war schon einmal die Ursache stiller Drift.
- **Strukturell gleiche Parameter immer als Keyword-Argument übergeben.** Drei
  `dict`-Parameter nebeneinander sind sonst irgendwann vertauscht.
- **Fehlerklassen trennen.** Ein fehlgeschlagener Write auf den kritischen Pfad
  (`dashboard_snapshot`) muss den Lauf failen lassen (`FirestoreWriteError`) —
  eine stille alte Seite ist schlimmer als ein roter Workflow. Ein Fehler in
  einem Nebenpfad (Historien-Logs, Sentiment) darf den kritischen Write **nicht**
  verhindern. Bei Zeiger-/Fortschritts-Logik zwischen PERMANENT (Zeiger rückt
  vor) und TRANSIENT (Zeiger friert ein) unterscheiden.
- **Doc-Ids idempotent wählen.** Ein Wiederholungslauf darf keine Duplikate
  erzeugen — und wenn dieselbe Quelle über mehrere Tage erneut auftaucht, darf
  das Datum nicht Teil der Id sein.
- **Firestore-Reads/Writes/Deletes sind ein Budget.** Spark-Free-Tier: 50.000
  Reads/Tag, 20.000 Writes/Tag, 20.000 Deletes/Tag, Reset täglich um
  Mitternacht Pacific Time. Vor jeder größeren Aktion (Backfill,
  Hyperparameter-Suche mit mehreren Corpus-Builds, Massen-Tests) die
  Read-/Write-Anzahl abschätzen und im Log ausgeben — mehrere
  Smoke-Test-Läufe, die je einen vollen Corpus neu laden, summieren sich
  schnell (2026-08-04: Testläufe + Tagesverbrauch zusammen haben die
  Read-Quota erschöpft, stündlicher Light-Job schlug sichtbar fehl). Bei
  einem langen Produktionslauf (z.B. 11h-Suche) den Corpus einmalig laden,
  danach rein In-Memory arbeiten — keine weiteren Reads während der
  eigentlichen Schleife.
- Dependencies in `requirements.txt` **exakt gepinnt**. Schwere/optionale
  Abhängigkeiten (Torch/Transformers) bleiben in `requirements-news.txt` und
  werden nur im zugehörigen Workflow installiert.
- Teure oder fragile Pipeline-Schritte bekommen einen Env-Kill-Switch
  (Vorbild: `MARKET_PREDICTOR_ENABLED`), damit der Rest weiterläuft.
- Neue Env-Variablen/Secrets in **allen** Workflows verdrahten, die sie
  brauchen — ein Secret, das nur in der lokalen `.env` steht, ist in Produktion
  wirkungslos und der Fehler ist wochenlang unsichtbar. Auch ein bereits per
  `gh secret set` gesetztes Secret allein bewirkt noch nichts — es muss
  zusätzlich im `env:`-Block der jeweiligen Workflow-YAML referenziert werden
  (`${{ secrets.NAME }}`), sonst bleibt es wirkungslos, ohne dass das auffällt.

## Code-Style — TypeScript / React

- **Ableitungen sind reine Funktionen** in `derive.ts`, ohne React-Bezug, ohne
  Datumszugriff auf `Date.now()` im Inneren (Zeit kommt als Parameter, z. B. aus
  dem geteilten `useNow`-Ticker in `App.tsx`). Nur so sind sie mit Vitest
  testbar und nur so bleibt die Zeitlogik deterministisch.
- **Zeitzonen: Europe/Berlin, DST-sicher.** Auktions-Countdown und
  Update-Cutoff sind schon zweimal an DST gescheitert. Neue Zeitlogik gegen die
  bestehenden Helfer in `derive.ts` bauen, nicht neu erfinden.
- Keine `<form>`-Tags; Interaktion über `onClick`/`onChange`.
- `localStorage` nur mit `kickbaseagent_`-Präfix (`kickbaseagent_active_tab`,
  `kickbaseagent_view_<tab>`). Keys sind Kompatibilitäts-Verträge — beim
  Umbenennen eines Tabs bleibt der `key` unverändert.
- Tailwind: nur Utility-Klassen der Config (`brand`-Skala, `slate`),
  `darkMode: "media"`. **Jede neue Textfarbe/Select/Input im Dark Mode
  gegenprüfen** — unlesbarer Dark-Mode-Text ist hier ein wiederkehrender Bug.
- Mobile ist ein Bürger erster Klasse: Tap-Ziele ≥ 44px, Wisch-Gesten wechseln
  Tabs. Jedes neue Overlay/Modal registriert sich per
  `useModalOpenTracking()`, sonst wischt der Nutzer den Hintergrund-Tab weg.
  Scroll-/Touch-Handler nie desktop-only testen.
- Icons als Inline-JSX mit `fill="currentColor"`/`stroke="currentColor"` in
  `icons.tsx` (erben Textfarbe), nicht als `<img src>`.
- **Keine echten Vereinslogos.** Die Wappen in `frontend/public/crests/` sind
  selbst generierte Monogramme — bewusst, wegen Markenrecht. Dabei bleibt es.
- Tote Felder und tote Funktionen werden gelöscht, nicht kommentiert. Ein Feld,
  das nur geschrieben und nirgends gelesen wird, gehört raus (Backend,
  `types.ts`, `derive.ts` — alle drei).

## Domänen-Vokabular (bitte exakt so)

Code, Bezeichner und Commits auf Englisch; UI-Texte und Doku auf Deutsch.
Diese Begriffe sind app-weit vereinheitlicht — nicht wieder aufweichen:

| Begriff | Bedeutung |
|---|---|
| **Fitness** | Spielerzustand: Fit / Verletzt / Angeschlagen / Im Aufbau (`status_code`) |
| **Verfügbarkeit** | Markt-Status (gelistet, Angebot, frei) — nicht mit Fitness vermischen |
| **Kapital** | exakter Kontostand (`own_budget_exact`) |
| **Budget** | inkl. Überziehungsrahmen (`own_available_budget`) |
| **average_points** | Punkteschnitt (nicht `points_avg`, nicht `total_points`) |
| **k/Punkt** | `market_value / average_points` — app-weit diese eine Definition |
| **Prognose 1T / 3T** | ML-Prognose je Horizont (nicht „ML-Prognose", nicht „Einschätzung") |
| **Fairwert / Signal** | positionsbezogene Referenzbewertung aus `player_valuation.py` |

Status-Codes: `{1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau"}` — verifiziert,
Quelle ist `MDs/codes.md`. Code `8` ist unbeobachtet und **nicht** zu raten.

## Tests (verbindlich)

**Jedes neue Feature UND jeder Bugfix ist erst fertig, wenn ein automatisierter
Test ihn abdeckt.** Ein Bugfix ohne Regressionstest ist unvollständig: Test
zuerst rot (reproduziert den Bug), dann grün. Ebene passend wählen:

| Was | Wo | Runner |
|---|---|---|
| Reine Logik (`derive.ts`, `format.ts`, …) | `frontend/src/**/*.test.ts` | Vitest, TDD |
| Komponenten-Interaktion, ohne echtes Firebase | `frontend/tests-ct/*.ct.tsx` | Playwright CT |
| App-weites Verhalten (Tabs, Touch, Zusammenspiel) | `frontend/tests-e2e/*.spec.ts` | Playwright E2E |
| Backend | `tests/*.py` (`unittest.TestCase`) | CI: `python -m pytest tests/ -v` |

Immer `python -m pytest` (nicht bares `pytest`) — `tests/` hat kein
`__init__.py`, bare Aufrufe finden `src` nicht.

Ausnahme nur bei echter, im PR begründeter Unmöglichkeit (reiner Copy-Fix ohne
Verhaltensänderung). Es gibt bewusst **kein** hartes CI-Gate dafür; die
Durchsetzung läuft über diese Datei und `.github/pull_request_template.md`.

**Was Unit-Tests hier zuverlässig nicht finden:** Debounce-/Timing-Fehler,
Cursor-Position, Touch-Gesten, echte Netz-/RSS-/Sentiment-Läufe, kaputte
Dependency-Auflösung. Bei Änderungen mit diesem Risikoprofil gehört ein echter
Browser- oder Live-Smoke-Test dazu. Erfahrungswert aus mehreren Sessions: dort
fand der echte Test **jedes Mal** einen Bug, den mehrere statische Reviews
übersehen hatten. Jeder Test wird per Mutation-Check verifiziert (Fix
temporär zurücknehmen → Test muss rot werden), sonst ist er vakuos.

Die Sandbox hat echten Live-Zugriff auf Kickbase-API und Firestore (`.env` +
`firebase-service-account.json` im Repo-Root). Vor dem Bau eines Umwegs über
GitHub Actions also erst testen, ob es direkt geht.

## Git- und PR-Workflow

Jede funktionale Änderung (`src/`, `tests/`, `frontend/src/`,
`frontend/tests-*`, `.github/workflows/`) läuft über einen echten PR:
`gh pr create` + `gh pr merge --auto --squash` (kein `--admin` nötig).
`main` ist per Ruleset geschützt, 4 Required Checks.

Direkt-Push auf `main` bleibt nur für reine Doku-/Planungs-Commits (Specs,
Pläne, `HANDOFF.md`, diese Datei) ohne Code-Wirkung. Im Zweifel: PR.

Zeilenenden sind LF (`.gitattributes: * text=auto eol=lf`) — CRLF-Drift von der
Windows-Seite nicht mitcommitten. `data/kickbase.db` ist gitignored und wird
bei jedem Lauf neu erzeugt; nie zurückcommitten.

An diesem Repo arbeiten gelegentlich **mehrere Sessions/Worktrees parallel**.
Vor dem Start `git status`, `git log`, `git worktree list` prüfen und nicht
etwas duplizieren, das schon in Arbeit ist. GitHub Actions liest beim
Merge/Check immer vom Remote `main`, nicht von lokalen Commits — vor jeder
Live-Verifikation eines frischen Fixes `git log origin/main --oneline`
prüfen, nicht davon ausgehen, dass ein lokaler Commit schon gepusht ist.

## Sandbox- und Ausführungshinweise

- `npm install`/`npm run` **niemals im Haupt-Checkout** ausführen
  (`/workspace/work` ist ein Windows-DrvFs-Mount mit geteilter `node_modules` —
  ein `npm install` dort würde Unix-Bin-Shims statt `.cmd`-Dateien erzeugen und
  `npm run` auf der Windows/Rider-Seite brechen). In einer eigenen, isolierten
  Git-Worktree ist `npm install` dagegen unproblematisch (eigene
  `node_modules`-Kopie).

## Vorgehen bei größeren Änderungen

- Bei Architekturentscheidungen, mehreren betroffenen Dateien, neuen
  Dependencies oder Refactors: kurz den Plan skizzieren (was, warum), bevor
  Code entsteht. Bei Tippfehlern und Einzeilern einfach machen.
- **Jedes größere Feature und jeder nicht-triviale Bugfix läuft über
  Spec + Plan, bevor Code entsteht** — Design/Kontext/Entscheidungen als Spec
  nach `docs/superpowers/specs/YYYY-MM-DD-<thema>-design.md`, danach die
  Umsetzung als Task-für-Task-Plan nach `docs/superpowers/plans/YYYY-MM-DD-
  <thema>.md`. Beide Dokumente werden committet (Doku-Commit, Direkt-Push
  erlaubt), bevor die eigentliche Umsetzung beginnt. Bei einer reinen
  Umsetzung ohne offene Design-Fragen (z. B. eine bereits im Chat
  durchgesprochene, klar gescopte Änderung) reicht ein Plan ohne separate
  Spec. Ausführung danach bevorzugt subagent-driven (frischer Implementer +
  Reviewer pro Task), nicht inline im Hauptkontext.
- Existieren mehrere sinnvolle Wege mit relevanten Konsequenzen: Optionen mit
  Trade-offs nennen statt still einen auszuwählen.
- **Jeden Plan gegen den echten, aktuellen Code verifizieren, nicht gegen den
  Konversationskontext oder einen älteren Plan.** Die betroffenen Dateien vor
  dem Schreiben der Tasks tatsächlich lesen. Ein Plan von letzter Woche kann
  stale sein; ein bereits „abgenickter" Task kann durch einen späteren Fix
  widerlegt sein. Ground Truth ist die laufende Implementierung.
- Subagent-Berichte nie ungeprüft übernehmen — `git diff` / `git status`
  selbst ansehen.
- Fehlt eine Information, die das Ergebnis wesentlich verändert: nachfragen.
  Keine stillen Annahmen. Eine Sandbox-Fähigkeit („ich kann X nicht") vor dem
  Umweg explizit testen.
- Bei einer Sammelbestätigung des Users („passt so") über mehrere gleichzeitig
  geänderte Dateien hinweg nachfragen, welche Teile gemeint sind.
- Bei Governance-/Berechtigungsfragen auf GitHub alle relevanten Endpunkte
  auflisten (`/rulesets` *und* `/branches/main/protection`), nicht nur den
  erwarteten einen — sie gelten kumulativ.

## ML-spezifisch

- Zielwerte und Features sind in `market_predictor.py` zentral definiert
  (`FEATURES`, `TARGET_*`). Kein Feature „mal ausprobieren" und drin lassen —
  toter, aber getesteter Berechnungscode ist ok, ein inaktives Feature in
  `FEATURES` nicht.
- Bewertung nur per Walk-Forward über genug Folds. Kleine Fold-Zahlen haben hier
  schon zu einer um 8 Prozentpunkte zu optimistischen Behauptung geführt.
- **Bei Mehrtage-Horizonten gehört ein Embargo in die Walk-Forward-Evaluation**
  (die letzten `horizon_days` Trainingstage vor jedem Cutoff ausschließen).
  Ohne das leckt das Label über den Cutoff und tiefe, unregularisierte Modelle
  gewinnen scheinbar. `_walk_forward_backtest()` embargot deshalb bei
  Mehrtage-Horizonten die letzten `horizon_days` Trainingstage vor jedem
  Cutoff (siehe `_apply_embargo` in `market_predictor.py`) — jede neue
  Mehrtage-Auswertung nutzt denselben Helfer, statt die Logik neu zu
  erfinden.
- Cold-Start ist kein Bug: neue Features zeigen anfangs Platzhalter. Erst nach
  echtem Datenaufbau bewerten, vorher nicht daran optimieren.
- Wird eine schon live gezeigte Genauigkeitszahl durch einen Fix rückwirkend
  schlechter: das dem User sagen, nicht stillschweigend korrigieren.
