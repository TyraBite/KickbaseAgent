# Gebotsvorschläge-Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zwei bisher fehlende Signale zur Gebotsvorschläge-Datengrundlage hinzufügen (unverkauft abgelaufene Systemangebote, Self-vs-Fremd-Kauf-Tag) und als neuen Abschnitt im "Modell-Tracking"-Tab anzeigen — basierend auf `docs/superpowers/specs/2026-07-30-gebotstracking-design.md`.

**Architecture:** Pro Lauf wird verglichen, welche Systemangebote-Spieler-IDs seit dem letzten Lauf aus dem Markt verschwunden sind (neuer Zeiger `last_seen_system_listing_ids` in `bid_premium_state`). Verschwindet eine ID OHNE passenden Systemkauf im (ohnehin schon abgerufenen) Activity-Feed, gilt sie als unverkauft abgelaufen → neue, separate Firestore-Collection `bid_premium_unsold_log`. Findet sich ein passender Kauf, läuft das wie bisher in `bid_premium_log`, jetzt zusätzlich mit `bought_by_self`-Tag. Beide neuen Datenquellen fließen NICHT in `suggestBid()` ein - nur aggregierte Zähler pro Position im Snapshot (`bid_premium_outcome_counts`), angezeigt im Modell-Tracking-Tab.

**Tech Stack:** Python 3.11 (Backend, `src/`), TypeScript/React (Frontend, `frontend/src/`), Firestore, `unittest`. Kein Test-Framework im Frontend - Verifikation über `tsc --noEmit`.

## Global Constraints

- Fall-2-Daten (`bid_premium_unsold_log`) fließen NICHT in `suggestBid()`/`bid_premium_log` ein - rein additiv, ändert keine bestehende Gebotsempfehlung.
- Kein neuer Kickbase-API-Call - Erkennung nutzt ausschließlich bereits abgerufene `market_listings` und `activities`.
- Kein Mehrfach-Bestätigungs-Fenster für die Verschwindens-Erkennung (v1, akzeptierte Vereinfachung, siehe Spec).
- `bought_by_self` fehlt auf allen vor diesem Feature entstandenen `bid_premium_log`-Einträgen (rückwirkend nicht rekonstruierbar) - überall mit `.get("bought_by_self")` (truthy-Check, nie direkter Key-Zugriff) lesen.
- Firestore-Pointer-Writes MÜSSEN `merge=True` nutzen - `bid_premium_state/current` trägt jetzt zwei unabhängig aktualisierte Felder (`last_processed_dt`, `last_seen_system_listing_ids`), ein `.set()` ohne merge würde das jeweils andere Feld löschen.
- Backend-Tests: `python3 -m unittest discover -s tests -v` aus dem Repo-Root, muss nach jedem Task grün bleiben.
- Frontend-Verifikation: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` nach jedem Frontend-Task.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`) - Repo-Owner pusht selbst.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `src/bid_premium.py` | `build_new_entries()` bekommt `bought_by_self`-Tag; neue `detect_unsold_listings()`; `update_and_load()` gibt jetzt `(history, outcome_counts)` zurück |
| `src/firestore_db.py` | Pointer-Writes auf `merge=True`; neue `last_seen_system_listing_ids`-Getter/Setter; neue `bid_premium_unsold_log`-Getter/Setter |
| `src/dashboard_export.py` | Call-Site-Update für die neue `update_and_load()`-Signatur, neues `bid_premium_outcome_counts`-Snapshot-Feld |
| `frontend/src/types.ts` | `BidPremiumEntry.bought_by_self?`, neuer Typ `BidPremiumOutcomeCounts` |
| `frontend/src/components/MlGenauigkeitTab.tsx` | Neuer Abschnitt "Gebotsvorschläge-Tracking" |

---

