# Startelf-Status-Historie (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the existing fitness-history diff/persistence/ML-feature pipeline (`_detect_status_changes`, `firestore_db`'s fitness-specific Firestore helpers, `_fitness_features_as_of`) into field-agnostic versions, then reuse them to add a second, parallel `starting_rank` (Startelf-Status) history pipeline — new `starting_rank_history_log`/`starting_rank_baseline` Firestore collections, two new ML features (`days_since_last_starting_rank_change`, `starting_rank_change_count_90d`) — without changing the on-disk shape or behavior of the existing fitness data by even one byte.

**Architecture:** Every generalized function keeps a 1:1 behavioral mirror of its fitness-only predecessor (same formula, same error handling, same doc-id scheme), gaining only a `field`/`collection`/feature-name parameter. `dashboard_export.py`'s `export()` keeps fitness and starting_rank as two parallel, independently-erroring blocks (not a shared loop) so warning messages stay concrete and one field's Firestore failure never blocks the other's. Firestore's on-disk schema for `fitness_history_log`/`fitness_status_baseline` (field names `from_status_code`/`to_status_code`, flat `player_id -> status_code` baseline dict) is reproduced byte-for-byte by the generalized code — call sites reshape the pure diff function's generic `{"from": ..., "to": ...}` output back into the field-specific document shape before writing.

**Tech Stack:** Python, plain `unittest` (`unittest.mock.patch`/`MagicMock`), `pandas`, `google-cloud-firestore` (mocked in tests, never called for real).

## Global Constraints

- The existing `fitness_history_log`/`fitness_status_baseline` Firestore collections' on-disk schema (`from_status_code`/`to_status_code` field names in history docs; flat `player_id -> status_code` dict in the baseline doc) must stay byte-identical after the refactor — no migration, no breaking already-written data (spec: "keine Migration, kein Bruch bestehender Firestore-Daten").
- Every task that generalizes an existing fitness-only function or call site must include a test proving the fitness behavior is unchanged (regression), not just a test of the new `starting_rank` behavior — this is the refactor's actual safety net, not optional polish.
- `export()`'s fitness and starting_rank diff/baseline blocks stay two parallel, readable code blocks with their own try/except and their own concrete warning text — never merged into a shared loop (spec: merging would make warnings "unleserlich generisch").
- No optional/default parameters added to production functions purely for testability (project convention — see `feedback_avoid_optional_params.md`); new required parameters get real arguments at every call site, not defaults.
- Firestore reads for a diff baseline must never crash `export()` or block the critical `dashboard_snapshot` write; a baseline read failure skips that field's diff for this run only, and the baseline write always runs unconditionally afterward (self-healing for the next run).
- Cold-start behavior (no history yet) returns the existing placeholder pair (`9999`/`0`) — expected and harmless, not a bug to fix in this plan.
- No frontend changes, no Firestore migration scripts, no `firestore.rules` changes (the new collections are already covered by the existing default deny-all catch-all rule) — this plan is backend-Python only (`src/`, `tests/`).
- Follow existing file conventions: German-language docstrings/comments matching the surrounding file's style, class-per-behavior-group test organization, `unittest.mock.patch`/`MagicMock`, run via `python -m unittest`.

---

## Task 1: `_detect_field_changes()` — generalize the diff function in `dashboard_export.py`

**Files:**
- Modify: `src/dashboard_export.py:388-412` (rename/generalize `_detect_status_changes`), `src/dashboard_export.py:503` (its one call site inside `export()`)
- Test: `tests/test_dashboard_export.py:6-18` (import), `tests/test_dashboard_export.py:555-587` (rename/extend `DetectStatusChangesTests`)

**Interfaces:**
- Produces: `_detect_field_changes(previous_players: dict[str, dict], all_players: list[dict], field: str) -> list[dict]`, each item shaped `{"player_id": ..., "from": ..., "to": ...}`. Consumed by Task 2/3's `export()` blocks and (indirectly, as the pattern to follow) nowhere else in this codebase.

- [ ] **Step 1: Write the failing test — rename `DetectStatusChangesTests` to `DetectFieldChangesTests`, generalize its expectations, add a `starting_rank` case**

Replace the whole `DetectStatusChangesTests` class (`tests/test_dashboard_export.py:555-587`) with:

```python
class DetectFieldChangesTests(unittest.TestCase):
    def test_no_change_returns_empty_list(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}}
        all_players = [{"player_id": "p1", "status_code": 0}]
        self.assertEqual(_detect_field_changes(previous, all_players, "status_code"), [])

    def test_one_change_returns_one_event_with_correct_values(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}}
        all_players = [{"player_id": "p1", "status_code": 1}]
        result = _detect_field_changes(previous, all_players, "status_code")
        self.assertEqual(result, [{"player_id": "p1", "from": 0, "to": 1}])

    def test_mixed_players_only_changed_ones_become_events(self):
        previous = {
            "p1": {"player_id": "p1", "status_code": 0},
            "p2": {"player_id": "p2", "status_code": 1},
        }
        all_players = [
            {"player_id": "p1", "status_code": 0},
            {"player_id": "p2", "status_code": 0},
        ]
        result = _detect_field_changes(previous, all_players, "status_code")
        self.assertEqual(result, [{"player_id": "p2", "from": 1, "to": 0}])

    def test_player_without_prior_snapshot_is_skipped(self):
        result = _detect_field_changes({}, [{"player_id": "p_new", "status_code": 1}], "status_code")
        self.assertEqual(result, [])

    def test_player_missing_from_all_players_causes_no_crash(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}, "p2": {"player_id": "p2", "status_code": 0}}
        result = _detect_field_changes(previous, [{"player_id": "p1", "status_code": 0}], "status_code")
        self.assertEqual(result, [])

    def test_starting_rank_field_change_detected(self):
        """Regressionsschutz fuer die Generalisierung selbst (siehe
        docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md,
        Abschnitt Testing): dieselbe Diff-Logik wie oben, aber mit
        field='starting_rank' statt 'status_code' - beweist, dass die
        Funktion tatsaechlich feld-generisch ist, nicht nur umbenannt."""
        previous = {"p1": {"player_id": "p1", "starting_rank": 3}}
        all_players = [{"player_id": "p1", "starting_rank": 1}]
        result = _detect_field_changes(previous, all_players, "starting_rank")
        self.assertEqual(result, [{"player_id": "p1", "from": 3, "to": 1}])

    def test_starting_rank_none_values_are_skipped(self):
        previous = {"p1": {"player_id": "p1", "starting_rank": None}}
        all_players = [{"player_id": "p1", "starting_rank": 1}]
        self.assertEqual(_detect_field_changes(previous, all_players, "starting_rank"), [])
```

Also update the import at `tests/test_dashboard_export.py:12`: replace `_detect_status_changes,` with `_detect_field_changes,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard_export.DetectFieldChangesTests -v`
Expected: FAIL/ERROR — `ImportError: cannot import name '_detect_field_changes'`.

- [ ] **Step 3: Implement `_detect_field_changes()`, replacing `_detect_status_changes()`**

Replace `_detect_status_changes` (`src/dashboard_export.py:388-412`) with:

```python
def _detect_field_changes(previous_players: dict[str, dict], all_players: list[dict], field: str) -> list[dict]:
    """Reine Diff-Funktion: vergleicht `field` je Spieler zwischen der
    vorherigen Baseline (previous_players) und den frisch gefetchten
    all_players (Heavy-Cron, 1x/Tag, siehe player_valuation.fetch_all_players).
    Liefert ein Event-Dict {'player_id', 'from', 'to'} pro tatsaechlichem
    Wechsel - Rohbasis fuer die feldspezifische Firestore-History (siehe
    firestore_db.upsert_history_entries). Spieler ohne vorherigen Stand (neu
    im Pool) oder die aus all_players verschwunden sind werden uebersprungen,
    kein Crash. Ersetzt das frueher status_code-spezifische
    _detect_status_changes() - identische Logik, jetzt fuer status_code UND
    starting_rank genutzt (siehe
    docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md).
    Aufrufstellen bauen aus dem generischen {'from', 'to'}-Ergebnis das
    jeweils feldspezifische Schema (from_status_code/to_status_code bzw.
    from_starting_rank/to_starting_rank) - das bestehende Firestore-Schema
    bleibt dadurch byte-identisch."""
    changes = []
    for row in all_players:
        pid = row.get("player_id")
        if not pid or pid not in previous_players:
            continue
        old_value = previous_players[pid].get(field)
        new_value = row.get(field)
        if old_value is None or new_value is None or old_value == new_value:
            continue
        changes.append({"player_id": pid, "from": old_value, "to": new_value})
    return changes
```

Fix its one call site inside `export()` (`src/dashboard_export.py:503`) — replace:

