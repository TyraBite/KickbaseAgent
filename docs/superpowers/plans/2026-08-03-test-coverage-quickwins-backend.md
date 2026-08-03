# Test-Coverage Quick Wins — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die "Quick Win"-Backend-Funde aus `docs/superpowers/plans/2026-08-03-test-coverage-audit.md` schliessen — 10 gezielte, eng abgegrenzte Testfälle für bisher ungetestete oder unzureichend getestete reine Funktionen/Code-Pfade.

**Architecture:** Reines Test-Hinzufuegen, kein Produktionscode wird veraendert (Ausnahme: falls ein Test einen echten Bug aufdeckt — dann TDD, Fix separat dokumentieren, siehe Global Constraints).

**Tech Stack:** Python `unittest`, gleiche Konventionen wie die bestehenden 295 Tests.

## Global Constraints

- **Kein Produktionscode aendern**, ausser ein neuer Test deckt tatsaechlich einen echten Bug auf — dann TDD (Test rot, Fix, Test gruen), und im finalen Report explizit als "echten Bug gefunden" markieren, nicht stillschweigend.
- Jede neue Testklasse folgt dem Namens-/Strukturmuster der jeweils bestehenden Testdatei (siehe pro Task referenzierte Datei) — keine neue Teststruktur erfinden.
- Reine Funktionen ohne Seiteneffekte (`player_valuation.py`, Teile von `fetcher.py`/`kickbase_client.py`/`market_predictor.py`) brauchen kein Mocking. Wo Mocking noetig ist (Firestore/`db.py`/HTTP), das jeweils schon in der Datei etablierte Mock-Muster wiederverwenden (z.B. In-Memory-SQLite in `test_db.py`, `unittest.mock.patch` in `test_fetcher.py`).
- Push-Policy: **PR-Pflicht** (seit 2026-08-03, siehe [[project_kickbaseagent_git_workflow]]) — `gh pr create` + `gh pr merge --auto --squash`, kein Direkt-Push, kein `--admin`.
- Vor Branch-Erstellung `git log origin/main --oneline -5` pruefen (main bewegt sich hier haeufig durch parallele Sessions).
- Alle 10 Tasks in EINEM PR buendeln (zusammenhaengende Testabdeckungs-Nacharbeit, kein Grund fuer 10 einzelne PRs) — ein Commit pro Task, dann ein gemeinsamer PR am Ende.

---

## Task 1: `player_valuation.py::k_per_point()`/`signal()`/`fairwert()`

**Files:** Modify: `tests/test_player_valuation.py`

- [ ] Failing Tests fuer alle drei Funktionen schreiben: `k_per_point(market_value, average_points)` (inkl. `average_points<=0`-Guard), `signal(market_value, fairwert)` (inkl. `fairwert<=0`/`None`), `fairwert(k, average_points)` (inkl. `average_points is None`). Je 2-3 Faelle pro Funktion (Normalfall + Null-/Zero-Guard).
- [ ] Tests laufen lassen, Fehlschlag bestaetigen (falls die Funktionen bereits korrekt sind, ist das PASS von Anfang an in Ordnung — hier ist NICHTS kaputt, es fehlte nur der Test).
- [ ] Commit: `git commit -m "Test: player_valuation k_per_point/signal/fairwert (bisher ungetestet)"`.

## Task 2: `player_valuation.py::calibrate()`/`build_reference_set()` — NICHT in diesem Batch

Explizit uebersprungen — laut Audit "Braucht Entscheidung" (Fixture-Design fuer Positions-Buckets), nicht Teil der
Quick-Win-Freigabe. Nur als Platzhalter-Eintrag hier, damit die Nummerierung mit dem Audit-Dokument uebereinstimmt.

## Task 3: `fetcher.py::_market_item_to_row()`

**Files:** Modify: `tests/test_fetcher.py`

- [ ] Drei Fixtures: Owner als Dict (`{"i": ..., "n": ...}`), Owner als String, kein Owner (Systemangebot). Fuer jede: `_market_item_to_row()` aufrufen, `owner_name`/`owner_id`-Feld (je nach tatsaechlicher Rueckgabe-Struktur, in der Funktion nachlesen) korrekt pruefen. Zusaetzlich `price_delta_pct`-Berechnung und Leading-Bid-Matching je einmal abdecken.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: fetcher._market_item_to_row Dict-/String-/kein-Owner-Faelle (dokumentierter Live-Crash-Pfad)"`.

## Task 4: `fetcher.py::_apply_market_value_history()`

**Files:** Modify: `tests/test_fetcher.py`

- [ ] Zwei Faelle: History mit genau 7 Eintraegen (unter der `len(entries)>=8`-Schwelle, `market_value_change_7d` bleibt `None`/unveraendert) und mit 8+ Eintraegen (Wert wird berechnet). Bestehendes Mock-Muster fuer den Worker (`_apply_or_reuse_market_value_history` mockt bereits `_apply_market_value_history` weg — hier stattdessen direkt gegen die echte Funktion testen, nicht durch den Wrapper).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: fetcher._apply_market_value_history 7-vs-8-Eintraege-Grenzfall"`.