## Task 1: `src/bid_premium.py` — `bought_by_self`-Tag

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: bestehende `build_new_entries()`-Signatur (siehe Datei) + neuer Parameter `own_name: str | None`.
- Produces: jeder Eintrag aus `build_new_entries()` bekommt zusätzlich `"bought_by_self": bool`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bid_premium.py`, in die bestehende Klasse `BuildNewEntriesTests` ergänzen (nutzt deren vorhandene `_trade_activity()`/`_days_since_epoch()`-Helfer unverändert):

```python
    def test_marks_entry_as_bought_by_self_when_buyer_matches_own_name(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Ich", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name="Ich", get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertTrue(entries[0]["bought_by_self"])

    def test_marks_entry_as_not_bought_by_self_when_buyer_differs(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Rivale", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name="Ich", get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertFalse(entries[0]["bought_by_self"])

    def test_bought_by_self_is_false_when_own_name_not_provided(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Rivale", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name=None, get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertFalse(entries[0]["bought_by_self"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium.BuildNewEntriesTests -v`
Expected: FAIL (`TypeError: build_new_entries() got an unexpected keyword argument 'own_name'`)

- [ ] **Step 3: Implement**

In `src/bid_premium.py`, Signatur von `build_new_entries()` erweitern:

```python
def build_new_entries(
    token: str,
    league_id: str,
    activities: list[dict],
    since_dt: str | None,
    players_map: dict[str, dict],
    own_name: str | None = None,
    get_history=get_market_value_history,
) -> tuple[list[dict], str | None]:
```

Im `entries.append({...})`-Block ergänzen:

```python
        entries.append({
            "activity_id": activity["i"],
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": market_value_then,
            "average_points_then": player.get("average_points"),
            "premium_pct": premium_pct,
            "purchased_at": activity["dt"],
            "bought_by_self": bool(own_name) and activity["data"].get("byr") == own_name,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS (alle Tests, auch die bestehenden - `own_name` hat einen Default, keine bestehende Aufrufstelle bricht)

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: bought_by_self-Tag in build_new_entries()"
```

---

## Task 2: `src/firestore_db.py` — Pointer-Merge-Fix + neue Getter/Setter

**Files:**
- Modify: `src/firestore_db.py`
- Test: `tests/test_firestore_db.py`

**Interfaces:**
- Produces: `upsert_bid_premium_pointer()` nutzt jetzt `merge=True`; neue `get_bid_premium_last_seen_listing_ids(client) -> list[str]`, `upsert_bid_premium_last_seen_listing_ids(client, ids: list[str]) -> None`, `upsert_unsold_log_entries(client, entries: list[dict]) -> None`, `get_unsold_log(client) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_firestore_db.py`, in die bestehende Klasse `BidPremiumPointerTests` ergänzen sowie zwei neue Klassen:

```python
    def test_upsert_pointer_uses_merge_to_not_clobber_other_fields(self):
        client = MagicMock()
        firestore_db.upsert_bid_premium_pointer(client, "2026-07-01T00:00:00Z")
        client.collection.return_value.document.return_value.set.assert_called_once_with(
            {"last_processed_dt": "2026-07-01T00:00:00Z"}, merge=True
        )


class BidPremiumLastSeenListingIdsTests(unittest.TestCase):
    def test_get_returns_empty_list_when_no_doc(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False
        self.assertEqual(firestore_db.get_bid_premium_last_seen_listing_ids(client), [])

    def test_get_returns_stored_ids(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"last_seen_system_listing_ids": ["p1", "p2"]}
        self.assertEqual(firestore_db.get_bid_premium_last_seen_listing_ids(client), ["p1", "p2"])

    def test_upsert_writes_with_merge(self):
        client = MagicMock()
        firestore_db.upsert_bid_premium_last_seen_listing_ids(client, ["p1", "p2"])
        client.collection.assert_called_with("bid_premium_state")
        client.collection.return_value.document.assert_called_with("current")
        client.collection.return_value.document.return_value.set.assert_called_once_with(
            {"last_seen_system_listing_ids": ["p1", "p2"]}, merge=True
        )


class UnsoldLogTests(unittest.TestCase):
    def test_upsert_writes_docs_keyed_by_player_id_and_detected_at(self):
        client = MagicMock()
        entries = [{"player_id": "p1", "detected_at": "2026-07-30", "position": "Sturm"}]
        firestore_db.upsert_unsold_log_entries(client, entries)
        batch = client.batch.return_value
        self.assertEqual(batch.set.call_count, 1)
        batch.commit.assert_called_once()

    def test_upsert_empty_entries_writes_nothing(self):
        client = MagicMock()
        firestore_db.upsert_unsold_log_entries(client, [])
        client.batch.assert_not_called()

    def test_get_returns_all_docs(self):
        client = MagicMock()
        doc = MagicMock()
        doc.to_dict.return_value = {"player_id": "p1"}
        client.collection.return_value.stream.return_value = [doc]
        self.assertEqual(firestore_db.get_unsold_log(client), [{"player_id": "p1"}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_firestore_db.BidPremiumPointerTests tests.test_firestore_db.BidPremiumLastSeenListingIdsTests tests.test_firestore_db.UnsoldLogTests -v`
Expected: FAIL (`AttributeError`/`AssertionError` - Funktionen fehlen bzw. nutzen noch kein `merge=True`)

- [ ] **Step 3: Implement**

In `src/firestore_db.py`, bestehende Funktion ändern:

```python
def upsert_bid_premium_pointer(client: firestore.Client, dt: str) -> None:
    client.collection("bid_premium_state").document("current").set(
        {"last_processed_dt": dt}, merge=True
    )
```

Direkt danach ergänzen:

```python
def get_bid_premium_last_seen_listing_ids(client: firestore.Client) -> list[str]:
    """Systemangebote-Spieler-IDs, die beim letzten Lauf noch gelistet waren
    - Vergleichsbasis fuer detect_unsold_listings() (src/bid_premium.py).
    Liegt im selben Dokument wie last_processed_dt, aber unabhaengig davon
    aktualisiert - deshalb merge=True bei beiden Writes."""
    doc = client.collection("bid_premium_state").document("current").get()
    return doc.to_dict().get("last_seen_system_listing_ids", []) if doc.exists else []


def upsert_bid_premium_last_seen_listing_ids(client: firestore.Client, ids: list[str]) -> None:
    client.collection("bid_premium_state").document("current").set(
        {"last_seen_system_listing_ids": ids}, merge=True
    )


def upsert_unsold_log_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Ein Dokument pro erkanntem 'unverkauft abgelaufen'-Fall, Doc-Id =
    player_id + detected_at (macht Re-Laeufe am selben Tag idempotent)."""
    docs = {f"{e['player_id']}_{e['detected_at']}": e for e in entries}
    _write_in_batches(client, "bid_premium_unsold_log", docs)


def get_unsold_log(client: firestore.Client) -> list[dict]:
    """Liest die komplette bid_premium_unsold_log-Collection - klein und
    langsam wachsend (nur bei tatsaechlich unverkauften Angeboten), analog
    get_bid_premium_history."""
    return [doc.to_dict() for doc in client.collection("bid_premium_unsold_log").stream()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_firestore_db -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "firestore_db: bid_premium-Pointer auf merge=True, last_seen_system_listing_ids + bid_premium_unsold_log"
```

---

## Task 3: `src/bid_premium.py` — `detect_unsold_listings()`

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: `market_listings: list[dict]` (rohe Listing-Dicts, wie in `dashboard_export.py` vorhanden - Felder `player_id`/`is_system_offer`), `activities: list[dict]`, `last_seen_ids: list[str]`, `players_map: dict[str, dict]`, `detected_at: str`.
- Produces: `detect_unsold_listings(market_listings, activities, last_seen_ids, players_map, detected_at) -> tuple[list[dict], list[str]]` - `(neue_unsold_entries, aktuelle_ids_fuer_naechsten_zeiger)`. Konsumiert von Task 4.

- [ ] **Step 1: Write the failing tests**

```python
class DetectUnsoldListingsTests(unittest.TestCase):
    def _players_map(self):
        return {"p1": {"player_id": "p1", "position": "Sturm", "market_value": 5_000_000, "average_points": 90}}

    def test_disappeared_id_without_matching_trade_is_unsold(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[],  # p1 ist jetzt NICHT mehr gelistet
            activities=[],  # kein Trade fuer p1
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["player_id"], "p1")
        self.assertEqual(entries[0]["position"], "Sturm")
        self.assertEqual(entries[0]["market_value_then"], 5_000_000)
        self.assertEqual(entries[0]["detected_at"], "2026-07-30")
        self.assertEqual(current_ids, [])

    def test_disappeared_id_with_matching_system_purchase_is_not_unsold(self):
        activities = [_trade_activity("2026-07-29T10:00:00Z", pi="p1")]
        entries, _current_ids = detect_unsold_listings(
            market_listings=[],
            activities=activities,
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])

    def test_disappeared_id_with_matching_manager_to_manager_trade_is_not_unsold(self):
        # Verkauft an einen Mitspieler (slr vorhanden) ist kein Systemkauf,
        # zaehlt fuer detect_unsold_listings() trotzdem als "erklaertes
        # Verschwinden" - der Spieler war ja jemandes Wunschkader-Ziel und
        # wurde regulaer weitergehandelt, kein Hinweis auf einen zu niedrigen
        # Gebotsvorschlag.
        activities = [_trade_activity("2026-07-29T10:00:00Z", pi="p1", slr="Rivale")]
        entries, _current_ids = detect_unsold_listings(
            market_listings=[],
            activities=activities,
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])

    def test_still_listed_id_is_not_unsold_and_stays_in_current_ids(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p1", "is_system_offer": True}],
            activities=[],
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])
        self.assertEqual(current_ids, ["p1"])

    def test_newly_listed_id_not_in_last_seen_is_added_to_current_ids(self):
        _entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p_new", "is_system_offer": True}],
            activities=[],
            last_seen_ids=[],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(current_ids, ["p_new"])

    def test_non_system_listing_is_ignored_for_current_ids(self):
        _entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p1", "is_system_offer": False}],
            activities=[],
            last_seen_ids=[],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(current_ids, [])

    def test_disappeared_id_unknown_in_players_map_is_skipped_not_crashed(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[],
            activities=[],
            last_seen_ids=["p_unknown"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])
        self.assertEqual(current_ids, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium.DetectUnsoldListingsTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

In `src/bid_premium.py` ergänzen:

```python
def detect_unsold_listings(
    market_listings: list[dict],
    activities: list[dict],
    last_seen_ids: list[str],
    players_map: dict[str, dict],
    detected_at: str,
) -> tuple[list[dict], list[str]]:
    """Vergleicht die Systemangebote-Spieler-IDs von 'letztem Lauf' (last_seen_ids)
    gegen 'jetzt' (market_listings) - jede verschwundene ID, fuer die sich KEIN
    Trade (egal ob Systemkauf oder Mitspieler-Handel) im Activity-Feed findet,
    gilt als unverkauft abgelaufen (0% Aufschlag haette gereicht). Findet sich
    IRGENDEIN Trade fuer diese ID, ist das Verschwinden erklaert (Systemkauf
    landet ohnehin schon in bid_premium_log ueber build_new_entries();
    Mitspieler-Handel ist regulaerer Weiterverkauf, kein Signal fuer
    Gebotsvorschlaege). Keine Kickbase-API-Calls - nutzt nur bereits
    abgerufene Daten."""
    current_ids = [l["player_id"] for l in market_listings if l.get("is_system_offer")]
    current_ids_set = set(current_ids)
    disappeared = set(last_seen_ids) - current_ids_set

    traded_player_ids = {
        a["data"].get("pi")
        for a in activities
        if a.get("t") == TRADE_ACTIVITY_TYPE
    }

    entries = []
    for player_id in disappeared:
        if player_id in traded_player_ids:
            continue
        player = players_map.get(player_id)
        if not player:
            continue
        entries.append({
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": player.get("market_value"),
            "average_points_then": player.get("average_points"),
            "detected_at": detected_at,
        })

    return entries, current_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: detect_unsold_listings() - unverkauft abgelaufene Systemangebote erkennen"
```

---

## Task 4: `src/bid_premium.py` — `update_and_load()` erweitert, `_build_outcome_counts()`

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: `detect_unsold_listings()` (Task 3), `firestore_db.get_bid_premium_last_seen_listing_ids/upsert_bid_premium_last_seen_listing_ids/upsert_unsold_log_entries/get_unsold_log` (Task 2).
- Produces: `update_and_load(client, token, league_id, activities, players_map, market_listings, own_name, detected_at, get_history=...) -> tuple[list[dict], dict]` - `(bid_premium_history, outcome_counts)`. **Signatur-Bruch** - alle Aufrufer (Task 5) müssen angepasst werden.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bid_premium.py`, in der bestehenden Klasse `UpdateAndLoadTests` die drei existierenden Tests anpassen (neue Pflicht-Parameter, neuer Tupel-Rueckgabewert) und einen neuen Test ergänzen:

```python
class UpdateAndLoadTests(unittest.TestCase):
    @patch("src.bid_premium.firestore_db")
    def test_writes_new_entries_and_advances_pointer_when_found(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = None
        mock_fs.get_bid_premium_history.return_value = [{"activity_id": "act_1", "player_id": "p1", "position": "Sturm"}]
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = []
        mock_fs.get_unsold_log.return_value = []
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")
        client = MagicMock()

        history, outcome_counts = update_and_load(
            client=client, token="tok", league_id="l1", activities=activities,
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "average_points": 100}},
            market_listings=[], own_name="Ich", detected_at="2026-07-01",
            get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        mock_fs.upsert_bid_premium_entries.assert_called_once()
        mock_fs.upsert_bid_premium_pointer.assert_called_once_with(client, "2026-07-01T10:00:00Z")
        self.assertEqual(history, [{"activity_id": "act_1", "player_id": "p1", "position": "Sturm"}])
        self.assertEqual(outcome_counts, {"Sturm": {"rival_purchases": 1, "self_purchases": 0, "unsold": 0}})

    @patch("src.bid_premium.firestore_db")
    def test_no_new_purchases_skips_writes_but_still_returns_history(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = [{"activity_id": "act_old", "position": "Sturm"}]
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = []
        mock_fs.get_unsold_log.return_value = []

        history, _outcome_counts = update_and_load(
            client=MagicMock(), token="tok", league_id="l1", activities=[],
            players_map={}, market_listings=[], own_name=None, detected_at="2026-07-05",
            get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_bid_premium_entries.assert_not_called()
        mock_fs.upsert_bid_premium_pointer.assert_not_called()
        self.assertEqual(history, [{"activity_id": "act_old", "position": "Sturm"}])

    def test_none_client_is_noop_and_returns_empty(self):
        history, outcome_counts = update_and_load(
            client=None, token="tok", league_id="l1", activities=[{"anything": True}],
            players_map={}, market_listings=[], own_name=None, detected_at="2026-07-05",
        )
        self.assertEqual(history, [])
        self.assertEqual(outcome_counts, {})

    @patch("src.bid_premium.firestore_db")
    def test_unsold_detection_writes_entry_and_shows_up_in_outcome_counts(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = []
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = ["p1"]
        mock_fs.get_unsold_log.return_value = [{"player_id": "p1", "position": "Sturm", "detected_at": "2026-07-06"}]
        client = MagicMock()

        _history, outcome_counts = update_and_load(
            client=client, token="tok", league_id="l1", activities=[],
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "market_value": 1, "average_points": 1}},
            market_listings=[], own_name=None, detected_at="2026-07-06",
            get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_unsold_log_entries.assert_called_once()
        mock_fs.upsert_bid_premium_last_seen_listing_ids.assert_called_once_with(client, [])
        self.assertEqual(outcome_counts, {"Sturm": {"rival_purchases": 0, "self_purchases": 0, "unsold": 1}})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium.UpdateAndLoadTests -v`
Expected: FAIL (`TypeError` - fehlende Parameter, alte Signatur)

- [ ] **Step 3: Implement**

In `src/bid_premium.py` ergänzen (vor `update_and_load()`):

```python
def _build_outcome_counts(full_history: list[dict], unsold_log: list[dict]) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for entry in full_history:
        bucket = counts.setdefault(entry["position"], {"rival_purchases": 0, "self_purchases": 0, "unsold": 0})
        if entry.get("bought_by_self"):
            bucket["self_purchases"] += 1
        else:
            bucket["rival_purchases"] += 1
    for entry in unsold_log:
        bucket = counts.setdefault(entry["position"], {"rival_purchases": 0, "self_purchases": 0, "unsold": 0})
        bucket["unsold"] += 1
    return counts
```

`update_and_load()` komplett ersetzen:

```python
def update_and_load(
    client,
    token: str,
    league_id: str,
    activities: list[dict],
    players_map: dict[str, dict],
    market_listings: list[dict],
    own_name: str | None,
    detected_at: str,
    get_history=get_market_value_history,
) -> tuple[list[dict], dict]:
    """Zentraler Einstiegspunkt, von dashboard_export.export() aufgerufen.
    client=None (FIRESTORE_ENABLED fehlt, lokaler Testlauf) ist ein reines
    No-Op - leere Historie UND leere outcome_counts in diesem Fall.

    Die bid_premium_log-Collection waechst dauerhaft (ein Eintrag pro
    Systemkauf, fuer den Rest der Saison und darueber hinaus) und wird
    komplett in dashboard_snapshot/latest eingebettet (Firestores 1-MiB-
    Dokumentgrenze, schon jetzt ~450 Spieler schwer). suggestBid() im
    Frontend nutzt ohnehin nur die k=20 aehnlichsten Eintraege je Position -
    hier deshalb auf die MAX_HISTORY_ENTRIES_IN_SNAPSHOT neuesten Kaeufe
    gedeckelt (neueste zuerst, absteigend nach purchased_at). activity_id
    ist nur die Firestore-Schreib-Doc-Id und wird von keinem Frontend-
    Verbraucher gelesen (siehe frontend/src/types.ts::BidPremiumEntry) -
    wird deshalb vor dem Zurueckgeben entfernt statt unnoetig mitgeschickt
    zu werden.

    outcome_counts wird aus der VOLLEN (nicht gedeckelten) Historie berechnet
    - eine Zaehlung soll nicht durch den Snapshot-Cap verzerrt werden."""
    if client is None:
        return [], {}

    pointer = firestore_db.get_bid_premium_pointer(client)
    new_entries, new_pointer = build_new_entries(
        token, league_id, activities, pointer, players_map, own_name, get_history=get_history
    )
    if new_entries:
        firestore_db.upsert_bid_premium_entries(client, new_entries)
    if new_pointer:
        firestore_db.upsert_bid_premium_pointer(client, new_pointer)

    last_seen_ids = firestore_db.get_bid_premium_last_seen_listing_ids(client)
    unsold_entries, current_ids = detect_unsold_listings(
        market_listings, activities, last_seen_ids, players_map, detected_at
    )
    if unsold_entries:
        firestore_db.upsert_unsold_log_entries(client, unsold_entries)
    firestore_db.upsert_bid_premium_last_seen_listing_ids(client, current_ids)

    full_history = firestore_db.get_bid_premium_history(client)
    unsold_log = firestore_db.get_unsold_log(client)
    outcome_counts = _build_outcome_counts(full_history, unsold_log)

    capped = sorted(full_history, key=lambda e: e["purchased_at"], reverse=True)[:MAX_HISTORY_ENTRIES_IN_SNAPSHOT]
    history_for_frontend = [{k: v for k, v in e.items() if k != "activity_id"} for e in capped]
    return history_for_frontend, outcome_counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: update_and_load() liefert (history, outcome_counts), verdrahtet detect_unsold_listings()"
```

---

## Task 5: `src/dashboard_export.py` — Call-Site-Update + Snapshot-Feld

**Files:**
- Modify: `src/dashboard_export.py`

**Interfaces:**
- Consumes: `bid_premium.update_and_load()`s neue Signatur (Task 4).
- Produces: `data["bid_premium_outcome_counts"]` im Snapshot.

- [ ] **Step 1: Update the call site**

In `src/dashboard_export.py`, Zeile mit `bid_premium.update_and_load(...)` ersetzen:

```python
    bid_premium_history, bid_premium_outcome_counts = bid_premium.update_and_load(
        fs_client, token, league_id, activities, players_map, market_listings, own_name, fetched_at
    )
```

- [ ] **Step 2: Add the new field to the `data` dict**

```python
        "bid_premium_history": bid_premium_history,
        "bid_premium_outcome_counts": bid_premium_outcome_counts,
```

(direkt nach der bestehenden `"bid_premium_history": bid_premium_history,`-Zeile einfügen)

- [ ] **Step 3: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün (93+ Tests, keine bestehende Aufrufstelle von `bid_premium.update_and_load` außer dieser einen)

- [ ] **Step 4: Commit**

```bash
git add src/dashboard_export.py
git commit -m "dashboard_export: bid_premium_outcome_counts in den Snapshot verdrahtet"
```

---

## Task 6: `types.ts` — neue Typen

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `BidPremiumEntry.bought_by_self?: boolean`, neuer Typ `BidPremiumOutcomeCounts`, `DashboardSnapshot.bid_premium_outcome_counts?`.

- [ ] **Step 1: Extend `BidPremiumEntry` and add the new type**

```ts
export interface BidPremiumEntry {
  player_id: string;
  position: string;
  market_value_then: number;
  average_points_then: number | null;
  premium_pct: number;
  purchased_at: string;
  // Fehlt auf Eintraegen von vor diesem Feature - siehe Global Constraints
  // im Plan, immer mit `?? false`/truthy-Check lesen, nie als Pflichtfeld.
  bought_by_self?: boolean;
}

export interface BidPremiumOutcomeCountsEntry {
  rival_purchases: number;
  self_purchases: number;
  unsold: number;
}

export type BidPremiumOutcomeCounts = Record<string, BidPremiumOutcomeCountsEntry>;
```

- [ ] **Step 2: Extend `DashboardSnapshot`**

```ts
  bid_premium_outcome_counts?: BidPremiumOutcomeCounts;
```

(direkt neben der bestehenden `bid_premium_history?: BidPremiumEntry[];`-Zeile)

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: BidPremiumEntry.bought_by_self, BidPremiumOutcomeCounts neu"
```

---

## Task 7: `MlGenauigkeitTab.tsx` — Abschnitt "Gebotsvorschläge-Tracking"

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx`

**Interfaces:**
- Consumes: `data.bid_premium_outcome_counts` (Task 6). Kein `App.tsx`-Update nötig - die Komponente bekommt schon den vollen `data: DashboardSnapshot`-Snapshot als Prop (`<MlGenauigkeitTab data={data} />`), keine einzeln durchgereichten Felder.

- [ ] **Step 1: Extend the component's imports and read the new field**

In `frontend/src/components/MlGenauigkeitTab.tsx`, Import ergänzen:

```ts
import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlModelType } from "../types";
```

`export default function MlGenauigkeitTab({ data }: { data: DashboardSnapshot })` - Zugriff auf das neue Feld ergänzen (kein Props-Umbau nötig, `data` ist schon der volle Snapshot):

```ts
  const outcomeCounts: BidPremiumOutcomeCounts = data.bid_premium_outcome_counts ?? {};
```

(direkt nach `const trend = data.ml_accuracy_trend ?? [];` einfügen)

- [ ] **Step 2: Render the new section**

Direkt nach dem schließenden `</div>` des bestehenden Kopf-an-Kopf-Blocks (vor `<h3 ... >Trend: ...</h3>`) einfügen:

```tsx
      {Object.keys(outcomeCounts).length > 0 && (
        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Gebotsvorschläge-Tracking</h3>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Was aus abgeschlossenen Systemangeboten wurde, pro Position - Fremd-Käufe (echtes Gewinner-Gebot),
            eigene Käufe (Gebot war ausreichend, echter Mindestpreis unbekannt), unverkauft abgelaufen (0% Aufschlag
            hätte gereicht). Fließt nicht in die Gebotsempfehlungen ein, reine Beobachtung.
          </p>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
            {Object.entries(outcomeCounts).map(([position, counts]) => (
              <div key={position} className="rounded-xl border border-slate-200 p-3 text-xs dark:border-slate-800">
                <div className="mb-1 text-sm font-medium text-slate-900 dark:text-slate-50">{position}</div>
                <div className="text-slate-500 dark:text-slate-400">
                  {counts.rival_purchases} Fremd-Käufe · {counts.self_purchases} eigene · {counts.unsold} unverkauft
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx
git commit -m "MlGenauigkeitTab: neuer Abschnitt Gebotsvorschlaege-Tracking (Fremd-/Eigen-Kaeufe/unverkauft pro Position)"
```

---

## Task 8: Live-Verifikation (manuelle Schritte, kein Code)

**Files:** keine (operative Schritte gegen die echte Produktionsumgebung)

- [ ] **Step 1**: Alle Commits pushen (User macht das selbst).
- [ ] **Step 2**: `gh workflow run dashboard.yml` (Light reicht - `bid_premium.update_and_load()` läuft in beiden Modi) manuell anstoßen. Der ERSTE Lauf nach diesem Deploy setzt `last_seen_system_listing_ids` erstmals - noch keine "verschwunden"-Erkennung möglich (Zeiger war vorher leer), das ist erwartet, kein Fehler.
- [ ] **Step 3**: `gh run watch <run-id> --exit-status` - Erfolg abwarten.
- [ ] **Step 4**: Live prüfen: `dashboard_snapshot/latest` hat ein `bid_premium_outcome_counts`-Objekt (kann anfangs pro Position `{rival_purchases: N, self_purchases: 0, unsold: 0}` zeigen - `self_purchases`/`unsold` sind erst ab jetzt neu, alte Einträge zählen als Fremd-Kauf mangels `bought_by_self`-Feld). Firestore `bid_premium_state/current` hat jetzt zusätzlich `last_seen_system_listing_ids`.
- [ ] **Step 5**: Ein zweiter Lauf ein bis zwei Stunden später (nächster planmäßiger stündlicher Light-Lauf reicht) sollte, falls in der Zwischenzeit ein Systemangebot verschwunden ist, entweder einen neuen `bid_premium_log`- oder `bid_premium_unsold_log`-Eintrag zeigen - Stichprobe machen.
- [ ] **Step 6**: Echter Browser-Test durch den User (Sandbox kann kein `npm run dev`): Tab "Modell-Tracking" öffnen → neuer Abschnitt "Gebotsvorschläge-Tracking" zeigt Zähler pro Position.

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: beide neuen Signale (unverkauft/self-Tag), separate Speicherung ohne Einfluss auf `suggestBid()`, Anzeige im Modell-Tracking-Tab - alle Abschnitte der Spec haben eine Task.
- **Platzhalter-Scan**: keine TBD/"analog zu Task N ohne Code" gefunden. Beim Selbst-Review einen echten Bug im eigenen Testcode (Task 4, letzter Test) gefunden und gefixt: die Assertion verglich `client` mit sich selbst (`... if False else mock_fs...call_args[0][0]` wertet immer zur zweiten Haelfte aus - eine leere, immer-wahre Pruefung), weil `client` nie in einer Variable festgehalten wurde. Jetzt `client = MagicMock()` explizit gesetzt und in Call + Assertion wiederverwendet - die Assertion prueft jetzt tatsaechlich, dass derselbe Client durchgereicht wird.
- **Typ-Konsistenz**: `bought_by_self`/`bid_premium_outcome_counts`/`detect_unsold_listings`/`_build_outcome_counts` durchgängig gleich benannt zwischen allen Tasks. `update_and_load()`s neue Signatur (Task 4) passt exakt zum Call-Site-Update in Task 5.
- **Merge-Sicherheit explizit geprüft**: Task 2 ändert `upsert_bid_premium_pointer()` auf `merge=True` UND nutzt `merge=True` für die neue `last_seen_system_listing_ids`-Funktion - ohne das würde einer der beiden Writes das jeweils andere Feld im `bid_premium_state/current`-Dokument löschen (echtes Risiko, da beide Felder unabhängig und zu unterschiedlichen Zeitpunkten im selben Lauf geschrieben werden).