```python
            status_changes = _detect_status_changes(previous_players_for_fitness_diff, heavy["all_players"])
```

with:

```python
            status_changes = [
                {"player_id": c["player_id"], "from_status_code": c["from"], "to_status_code": c["to"]}
                for c in _detect_field_changes(previous_players_for_fitness_diff, heavy["all_players"], "status_code")
            ]
```

- [ ] **Step 4: Run the full dashboard_export test suite to verify everything passes**

Run: `python -m unittest tests.test_dashboard_export -v`
Expected: PASS (all tests, including `ExportWritesFitnessHistoryOnStatusChangeTests` — the reshaped list comprehension reproduces the exact same `status_changes` shape the rest of `export()` already expects, so no other test needs touching in this task).

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "refactor: generalize _detect_status_changes to _detect_field_changes"
```

---

## Task 2: Generalize `firestore_db.py`'s fitness persistence functions and rewire `export()`'s fitness block

**Files:**
- Modify: `src/firestore_db.py:204-241` (replace the 4 fitness-specific functions with 4 generic ones)
- Modify: `src/dashboard_export.py:479-520` (`export()`'s fitness diff/baseline block — firestore call renames only, still one collection each)
- Test: `tests/test_firestore_db.py:326-399` (rename/extend the fitness persistence test classes)
- Test: `tests/test_dashboard_export.py:249-399` (`ExportActivityFeedGuardTests`, `ExportWritesFitnessHistoryOnStatusChangeTests` — patch target renames, one call-arg-index fix)

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `upsert_history_entries(client, collection: str, entries: list[dict], doc_id_fn: Callable[[dict], str] = <default {date}_{player_id}>) -> None`, `get_history(client, collection: str) -> list[dict]`, `upsert_baseline(client, collection: str, doc_id: str, data: dict) -> None`, `get_baseline(client, collection: str, doc_id: str) -> dict`. Consumed by Task 3 (starting_rank block) and Task 6 (`_load_change_events_by_player`). **`doc_id_fn` is a deliberate addition beyond the design spec's sketch**: the spec hardcoded `{date}_{player_id}` inside the function, which is correct for `fitness_history_log`/`starting_rank_history_log` (one change-event per player per day) but breaks the *other* consumer of this same generalized function planned in a sibling feature — `player_news_log` (Phase B, `docs/superpowers/specs/2026-08-02-news-sentiment-design.md`), which needs multiple documents per player per day (one per article, doc-id `{date}_{player_id}_{article_hash}`). Making the doc-id formula an overridable parameter (default = today's exact formula, so both this task's own two call sites need no changes) avoids a second, incompatible copy of this function later. Found during this session's plan-writing pass for the sibling News-Sentiment plan — fix applied here before Task 2 is implemented, not as a later patch.

- [ ] **Step 1: Write the failing tests — replace the fitness-specific Firestore test classes with generalized ones**

Replace `UpsertFitnessHistoryEntriesTests`, `GetFitnessHistoryTests`, `FitnessStatusBaselineTests` (`tests/test_firestore_db.py:326-399`) with:

```python
class UpsertHistoryEntriesTests(unittest.TestCase):
    def test_writes_docs_keyed_by_date_and_player_id(self):
        client = MagicMock()
        entries = [
            {"player_id": "p1", "date": "2026-07-31", "from_status_code": 0, "to_status_code": 1, "recorded_at": "2026-07-31T21:07:00+00:00"},
            {"player_id": "p2", "date": "2026-07-31", "from_status_code": 2, "to_status_code": 0, "recorded_at": "2026-07-31T21:07:00+00:00"},
        ]

        firestore_db.upsert_history_entries(client, "fitness_history_log", entries)

        client.collection.assert_any_call("fitness_history_log")
        self.assertEqual(_doc_ids(client), ["2026-07-31_p1", "2026-07-31_p2"])
        batch = client.batch.return_value
        batch.commit.assert_called_once()

    def test_collection_name_is_a_parameter_not_hardcoded(self):
        client = MagicMock()
        entries = [{"player_id": "p1", "date": "2026-08-02", "from_starting_rank": 3, "to_starting_rank": 1}]

        firestore_db.upsert_history_entries(client, "starting_rank_history_log", entries)

        client.collection.assert_any_call("starting_rank_history_log")

    def test_empty_entries_writes_nothing(self):
        client = MagicMock()
        firestore_db.upsert_history_entries(client, "fitness_history_log", [])
        client.batch.assert_not_called()

    def test_doc_id_fn_override_allows_multiple_docs_per_player_per_day(self):
        """Regressionsschutz fuer genau das Problem, das eine hardcodierte
        {date}_{player_id}-Formel haette: player_news_log (Phase B) braucht
        mehrere Dokumente pro Spieler UND Tag (ein Artikel-Hash pro Dokument),
        nicht nur eines. Ohne ueberschreibbaren doc_id_fn wuerde der zweite
        Eintrag hier den ersten stillschweigend overschreiben."""
        client = MagicMock()
        entries = [
            {"player_id": "p1", "date": "2026-08-02", "article_hash": "aaa111"},
            {"player_id": "p1", "date": "2026-08-02", "article_hash": "bbb222"},
        ]

        firestore_db.upsert_history_entries(
            client, "player_news_log", entries,
            doc_id_fn=lambda e: f"{e['date']}_{e['player_id']}_{e['article_hash']}",
        )

        self.assertEqual(
            _doc_ids(client),
            ["2026-08-02_p1_aaa111", "2026-08-02_p1_bbb222"],
        )


class GetHistoryTests(unittest.TestCase):
    def test_returns_all_docs_as_dicts(self):
        client = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {"player_id": "p1", "date": "2026-07-31"}
        doc2.to_dict.return_value = {"player_id": "p2", "date": "2026-07-31"}
        client.collection.return_value.stream.return_value = [doc1, doc2]

        result = firestore_db.get_history(client, "fitness_history_log")

        client.collection.assert_any_call("fitness_history_log")
        self.assertEqual(result, [{"player_id": "p1", "date": "2026-07-31"}, {"player_id": "p2", "date": "2026-07-31"}])

    def test_collection_name_is_a_parameter_not_hardcoded(self):
        client = MagicMock()
        client.collection.return_value.stream.return_value = []

        firestore_db.get_history(client, "starting_rank_history_log")

        client.collection.assert_any_call("starting_rank_history_log")