## Task 5: `firestore_db.py::_write_in_batches()` >500-Dokument-Chunking

**Files:** Modify: `tests/test_firestore_db.py`

- [ ] 501 Dummy-Eintraege bauen, `_write_in_batches()` aufrufen (gemockter Firestore-Client, bestehendes Mock-Muster in derselben Datei wiederverwenden), `client.batch.call_count == 2` UND dass beide `commit()`-Aufrufe passieren pruefen.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: firestore_db._write_in_batches ueber die 500er-Chunk-Grenze"`.

## Task 6: `discord_notify.py::_post_with_retry()`

**Files:** Create: `tests/test_discord_notify.py` (existiert noch nicht)

- [ ] Neue Testdatei nach dem Muster der uebrigen `test_*.py`-Dateien. Zwei Faelle: (a) `requests.post` liefert einmal 429 (mit `retry_after`-Header) dann 200 — genau 2 Aufrufe, kein Exception; (b) `requests.post` liefert dauerhaft 429 ueber `_MAX_RETRIES` hinaus → `RuntimeError`.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: discord_notify._post_with_retry 429-Retry-Logik (bisher kein Testfile)"`.

## Task 7: `db.py`-Schreibfunktionen Round-Trip

**Files:** Modify: `tests/test_db.py`

- [ ] Fuer `replace_market_listings`, `upsert_own_budget`, `upsert_season_context`, `replace_manager_budgets`: In-Memory-SQLite (bestehendes Muster in derselben Datei), Zeilen schreiben, zweimal fuer denselben `fetched_at` schreiben (Idempotenz — Tabelle hat danach weiterhin genau N Zeilen, nicht 2N), Werte zurueeklesen und auf Uebereinstimmung pruefen.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: db.py Schreibfunktionen Round-Trip + Idempotenz (replace_market_listings/upsert_own_budget/upsert_season_context/replace_manager_budgets)"`.

## Task 8: `dashboard_export.py::_build_recent_transfers()` unbekannte `player_id`

**Files:** Modify: `tests/test_dashboard_export.py`

- [ ] Neuer Testfall in der bestehenden `BuildRecentTransfersTests`-Klasse: eine Activity mit einem `player_id`, der NICHT in `players_map` vorkommt → Ergebnis enthaelt diesen Eintrag nicht (dokumentiert das aktuelle Silent-Drop-Verhalten als bewusst, nicht als Bug).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: _build_recent_transfers verwirft Trades mit unbekannter player_id (dokumentiertes Verhalten)"`.

## Task 9: `kickbase_client.py::_raise_for_status()`/`get_teams()`

**Files:** Modify: `tests/test_kickbase_client.py`

- [ ] `_raise_for_status()`: gemocktes Response-Objekt mit `status_code=401` → `KickbaseAuthError`; mit `status_code=503` → generischer `KickbaseError`.
- [ ] `get_teams()`: Fixture mit einem Team-Dict, dem `tid` ODER `tn` fehlt → wird korrekt rausgefiltert (Dict-Comprehension-Bedingung `if t.get("tid") and t.get("tn")`).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: kickbase_client _raise_for_status 401-vs-generisch, get_teams Filterung"`.

## Task 10: `market_predictor.py::_parse_minutes()` + `main.py::_predict_market_values()`

**Files:** Modify: `tests/test_market_predictor.py`, `tests/test_main.py` (Letztere existiert noch nicht, anlegen)

- [ ] `_parse_minutes("garbage")` → `0`, `_parse_minutes(None)` → `0` (bestehender `except ValueError: return 0`-Fallback fuer malformte `"mp"`-Strings von der echten API).
- [ ] `_predict_market_values()` mit `MARKET_PREDICTOR_ENABLED` auf `"0"`/`"false"`/`"no"` (case-insensitiv) → `None`, OHNE dass `market_predictor` importiert wird (pruefen z.B. per `sys.modules`-Check oder Mock-Import-Guard, je nachdem wie die Funktion tatsaechlich strukturiert ist — im Quellcode nachlesen).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: market_predictor._parse_minutes malformte Eingabe, main._predict_market_values Env-Var-Parsing"`.

## Finale Verifikation + PR

- [ ] `python3 -m unittest discover -s tests` — alle Tests gruen (295 + ~20 neue).
- [ ] Branch erstellen, alle 10 Commits (bereits einzeln gemacht), pushen: `git push -u origin test-coverage-quickwins-backend`.
- [ ] `gh pr create --title "Test-Coverage Quick Wins: Backend" --body "Siehe docs/superpowers/plans/2026-08-03-test-coverage-quickwins-backend.md"`.
- [ ] `gh pr merge --auto --squash`, auf die 4 Required Checks warten, Merge bestaetigen.