class BaselineTests(unittest.TestCase):
    """Eigenes Dokument als Diff-Baseline (analog BidPremiumPointerTests) -
    absichtlich NICHT dashboard_snapshot/latest, das der stuendliche
    Light-Cron ueberschreibt (siehe upsert_baseline). Generalisierte
    Fassung von FitnessStatusBaselineTests - collection/doc_id sind jetzt
    Parameter statt hardcoded 'fitness_status_baseline'/'latest'."""

    def test_get_baseline_returns_empty_dict_when_no_doc(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        self.assertEqual(firestore_db.get_baseline(client, "fitness_status_baseline", "latest"), {})

    def test_get_baseline_returns_stored_values(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"p1": 0, "p2": 2}

        self.assertEqual(firestore_db.get_baseline(client, "fitness_status_baseline", "latest"), {"p1": 0, "p2": 2})

    def test_get_baseline_uses_collection_and_doc_id_parameters(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        firestore_db.get_baseline(client, "starting_rank_baseline", "latest")

        client.collection.assert_called_with("starting_rank_baseline")
        client.collection.return_value.document.assert_called_with("latest")

    def test_upsert_baseline_writes_expected_doc(self):
        client = MagicMock()

        firestore_db.upsert_baseline(client, "fitness_status_baseline", "latest", {"p1": 0, "p2": 2})

        client.collection.assert_called_with("fitness_status_baseline")
        client.collection.return_value.document.assert_called_with("latest")
        client.collection.return_value.document.return_value.set.assert_called_once_with({"p1": 0, "p2": 2})

    def test_upsert_baseline_uses_collection_and_doc_id_parameters(self):
        client = MagicMock()

        firestore_db.upsert_baseline(client, "starting_rank_baseline", "latest", {"p1": 1})

        client.collection.assert_called_with("starting_rank_baseline")

    def test_upsert_baseline_replaces_instead_of_merging(self):
        """Kein merge=True: verschwundene Spieler muessen aus der Baseline
        fallen, sonst wuerde ein alter Wert ewig als Vorwert weiterleben."""
        client = MagicMock()

        firestore_db.upsert_baseline(client, "fitness_status_baseline", "latest", {"p1": 0})

        _args, kwargs = client.collection.return_value.document.return_value.set.call_args
        self.assertNotIn("merge", kwargs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_firestore_db -v`
Expected: FAIL/ERROR — `AttributeError: module 'src.firestore_db' has no attribute 'upsert_history_entries'` (etc.).

- [ ] **Step 3: Implement the 4 generic functions, replacing the fitness-specific ones**

Add `from typing import Callable` to `src/firestore_db.py`'s import block (top of file, alongside the existing `from google.cloud import firestore` line) — needed for `upsert_history_entries`'s new `doc_id_fn` parameter below.

Replace `upsert_fitness_history_entries`/`get_fitness_history`/`upsert_fitness_status_baseline`/`get_fitness_status_baseline` (`src/firestore_db.py:204-241`) with:

```python
def upsert_history_entries(
    client: firestore.Client,
    collection: str,
    entries: list[dict],
    doc_id_fn: Callable[[dict], str] = lambda e: f"{e['date']}_{e['player_id']}",
) -> None:
    """Generalisierte Fassung von upsert_fitness_history_entries (ersetzt
    sie) - EIN Dokument pro Eintrag, Doc-Id per Default `{date}_{player_id}`
    macht einen erneuten Heavy-Lauf am selben Tag idempotent (ueberschreibt
    statt zu duplizieren) - passt fuer fitness_history_log UND
    starting_rank_history_log (siehe dashboard_export.py,
    docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md),
    die beide GENAU EIN Change-Event pro Spieler/Tag kennen. `doc_id_fn` ist
    ueberschreibbar fuer Collections mit MEHREREN Dokumenten pro Spieler/Tag
    (z.B. player_news_log, mehrere Artikel moeglich - siehe
    docs/superpowers/specs/2026-08-02-news-sentiment-design.md), ohne eine
    dritte, fast identische Kopie dieser Funktion zu brauchen."""
    docs = {doc_id_fn(e): e for e in entries}
    _write_in_batches(client, collection, docs)


def get_history(client: firestore.Client, collection: str) -> list[dict]:
    """Generalisierte Fassung von get_fitness_history (ersetzt sie) - liest
    die komplette angegebene Collection, bleibt klein (nur echte Wechsel,
    deutlich unter 450/Tag), analog get_bid_premium_history. Wird einmal
    pro ML-Lauf gelesen, nicht pro Spieler."""
    return [doc.to_dict() for doc in client.collection(collection).stream()]


def upsert_baseline(client: firestore.Client, collection: str, doc_id: str, data: dict) -> None:
    """Generalisierte Fassung von upsert_fitness_status_baseline (ersetzt
    sie) - collection/doc_id als Parameter statt hardcoded
    "fitness_status_baseline"/"latest". Komplett unabhaengig vom
    dashboard_snapshot/latest-Dokument (siehe dessen Docstring-Historie) -
    wird JEDEN Heavy-Lauf komplett ueberschrieben (kein merge=True - immer
    der volle Ist-Stand von JETZT), Diff-Quelle fuer den naechsten Lauf."""
    client.collection(collection).document(doc_id).set(data)


def get_baseline(client: firestore.Client, collection: str, doc_id: str) -> dict:
    """Generalisierte Fassung von get_fitness_status_baseline (ersetzt sie)
    - leeres Dict beim allerersten Lauf (Cold Start, noch kein Dokument
    vorhanden) - der jeweilige _detect_field_changes()-Aufruf behandelt das
    korrekt (kein Vorwert fuer irgendeinen Spieler -> keine Events)."""
    doc = client.collection(collection).document(doc_id).get()
    return doc.to_dict() if doc.exists else {}
```

- [ ] **Step 4: Run `test_firestore_db.py` to verify it passes**

Run: `python -m unittest tests.test_firestore_db -v`
Expected: PASS (all tests).

- [ ] **Step 5: Write the failing dashboard_export tests — rename the fitness block's Firestore patch targets**

In `tests/test_dashboard_export.py`, update `ExportActivityFeedGuardTests.test_activity_feed_error_does_not_abort_export` (`tests/test_dashboard_export.py:271-275`): replace

```python
        ), patch(
            "src.dashboard_export.firestore_db.get_fitness_status_baseline", return_value={}
        ), patch(
            "src.dashboard_export.firestore_db.upsert_fitness_status_baseline"
        ), patch(
```

with

```python
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline", return_value={}
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ), patch(
```

Replace the whole `ExportWritesFitnessHistoryOnStatusChangeTests` class (`tests/test_dashboard_export.py:287-399`) with:

```python
class ExportWritesFitnessHistoryOnStatusChangeTests(unittest.TestCase):
    """Diff-Baseline ist bewusst das eigene fitness_status_baseline/latest-Dokument
    (flaches player_id -> status_code-Dict) und NICHT dashboard_snapshot/latest:
    letzteres wird vom stuendlichen Light-Cron ueberschrieben, der status_code fuer
    own_squad/market_listings-Spieler frisch ueberlagert - ein zwischenzeitlicher
    Statuswechsel waere im naechsten Heavy-Diff schon 'alt == neu' und damit
    dauerhaft verloren (Fund im finalen Review). Nutzt jetzt die generalisierten
    firestore_db.get_baseline/upsert_baseline/upsert_history_entries - noch mit
    genau EINEM Aufruf pro Funktion (starting_rank-Block folgt in Task 3)."""

    def _run_export_with(self, baseline_status_by_player, fresh_all_players):
        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline",
            return_value=baseline_status_by_player,
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ) as mock_upsert_baseline, patch(
            "src.dashboard_export.firestore_db.upsert_history_entries"
        ) as mock_upsert_history, patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            export()
        return mock_upsert_history, mock_upsert_baseline

    def test_status_change_in_heavy_mode_is_written_to_fitness_history(self):
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = self._run_export_with({"p1": 0}, fresh_all_players)

        mock_upsert_history.assert_called_once()
        self.assertEqual(mock_upsert_history.call_args.args[1], "fitness_history_log")
        written_entries = mock_upsert_history.call_args.args[2]
        self.assertEqual(len(written_entries), 1)
        self.assertEqual(written_entries[0]["player_id"], "p1")
        self.assertEqual(written_entries[0]["from_status_code"], 0)
        self.assertEqual(written_entries[0]["to_status_code"], 1)
        self.assertEqual(written_entries[0]["date"], "2026-07-31")

    def test_baseline_is_refreshed_to_current_status(self):
        """Der Baseline-Write laeuft in JEDEM Heavy-Lauf auf den Ist-Stand von
        heute - sonst wuerde derselbe Wechsel morgen erneut als Event gemeldet."""
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        _mock_upsert_history, mock_upsert_baseline = self._run_export_with({"p1": 0}, fresh_all_players)

        mock_upsert_baseline.assert_called_once_with(ANY, "fitness_status_baseline", "latest", {"p1": 1})

    def test_no_status_change_writes_nothing(self):
        unchanged_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = self._run_export_with({"p1": 0}, unchanged_all_players)

        mock_upsert_history.assert_not_called()

    def test_fitness_history_write_error_does_not_abort_export(self):
        """Analog zu ExportActivityFeedGuardTests.test_activity_feed_error_does_not_abort_export:
        fitness_history_log ist ein sekundaeres/nicht-kritisches Feature - ein
        Firestore-Fehler beim Schreiben (Netzwerk-Hickup, Berechtigung, partieller
        Batch-Fehler) darf den restlichen export()-Lauf und insbesondere den
        kritischen dashboard_snapshot-Write (_finalize_firestore_write) nicht
        verhindern."""
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline", return_value={"p1": 0}
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ), patch(
            "src.dashboard_export.firestore_db.upsert_history_entries",
            side_effect=RuntimeError("Firestore down"),
        ), patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            data = export()

        self.assertEqual(data["bid_premium_history"], [])
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard_export -v`
Expected: FAIL — `export()` still calls `firestore_db.get_fitness_status_baseline`/`upsert_fitness_status_baseline`/`upsert_fitness_history_entries`, which are no longer patched (AttributeError, since those names no longer exist on `firestore_db` after Step 3) or the calls raise because the real names moved.

- [ ] **Step 7: Rewire `export()`'s fitness block to the generalized Firestore functions**

Replace the fitness diff/baseline block inside `export()` (`src/dashboard_export.py:479-520`, the part between `fs_client = ...` and the `activity_feed_ok = True` line) with:

```python
    fs_client = firestore_db.connect() if os.environ.get("FIRESTORE_ENABLED") else None
    if fs_client and heavy["all_players"] is not None:
        # Diff-Baseline kommt aus einem EIGENEN Dokument (fitness_status_baseline/latest),
        # nicht aus dashboard_snapshot/latest: dessen players-Map wird vom stuendlichen
        # Light-Cron ueberschrieben, der status_code fuer own_squad/market_listings-Spieler
        # frisch ueberlagert - ein Statuswechsel, den der Light-Lauf zwischenzeitlich
        # eingebaut hat, waere im naechsten Heavy-Diff schon "alt == neu" und damit
        # unwiederbringlich verloren (kein Backfill moeglich).
        current_status_by_player = {
            p["player_id"]: p["status_code"] for p in heavy["all_players"] if p.get("player_id")
        }
        try:
            baseline_status_by_player = firestore_db.get_baseline(fs_client, "fitness_status_baseline", "latest")
        except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
            print(
                f"Warnung: fitness_status_baseline-Lesezugriff fehlgeschlagen, Fitness-Diff uebersprungen: {exc}",
                file=sys.stderr,
            )
            baseline_status_by_player = None

        if baseline_status_by_player is not None:
            previous_players_for_fitness_diff = {
                pid: {"status_code": code} for pid, code in baseline_status_by_player.items()
            }
            status_changes = [
                {"player_id": c["player_id"], "from_status_code": c["from"], "to_status_code": c["to"]}
                for c in _detect_field_changes(previous_players_for_fitness_diff, heavy["all_players"], "status_code")
            ]
            if status_changes:
                fitness_entries = [
                    {**change, "date": fetched_at, "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                    for change in status_changes
                ]
                try:
                    firestore_db.upsert_history_entries(fs_client, "fitness_history_log", fitness_entries)
                except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
                    print(f"Warnung: fitness_history_log-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)

        # Baseline-Write bewusst UNBEDINGT (auch wenn der Read oben fehlschlug oder es
        # keine Wechsel gab): sie wird immer auf den heutigen Ist-Stand gesetzt, damit
        # der naechste Heavy-Lauf eine korrekte, selbstheilende Startbasis hat.
        try:
            firestore_db.upsert_baseline(fs_client, "fitness_status_baseline", "latest", current_status_by_player)
        except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
            print(f"Warnung: fitness_status_baseline-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)
```

(The `activity_feed_ok = True` line and everything after it stays exactly as-is.)

- [ ] **Step 8: Run the full dashboard_export and firestore_db test suites to verify everything passes**

Run: `python -m unittest tests.test_dashboard_export tests.test_firestore_db -v`
Expected: PASS (all tests).

- [ ] **Step 9: Commit**

```bash
git add src/dashboard_export.py src/firestore_db.py tests/test_dashboard_export.py tests/test_firestore_db.py
git commit -m "refactor: generalize firestore_db fitness persistence helpers and rewire export()"
```

---

## Task 3: Add the new `starting_rank` diff-and-persist block to `export()`

This is the highest-risk task in this plan: `firestore_db.get_baseline`/`upsert_baseline`/`upsert_history_entries` will now be called **twice** per heavy `export()` run (once for `fitness_status_baseline`/`fitness_history_log`, once for `starting_rank_baseline`/`starting_rank_history_log`) through the *same* generalized functions. A test that mocks `get_baseline` with a single flat `return_value=...` (as Task 2 did) would make the starting_rank diff spuriously see the fitness baseline's values as its own baseline — a fitness-only regression test could then start asserting on a call count or dict shape that's secretly also carrying starting_rank noise. This task's mocks must be collection-aware (`side_effect` keyed by the `collection` argument) precisely to prevent this cross-contamination.

**Files:**
- Modify: `src/dashboard_export.py` (add the new starting_rank block right after the fitness block from Task 2, inside `export()`)
- Test: `tests/test_dashboard_export.py` (module-level helper extraction + fitness test updates + new `ExportWritesStartingRankHistoryOnRankChangeTests` class)

**Interfaces:**
- Consumes: `_detect_field_changes` (Task 1), `firestore_db.get_baseline`/`upsert_baseline`/`upsert_history_entries` (Task 2).
- Produces: nothing new consumed by later tasks — this task completes the `dashboard_export.py` side of the spec.

- [ ] **Step 1: Write the failing tests — collection-aware helper + updated fitness assertions + new starting_rank test class**

In `tests/test_dashboard_export.py`, add this module-level helper right before `class ExportWritesFitnessHistoryOnStatusChangeTests` (do NOT keep it as a class method anymore — both this class and the new starting_rank class need it):

```python
def _run_export_with_baselines(
    fresh_all_players, fitness_baseline_by_player=None, starting_rank_baseline_by_player=None,
):
    """Gemeinsamer Test-Helper fuer die Fitness- UND Startelf-Rang-Diff-Bloecke
    in export() (siehe docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md).
    get_baseline wird jetzt fuer ZWEI Collections aufgerufen
    (fitness_status_baseline UND starting_rank_baseline) ueber dieselbe
    generalisierte Funktion - ein flaches return_value= wuerde beide Aufrufe
    denselben Wert liefern lassen und den jeweils ANDEREN Diff-Block
    verunreinigen. side_effect keyed nach collection haelt beide Faelle
    strikt getrennt; nicht angegebene Baselines defaulten auf {} (Cold
    Start - kein Diff fuer dieses Feld in diesem Testlauf)."""
    fitness_baseline_by_player = fitness_baseline_by_player if fitness_baseline_by_player is not None else {}
    starting_rank_baseline_by_player = (
        starting_rank_baseline_by_player if starting_rank_baseline_by_player is not None else {}
    )

    def _get_baseline_side_effect(_client, collection, _doc_id):
        if collection == "fitness_status_baseline":
            return fitness_baseline_by_player
        if collection == "starting_rank_baseline":
            return starting_rank_baseline_by_player
        raise AssertionError(f"unerwarteter Baseline-Collection-Name: {collection!r}")

    with patch.dict(
        os.environ,
        {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
        clear=True,
    ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
        "src.dashboard_export.get_me", return_value={"cpi": "1"}
    ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
        "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
    ), patch("src.dashboard_export.firestore_db.connect"), patch(
        "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
    ), patch(
        "src.dashboard_export.firestore_db.get_baseline", side_effect=_get_baseline_side_effect,
    ), patch(
        "src.dashboard_export.firestore_db.upsert_baseline"
    ) as mock_upsert_baseline, patch(
        "src.dashboard_export.firestore_db.upsert_history_entries"
    ) as mock_upsert_history, patch(
        "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
    ), patch("src.dashboard_export._load_wunschkader", return_value=None
    ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
    ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
    ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
    ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
        export()
    return mock_upsert_history, mock_upsert_baseline
```

Now delete the `_run_export_with` method from `ExportWritesFitnessHistoryOnStatusChangeTests` (it's replaced by the module-level helper above) and rewrite its 3 tests that call it (the 4th, `test_fitness_history_write_error_does_not_abort_export`, keeps its own explicit `with` block from Task 2 unchanged except the `get_baseline` patch must become collection-aware too — see below):

```python
class ExportWritesFitnessHistoryOnStatusChangeTests(unittest.TestCase):
    """Diff-Baseline ist bewusst das eigene fitness_status_baseline/latest-Dokument
    (flaches player_id -> status_code-Dict) und NICHT dashboard_snapshot/latest:
    letzteres wird vom stuendlichen Light-Cron ueberschrieben, der status_code fuer
    own_squad/market_listings-Spieler frisch ueberlagert - ein zwischenzeitlicher
    Statuswechsel waere im naechsten Heavy-Diff schon 'alt == neu' und damit
    dauerhaft verloren (Fund im finalen Review)."""

    def test_status_change_in_heavy_mode_is_written_to_fitness_history(self):
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = _run_export_with_baselines(
            fresh_all_players, fitness_baseline_by_player={"p1": 0},
        )

        mock_upsert_history.assert_called_once()
        self.assertEqual(mock_upsert_history.call_args.args[1], "fitness_history_log")
        written_entries = mock_upsert_history.call_args.args[2]
        self.assertEqual(len(written_entries), 1)
        self.assertEqual(written_entries[0]["player_id"], "p1")
        self.assertEqual(written_entries[0]["from_status_code"], 0)
        self.assertEqual(written_entries[0]["to_status_code"], 1)
        self.assertEqual(written_entries[0]["date"], "2026-07-31")

    def test_baseline_is_refreshed_to_current_status(self):
        """Der Baseline-Write laeuft in JEDEM Heavy-Lauf auf den Ist-Stand von
        heute - sonst wuerde derselbe Wechsel morgen erneut als Event gemeldet.
        assert_any_call statt assert_called_once_with: upsert_baseline wird
        jetzt ZWEIMAL pro Lauf aufgerufen (fitness UND starting_rank, siehe
        Modul-Docstring von _run_export_with_baselines) - nur der konkrete
        Fitness-Aufruf wird hier geprueft."""
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        _mock_upsert_history, mock_upsert_baseline = _run_export_with_baselines(
            fresh_all_players, fitness_baseline_by_player={"p1": 0},
        )

        mock_upsert_baseline.assert_any_call(ANY, "fitness_status_baseline", "latest", {"p1": 1})

    def test_no_status_change_writes_nothing(self):
        unchanged_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = _run_export_with_baselines(
            unchanged_all_players, fitness_baseline_by_player={"p1": 0},
        )

        mock_upsert_history.assert_not_called()

    def test_fitness_history_write_error_does_not_abort_export(self):
        """Analog zu ExportActivityFeedGuardTests.test_activity_feed_error_does_not_abort_export:
        fitness_history_log ist ein sekundaeres/nicht-kritisches Feature - ein
        Firestore-Fehler beim Schreiben (Netzwerk-Hickup, Berechtigung, partieller
        Batch-Fehler) darf den restlichen export()-Lauf und insbesondere den
        kritischen dashboard_snapshot-Write (_finalize_firestore_write) nicht
        verhindern."""
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        def _get_baseline_side_effect(_client, collection, _doc_id):
            return {"p1": 0} if collection == "fitness_status_baseline" else {}

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline", side_effect=_get_baseline_side_effect,
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ), patch(
            "src.dashboard_export.firestore_db.upsert_history_entries",
            side_effect=RuntimeError("Firestore down"),
        ), patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            data = export()

        self.assertEqual(data["bid_premium_history"], [])
```

Add the new starting_rank test class right after it:

```python
class ExportWritesStartingRankHistoryOnRankChangeTests(unittest.TestCase):
    """Spiegelt ExportWritesFitnessHistoryOnStatusChangeTests 1:1 fuer
    starting_rank (siehe
    docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md) -
    eigene Baseline-Collection (starting_rank_baseline/latest), eigene
    History-Collection (starting_rank_history_log), aber ueber dieselben
    generalisierten firestore_db-Funktionen wie Fitness."""

    def test_rank_change_in_heavy_mode_is_written_to_starting_rank_history(self):
        fresh_all_players = [
            {"player_id": "p1", "name": "Amiri", "position": "Mittelfeld", "team_name": "Frankfurt",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = _run_export_with_baselines(
            fresh_all_players, starting_rank_baseline_by_player={"p1": 3},
        )

        mock_upsert_history.assert_called_once()
        self.assertEqual(mock_upsert_history.call_args.args[1], "starting_rank_history_log")
        written_entries = mock_upsert_history.call_args.args[2]
        self.assertEqual(len(written_entries), 1)
        self.assertEqual(written_entries[0]["player_id"], "p1")
        self.assertEqual(written_entries[0]["from_starting_rank"], 3)
        self.assertEqual(written_entries[0]["to_starting_rank"], 1)
        self.assertEqual(written_entries[0]["date"], "2026-07-31")

    def test_baseline_is_refreshed_to_current_rank(self):
        fresh_all_players = [
            {"player_id": "p1", "name": "Amiri", "position": "Mittelfeld", "team_name": "Frankfurt",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        _mock_upsert_history, mock_upsert_baseline = _run_export_with_baselines(
            fresh_all_players, starting_rank_baseline_by_player={"p1": 3},
        )

        mock_upsert_baseline.assert_any_call(ANY, "starting_rank_baseline", "latest", {"p1": 1})

    def test_no_rank_change_writes_nothing(self):
        unchanged_all_players = [
            {"player_id": "p1", "name": "Amiri", "position": "Mittelfeld", "team_name": "Frankfurt",
             "status_code": 0, "starting_rank": 3, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_history, _mock_upsert_baseline = _run_export_with_baselines(
            unchanged_all_players, starting_rank_baseline_by_player={"p1": 3},
        )

        mock_upsert_history.assert_not_called()

    def test_starting_rank_history_write_error_does_not_abort_export(self):
        fresh_all_players = [
            {"player_id": "p1", "name": "Amiri", "position": "Mittelfeld", "team_name": "Frankfurt",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        def _get_baseline_side_effect(_client, collection, _doc_id):
            return {"p1": 3} if collection == "starting_rank_baseline" else {}

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline", side_effect=_get_baseline_side_effect,
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ), patch(
            "src.dashboard_export.firestore_db.upsert_history_entries",
            side_effect=RuntimeError("Firestore down"),
        ), patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            data = export()

        self.assertEqual(data["bid_premium_history"], [])

    def test_fitness_baseline_read_error_does_not_affect_starting_rank_or_the_unconditional_baseline_write(self):
        """Fehlerfall aus der Spec ('Baseline-Lesefehler', siehe
        docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md,
        Abschnitt Fehlerfaelle) - fuer den urspruenglichen Fitness-Code gab
        es dafuer NIE einen dedizierten Test (siehe Implementierungsplan-
        Recherche); mit zwei Feldern ueber dieselben generalisierten
        Firestore-Funktionen wird er sicherheitsrelevant: ein fehlschlagender
        get_baseline-Read fuer EIN Feld darf weder das ANDERE Feld noch
        dessen eigenen, unbedingten Baseline-Write beeinflussen."""
        fresh_all_players = [
            {"player_id": "p1", "name": "Amiri", "position": "Mittelfeld", "team_name": "Frankfurt",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        def _get_baseline_side_effect(_client, collection, _doc_id):
            if collection == "fitness_status_baseline":
                raise RuntimeError("Firestore down")
            return {"p1": 3}

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_baseline", side_effect=_get_baseline_side_effect,
        ), patch(
            "src.dashboard_export.firestore_db.upsert_baseline"
        ) as mock_upsert_baseline, patch(
            "src.dashboard_export.firestore_db.upsert_history_entries"
        ) as mock_upsert_history, patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            data = export()

        # Fitness-Diff wurde uebersprungen (Read schlug fehl) - kein Fitness-History-Write.
        history_collections_written = [c.args[1] for c in mock_upsert_history.call_args_list]
        self.assertNotIn("fitness_history_log", history_collections_written)
        # Startelf-Rang-Diff lief normal (p1: 3 -> 1 ist ein Wechsel, unbeeinflusst vom Fitness-Fehler).
        self.assertIn("starting_rank_history_log", history_collections_written)
        # Beide Baseline-Writes laufen trotzdem unbedingt (Fitness self-healing trotz Lesefehler,
        # Startelf-Rang ohnehin unbeeinflusst).
        mock_upsert_baseline.assert_any_call(ANY, "fitness_status_baseline", "latest", {"p1": 1})
        mock_upsert_baseline.assert_any_call(ANY, "starting_rank_baseline", "latest", {"p1": 1})
        # Der kritische dashboard_snapshot-Write lief trotz des Fitness-Lesefehlers durch.
        self.assertEqual(data["bid_premium_history"], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard_export -v`
Expected: FAIL — `test_rank_change_in_heavy_mode_is_written_to_starting_rank_history` etc. fail because `export()` doesn't have a starting_rank block yet (`mock_upsert_history.assert_called_once()` fails with 0 calls); `test_baseline_is_refreshed_to_current_status`/`test_baseline_is_refreshed_to_current_rank` fail because `upsert_baseline` is only called once (fitness) not twice; `test_fitness_baseline_read_error_does_not_affect_starting_rank_or_the_unconditional_baseline_write` fails because there's no starting_rank history/baseline write to find at all yet.

- [ ] **Step 3: Add the starting_rank diff/baseline block to `export()`**

Immediately after the fitness block from Task 2 (right after the `firestore_db.upsert_baseline(fs_client, "fitness_status_baseline", ...)` try/except, still inside the `if fs_client and heavy["all_players"] is not None:` guard, before the `activity_feed_ok = True` line), add:

```python
        # Startelf-Status-Historie (NEU, siehe
        # docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md) -
        # identischer Ablauf wie der Fitness-Block oben, bewusst NICHT in eine
        # gemeinsame Schleife gepresst: eigene Baseline-Dokumente, eigene
        # Warnmeldungstexte, ein Fehler in einem Feld darf das andere nicht
        # mitreissen.
        current_rank_by_player = {
            p["player_id"]: p["starting_rank"] for p in heavy["all_players"] if p.get("player_id")
        }
        try:
            baseline_rank_by_player = firestore_db.get_baseline(fs_client, "starting_rank_baseline", "latest")
        except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
            print(
                f"Warnung: starting_rank_baseline-Lesezugriff fehlgeschlagen, Startelf-Rang-Diff uebersprungen: {exc}",
                file=sys.stderr,
            )
            baseline_rank_by_player = None

        if baseline_rank_by_player is not None:
            previous_players_for_rank_diff = {
                pid: {"starting_rank": rank} for pid, rank in baseline_rank_by_player.items()
            }
            starting_rank_changes = [
                {"player_id": c["player_id"], "from_starting_rank": c["from"], "to_starting_rank": c["to"]}
                for c in _detect_field_changes(previous_players_for_rank_diff, heavy["all_players"], "starting_rank")
            ]
            if starting_rank_changes:
                starting_rank_entries = [
                    {**change, "date": fetched_at, "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                    for change in starting_rank_changes
                ]
                try:
                    firestore_db.upsert_history_entries(fs_client, "starting_rank_history_log", starting_rank_entries)
                except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
                    print(f"Warnung: starting_rank_history_log-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)

        try:
            firestore_db.upsert_baseline(fs_client, "starting_rank_baseline", "latest", current_rank_by_player)
        except Exception as exc:  # sekundaeres Feature - darf den kritischen dashboard_snapshot-Write nicht verhindern
            print(f"Warnung: starting_rank_baseline-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)
```

- [ ] **Step 4: Run the full dashboard_export test suite to verify everything passes**

Run: `python -m unittest tests.test_dashboard_export -v`
Expected: PASS (all tests, including both `ExportWritesFitnessHistoryOnStatusChangeTests` and `ExportWritesStartingRankHistoryOnRankChangeTests`).

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "feat: add starting_rank history diff-and-persist block to export()"
```

---

## Task 4: `_change_recency_features()` — generalize `_fitness_features_as_of()` in `market_predictor.py`

**Files:**
- Modify: `src/market_predictor.py:92-93` (rename constants), `src/market_predictor.py:192-207` (rename/generalize the function), `src/market_predictor.py:244-247` (its one call site inside `_fetch_player_training_frame`)
- Test: `tests/test_market_predictor.py:11-34` (imports), `tests/test_market_predictor.py:439-473` (rename/extend `FitnessFeaturesAsOfTests`), `tests/test_market_predictor.py:527` (one stray constant reference forced by the import rename)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_change_recency_features(events: list[dict], as_of_date: datetime.date, days_feature: str, count_feature: str, window_days: int = CHANGE_COUNT_WINDOW_DAYS) -> dict`, `NO_HISTORY_DAYS_PLACEHOLDER` (= `9999`), `CHANGE_COUNT_WINDOW_DAYS` (= `90`). Consumed by Task 5 (`_fetch_player_training_frame`'s new starting_rank column computation).

- [ ] **Step 1: Write the failing tests — rename `FitnessFeaturesAsOfTests` to `ChangeRecencyFeaturesTests`, add starting_rank cases**

Update the import block in `tests/test_market_predictor.py:11-34`: replace `_fitness_features_as_of,` with `_change_recency_features,` and replace `FITNESS_NO_HISTORY_DAYS,` with `NO_HISTORY_DAYS_PLACEHOLDER,`.

Fix the one stray usage outside the class being rewritten, at `tests/test_market_predictor.py:527` (inside `FetchPlayerTrainingFrameFitnessColumnsTests.test_player_without_any_fitness_events_gets_placeholder` — only the constant name changes here, its `_fetch_player_training_frame` call signature is untouched until Task 5):

```python
        self.assertEqual(list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER])
```

Replace the whole `FitnessFeaturesAsOfTests` class (`tests/test_market_predictor.py:439-473`) with:

```python
class ChangeRecencyFeaturesTests(unittest.TestCase):
    def test_no_prior_event_returns_placeholder(self):
        result = _change_recency_features(
            [], datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], NO_HISTORY_DAYS_PLACEHOLDER)
        self.assertEqual(result["status_change_count_90d"], 0)

    def test_ignores_events_after_as_of_date(self):
        events = [{"date": "2026-08-01", "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], NO_HISTORY_DAYS_PLACEHOLDER)

    def test_one_event_returns_correct_days_since(self):
        events = [{"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 1)

    def test_multiple_events_only_within_window_counted(self):
        events = [
            {"date": "2026-01-01", "from_status_code": 0, "to_status_code": 1},
            {"date": "2026-07-01", "from_status_code": 1, "to_status_code": 0},
            {"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
        ]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 2)

    def test_event_exactly_90_days_before_is_excluded_boundary(self):
        as_of = datetime.date(2026, 7, 31)
        boundary_date = (as_of - datetime.timedelta(days=90)).isoformat()
        events = [{"date": boundary_date, "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, as_of, "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["status_change_count_90d"], 0)
        self.assertEqual(result["days_since_last_status_change"], 90)

    def test_starting_rank_feature_names_produce_same_formula(self):
        """Regressionsschutz fuer die Generalisierung selbst (siehe
        docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md,
        Abschnitt Testing): identische Events/Datum wie
        test_one_event_returns_correct_days_since, aber mit den
        Startelf-Rang-Feature-Namen durchgereicht - beweist, dass die Formel
        unveraendert bleibt, unabhaengig vom Feld."""
        events = [{"date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31),
            "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
        )
        self.assertEqual(result["days_since_last_starting_rank_change"], 11)
        self.assertEqual(result["starting_rank_change_count_90d"], 1)

    def test_starting_rank_feature_names_cold_start_placeholder(self):
        result = _change_recency_features(
            [], datetime.date(2026, 7, 31),
            "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
        )
        self.assertEqual(result["days_since_last_starting_rank_change"], NO_HISTORY_DAYS_PLACEHOLDER)
        self.assertEqual(result["starting_rank_change_count_90d"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_market_predictor.ChangeRecencyFeaturesTests -v`
Expected: FAIL/ERROR — `ImportError: cannot import name '_change_recency_features'`.

- [ ] **Step 3: Implement — rename the constants, generalize the function, fix its one call site**

Replace the two constants at `src/market_predictor.py:92-93`:

```python
NO_HISTORY_DAYS_PLACEHOLDER = 9999  # Platzhalter: kein Wechsel-Ereignis vor diesem Datum bekannt (Cold-Start oder Spieler noch nie in der jeweiligen History-Collection) - feldneutral, siehe _change_recency_features()
CHANGE_COUNT_WINDOW_DAYS = 90
```

Replace `_fitness_features_as_of` (`src/market_predictor.py:192-207`) with:

```python
def _change_recency_features(
    events: list[dict], as_of_date: datetime.date,
    days_feature: str, count_feature: str,
    window_days: int = CHANGE_COUNT_WINDOW_DAYS,
) -> dict:
    """events: EIN Spielers Eintraege aus der jeweiligen History-Collection
    (mindestens {'date': 'YYYY-MM-DD', ...}), Reihenfolge egal. as_of_date:
    das Datum der Trainings-/Prognose-Zeile. Nur Ereignisse mit event_date
    <= as_of_date fliessen ein - kein Lookahead in die Zukunft dieser Zeile.
    days_feature/count_feature benennen die beiden Ergebnis-Keys (z.B.
    'days_since_last_status_change'/'status_change_count_90d' fuer Fitness,
    'days_since_last_starting_rank_change'/'starting_rank_change_count_90d'
    fuer Startelf-Rang). Generalisierte Fassung von
    _fitness_features_as_of() (ersetzt sie), identische Formel, siehe
    docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md."""
    relevant = [e for e in events if datetime.date.fromisoformat(e["date"]) <= as_of_date]
    if not relevant:
        return {days_feature: NO_HISTORY_DAYS_PLACEHOLDER, count_feature: 0}
    last_date = max(datetime.date.fromisoformat(e["date"]) for e in relevant)
    days_since = (as_of_date - last_date).days
    cutoff = as_of_date - datetime.timedelta(days=window_days)
    count = sum(1 for e in relevant if datetime.date.fromisoformat(e["date"]) > cutoff)
    return {days_feature: days_since, count_feature: count}
```

Fix its one call site inside `_fetch_player_training_frame` (`src/market_predictor.py:244-247`) — replace:

```python
    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(lambda ts: _fitness_features_as_of(events, ts.date()))
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])
```

with:

```python
    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(
        lambda ts: _change_recency_features(
            events, ts.date(), "days_since_last_status_change", "status_change_count_90d",
        )
    )
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])
```

- [ ] **Step 4: Run the full market_predictor test suite to verify everything passes**

Run: `python -m unittest tests.test_market_predictor -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "refactor: generalize _fitness_features_as_of to _change_recency_features"
```

---

## Task 5: Thread `starting_rank_events_by_player` through `_fetch_player_training_frame()` and `_build_corpus()`

At this point in the plan, `backfill_prediction_log()`/`predict_market_value_changes()` still only load fitness events (via the old `_load_fitness_events_by_player()`, untouched until Task 6) — they pass a literal `{}` for the new starting_rank dict. `{}` here is a legitimate value ("no starting_rank events considered in this call"), not a placeholder standing in for missing work — Task 6 replaces it with the real loaded dict.

**Files:**
- Modify: `src/market_predictor.py:210-249` (`_fetch_player_training_frame` — new param, 2 new computed columns)
- Modify: `src/market_predictor.py:252-286` (`_build_corpus` — new param, threads it into `executor.submit`)
- Modify: `src/market_predictor.py:609`, `src/market_predictor.py:975` (the two `_build_corpus(...)` call sites — add the literal `{}` argument)
- Test: `tests/test_market_predictor.py:501-527` (extend `FetchPlayerTrainingFrameFitnessColumnsTests` call signatures), new test classes in the same file

**Interfaces:**
- Consumes: `_change_recency_features` (Task 4).
- Produces: `_fetch_player_training_frame(token, league_id, competition_id, player_id, team_id, fitness_events_by_player, starting_rank_events_by_player) -> pd.DataFrame | None` (now 7 positional args) and `_build_corpus(token, league_id, competition_id, fitness_events_by_player, starting_rank_events_by_player) -> pd.DataFrame` (now 5 positional args). Consumed by Task 6 (wires the real starting_rank loader into the two top-level callers) and Task 7 (relies on the 2 new DataFrame columns existing so `FEATURES` can reference them).

- [ ] **Step 1: Write the failing tests — extend existing fitness tests with the new required argument, add new starting_rank column tests, add a `_build_corpus` threading test**

Add `_build_corpus` to the import block at the top of `tests/test_market_predictor.py` (next to the other `src.market_predictor` imports): add `_build_corpus,` to the `from src.market_predictor import (...)` list.

Update `FetchPlayerTrainingFrameFitnessColumnsTests` (`tests/test_market_predictor.py:501-527`) to pass the new required 7th argument:

```python
class FetchPlayerTrainingFrameFitnessColumnsTests(unittest.TestCase):
    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_fitness_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-31"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        fitness_events_by_player = {
            "p1": [{"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", fitness_events_by_player, {})

        self.assertEqual(list(result["days_since_last_status_change"]), [5, 11])
        self.assertEqual(list(result["status_change_count_90d"]), [1, 1])

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_fitness_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {})

        self.assertEqual(list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER])
```

Add a new mirror class right after it:

```python
class FetchPlayerTrainingFrameStartingRankColumnsTests(unittest.TestCase):
    """Spiegelt FetchPlayerTrainingFrameFitnessColumnsTests 1:1 fuer
    starting_rank - beweist, dass die zweite Event-Quelle unabhaengig von
    der ersten funktioniert (leeres fitness_events_by_player daneben, kein
    Cross-Contamination zwischen den beiden Feature-Paaren)."""

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_starting_rank_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-31"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        starting_rank_events_by_player = {
            "p1": [{"player_id": "p1", "date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", {}, starting_rank_events_by_player)

        self.assertEqual(list(result["days_since_last_starting_rank_change"]), [5, 11])
        self.assertEqual(list(result["starting_rank_change_count_90d"]), [1, 1])
        self.assertEqual(
            list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER, NO_HISTORY_DAYS_PLACEHOLDER]
        )

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_starting_rank_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {})

        self.assertEqual(list(result["days_since_last_starting_rank_change"]), [NO_HISTORY_DAYS_PLACEHOLDER])
```

Add a `_build_corpus` threading test:

```python
class BuildCorpusStartingRankThreadingTests(unittest.TestCase):
    @patch("src.market_predictor._fetch_player_training_frame")
    @patch("src.market_predictor._fetch_competition_player_ids", return_value={"p1": "t1"})
    def test_starting_rank_events_by_player_passed_through_to_training_frame(
        self, mock_fetch_ids, mock_fetch_frame
    ):
        mock_fetch_frame.return_value = pd.DataFrame({"player_id": ["p1"], "mv": [1_000_000]})
        fitness_events = {"p1": [{"date": "2026-07-20"}]}
        starting_rank_events = {"p1": [{"date": "2026-07-25"}]}

        _build_corpus("tok", "l1", "c1", fitness_events, starting_rank_events)

        mock_fetch_frame.assert_called_once_with("tok", "l1", "c1", "p1", "t1", fitness_events, starting_rank_events)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_market_predictor.FetchPlayerTrainingFrameStartingRankColumnsTests tests.test_market_predictor.BuildCorpusStartingRankThreadingTests -v`
Expected: FAIL — `TypeError: _fetch_player_training_frame() takes 6 positional arguments but 7 were given` (and `_build_corpus() missing 1 required positional argument`).

- [ ] **Step 3: Implement — add the new parameter and computed columns to `_fetch_player_training_frame`, thread it through `_build_corpus`, update the two call sites**

Change the signature of `_fetch_player_training_frame` (`src/market_predictor.py:210-213`):

```python
def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str,
    fitness_events_by_player: dict[str, list[dict]],
    starting_rank_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame | None:
```

Add the starting_rank column computation right after the existing fitness column computation (from Task 4), still inside `_fetch_player_training_frame`, before the final `return merged`:

```python
    rank_events = starting_rank_events_by_player.get(player_id, [])
    rank_features = merged["date"].apply(
        lambda ts: _change_recency_features(
            rank_events, ts.date(),
            "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
        )
    )
    merged["days_since_last_starting_rank_change"] = rank_features.apply(
        lambda f: f["days_since_last_starting_rank_change"]
    )
    merged["starting_rank_change_count_90d"] = rank_features.apply(
        lambda f: f["starting_rank_change_count_90d"]
    )
```

Change the signature of `_build_corpus` (`src/market_predictor.py:252-254`):

```python
def _build_corpus(
    token: str, league_id: str, competition_id: str,
    fitness_events_by_player: dict[str, list[dict]],
    starting_rank_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame:
```

Fix its `executor.submit` call (`src/market_predictor.py:264-267`) — replace:

```python
        futures = {
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid, fitness_events_by_player): pid
            for pid, tid in player_to_team.items()
        }
```

with:

```python
        futures = {
            executor.submit(
                _fetch_player_training_frame,
                token, league_id, competition_id, pid, tid,
                fitness_events_by_player, starting_rank_events_by_player,
            ): pid
            for pid, tid in player_to_team.items()
        }
```

Fix the two `_build_corpus(...)` call sites, adding the literal `{}` (no starting_rank events loaded yet at this point in the plan — Task 6 replaces it):

At `src/market_predictor.py:609` (inside `backfill_prediction_log`):

```python
    corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, {})
```

At `src/market_predictor.py:975` (inside `predict_market_value_changes`):

```python
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, {})
```

- [ ] **Step 4: Run the full market_predictor test suite to verify everything passes**

Run: `python -m unittest tests.test_market_predictor -v`
Expected: PASS (all tests, including `BackfillPredictionLogTargetColTests`/`PredictMarketValueChangesThreeDayIsolationTests`, whose `_build_corpus` mocks accept the extra `{}` argument transparently since they patch the whole function).

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "feat: thread starting_rank events through _fetch_player_training_frame and _build_corpus"
```

---

## Task 6: `_load_change_events_by_player()` — generalize `_load_fitness_events_by_player()` and wire both top-level entry points

**Files:**
- Modify: `src/market_predictor.py:106-121` (rename/generalize the loader)
- Modify: `src/market_predictor.py:608-609` (inside `backfill_prediction_log`), `src/market_predictor.py:974-975` (inside `predict_market_value_changes`) — load both collections, drop the `{}` placeholder from Task 5
- Test: `tests/test_market_predictor.py:11-34` (imports), `tests/test_market_predictor.py:475-498` (rename/extend `LoadFitnessEventsByPlayerTests`), `tests/test_market_predictor.py:311`/`357` (patch target rename in `BackfillPredictionLogTargetColTests`), `tests/test_market_predictor.py:718` (patch target rename in `PredictMarketValueChangesThreeDayIsolationTests`)

**Interfaces:**
- Consumes: `firestore_db.get_history` (Task 2).
- Produces: `_load_change_events_by_player(collection: str) -> dict[str, list[dict]]`. This completes the wiring `backfill_prediction_log()`/`predict_market_value_changes()` need — no later task depends on this beyond Task 7's `FEATURES` addition (which is independent of how the events got loaded).

- [ ] **Step 1: Write the failing tests — rename `LoadFitnessEventsByPlayerTests`, add a starting_rank case, rename the two stray patch decorators**

Update the import block at the top of `tests/test_market_predictor.py`: replace `_load_fitness_events_by_player,` with `_load_change_events_by_player,`.

Replace the whole `LoadFitnessEventsByPlayerTests` class (`tests/test_market_predictor.py:475-498`) with:

```python
class LoadChangeEventsByPlayerTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
            {"player_id": "p1", "date": "2026-07-25", "from_status_code": 1, "to_status_code": 0},
            {"player_id": "p2", "date": "2026-07-22", "from_status_code": 0, "to_status_code": 2},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_change_events_by_player("fitness_history_log")
        mock_get.assert_called_once_with(mock_connect.return_value, "fitness_history_log")
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_change_events_by_player("fitness_history_log"), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_change_events_by_player("fitness_history_log"), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_starting_rank_entries_by_player_id(self, mock_connect, mock_get):
        """Regressionsschutz fuer die Generalisierung selbst: gleiche Logik
        wie test_groups_entries_by_player_id, aber mit collection=
        'starting_rank_history_log' - beweist collection ist ein echter
        Parameter, nicht hardcoded."""
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_change_events_by_player("starting_rank_history_log")
        mock_get.assert_called_once_with(mock_connect.return_value, "starting_rank_history_log")
        self.assertEqual(len(result["p1"]), 1)
```

Rename the two `@patch("src.market_predictor._load_fitness_events_by_player", return_value={})` decorators in `BackfillPredictionLogTargetColTests` (`tests/test_market_predictor.py:311` and `:357`) and the one in `PredictMarketValueChangesThreeDayIsolationTests` (`tests/test_market_predictor.py:718`) to:

```python
    @patch("src.market_predictor._load_change_events_by_player", return_value={})
```

(Leave the mock parameter name `mock_fitness_events` as-is in those test method signatures — it's just a local variable name, not part of the assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_market_predictor.LoadChangeEventsByPlayerTests -v`
Expected: FAIL/ERROR — `ImportError: cannot import name '_load_change_events_by_player'`.

- [ ] **Step 3: Implement — generalize the loader, wire both top-level entry points**

Replace `_load_fitness_events_by_player` (`src/market_predictor.py:106-121`) with:

```python
def _load_change_events_by_player(collection: str) -> dict[str, list[dict]]:
    """Liest die angegebene History-Collection (siehe firestore_db.get_history)
    einmal pro Lauf und gruppiert nach player_id - Basis fuer
    _change_recency_features() in _fetch_player_training_frame(). Leeres
    Dict bei deaktiviertem Firestore oder Lesefehler (gleiches
    Resilienz-Muster wie _load_recent_prediction_log) - jeder Spieler
    bekommt dann ueberall den Cold-Start-Platzhalter, kein Crash.
    Generalisierte Fassung von _load_fitness_events_by_player() (ersetzt
    sie), collection als Parameter statt hardcoded 'fitness_history_log' -
    genutzt fuer 'fitness_history_log' UND 'starting_rank_history_log'."""
    events_by_player: dict[str, list[dict]] = defaultdict(list)
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            for entry in firestore_db.get_history(firestore_db.connect(), collection):
                events_by_player[entry["player_id"]].append(entry)
        except Exception as exc:
            print(f"Warnung: {collection}-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)
            return {}
    return dict(events_by_player)
```

Replace the two lines inside `backfill_prediction_log` (`src/market_predictor.py:608-609`):

```python
    fitness_events_by_player = _load_fitness_events_by_player()
    corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, {})
```

with:

```python
    fitness_events_by_player = _load_change_events_by_player("fitness_history_log")
    starting_rank_events_by_player = _load_change_events_by_player("starting_rank_history_log")
    corpus = _build_corpus(
        token, league_id, competition_id, fitness_events_by_player, starting_rank_events_by_player,
    )
```

Replace the analogous two lines inside `predict_market_value_changes` (`src/market_predictor.py:974-975`):

```python
        fitness_events_by_player = _load_fitness_events_by_player()
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, {})
```

with:

```python
        fitness_events_by_player = _load_change_events_by_player("fitness_history_log")
        starting_rank_events_by_player = _load_change_events_by_player("starting_rank_history_log")
        corpus = _build_corpus(
            token, league_id, competition_id, fitness_events_by_player, starting_rank_events_by_player,
        )
```

- [ ] **Step 4: Run the full market_predictor test suite to verify everything passes**

Run: `python -m unittest tests.test_market_predictor -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "refactor: generalize _load_fitness_events_by_player to _load_change_events_by_player"
```

---

## Task 7: Add the two new entries to `FEATURES` and fix all hardcoded-column test fixtures

Adding to `FEATURES` is what actually makes the model *use* the two new columns (`_fetch_player_training_frame` has computed them since Task 5, but nothing selected them for training yet). Several test fixtures across the file hardcode the exact list of DataFrame columns and feed them through `train[FEATURES]`/`test[FEATURES]`/`today_df[FEATURES]` — those fixtures will raise `KeyError` the moment `FEATURES` grows unless the two new columns are added to them too.

**Files:**
- Modify: `src/market_predictor.py:64-70` (`FEATURES` list)
- Test: `tests/test_market_predictor.py:11-34` (import `FEATURES`), `tests/test_market_predictor.py:290-307` (`BackfillPredictionLogTargetColTests._history_df`), `tests/test_market_predictor.py:570-587` (`TrainAndEvaluateTargetColTests._history_df`), `tests/test_market_predictor.py:608-625` (`WalkForwardBacktestTargetColTests._history_df`), `tests/test_market_predictor.py:692-707` (`PredictMarketValueChangesThreeDayIsolationTests._today_df`)

**Interfaces:**
- Consumes: the 2 new DataFrame columns produced by Task 5's `_fetch_player_training_frame`.
- Produces: nothing consumed by later tasks — this is the final task in this plan.

- [ ] **Step 1: Write the failing test — assert the new feature names are in `FEATURES`, and pre-emptively fix the fixtures that would otherwise `KeyError`**

Add `FEATURES` to the import block at the top of `tests/test_market_predictor.py` (next to `TARGET`/`TARGET_3D`).

Add a new test class:

```python
class FeaturesListStartingRankTests(unittest.TestCase):
    def test_features_includes_starting_rank_recency_columns(self):
        self.assertIn("days_since_last_starting_rank_change", FEATURES)
        self.assertIn("starting_rank_change_count_90d", FEATURES)
```

In `BackfillPredictionLogTargetColTests._history_df` (`tests/test_market_predictor.py:296-306`), add the two new columns right after the existing fitness placeholder line:

```python
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            target_col: rng.randn(n) * 5000,
            unclipped_col: rng.randn(n) * 5000,
        })
```

In `TrainAndEvaluateTargetColTests._history_df` (`tests/test_market_predictor.py:576-586`):

```python
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "mv_target_clipped": rng.randn(n) * 5000,
            "alt_target_clipped": rng.randn(n) * 9000,
        })
```

In `WalkForwardBacktestTargetColTests._history_df` (`tests/test_market_predictor.py:614-624`):

```python
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            target_col: rng.randn(n) * 5000,
            unclipped_col: rng.randn(n) * 5000,
        })
```

In `PredictMarketValueChangesThreeDayIsolationTests._today_df` (`tests/test_market_predictor.py:692-707`):

```python
    def _today_df(self):
        return pd.DataFrame({
            "player_id": ["p1"],
            "date": [pd.Timestamp("2026-07-31")],
            "mv": [1_000_000],
            "p": [5],
            "days_to_next": [3],
            "mv_change_1d": [100],
            "mv_trend_1d": [0.01],
            "mv_change_3d": [200],
            "mv_vol_3d": [50],
            "mv_trend_7d": [0.02],
            "market_divergence": [1.0],
            "days_since_last_status_change": [10],
            "status_change_count_90d": [0],
            "days_since_last_starting_rank_change": [10],
            "starting_rank_change_count_90d": [0],
        })
```

- [ ] **Step 2: Run tests to verify the new test fails and confirm the fixture fixes are needed**

Run: `python -m unittest tests.test_market_predictor.FeaturesListStartingRankTests -v`
Expected: FAIL — `AssertionError: 'days_since_last_starting_rank_change' not found in [...]` (FEATURES doesn't have the new entries yet).

Run: `python -m unittest tests.test_market_predictor -v`
Expected: the 4 fixture-touching test classes above still PASS at this point (their fixtures were pre-emptively fixed in Step 1, and `FEATURES` hasn't grown yet so the extra unused columns are harmless) — only `FeaturesListStartingRankTests` fails. This order (fix fixtures first, in the same step as writing the assertion, before growing `FEATURES`) avoids a moment where the suite is red for an unrelated reason.

- [ ] **Step 3: Implement — add the two new entries to `FEATURES`**

Replace the `FEATURES` list (`src/market_predictor.py:64-70`) with:

```python
FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
    "days_since_last_status_change", "status_change_count_90d",
    "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
]
```

- [ ] **Step 4: Run the full market_predictor test suite to verify everything passes**

Run: `python -m unittest tests.test_market_predictor -v`
Expected: PASS (all tests).

- [ ] **Step 5: Run the entire project test suite as a final full-plan regression check**

Run: `python -m unittest discover -s tests`
Expected: PASS (all tests across all test files — confirms the whole refactor, from `_detect_field_changes` through `FEATURES`, is internally consistent).

- [ ] **Step 6: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "feat: add starting_rank recency features to the ML FEATURES list"
```
