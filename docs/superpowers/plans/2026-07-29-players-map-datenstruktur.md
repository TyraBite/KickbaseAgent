# Players-Map Datenstruktur-Umbau Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ersetzt die 5 parallelen, namens-verknüpften Firestore-Arrays (`alle_spieler`/`transfermarkt`/`eigenes_team_split`/`wunschkader`/`spekulation`) durch eine einzige `players`-Map (`player_id -> Rohdaten`) plus dünne Referenz-Listen, und verschiebt alle ableitbaren Berechnungen (Signal/Fairwert/Status-Text/Trend/Budget/Rendite%/Hype-Gipfel/Auktions-Status) vom Python-Backend ins TypeScript-Frontend.

**Architecture:** EIN Firestore-Dokument bleibt (1 Read pro Seitenaufruf, keine Quota-Verschlechterung). Backend schreibt nur noch rohe/gefetchte Felder + ML-Prognose (das einzige, was clientseitig nicht berechenbar ist). Frontend berechnet alles andere live aus diesen Rohdaten über eine neue geteilte `derive.ts`-Bibliothek. Cutover ist atomar (kein Firestore-Doppelschreiben) — Frontend-Migration läuft Tab für Tab gegen eine kurzzeitig erweiterte (optionale Alt-Felder) `DashboardSnapshot`-TS-Type, rein compile-zeitlich, ohne Firestore-Bezug.

**Tech Stack:** Python 3.11 (Backend, `src/`), TypeScript/React/Vite (Frontend, `frontend/src/`), Firestore (`google-cloud-firestore` Server-SDK, `firebase` Client-SDK), `unittest` (Backend-Tests).

## Global Constraints

- Firestore-Dokumentgröße: Ziel ≈119KB (von ≈196KB), weit unter dem 1MiB-Hard-Limit — erreicht NUR wenn fehlende Felder weggelassen (nicht `null` geschrieben) werden und `team_id` nicht mitgespeichert wird.
- Kein Firestore-Doppelschreiben — atomarer Cutover, kein Feature-Flag, kein Schema-Versionsfeld.
- Feldname-Standardisierung: überall `average_points` (nicht `points_avg`).
- `player_id` ist ab jetzt der einzige Join-Key für Spieler-Daten — kein Namens-Match mehr, außer als expliziter, einmaliger Migrationsschritt für Alt-Daten.
- **Frontend hat kein Test-Framework** (kein `npm install` in der Entwickler-Sandbox möglich, bestätigt in mehreren Vorgänger-Sessions) — Verifikation der Frontend-Tasks läuft über `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` (funktioniert ohne `npm install`, `node_modules` liegt bereits vor), NICHT über echte Tests. Jeder Frontend-Task endet mit diesem Befehl statt einem Testlauf.
- Backend-Tests laufen mit `python3 -m unittest discover -s tests -v` (oder gezielt `python3 -m unittest tests.test_X -v`) aus dem Repo-Root.
- Kein Push in dieser Session — Commits bleiben lokal (Standing-Rule `NeverPushOnMain`), der Repo-Owner pusht selbst.
- Reihenfolge ist verbindlich: Backend (Tasks 1-9) MUSS vor Frontend (Tasks 10-20) abgeschlossen sein — Frontend-Tasks lesen ein Schema, das erst nach Task 9 existiert. Cleanup (Task 21) kann jederzeit separat laufen.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `src/dashboard_export.py` | Kernstück des Backend-Umbaus: `_build_players_map`/`_build_transfermarkt_listings`/`_build_wunschkader_targets` neu, ~14 alte `_build_*`/Helfer-Funktionen gelöscht, `export()` neu verdrahtet |
| `src/player_valuation.py` | `points_avg` → `average_points` Umbenennung (12 Stellen) |
| `src/migrate_wunschkader_player_ids.py` | NEU — einmaliges Migrationsskript, danach löschbar |
| `tests/test_dashboard_export.py` | Alte `_build_*`-Tests raus, neue `BuildPlayersMapTests`/`BuildTransfermarktListingsTests`/`BuildWunschkaderTargetsTests`, `ResolveIsLightTests`/`ResolveHeavyDataTests` angepasst |
| `frontend/src/types.ts` | Neue Wire-Typen (`PlayerRecord`, `TransfermarktListing`, `Calibration`), `DashboardSnapshot` erweitert (Alt-Felder zeitweise optional) |
| `frontend/src/lib/derive.ts` | NEU — alle Ableitungs-Formeln + Builder-Funktionen |
| `frontend/src/lib/wunschkaderResolve.ts` | NEU — geteilter `computedFor`/`ResolvedTarget`-Resolver (Wunschkader + Eigenes-Team-Watchlist) |
| `frontend/src/components/AlleSpielerTab.tsx` | Migriert auf `players`-Map (zuerst, einfachster Tab) |
| `frontend/src/components/TransfermarktTab.tsx` | Migriert (Auktions-Countdown-Logik, höchstes Zeitzonen-Risiko) |
| `frontend/src/components/SpekulationTab.tsx` | Migriert (hängt an `TransfermarktTab`s Builder-Output) |
| `frontend/src/components/EigenesTeamTab.tsx` | Migriert (zieht `wunschkaderResolve.ts` mit raus) |
| `frontend/src/components/WunschkaderTab.tsx` | Migriert zuletzt (größte Komplexität: `AddTargetModal`, `replaceTarget`, Firestore-Write-Payload) |
| `frontend/src/App.tsx` | `transfermarktRows` einmal gemeinsam berechnen, an `TransfermarktTab` + `SpekulationTab` reichen |
| `index.html`, `.github/workflows/frontend-pilot.yml` | Cleanup: alte Seite + `/old/`-Deploy-Schritt entfernen |

---

## Task 1: `player_valuation.py` — `points_avg` → `average_points`

**Files:**
- Modify: `src/player_valuation.py` (12 Stellen: `fetch_all_players`, `k_per_point`, fairwert/signal-Helfer, `build_reference_set`, `calibrate`, `KNOWN_ANCHORS`, `_print_report`)
- Test: `tests/test_player_valuation.py` (neu — existiert bisher nicht)

**Interfaces:**
- Produces: `fetch_all_players()` gibt pro Zeile `"average_points"` statt `"points_avg"` zurück — Task 2 (`_build_players_map`) konsumiert dieses Feld unter dem neuen Namen.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_player_valuation.py
import unittest
from src.player_valuation import fetch_all_players


class FetchAllPlayersFieldNameTests(unittest.TestCase):
    def test_output_uses_average_points_not_points_avg(self):
        # Reiner Vertrags-Test ohne echten API-Call: prueft nur, dass die
        # Konstante/Doku-Referenz auf 'average_points' zeigt, indem wir das
        # Modul nach dem alten Feldnamen durchsuchen.
        import inspect
        import src.player_valuation as pv
        source = inspect.getsource(pv)
        self.assertNotIn('"points_avg"', source)
        self.assertIn('"average_points"', source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_player_valuation -v`
Expected: FAIL (`"points_avg"` noch im Quelltext gefunden)

- [ ] **Step 3: Rename all 12 occurrences**

In `src/player_valuation.py`: ersetze jedes `points_avg` durch `average_points` (Dict-Keys, Variablennamen, Docstrings, `KNOWN_ANCHORS`-Referenzen, `_print_report`-Ausgabetext). Kein Verhaltens-Unterschied, reine Umbenennung.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_player_valuation -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite (regression check)**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle Tests grün (kein anderer Test referenziert `points_avg` außerhalb von `tests/test_dashboard_export.py`, das in Task 7 ohnehin überarbeitet wird)

- [ ] **Step 6: Commit**

```bash
git add src/player_valuation.py tests/test_player_valuation.py
git commit -m "player_valuation: points_avg -> average_points umbenannt (Feldname-Standardisierung)"
```

---

## Task 2: `_build_players_map()` — die zentrale Merge-Logik

**Files:**
- Modify: `src/dashboard_export.py` (neue Funktion, vor `export()` einfügen)
- Test: `tests/test_dashboard_export.py` (neue Klasse `BuildPlayersMapTests`)

**Interfaces:**
- Consumes: `all_players: list[dict] | None` (aus `player_valuation.fetch_all_players()`, Felder: `player_id, name, position, team_id, team_name, market_value, average_points, starting_rank, status_code`), `own_squad`/`market_listings` (SQLite-Rows mit `player_id, name, position, team_name, status_code, starting_rank, market_value, average_points, total_points, market_value_change_7d, market_value_low_92d, market_value_high_92d, market_value_in_drop_phase`), `predictions: dict | None` (Form `{"predictions": {player_id: value}}`), `previous_players: dict[str, dict] | None`, `is_light: bool`.
- Produces: `dict[str, dict]` — die neue `players`-Map. Wird von Task 7 (`export()`) und indirekt von Task 4 (`_build_wunschkader_targets`) konsumiert.

- [ ] **Step 1: Write the failing tests**

```python
# In tests/test_dashboard_export.py, neue Klasse (Imports ergänzen: _build_players_map)
class BuildPlayersMapTests(unittest.TestCase):
    def _all_players_row(self, **overrides):
        row = {
            "player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
            "team_id": "t1", "team_name": "Bremen", "market_value": 10_000_000,
            "average_points": 120, "starting_rank": 1, "status_code": 0,
        }
        row.update(overrides)
        return row

    def _light_row(self, **overrides):
        row = {
            "player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
            "team_name": "Bremen", "status_code": 0, "starting_rank": 1,
            "market_value": 10_500_000, "average_points": 122, "total_points": 488,
            "market_value_change_7d": 50_000, "market_value_low_92d": 9_800_000,
            "market_value_high_92d": 10_600_000, "market_value_in_drop_phase": False,
        }
        row.update(overrides)
        return row

    def test_heavy_mode_builds_from_all_players_without_team_id(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[], market_listings=[],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertNotIn("team_id", result["p1"])
        self.assertEqual(result["p1"]["market_value"], 10_000_000)

    def test_heavy_mode_history_fields_absent_when_not_in_light_path(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[], market_listings=[],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertNotIn("market_value_change_7d", result["p1"])

    def test_heavy_mode_overlays_own_squad_history_fields(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[self._light_row()],
            market_listings=[], predictions=None, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)
        self.assertEqual(result["p1"]["market_value"], 10_500_000)

    def test_market_listings_overlay_same_as_own_squad(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[],
            market_listings=[self._light_row(player_id="p1")],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)

    def test_ml_prediction_set_only_for_predicted_ids(self):
        result = _build_players_map(
            all_players=[self._all_players_row(player_id="p1"), self._all_players_row(player_id="p2", name="Foo")],
            own_squad=[], market_listings=[],
            predictions={"predictions": {"p1": 45_000}}, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["ml_prediction"], 45_000)
        self.assertNotIn("ml_prediction", result["p2"])

    def test_light_mode_untouched_players_carried_forward_unchanged(self):
        previous = {"p9": {"player_id": "p9", "name": "Unberuehrt", "market_value": 1_000_000}}
        result = _build_players_map(
            all_players=None, own_squad=[], market_listings=[],
            predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p9"], previous["p9"])

    def test_light_mode_touched_player_gets_fresh_values_not_stale(self):
        previous = {"p1": {"player_id": "p1", "name": "Krauß", "market_value": 9_000_000,
                            "market_value_change_7d": -100_000}}
        result = _build_players_map(
            all_players=None, own_squad=[self._light_row(market_value_change_7d=50_000)],
            market_listings=[], predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)
        self.assertEqual(result["p1"]["market_value"], 10_500_000)

    def test_light_mode_preserves_ml_prediction_when_predictions_is_none(self):
        previous = {"p1": {"player_id": "p1", "name": "Krauß", "ml_prediction": 12_345}}
        result = _build_players_map(
            all_players=None, own_squad=[], market_listings=[],
            predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p1"]["ml_prediction"], 12_345)

    def test_light_mode_new_player_not_in_previous_snapshot_does_not_crash(self):
        result = _build_players_map(
            all_players=None, own_squad=[self._light_row(player_id="p_new")],
            market_listings=[], predictions=None, previous_players={}, is_light=True,
        )
        self.assertEqual(result["p_new"]["market_value"], 10_500_000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export.BuildPlayersMapTests -v`
Expected: FAIL (`ImportError: cannot import name '_build_players_map'`)

- [ ] **Step 3: Implement**

In `src/dashboard_export.py`, oberhalb von `export()` einfügen:

```python
def _build_players_map(
    all_players: list[dict] | None,
    own_squad,
    market_listings,
    predictions: dict | None,
    previous_players: dict[str, dict] | None,
    is_light: bool,
) -> dict[str, dict]:
    """Baut/aktualisiert die players-Map (player_id -> rohe Felder +
    ml_prediction). Heavy: kompletter Rebuild aus den ~450 all_players-
    Zeilen (team_id wird NICHT uebernommen - niemand client-seitig braucht
    ihn). Light: startet als Kopie der VORHERIGEN Map - die anderen ~380
    Spieler bleiben dadurch unveraendert, kein Re-Fetch.

    In BEIDEN Modi werden anschliessend own_squad+market_listings (immer
    taggenau frisch, siehe fetcher.run()) auf die Basis ueberlagert - das
    ist das EINZIGE, was in einem Light-Lauf tatsaechlich veraendert wird.
    History-Felder werden nur uebernommen wenn die Zeile sie tatsaechlich
    hat (Feld bleibt UNGESETZT statt explizit null - sonst wuerden fuer
    ~380 Spieler pro Light-Lauf vorhandene Werte verloren gehen, obwohl sie
    gar nicht angefasst wurden).

    ml_prediction wird nur fuer player_ids in predictions['predictions']
    gesetzt/ueberschrieben - alle anderen behalten den Wert aus `base`
    (Light: der letzte bekannte Stand; Heavy: keiner, da `base` dort frisch
    aufgebaut wird)."""
    if is_light:
        base: dict[str, dict] = {pid: dict(p) for pid, p in (previous_players or {}).items()}
    else:
        base = {
            p["player_id"]: {
                "player_id": p["player_id"],
                "name": p["name"],
                "position": p["position"],
                "team_name": p["team_name"],
                "status_code": p["status_code"],
                "starting_rank": p["starting_rank"],
                "market_value": p["market_value"],
                "average_points": p["average_points"],
            }
            for p in (all_players or [])
            if p.get("player_id")
        }

    HISTORY_FIELDS = (
        "market_value_change_7d", "market_value_low_92d",
        "market_value_high_92d", "market_value_in_drop_phase",
    )
    for row in list(own_squad) + list(market_listings):
        pid = row["player_id"]
        entry = dict(base.get(pid) or {"player_id": pid})
        entry.update({
            "name": row["name"],
            "position": row["position"],
            "team_name": row["team_name"],
            "status_code": row["status_code"],
            "starting_rank": row["starting_rank"],
            "market_value": row["market_value"],
            "average_points": row["average_points"],
            "total_points": row["total_points"],
        })
        for field in HISTORY_FIELDS:
            value = row[field]
            if value is not None:
                entry[field] = value
        base[pid] = entry

    predictions_by_id = (predictions or {}).get("predictions", {})
    for pid, value in predictions_by_id.items():
        if pid in base:
            base[pid]["ml_prediction"] = value

    return base
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export.BuildPlayersMapTests -v`
Expected: PASS (9 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _build_players_map() - zentrale Light/Heavy-Merge-Logik fuer die neue players-Map"
```

---

## Task 3: `_build_transfermarkt_listings()`

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py` (neue Klasse `BuildTransfermarktListingsTests`)

**Interfaces:**
- Consumes: `market_listings` (SQLite-Rows, gleiche Quelle wie Task 2).
- Produces: `list[dict]`, je Eintrag `{player_id, price, price_delta_pct, offering_username, is_system_offer, pending_offers_count, leading_bid_username, leading_bid_price, is_own_leading_bid, listed_at, expires_at, expiry_is_estimate}` — konsumiert von Task 7 (`export()`).

- [ ] **Step 1: Write the failing test**

```python
class BuildTransfermarktListingsTests(unittest.TestCase):
    def test_extracts_only_raw_listing_fields(self):
        listing = {
            "player_id": "p1", "price": 5_000_000, "price_delta_pct": 2.5,
            "offering_username": None, "is_system_offer": 1, "pending_offers_count": 0,
            "leading_bid_username": None, "leading_bid_price": None, "is_own_leading_bid": 0,
            "listed_at": "2026-07-27T10:00:00Z", "expires_at": "2026-07-29T20:00:00Z",
            "expiry_is_estimate": 0,
        }

        result = _build_transfermarkt_listings([listing])

        self.assertEqual(result[0]["player_id"], "p1")
        self.assertEqual(result[0]["price"], 5_000_000)
        self.assertIs(result[0]["is_system_offer"], True)
        self.assertNotIn("auction_status", result[0])
        self.assertNotIn("affordable", result[0])
        self.assertNotIn("signal", result[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard_export.BuildTransfermarktListingsTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

```python
def _build_transfermarkt_listings(market_listings) -> list[dict]:
    """Reine Markt-Rohfelder je Listing - kein Merge mit Spieler-Stammdaten
    mehr (die kommen aus der players-Map), kein auction_status/affordable
    (clientseitig aus listed_at/expires_at/expiry_is_estimate + price +
    eigenem Budget berechnet, siehe frontend/src/lib/derive.ts)."""
    return [
        {
            "player_id": r["player_id"],
            "price": r["price"],
            "price_delta_pct": r["price_delta_pct"],
            "offering_username": r["offering_username"],
            "is_system_offer": bool(r["is_system_offer"]),
            "pending_offers_count": r["pending_offers_count"],
            "leading_bid_username": r["leading_bid_username"],
            "leading_bid_price": r["leading_bid_price"],
            "is_own_leading_bid": bool(r["is_own_leading_bid"]),
            "listed_at": r["listed_at"],
            "expires_at": r["expires_at"],
            "expiry_is_estimate": bool(r["expiry_is_estimate"]),
        }
        for r in market_listings
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_dashboard_export.BuildTransfermarktListingsTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _build_transfermarkt_listings() - duenne Rohfeld-Liste statt vollem Merge"
```

---

## Task 4: `_build_wunschkader_targets()` (ersetzt `_build_wunschkader`)

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py` (neue Klasse `BuildWunschkaderTargetsTests`, ersetzt `BuildWunschkaderTests`)

**Interfaces:**
- Consumes: `wunschkader: dict` (Firestore `wunschkader/current`, `targets` jetzt MIT `player_id` — siehe Task 8 Migration), `players_map: dict[str, dict]` (aus Task 2).
- Produces: `list[dict]`, je Eintrag `{player_id, role, note, actual_bid}` — konsumiert von Task 7.

- [ ] **Step 1: Write the failing tests**

```python
class BuildWunschkaderTargetsTests(unittest.TestCase):
    def test_passes_through_player_id_and_overlay_fields(self):
        wunschkader = {"targets": [{"player_id": "p1", "role": "Starter", "note": "geprüft", "actual_bid": 16_000_000}]}
        players_map = {"p1": {"player_id": "p1", "name": "Krauß"}}

        rows = _build_wunschkader_targets(wunschkader, players_map)

        self.assertEqual(rows[0], {"player_id": "p1", "role": "Starter", "note": "geprüft", "actual_bid": 16_000_000})

    def test_keeps_target_even_when_player_id_unknown(self):
        wunschkader = {"targets": [{"player_id": "p_missing", "role": "Starter", "note": None, "actual_bid": None}]}

        rows = _build_wunschkader_targets(wunschkader, players_map={})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_id"], "p_missing")

    def test_empty_targets_returns_empty_list(self):
        self.assertEqual(_build_wunschkader_targets({"targets": []}, players_map={}), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export.BuildWunschkaderTargetsTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

```python
def _build_wunschkader_targets(wunschkader: dict, players_map: dict) -> list[dict]:
    """Wunschkader-Ziele sind jetzt eine reine player_id-Referenzliste
    (Firestore wunschkader/current speichert player_id direkt seit der
    einmaligen Migration, siehe migrate_wunschkader_player_ids.py) - keine
    Namens-Aufloesung, keine Praesentations-Felder mehr (team_name/
    market_value/status/planned_price loest der Client selbst ueber
    players[player_id] auf). Nur eine Sanity-Warnung falls ein player_id
    (noch) nicht in players_map auftaucht - das Ziel bleibt trotzdem in der
    Liste (kein stiller Datenverlust bei einem einzelnen kaputten Eintrag,
    gleiche Philosophie wie _load_wunschkader())."""
    targets = wunschkader.get("targets", [])
    for t in targets:
        pid = t.get("player_id")
        if not pid or pid not in players_map:
            print(
                f"Warnung: Wunschkader-Ziel mit player_id={pid!r} nicht in players_map gefunden "
                "- siehe migrate_wunschkader_player_ids.py",
                file=sys.stderr,
            )
    return [
        {
            "player_id": t.get("player_id"),
            "role": t.get("role"),
            "note": t.get("note"),
            "actual_bid": t.get("actual_bid"),
        }
        for t in targets
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export.BuildWunschkaderTargetsTests -v`
Expected: PASS

- [ ] **Step 5: Delete the old `_build_wunschkader` and its tests**

In `src/dashboard_export.py`: `_build_wunschkader`-Funktion komplett löschen. In `tests/test_dashboard_export.py`: Klasse `BuildWunschkaderTests` (testet die alte Funktion) komplett löschen, Import von `_build_wunschkader` aus dem Import-Block entfernen, Import von `_build_wunschkader_targets` ergänzen.

- [ ] **Step 6: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün (alte Tests für `_build_wunschkader` sind weg, keine verwaisten Referenzen)

- [ ] **Step 7: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _build_wunschkader_targets() ersetzt _build_wunschkader (player_id statt Namens-Match)"
```

---

## Task 5: Tote Funktionen löschen (Fairwert/Signal/Auktion/Hype-Gipfel/Budget)

**Files:**
- Modify: `src/dashboard_export.py`
- Modify: `tests/test_dashboard_export.py`

**Interfaces:**
- Consumes: nichts Neues.
- Produces: nichts — reine Löschung. Task 7 (`export()`) darf danach keine dieser Funktionen mehr aufrufen.

Die gesamte Ableitungslogik wandert nach `frontend/src/lib/derive.ts` (Tasks 11-13). Diese Funktionen haben nach Task 7 keinen Aufrufer mehr:

- [ ] **Step 1: Delete `_player_row`, `_valuation`, `_k_per_point`, `_trend_direction`** aus `src/dashboard_export.py`.
- [ ] **Step 2: Delete `_build_transfermarkt`, `_auction_status`, `_next_update_cutoff`, `_format_duration`** (und zugehörige Konstanten `NEXT_MARKET_VALUE_UPDATE_HOUR`, Berlin-Timezone-Setup, `_NO_EXPIRY_SENTINEL_SECONDS` falls vorhanden) aus `src/dashboard_export.py`.
- [ ] **Step 3: Delete `_build_eigenes_team`, `_split_eigenes_team`** aus `src/dashboard_export.py`.
- [ ] **Step 4: Delete `_is_hype_gipfel`, `_build_spekulation`, `HYPE_CHANGE_THRESHOLD`, `SPEKULATION_FLOOR_PROTECTED`** aus `src/dashboard_export.py`.
- [ ] **Step 5: Delete `_build_alle_spieler`** aus `src/dashboard_export.py`.
- [ ] **Step 6: Delete `_estimate_price`** aus `src/dashboard_export.py` (bereits 1:1 in `WunschkaderTab.tsx` als `estimatePrice()` portiert — reiner Dead-Code-Abbau, siehe Task 11).
- [ ] **Step 7: Delete `_build_budget_plan`** aus `src/dashboard_export.py`.
- [ ] **Step 8: In `tests/test_dashboard_export.py` die entsprechenden Testklassen löschen**: `BuildAlleSpielerTests`, `BuildSpekulationTests`, `BuildTransfermarktTests`, `EstimatePriceTests`, `BuildBudgetPlanTests`. Zugehörige Imports aus dem Import-Block am Dateianfang entfernen.
- [ ] **Step 9: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL zu diesem Zeitpunkt erwartet (Import-Fehler), da `export()` diese Funktionen noch aufruft — wird in Task 7 aufgelöst. **Nicht committen, bevor Task 7 fertig ist** (dieser Task und Task 7 bilden zusammen einen atomaren Schritt — siehe Hinweis unten).

> **Hinweis zur Reihenfolge**: Tasks 5 und 7 gehören zusammen (Löschen + Neu-Verdrahten von `export()`), weil `export()` zwischen beiden Schritten nicht compilebar/lauffähig ist. Führe Task 5 direkt gefolgt von Task 6 und 7 aus, committe erst am Ende von Task 7.

---

## Task 6: `_resolve_heavy_data()` und `_resolve_is_light()` anpassen

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py` (`ResolveHeavyDataTests`, `ResolveIsLightTests` anpassen)

**Interfaces:**
- Produces: `_resolve_heavy_data(...)` gibt kein `starting_rank_by_player_id` mehr zurück, `predictions` ist im Light-Modus `None` (nicht mehr ein synthetisches Dict), `owned_by` wird im Light-Modus aus `cached_snapshot["owned_by"]` durchgereicht statt auf `{}` zurückgesetzt. `_resolve_is_light(mode, cached_snapshot)` erkennt zusätzlich einen Snapshot im ALTEN Schema (kein `"players"`-Key) als Cold-Start.

- [ ] **Step 1: Update the existing tests first (red)**

In `tests/test_dashboard_export.py`, `ResolveIsLightTests` erweitern:

```python
    def test_light_mode_with_old_shape_snapshot_falls_back_to_heavy(self):
        old_shape_snapshot = {"alle_spieler": []}  # kein "players"-Key
        self.assertFalse(_resolve_is_light("light", old_shape_snapshot))
```

`ResolveHeavyDataTests` — bestehende Assertions anpassen:

```python
    @patch("src.dashboard_export.player_valuation.resolve_ownership")
    @patch("src.dashboard_export.player_valuation.load_calibration")
    @patch("src.dashboard_export.market_predictor.predict_market_value_changes")
    @patch("src.dashboard_export.player_valuation.fetch_all_players")
    def test_light_mode_skips_all_expensive_functions(
        self, mock_fetch_all, mock_predict, mock_calibration, mock_resolve_ownership
    ):
        cached_snapshot = {
            "players": {"p1": {"player_id": "p1"}},
            "calibration": {"Sturm": 0.9},
            "ml_metrics": {"accuracy_trend": [3]},
            "ml_accuracy_trend": [3],
            "owned_by": {"p2": "Rivale"},
        }

        result = _resolve_heavy_data(
            is_light=True, cached_snapshot=cached_snapshot, token="tok", league_id="l1",
            competition_id="c1", ranking_rows=[], own_name="Ich",
        )

        mock_fetch_all.assert_not_called()
        mock_predict.assert_not_called()
        mock_resolve_ownership.assert_not_called()
        self.assertIsNone(result["all_players"])
        self.assertIsNone(result["predictions"])
        self.assertEqual(result["calibration"], {"Sturm": 0.9})
        self.assertEqual(result["owned_by"], {"p2": "Rivale"})
        self.assertNotIn("starting_rank_by_player_id", result)
```

Entferne den alten `test_light_mode_ml_prediction_flows_into_player_row`-Test (testete `_build_eigenes_team`, das jetzt gelöscht ist) und den alten `test_heavy_mode_calls_all_expensive_functions`-Test-Body auf `starting_rank_by_player_id` — passe die verbleibenden Assertions entsprechend an (kein `starting_rank_by_player_id` im Ergebnis mehr).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export.ResolveIsLightTests tests.test_dashboard_export.ResolveHeavyDataTests -v`
Expected: FAIL (alte Implementierung liefert noch `starting_rank_by_player_id`, synthetisches `predictions`-Dict, `owned_by={}`)

- [ ] **Step 3: Implement**

```python
def _resolve_is_light(mode: str | None, cached_snapshot: dict | None) -> bool:
    """Ein einziger Entscheidungspunkt fuer DASHBOARD_MODE=light vs. voller
    Lauf. Cold Start umfasst jetzt ZWEI Faelle: kein Snapshot gefunden ODER
    ein Snapshot im ALTEN Schema (vor der players-Map-Migration, erkennbar
    am fehlenden "players"-Key) - beide fuehren zum automatischen
    Selbstheilungs-Fallback auf den vollen Lauf."""
    is_cold_start = cached_snapshot is None or "players" not in cached_snapshot
    if mode == "light" and is_cold_start:
        print(
            "Warnung: DASHBOARD_MODE=light, aber kein verwertbarer Firestore-Snapshot "
            "gefunden (Cold Start oder alter Schema-Stand vor der players-Map-Migration) - "
            "falle automatisch auf den vollen Marktwert-Lauf zurueck.",
            file=sys.stderr,
        )
    return mode == "light" and not is_cold_start


def _resolve_heavy_data(
    is_light: bool,
    cached_snapshot: dict | None,
    token: str,
    league_id: str,
    competition_id: str,
    ranking_rows,
    own_name: str | None,
) -> dict:
    """Zentrale Weiche fuer alle marktwert-abgeleiteten export()-Eingaben.
    Light: liefert alles aus dem letzten Snapshot (inkl. owned_by, das
    frueher auf {} zurueckgesetzt wurde), predictions bleibt None statt
    eines synthetischen Dicts - _build_players_map() braucht das nicht
    mehr, da ml_prediction jetzt Teil der uebernommenen players-Map ist."""
    if is_light:
        return {
            "all_players": None,
            "predictions": None,
            "calibration": cached_snapshot["calibration"],
            "owned_by": cached_snapshot.get("owned_by", {}),
            "ml_metrics": cached_snapshot["ml_metrics"],
            "ml_accuracy_trend": cached_snapshot["ml_accuracy_trend"],
        }

    all_players = player_valuation.fetch_all_players(token, competition_id)
    predictions = market_predictor.predict_market_value_changes()
    owned_by = (
        player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
        if own_name
        else {}
    )
    return {
        "all_players": all_players,
        "predictions": predictions,
        "calibration": player_valuation.load_calibration(),
        "owned_by": owned_by,
        "ml_metrics": predictions["metrics"] if predictions else None,
        "ml_accuracy_trend": predictions["metrics"].get("accuracy_trend") if predictions else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export.ResolveIsLightTests tests.test_dashboard_export.ResolveHeavyDataTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _resolve_is_light/_resolve_heavy_data an players-Map-Schema angepasst"
```

---

## Task 7: `export()` neu verdrahten

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py` (kein neuer Test — `export()` selbst hat keine dedizierten Unit-Tests, die einzelnen Bausteine sind in Tasks 2-6 getestet; dieser Task verdrahtet sie nur)

**Interfaces:**
- Consumes: alle Ergebnisse aus Tasks 2, 3, 4, 6.
- Produces: die neue `data`-Dict-Form (siehe Schema oben), geschrieben über `_finalize_firestore_write()` (unverändert).

- [ ] **Step 1: Replace `export()`'s body**

```python
def export() -> dict:
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    mode = os.environ.get("DASHBOARD_MODE")
    cached_snapshot = None
    if mode == "light" and os.environ.get("FIRESTORE_ENABLED"):
        cached_snapshot = firestore_db.get_dashboard_snapshot(firestore_db.connect())
    is_light = _resolve_is_light(mode, cached_snapshot)

    fetched_at = fetcher.run()

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    own_squad, market_listings, ranking_rows, manager_budget_rows = _load_snapshot(fetched_at)

    own_budget_row = next((b for b in manager_budget_rows if b["is_own_exact"]), None)
    own_available_budget = own_budget_row["available_budget"] if own_budget_row else None
    own_name = own_budget_row["name"] if own_budget_row else None

    heavy = _resolve_heavy_data(is_light, cached_snapshot, token, league_id, competition_id, ranking_rows, own_name)

    previous_players = cached_snapshot.get("players", {}) if is_light else None
    players_map = _build_players_map(
        all_players=heavy["all_players"],
        own_squad=own_squad,
        market_listings=market_listings,
        predictions=heavy["predictions"],
        previous_players=previous_players,
        is_light=is_light,
    )

    wunschkader_config = _load_wunschkader()
    wunschkader_targets = (
        _build_wunschkader_targets(wunschkader_config, players_map) if wunschkader_config else []
    )

    data = {
        "fetched_at": fetched_at,
        "own_available_budget": own_available_budget,
        "own_budget_exact": own_budget_row["estimated_budget"] if own_budget_row else None,
        "team_total_value": sum((p["market_value"] or 0) for p in own_squad),
        "calibration": heavy["calibration"],
        "ml_metrics": heavy["ml_metrics"],
        "ml_accuracy_trend": heavy["ml_accuracy_trend"],
        "signal_thresholds": {"good": SIGNAL_GOOD, "critical": SIGNAL_CRITICAL},
        "players": players_map,
        "transfermarkt_listings": _build_transfermarkt_listings(market_listings),
        "own_squad_ids": [r["player_id"] for r in own_squad],
        "owned_by": heavy["owned_by"],
        "wunschkader_targets": wunschkader_targets,
        "wunschkader_formation": wunschkader_config.get("formation") if wunschkader_config else None,
        "wunschkader_sell_list": wunschkader_config.get("sell_list") if wunschkader_config else None,
        "wunschkader_updated_at": wunschkader_config.get("updated_at") if wunschkader_config else None,
        "ligaanalyse": _build_ligaanalyse(
            token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad,
            {pid: p["starting_rank"] for pid, p in players_map.items()},
        ),
    }

    _finalize_firestore_write(data)
    return data
```

- [ ] **Step 2: Update the module docstring**

Ersetze den Absatz über `DASHBOARD_MODE` (aus der Cron-Split-Session) um einen Hinweis auf das neue Schema: `players`-Map statt paralleler Arrays, alle abgeleiteten Werte jetzt clientseitig (siehe `frontend/src/lib/derive.ts`).

- [ ] **Step 3: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle Tests grün (Tasks 5+6+7 zusammen ergeben wieder ein lauffähiges Modul)

- [ ] **Step 4: Commit**

```bash
git add src/dashboard_export.py
git commit -m "dashboard_export: export() auf players-Map-Schema umgestellt, 14 tote Ableitungs-Funktionen entfernt"
```

---

## Task 8: `migrate_wunschkader_player_ids.py`

**Files:**
- Create: `src/migrate_wunschkader_player_ids.py`
- Test: `tests/test_migrate_wunschkader_player_ids.py`

**Interfaces:**
- Consumes: `firestore_db.get_dashboard_snapshot()`, `firestore_db.get_wunschkader()`, `firestore_db.upsert_wunschkader()` (alle bereits vorhanden, unverändert).
- Produces: schreibt `player_id` in bestehende Firestore-`wunschkader/current`-Einträge. Einmaliger Lauf, kein Dauerbetrieb-Code.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_migrate_wunschkader_player_ids.py
import unittest
from unittest.mock import MagicMock
from src.migrate_wunschkader_player_ids import _resolve_player_id


class ResolvePlayerIdTests(unittest.TestCase):
    def test_returns_id_for_unique_name_match(self):
        players = {"p1": {"name": "Krauß"}, "p2": {"name": "Stage"}}
        self.assertEqual(_resolve_player_id("Krauß", players), "p1")

    def test_returns_none_for_no_match(self):
        players = {"p1": {"name": "Krauß"}}
        self.assertIsNone(_resolve_player_id("Unbekannt", players))

    def test_returns_none_for_ambiguous_match(self):
        players = {"p1": {"name": "Müller"}, "p2": {"name": "Müller"}}
        self.assertIsNone(_resolve_player_id("Müller", players))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_migrate_wunschkader_player_ids -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement**

```python
# src/migrate_wunschkader_player_ids.py
"""Einmalige Migration: fuegt player_id zu den bestehenden Wunschkader-
targets/sell_list-Eintraegen hinzu (bisher nur per Name referenziert).
Kein Dauerbetrieb-Code, kein Dual-Path-Fallback - einmal per Hand
ausfuehren (`python -m src.migrate_wunschkader_player_ids`), danach kann
diese Datei wieder geloescht werden (Repo-Konvention: keine Backwards-
Compat-Shims fuer diesen kleinen, persoenlichen Datensatz).

Voraussetzung: dashboard_snapshot/latest muss bereits im NEUEN Schema
vorliegen (players-Map vorhanden) - sonst zuerst einen Heavy-Lauf von
dashboard_export.export() (oder workflow_dispatch von dashboard-
marktwerte.yml) durchfuehren."""
import sys

from src import firestore_db


def _resolve_player_id(name: str, players: dict[str, dict]) -> str | None:
    matches = [pid for pid, p in players.items() if p.get("name") == name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Warnung: '{name}' mehrfach gefunden ({matches}) - manuell aufloesen", file=sys.stderr)
    else:
        print(f"Warnung: '{name}' nicht gefunden - manuell aufloesen", file=sys.stderr)
    return None


def migrate() -> None:
    client = firestore_db.connect()
    snapshot = firestore_db.get_dashboard_snapshot(client)
    if not snapshot or "players" not in snapshot:
        raise RuntimeError("dashboard_snapshot/latest hat noch keine players-Map - zuerst Heavy-Lauf durchfuehren")
    players = snapshot["players"]

    wunschkader = firestore_db.get_wunschkader(client)
    if not wunschkader:
        print("Kein wunschkader/current-Dokument gefunden - nichts zu migrieren")
        return

    changed = False
    for target in wunschkader.get("targets", []):
        if "player_id" in target:
            continue
        pid = _resolve_player_id(target["name"], players)
        if pid:
            target["player_id"] = pid
            changed = True

    new_sell_list = []
    for entry in wunschkader.get("sell_list", []):
        if entry in players:  # schon eine player_id
            new_sell_list.append(entry)
            continue
        pid = _resolve_player_id(entry, players)
        new_sell_list.append(pid or entry)
        changed = changed or bool(pid)
    wunschkader["sell_list"] = new_sell_list

    if not changed:
        print("Keine Aenderungen noetig")
        return

    firestore_db.upsert_wunschkader(client, wunschkader)
    unresolved = [t.get("name") for t in wunschkader.get("targets", []) if "player_id" not in t]
    print(f"Migration geschrieben. Weiterhin ungeloest: {unresolved}")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_migrate_wunschkader_player_ids -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün

- [ ] **Step 6: Commit**

```bash
git add src/migrate_wunschkader_player_ids.py tests/test_migrate_wunschkader_player_ids.py
git commit -m "Neu: einmaliges Migrationsskript fuer Wunschkader-player_id (vor dem Cutover manuell auszufuehren)"
```

---

## Task 9: Backend-Cutover ausrollen (manuelle Schritte, kein Code)

**Files:** keine (operative Schritte gegen die echte Produktionsumgebung)

- [ ] **Step 1**: `python -m src.migrate_wunschkader_player_ids` **lokal gegen Produktions-Firestore** ausführen (braucht `GOOGLE_APPLICATION_CREDENTIALS`/`FIRESTORE_ENABLED=1`) — **NUR wenn `dashboard_snapshot/latest` schon die neue players-Map hat**. Falls noch nicht: diesen Schritt NACH Step 2 wiederholen.
- [ ] **Step 2**: Backend-Commits (Tasks 1-8) pushen (User macht das selbst).
- [ ] **Step 3**: `gh workflow run dashboard-marktwerte.yml` einmal manuell anstoßen — bringt `dashboard_snapshot/latest` sofort ins neue Schema, statt auf den nächsten Cron zu warten.
- [ ] **Step 4**: `gh run watch <run-id> --exit-status` — Erfolg abwarten.
- [ ] **Step 5**: Falls Step 1 noch nicht lief: jetzt `python -m src.migrate_wunschkader_player_ids` ausführen, Warnungen (ungelöste Namen) prüfen und ggf. manuell in der Firebase-Konsole nachtragen.
- [ ] **Step 6**: `src/migrate_wunschkader_player_ids.py` + `tests/test_migrate_wunschkader_player_ids.py` löschen (einmaliges Skript, danach nicht mehr gebraucht) und committen: `git commit -m "migrate_wunschkader_player_ids: einmalige Migration durchgefuehrt, Skript entfernt"`.

---

## Task 10: `types.ts` — neue Wire-Typen

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `PlayerRecord`, `TransfermarktListing`, `Calibration`, `RawWunschkaderTarget` (neu, mit `player_id`), `DashboardSnapshot` erweitert. Konsumiert von allen folgenden Frontend-Tasks.

- [ ] **Step 1: Add new wire types and extend `DashboardSnapshot`**

```ts
export interface PositionCalibrationEntry {
  k: number | null;
  n: number;
}

export interface Calibration {
  calibrated_at?: string;
  n: number;
  global_k: number | null;
  position_k: Record<string, PositionCalibrationEntry>;
}

export interface PlayerRecord {
  player_id: string;
  name: string;
  position: string;
  team_name: string | null;
  status_code: number | null;
  starting_rank: number | null;
  market_value: number | null;
  average_points: number | null;
  // Nur vorhanden fuer Spieler in own_squad/market_listings (light-path):
  market_value_change_7d?: number;
  market_value_low_92d?: number;
  market_value_high_92d?: number;
  market_value_in_drop_phase?: boolean;
  total_points?: number;
  // Nur vorhanden, wenn das ML-Modell einen Wert produziert hat:
  ml_prediction?: number;
}

export interface TransfermarktListing {
  player_id: string;
  price: number;
  price_delta_pct: number | null;
  offering_username: string | null;
  is_system_offer: boolean;
  pending_offers_count: number | null;
  leading_bid_username: string | null;
  leading_bid_price: number | null;
  is_own_leading_bid: boolean;
  listed_at: string | null;
  expires_at: string | null;
  expiry_is_estimate: boolean;
}
```

- [ ] **Step 2: Replace `RawWunschkaderTarget`**

```ts
// ALT (kept temporarily under a new name during the migration window):
export interface LegacyRawWunschkaderTarget {
  name: string;
  position: string;
  role?: string;
  note?: string;
  actual_bid?: number;
}

// NEU:
export interface RawWunschkaderTarget {
  player_id: string;
  role: string;
  note?: string;
  actual_bid?: number;
}
```

- [ ] **Step 3: Extend `DashboardSnapshot`**

```ts
export interface DashboardSnapshot {
  // NEU
  players: Record<string, PlayerRecord>;
  calibration: Calibration | null;
  transfermarkt_listings: TransfermarktListing[];
  own_squad_ids: string[];
  owned_by: Record<string, string>;
  wunschkader_targets: RawWunschkaderTarget[];
  wunschkader_sell_list: string[] | null;

  // ALT — optional, rein zur Compile-Zeit-Ueberbrueckung waehrend Tasks 15-19.
  // WIRD IN TASK 20 KOMPLETT ENTFERNT. Kein Firestore-Bezug, kein Live-Risiko.
  alle_spieler?: AlleSpielerRow[];
  transfermarkt?: TransfermarktRow[];
  eigenes_team_split?: EigenesTeamSplit;
  spekulation?: SpekulationRow[];
  wunschkader_raw?: { targets: LegacyRawWunschkaderTarget[]; formation?: string | null; sell_list?: string[] } | null;

  // UNVERAENDERT
  wunschkader_formation: string | null;
  ligaanalyse: LigaanalyseRow[];
  ml_metrics: MlMetrics | null;
  ml_accuracy_trend: MlAccuracyTrendEntry[] | null;
  signal_thresholds: SignalThresholds;
  own_budget_exact: number | null;
  own_available_budget: number | null;
  fetched_at: string;
  [key: string]: unknown;
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: Fehler in den 5 noch nicht migrierten Tab-Dateien (erwartet — sie referenzieren noch alte, jetzt teils umbenannte Typen wie `RawWunschkaderTarget`). Notiere die Fehlerliste, sie wird in Tasks 15-19 einzeln abgearbeitet.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: PlayerRecord/TransfermarktListing/Calibration neu, RawWunschkaderTarget auf player_id umgestellt"
```

---

## Task 11: `lib/derive.ts` — atomare Formeln (Teil 1: Bewertung)

**Files:**
- Create: `frontend/src/lib/derive.ts`

**Interfaces:**
- Consumes: `PlayerRecord`, `Calibration` (aus Task 10).
- Produces: `costPerPoint`, `kForPosition`, `valuation`, `signalFor`, `statusLabel`, `estimatePrice`, `plannedPriceFor`. Konsumiert von Tasks 13, 15-19.

- [ ] **Step 1: Read the exact Python source before porting**

Vor dem Schreiben: `src/dashboard_export.py`s (Git-History, vor Task 5s Löschung — `git show HEAD~N:src/dashboard_export.py` oder die Version vor diesem Plan) `_valuation()`/`_k_per_point()`-Funktionen UND `src/player_valuation.py`s `k_for_position()` exakt nachlesen, um Fairwert-Formel korrekt zu übernehmen (nicht raten).

- [ ] **Step 2: Implement**

```ts
// frontend/src/lib/derive.ts
import type { Calibration, PlayerRecord } from "../types";

// 1:1 Port von dashboard_export.py::_k_per_point()
export function costPerPoint(marketValue: number | null, averagePoints: number | null): number | null {
  if (!marketValue || !averagePoints) return null;
  return marketValue / averagePoints;
}

// 1:1 Port von player_valuation.py::k_for_position()
export function kForPosition(calibration: Calibration | null, position: string): number | null {
  if (!calibration) return null;
  return calibration.position_k[position]?.k ?? calibration.global_k ?? null;
}

// 1:1 Port von dashboard_export.py::_valuation()
export function valuation(
  marketValue: number | null,
  averagePoints: number | null,
  position: string,
  calibration: Calibration | null
): { fairwert: number | null; signal: number | null } {
  const k = kForPosition(calibration, position);
  if (!k || !marketValue || !averagePoints) return { fairwert: null, signal: null };
  const fairwert = k * averagePoints;
  const signal = Math.round((k / (marketValue / averagePoints)) * 100) / 100;
  return { fairwert, signal };
}

export function signalFor(
  marketValue: number | null,
  averagePoints: number | null,
  position: string,
  calibration: Calibration | null
): number | null {
  return valuation(marketValue, averagePoints, position, calibration).signal;
}

// 1:1 Port von kickbase_client.py::STATUS_LABELS, finalisiert 2026-07-29
const STATUS_LABELS: Record<number, string> = { 1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau" };

export function statusLabel(statusCode: number | null): string | null {
  if (statusCode === null || statusCode === 0) return null;
  if (statusCode in STATUS_LABELS) return STATUS_LABELS[statusCode];
  return `Status-Code ${statusCode} (Bedeutung in v4-API nicht zweifelsfrei bestätigt)`;
}

// 1:1 Port von dashboard_export.py::_estimate_price() (schon in WunschkaderTab.tsx
// vorhanden, wandert nur hierher)
export function estimatePrice(marketValue: number | null): number | null {
  if (!marketValue) return null;
  return Math.round(marketValue * 1.1);
}

export function plannedPriceFor(
  target: { actual_bid?: number },
  marketValue: number | null,
  isOwn: boolean
): number | null {
  if (target.actual_bid !== undefined) return target.actual_bid;
  if (isOwn) return 0;
  return estimatePrice(marketValue);
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine neuen Fehler durch diese Datei selbst (die 5 Tab-Fehler aus Task 10 bleiben bis Tasks 15-19 bestehen)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: Bewertungs-Formeln (Signal/Fairwert/Status-Label/geplanter Preis) von Python portiert"
```

---

## Task 12: `lib/derive.ts` — Auktions-Status (Europe/Berlin, DST-sicher)

**Files:**
- Modify: `frontend/src/lib/derive.ts`

**Interfaces:**
- Produces: `nextUpdateCutoff`, `auctionLabelAndRemaining`, `auctionStatus`, `AuctionStatus`. Höchstes Risiko dieses gesamten Umbaus (kein Test-Framework, echte Zeitzonen-Logik) — siehe Verifikations-Hinweis.

- [ ] **Step 1: Read the exact Python source before porting**

Vor dem Schreiben: die gelöschten (Task 5) `_next_update_cutoff()`/`_auction_status()`/`_format_duration()` aus der Git-History exakt nachlesen (`git show <commit-vor-task-5>:src/dashboard_export.py`), insbesondere den `NEXT_MARKET_VALUE_UPDATE_HOUR`-Wert und die genaue Rundungs-/Rollover-Logik für "schon nach 22 Uhr → morgen".

- [ ] **Step 2: Implement**

```ts
// In frontend/src/lib/derive.ts ergänzen
import { formatDurationMs } from "../format";
import type { TransfermarktListing } from "../types";

const NEXT_MARKET_VALUE_UPDATE_HOUR = 22;
const NO_EXPIRY_SENTINEL_SECONDS = 9_999_999;

function berlinParts(date: Date) {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Berlin", hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const map: Record<string, number> = {};
  for (const p of dtf.formatToParts(date)) if (p.type !== "literal") map[p.type] = Number(p.value);
  return map as { year: number; month: number; day: number; hour: number; minute: number; second: number };
}

// 1:1 Port von dashboard_export.py::_next_update_cutoff() - DST-sicher ueber
// Intl.DateTimeFormat statt hartkodiertem UTC-Offset.
export function nextUpdateCutoff(now: Date): Date {
  const p = berlinParts(now);
  const localNowAsUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  let cutoffLocalAsUtc = Date.UTC(p.year, p.month - 1, p.day, NEXT_MARKET_VALUE_UPDATE_HOUR, 0, 0, 0);
  if (localNowAsUtc >= cutoffLocalAsUtc) cutoffLocalAsUtc += 24 * 3600 * 1000;
  const offsetMinutes = Math.round((localNowAsUtc - now.getTime()) / 60000);
  return new Date(cutoffLocalAsUtc - offsetMinutes * 60000);
}

// 1:1 Port von dashboard_export.py::_auction_status()
export function auctionLabelAndRemaining(
  listedAt: string | null,
  expiresAt: string | null,
  expiryIsEstimate: boolean,
  now: Date
): { label: string; remainingSeconds: number } {
  if (!expiresAt) {
    return { label: "kein Zeitlimit", remainingSeconds: NO_EXPIRY_SENTINEL_SECONDS };
  }
  const remainingMs = new Date(expiresAt).getTime() - now.getTime();
  const remainingSeconds = Math.max(Math.round(remainingMs / 1000), 0);
  if (remainingSeconds <= 0) return { label: "Frist abgelaufen", remainingSeconds: 0 };
  const suffix = expiryIsEstimate ? " (geschätzt)" : "";
  return { label: `läuft ab in ${formatDurationMs(remainingMs)}${suffix}`, remainingSeconds };
}

export interface AuctionStatus { label: string; remainingSeconds: number; urgent: boolean }

export function auctionStatus(
  listedAt: string | null,
  expiresAt: string | null,
  expiryIsEstimate: boolean,
  now: Date
): AuctionStatus {
  const { label, remainingSeconds } = auctionLabelAndRemaining(listedAt, expiresAt, expiryIsEstimate, now);
  const cutoffSeconds = (nextUpdateCutoff(now).getTime() - now.getTime()) / 1000;
  const urgent = remainingSeconds > 0 && remainingSeconds < cutoffSeconds;
  return { label, remainingSeconds, urgent };
}

export function isAffordable(price: number | null, ownAvailableBudget: number | null): boolean {
  return ownAvailableBudget !== null && price !== null && price <= ownAvailableBudget;
}
```

- [ ] **Step 3: Verify via tsc**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine neuen Fehler durch diese Datei.

- [ ] **Step 4: Manual differential check (no test framework — do this by hand)**

Sobald Task 16 (`TransfermarktTab`-Migration) läuft und echte Live-Daten verfügbar sind: für mindestens 2-3 echte Marktangebote den alten server-berechneten `auction_status`-Text (falls noch im gecachten Alt-Snapshot sichtbar) gegen den neuen `auctionStatus(...)`-Wert für dieselbe `listed_at`/`expires_at`-Kombination vergleichen. Bei Abweichung: Zeitzonen-Logik in Step 2 nachprüfen, nicht einfach den Unterschied ignorieren.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: Auktions-Status/Cutoff (Europe/Berlin, DST-sicher) von Python portiert"
```

---

## Task 13: `lib/derive.ts` — Builder-Funktionen + Budget-Plan

**Files:**
- Modify: `frontend/src/lib/derive.ts`

**Interfaces:**
- Consumes: `PlayerRecord`, `TransfermarktListing`, `RawWunschkaderTarget`, `Calibration` (Task 10), atomare Funktionen aus Tasks 11-12.
- Produces: `buildPlayerRow`, `buildTransfermarktRows`, `buildSpekulationRows`, `buildEigenesTeamSplit`, `ownerFor`, `buildAlleSpielerRows`, `BudgetPlan`, `BudgetPlanSellRow`, `buildBudgetPlan`, `isHypeGipfel`, `isNearFloor`, `roiPct`, `sellSignal`, `trendDirection`. Konsumiert von Tasks 15-19.

- [ ] **Step 1: Implement remaining atomic functions**

```ts
// In frontend/src/lib/derive.ts ergänzen
const HYPE_CHANGE_THRESHOLD = 1_500_000;
const SPEKULATION_FLOOR_PROTECTED = 1_000_000;

export function trendDirection(change7d: number | null | undefined): "flat" | "up" | "down" {
  if (change7d === null || change7d === undefined || change7d === 0) return "flat";
  return change7d > 0 ? "up" : "down";
}

export function isHypeGipfel(p: {
  market_value_change_7d?: number | null;
  market_value: number | null;
  market_value_high_92d?: number | null;
  average_points: number | null;
}): boolean {
  return Boolean(
    p.market_value_change_7d &&
      p.market_value_change_7d > HYPE_CHANGE_THRESHOLD &&
      p.market_value !== null &&
      p.market_value_high_92d === p.market_value &&
      !p.average_points
  );
}

export function isNearFloor(price: number | null): boolean {
  return Boolean(price && price < SPEKULATION_FLOOR_PROTECTED);
}

export function roiPct(mlPrediction: number | null, price: number | null): number | null {
  if (!mlPrediction || mlPrediction <= 0 || !price) return null;
  return Math.round((mlPrediction / price) * 1000) / 10;
}

export function sellSignal(
  playerId: string,
  mlPrediction: number | null | undefined,
  sellListIds: ReadonlySet<string>
): "halten" | "verkaufen" {
  return sellListIds.has(playerId) && (mlPrediction ?? 0) > 0 ? "halten" : "verkaufen";
}
```

- [ ] **Step 2: Implement `buildPlayerRow` and `buildTransfermarktRows`**

```ts
export interface PlayerRow {
  player_id: string; name: string; position: string; team_name: string | null;
  status_label: string | null; starting_rank: number | null;
  market_value: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  average_points: number | null; total_points: number | null;
  fairwert: number | null; signal: number | null; ml_prediction: number | null;
}

export function buildPlayerRow(player: PlayerRecord, calibration: Calibration | null): PlayerRow {
  const { fairwert, signal } = valuation(player.market_value, player.average_points, player.position, calibration);
  return {
    player_id: player.player_id, name: player.name, position: player.position, team_name: player.team_name,
    status_label: statusLabel(player.status_code),
    starting_rank: player.starting_rank, market_value: player.market_value,
    market_value_change_7d: player.market_value_change_7d ?? null,
    market_value_low_92d: player.market_value_low_92d ?? null,
    market_value_high_92d: player.market_value_high_92d ?? null,
    average_points: player.average_points, total_points: player.total_points ?? null,
    fairwert, signal, ml_prediction: player.ml_prediction ?? null,
  };
}

export interface TransfermarktRow extends PlayerRow {
  price: number; price_delta_pct: number | null; offering_username: string | null;
  is_system_offer: boolean; affordable: boolean;
  auction_status: string; auction_remaining_seconds: number; auction_urgent: boolean;
  auction_expires_at: string | null;
}

export function buildTransfermarktRows(
  players: Record<string, PlayerRecord>,
  listings: TransfermarktListing[],
  calibration: Calibration | null,
  ownAvailableBudget: number | null,
  now: Date
): TransfermarktRow[] {
  return listings
    .filter((l) => players[l.player_id])
    .map((l) => {
      const player = players[l.player_id];
      const base = buildPlayerRow(player, calibration);
      const { label, remainingSeconds, urgent } = auctionStatus(l.listed_at, l.expires_at, l.expiry_is_estimate, now);
      return {
        ...base,
        price: l.price, price_delta_pct: l.price_delta_pct, offering_username: l.offering_username,
        is_system_offer: l.is_system_offer,
        affordable: isAffordable(l.price, ownAvailableBudget),
        auction_status: label, auction_remaining_seconds: remainingSeconds, auction_urgent: urgent,
        auction_expires_at: l.expires_at,
      };
    });
}
```

- [ ] **Step 3: Implement `buildSpekulationRows`**

```ts
export interface SpekulationRow {
  name: string; position: string; team_name: string | null; price: number;
  roi_pct: number; average_points: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  ml_prediction: number | null; auction_status: string | null; auction_urgent: boolean;
  auction_remaining_seconds: number | null; auction_expires_at: string | null;
  is_hype_gipfel: boolean; near_floor: boolean;
}

// Nimmt TransfermarktRow[] als Input, NICHT players+listings unabhaengig -
// garantiert identische Auktions-Werte zwischen Transfermarkt- und
// Spekulation-Tab fuer dasselbe Listing (spiegelt Python's
// _build_spekulation(transfermarkt_rows) exakt).
export function buildSpekulationRows(transfermarktRows: TransfermarktRow[]): SpekulationRow[] {
  return transfermarktRows
    .filter((r) => r.is_system_offer && roiPct(r.ml_prediction, r.price) !== null)
    .map((r) => ({
      name: r.name, position: r.position, team_name: r.team_name, price: r.price,
      roi_pct: roiPct(r.ml_prediction, r.price)!,
      average_points: r.average_points, market_value_change_7d: r.market_value_change_7d,
      ml_prediction: r.ml_prediction,
      is_hype_gipfel: isHypeGipfel(r), near_floor: isNearFloor(r.price),
      auction_status: r.auction_status, auction_remaining_seconds: r.auction_remaining_seconds,
      auction_urgent: r.auction_urgent, auction_expires_at: r.auction_expires_at,
      market_value_low_92d: r.market_value_low_92d, market_value_high_92d: r.market_value_high_92d,
    }))
    .sort((a, b) => b.roi_pct - a.roi_pct);
}
```

- [ ] **Step 4: Implement `buildEigenesTeamSplit`, `ownerFor`, `buildAlleSpielerRows`**

```ts
export interface EigenesTeamRow extends PlayerRow { sell_signal?: "halten" | "verkaufen" }
export interface EigenesTeamSplit { verkaufen: EigenesTeamRow[]; bleibt: EigenesTeamRow[] }

export function buildEigenesTeamSplit(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  targets: RawWunschkaderTarget[],
  sellListIds: string[],
  calibration: Calibration | null
): EigenesTeamSplit {
  const targetIds = new Set(targets.map((t) => t.player_id));
  const sellSet = new Set(sellListIds);
  const verkaufen: EigenesTeamRow[] = [];
  const bleibt: EigenesTeamRow[] = [];
  for (const pid of ownSquadIds) {
    const player = players[pid];
    if (!player) continue;
    const row = buildPlayerRow(player, calibration);
    if (targetIds.has(pid)) {
      bleibt.push(row);
    } else {
      verkaufen.push({ ...row, sell_signal: sellSignal(pid, player.ml_prediction, sellSet) });
    }
  }
  return { verkaufen, bleibt };
}

export function ownerFor(
  playerId: string, ownSquadIds: ReadonlySet<string>, ownedBy: Record<string, string>
): string {
  if (ownSquadIds.has(playerId)) return "Eigener Kader";
  return ownedBy[playerId] ?? "Frei";
}

export interface AlleSpielerRow extends PlayerRow { owner: string }

export function buildAlleSpielerRows(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  ownedBy: Record<string, string>,
  calibration: Calibration | null
): AlleSpielerRow[] {
  const ownSet = new Set(ownSquadIds);
  return Object.values(players).map((p) => ({
    ...buildPlayerRow(p, calibration),
    owner: ownerFor(p.player_id, ownSet, ownedBy),
  }));
}
```

- [ ] **Step 5: Implement `buildBudgetPlan`**

```ts
export interface BudgetPlanSellRow { player_id: string; market_value: number | null }
export interface BudgetPlan {
  cash: number; sell_rows: BudgetPlanSellRow[]; sell_proceeds: number;
  pool: number; committed: number; remaining: number;
}

export function buildBudgetPlan(params: {
  players: Record<string, PlayerRecord>;
  ownSquadIds: Set<string>;
  sellListIds: string[];
  targets: RawWunschkaderTarget[];
  ownBudgetExact: number | null;
}): BudgetPlan {
  const { players, ownSquadIds, sellListIds, targets, ownBudgetExact } = params;
  const sellRows: BudgetPlanSellRow[] = sellListIds
    .filter((pid) => ownSquadIds.has(pid) && players[pid])
    .map((pid) => ({ player_id: pid, market_value: players[pid].market_value }));
  const sellProceeds = sellRows.reduce((sum, r) => sum + (r.market_value || 0), 0);
  const cash = ownBudgetExact || 0;
  const pool = cash + sellProceeds;
  const committed = targets.reduce((sum, t) => {
    if (t.role === "Bank/Backup-Option") return sum;
    const isOwn = ownSquadIds.has(t.player_id);
    if (isOwn) return sum;
    const marketValue = players[t.player_id]?.market_value ?? null;
    return sum + (plannedPriceFor(t, marketValue, isOwn) || 0);
  }, 0);
  return { cash, sell_rows: sellRows, sell_proceeds: sellProceeds, pool, committed, remaining: pool - committed };
}
```

- [ ] **Step 6: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine neuen Fehler durch `derive.ts` selbst.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: Builder-Funktionen (Transfermarkt/Spekulation/Eigener-Kader/Alle-Spieler/Budget) fertig"
```

---

## Task 14: `lib/wunschkaderResolve.ts` — geteilter Resolver

**Files:**
- Create: `frontend/src/lib/wunschkaderResolve.ts`

**Interfaces:**
- Consumes: `PlayerRecord`, `TransfermarktListing`, `Calibration` (Task 10), `signalFor` (Task 11).
- Produces: `ResolvedTarget`, `resolveTarget()`. Konsumiert von Task 18 (`EigenesTeamTab`) und Task 19 (`WunschkaderTab`).

- [ ] **Step 1: Implement**

```ts
// frontend/src/lib/wunschkaderResolve.ts
import type { Calibration, PlayerRecord, TransfermarktListing } from "../types";
import { signalFor } from "./derive";
import { fmtNum } from "../format";

export interface ResolvedTarget {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  average_points: number | null;
  starting_rank: number | null;
  signal: number | null;
  team_name: string | null;
  status: string;
}

// Ersetzt WunschkaderTab.tsx's alte computedFor() - jetzt EINE Quelle
// (players[player_id]) statt zwei mit Per-Feld-Fallback, da player_id ein
// verlaesslicher Join-Key ist (kein Namens-Mismatch mehr moeglich).
export function resolveTarget(
  playerId: string,
  players: Record<string, PlayerRecord>,
  ownSquadIds: ReadonlySet<string>,
  listingsByPlayerId: ReadonlyMap<string, TransfermarktListing>,
  ownedBy: Record<string, string>,
  calibration: Calibration | null
): ResolvedTarget {
  const player = players[playerId];
  const listing = listingsByPlayerId.get(playerId);

  let status: string;
  if (ownSquadIds.has(playerId)) {
    status = "Eigener Kader";
  } else if (listing) {
    const anbieter = listing.is_system_offer ? "System" : listing.offering_username ?? "?";
    status = `Markt (${anbieter}, ${fmtNum(listing.price)})`;
  } else if (ownedBy[playerId]) {
    status = `Bei ${ownedBy[playerId]}`;
  } else if (player) {
    status = "Frei";
  } else {
    status = "Nicht gefunden";
  }

  return {
    player_id: playerId,
    name: player?.name ?? `Unbekannt (${playerId})`,
    position: player?.position ?? "Sturm",
    market_value: player?.market_value ?? null,
    average_points: player?.average_points ?? null,
    starting_rank: player?.starting_rank ?? null,
    signal: player ? signalFor(player.market_value, player.average_points, player.position, calibration) : null,
    team_name: player?.team_name ?? null,
    status,
  };
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine neuen Fehler.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/wunschkaderResolve.ts
git commit -m "Neu: wunschkaderResolve.ts - geteilter player_id-Resolver fuer Wunschkader + Eigenes-Team-Watchlist"
```

---

## Task 15: `AlleSpielerTab.tsx` migrieren (erster Tab — einfachster, keine Namens-Joins)

**Files:**
- Modify: `frontend/src/components/AlleSpielerTab.tsx`

**Interfaces:**
- Consumes: `buildAlleSpielerRows` (Task 13), `data.players`/`data.own_squad_ids`/`data.owned_by`/`data.calibration` (Task 10).

- [ ] **Step 1: Replace the data source**

In `AlleSpielerTab.tsx`: ersetze

```ts
const allRows = data.alle_spieler ?? [];
```

durch

```ts
const allRows = useMemo(
  () => buildAlleSpielerRows(data.players, data.own_squad_ids, data.owned_by, data.calibration),
  [data.players, data.own_squad_ids, data.owned_by, data.calibration]
);
```

und ergänze den Import: `import { buildAlleSpielerRows, type AlleSpielerRow } from "../lib/derive";` (statt `AlleSpielerRow` aus `types.ts` zu importieren — der Typ lebt jetzt in `derive.ts`, siehe Task 13 Step 4).

- [ ] **Step 2: Rename `points_avg` references**

Alle Vorkommen von `.points_avg` in dieser Datei zu `.average_points` ändern (Spalten-Definition, Filter, Sortierung).

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine Fehler mehr aus `AlleSpielerTab.tsx` (Fehler aus den anderen 4 noch nicht migrierten Tabs bleiben erwartungsgemäß bestehen).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AlleSpielerTab.tsx
git commit -m "AlleSpielerTab: auf players-Map umgestellt (average_points, buildAlleSpielerRows)"
```

---

## Task 16: `TransfermarktTab.tsx` migrieren (Auktions-Countdown-Risiko)

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Consumes: `buildTransfermarktRows` (Task 13), `data.players`/`data.transfermarkt_listings`/`data.calibration`/`data.own_available_budget` (Task 10).
- Produces: `transfermarktRows` — wird in Task 17 (`SpekulationTab`) an `App.tsx` weitergereicht, siehe dort.

- [ ] **Step 1: Add a live clock (this tab had none before — auction status used to arrive as a finished server string)**

```ts
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
```

(Falls `SpekulationTab.tsx` bereits einen identischen `useNow`-Hook exportiert: von dort importieren statt zu duplizieren — prüfen, ob er dort schon exportiert ist, sonst hier lokal lassen bis Task 17 ihn konsolidiert.)

- [ ] **Step 2: Replace the data source**

```ts
const now = useNow(60_000);
const visible = useMemo(
  () => buildTransfermarktRows(data.players, data.transfermarkt_listings, data.calibration, data.own_available_budget, new Date(now)),
  [data.players, data.transfermarkt_listings, data.calibration, data.own_available_budget, now]
);
```

Import ergänzen: `import { buildTransfermarktRows, type TransfermarktRow } from "../lib/derive";`.

- [ ] **Step 3: Rename `points_avg`/`average_points` and remove now-unused server-string handling**

Alle direkten `r.auction_status`/`r.auction_urgent`-Text-Zuweisungen bleiben (kommen jetzt aus dem Builder statt aus Firestore) — keine Änderung an der Render-Logik nötig, nur an der Datenquelle.

- [ ] **Step 4: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine Fehler mehr aus `TransfermarktTab.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktTab: auf players-Map + clientseitigen Auktions-Status umgestellt"
```

---

## Task 17: `SpekulationTab.tsx` migrieren + `App.tsx` (gemeinsame `transfermarktRows`)

**Files:**
- Modify: `frontend/src/components/SpekulationTab.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `buildSpekulationRows` (Task 13), `TransfermarktTab`s Builder-Output (Task 16) — MUSS dieselbe `transfermarktRows`-Berechnung verwenden wie `TransfermarktTab`, nicht unabhängig neu bauen.

- [ ] **Step 1: Lift `transfermarktRows` computation into `App.tsx`**

In `App.tsx`, wo `data` geladen ist, ergänzen:

```ts
const now = useNow(60_000); // gemeinsamer Ticker fuer beide Tabs
const transfermarktRows = useMemo(
  () => data ? buildTransfermarktRows(data.players, data.transfermarkt_listings, data.calibration, data.own_available_budget, new Date(now)) : [],
  [data, now]
);
const spekulationRows = useMemo(() => buildSpekulationRows(transfermarktRows), [transfermarktRows]);
```

`useNow` aus `TransfermarktTab.tsx` hierher verschieben und in beide Tabs importieren (statt zu duplizieren) — `TransfermarktTab`/`SpekulationTab` bekommen `now`/`transfermarktRows`/`spekulationRows` jetzt als Props statt sie selbst zu berechnen.

- [ ] **Step 2: Update `SpekulationTab.tsx` to accept rows as a prop**

```ts
export default function SpekulationTab({ rows, now }: { rows: SpekulationRow[]; now: number }) {
  // bisherige Logik unveraendert, nur `rows`/`now` kommen jetzt von aussen statt aus data.spekulation
}
```

- [ ] **Step 3: Update `TransfermarktTab.tsx` similarly (Task 16 nachziehen)**

`TransfermarktTab` bekommt `rows`/`now` ebenfalls als Props statt sie selbst zu berechnen (Konsolidierung des in Task 16 lokal eingeführten `useNow`).

- [ ] **Step 4: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine Fehler mehr aus `SpekulationTab.tsx`/`App.tsx`/`TransfermarktTab.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/SpekulationTab.tsx frontend/src/components/TransfermarktTab.tsx
git commit -m "SpekulationTab: baut auf TransfermarktTabs Zeilen auf (geteilter Ticker in App.tsx)"
```

---

## Task 18: `EigenesTeamTab.tsx` migrieren

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Consumes: `buildEigenesTeamSplit` (Task 13), `resolveTarget` (Task 14), `data.players`/`data.own_squad_ids`/`data.wunschkader_targets`/`data.wunschkader_sell_list`/`data.calibration`/`data.transfermarkt_listings`/`data.owned_by` (Task 10).

- [ ] **Step 1: Replace `eigenes_team_split` and `wunschkader_watchlist` data sources**

```ts
const split = useMemo(
  () => buildEigenesTeamSplit(data.players, data.own_squad_ids, data.wunschkader_targets, data.wunschkader_sell_list ?? [], data.calibration),
  [data.players, data.own_squad_ids, data.wunschkader_targets, data.wunschkader_sell_list, data.calibration]
);

const ownSquadIdSet = useMemo(() => new Set(data.own_squad_ids), [data.own_squad_ids]);
const listingsByPlayerId = useMemo(
  () => new Map(data.transfermarkt_listings.map((l) => [l.player_id, l])),
  [data.transfermarkt_listings]
);
const watchlist = useMemo(
  () => data.wunschkader_targets
    .filter((t) => !ownSquadIdSet.has(t.player_id))
    .map((t) => resolveTarget(t.player_id, data.players, ownSquadIdSet, listingsByPlayerId, data.owned_by, data.calibration)),
  [data.wunschkader_targets, ownSquadIdSet, data.players, listingsByPlayerId, data.owned_by, data.calibration]
);
```

Import ergänzen: `import { buildEigenesTeamSplit } from "../lib/derive"; import { resolveTarget, type ResolvedTarget } from "../lib/wunschkaderResolve";`.

- [ ] **Step 2: Update `WunschkaderWatchlistCard` to render `ResolvedTarget` instead of the old `WunschkaderRow`**

`WunschkaderWatchlistCard`s Props-Typ von `WunschkaderRow` auf `ResolvedTarget` ändern — Feldnamen sind identisch (`market_value`, `average_points` statt `points_avg` — beachten!), keine weitere Logik-Änderung nötig, da `cardTone(row.status)` unverändert funktioniert (String-Vergleich, unabhängig von der Quelle).

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine Fehler mehr aus `EigenesTeamTab.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/EigenesTeamTab.tsx
git commit -m "EigenesTeamTab: auf players-Map + geteilten resolveTarget()-Resolver umgestellt"
```

---

## Task 19: `WunschkaderTab.tsx` migrieren (letzter, komplexester Tab)

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `resolveTarget` (Task 14), `buildBudgetPlan` (Task 13), `data.players`/`data.own_squad_ids`/`data.transfermarkt_listings`/`data.owned_by`/`data.calibration`/`data.wunschkader_targets`/`data.wunschkader_sell_list`/`data.own_budget_exact` (Task 10).
- Produces: Firestore-Write-Payload für `wunschkader/current` (jetzt mit `player_id` statt `name`/`position`).

- [ ] **Step 1: Replace `computedFor()` with `resolveTarget()`**

Lokale `computedFor()`-Funktion komplett entfernen, stattdessen importieren: `import { resolveTarget, type ResolvedTarget } from "../lib/wunschkaderResolve";`. Jeder bisherige Aufruf `computedFor(t.name, wunschkader, alleSpieler)` wird zu `resolveTarget(t.player_id, data.players, ownSquadIds, listingsByPlayerId, data.owned_by, data.calibration)`.

- [ ] **Step 2: Update `EditTarget` type and all name-based state**

```ts
export type EditTarget = RawWunschkaderTarget & { _uid: number }; // player_id statt name jetzt Pflichtfeld ueber RawWunschkaderTarget
```

`ownSquadNames` (Set von Namen) → `ownSquadIds = new Set(data.own_squad_ids)`. `countByClub`/`teamNameFor`: statt `t.name` jetzt `t.player_id` an `resolveTarget` reichen, `team_name` aus dem `ResolvedTarget` lesen.

- [ ] **Step 3: Fix `replaceTarget()` to keep `player_id` (the bug this whole redesign started from)**

```ts
function replaceTarget(uid: number, replacement: AlleSpielerRow) {
  setEditState((prev) =>
    prev.map((t) => {
      if (t._uid !== uid) return t;
      const { note: _note, actual_bid: _bid, ...keep } = t;
      return { ...keep, player_id: replacement.player_id };
    })
  );
  setSelected(null);
}
```

- [ ] **Step 4: Update `scoreReplacementPool`/`suggestReplacements`/`searchReplacementPool` self-exclusion**

```ts
function scoreReplacementPool(
  alleSpieler: AlleSpielerRow[],
  target: { player_id?: string; position: string; market_value: number | null; average_points: number | null }
) {
  const pool = alleSpieler.filter(
    (p) => p.position === target.position && p.player_id !== target.player_id &&
      (p.owner === "Frei" || p.owner === "Eigener Kader")
  );
  // Rest unveraendert (Distanz-Sortierung nach market_value/average_points)
}
```

- [ ] **Step 5: Rewrite `AddTargetModal` — free-text → search**

```tsx
function AddTargetModal({
  presetPosition,
  alleSpieler,
  onAdd,
  onClose,
}: {
  presetPosition: Position | null;
  alleSpieler: AlleSpielerRow[];
  onAdd: (target: { player_id: string; position: Position; role: string }) => void;
  onClose: () => void;
}) {
  const [position, setPosition] = useState<Position>(presetPosition ?? "Sturm");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AlleSpielerRow | null>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const effectivePosition = presetPosition ?? position;
  const searchTarget = { position: effectivePosition, market_value: 0, average_points: 0 };
  const results = search.trim() ? searchReplacementPool(alleSpieler, searchTarget, search.trim()) : [];

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    onAdd({
      player_id: selected.player_id,
      position: presetPosition ?? position,
      role: presetPosition ? "Starter" : "Bank/Backup-Option",
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-50">
          Ziel hinzufügen{presetPosition ? ` (${presetPosition})` : ""}
        </h3>
        {!presetPosition && (
          <select value={position} onChange={(e) => { setPosition(e.target.value as Position); setSelected(null); }}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
            {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        )}
        <input
          type="text"
          value={selected ? selected.name : search}
          onChange={(e) => { setSelected(null); setSearch(e.target.value); }}
          placeholder="Spieler suchen…"
          autoFocus
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {!selected && search.trim() && (
          <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
            {results.length ? results.map((p) => (
              <button key={p.player_id} type="button" onClick={() => { setSelected(p); setSearch(""); }}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                {p.name} ({fmtNum(p.market_value)}, Ø{fmtNum(p.average_points)})
              </button>
            )) : (
              <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                Keine Treffer (freie Spieler/eigener Kader, Position {effectivePosition}).
              </p>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
            Abbrechen
          </button>
          <button type="submit" disabled={!selected} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
            Hinzufügen
          </button>
        </div>
      </form>
    </div>
  );
}
```

Bekannte, akzeptierte Einschränkung: Suchergebnisse sind auf Frei/Eigener-Kader beschränkt (geerbt von `scoreReplacementPool`) — ein Spieler eines anderen Managers kann über dieses Formular nicht mehr als Ziel eingetragen werden. Nicht Teil dieses Umbaus zu beheben.

- [ ] **Step 6: Update `handleSave()` — Firestore write payload**

```ts
async function handleSave() {
  setSaveStatus("Speichere…");
  try {
    const updatedAt = new Date().toISOString().slice(0, 10);
    const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
    await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
    setSaveStatus("Gespeichert. Änderungen erscheinen im nächsten Pipeline-Lauf (~2h).");
  } catch (err) {
    setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
  }
}
```

(Struktur unverändert — `targets` enthält jetzt automatisch `player_id` statt `name`/`position`, da `EditTarget`/`RawWunschkaderTarget` das seit Step 2 so vorsieht.)

- [ ] **Step 7: Update `liveBudgetPlan` to use `buildBudgetPlan`**

```ts
const liveBudgetPlan = useMemo(
  () => buildBudgetPlan({
    players: data.players,
    ownSquadIds,
    sellListIds: data.wunschkader_sell_list ?? [],
    targets: editState,
    ownBudgetExact: data.own_budget_exact,
  }),
  [data.players, ownSquadIds, data.wunschkader_sell_list, editState, data.own_budget_exact]
);
```

Lokale `estimatePrice`/`plannedPriceFor`-Definitionen entfernen, aus `derive.ts` importieren.

- [ ] **Step 8: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler außer dem bekannten vorbestehenden `ui.tsx`-`ImportMeta.env`-Fehler.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: player_id statt Name (computedFor->resolveTarget, AddTargetModal auf Suche umgestellt, replaceTarget-Bug gefixt)"
```

---

## Task 20: Alte Felder aus `types.ts` entfernen (finaler Cleanup)

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:** keine neuen — reine Löschung, letzter Schritt der Migration.

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "data\.\(alle_spieler\|transfermarkt\b\|spekulation\b\|eigenes_team_split\|wunschkader_watchlist\|wunschkader_raw\)" frontend/src`
Expected: keine Treffer (alle 5 Tabs sind migriert)

- [ ] **Step 2: Remove the optional legacy fields from `DashboardSnapshot`**

Entferne aus `types.ts`: `alle_spieler?`, `transfermarkt?`, `eigenes_team_split?`, `spekulation?`, `wunschkader_raw?` sowie die jetzt komplett ungenutzten Typen `LegacyRawWunschkaderTarget`, `EigenesTeamSplit` (falls nicht mehr anderweitig gebraucht — prüfen, ob `derive.ts` seine eigene `EigenesTeamSplit` exportiert, dann ist die in `types.ts` redundant).

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler außer dem bekannten vorbestehenden `ui.tsx`-Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: optionale Alt-Felder entfernt - Migration auf players-Map abgeschlossen"
```

---

## Task 21: Alte `index.html` + `/old/`-Deploy retirieren

**Files:**
- Delete: `index.html` (Repo-Root)
- Modify: `.github/workflows/frontend-pilot.yml`

**Interfaces:** keine — reines Aufräumen, unabhängig von den anderen Tasks zeitlich einsortierbar (kann auch vor Task 1 laufen, hat keine Abhängigkeit).

- [ ] **Step 1: Delete the legacy file**

```bash
git rm index.html
```

- [ ] **Step 2: Remove the `/old/` deploy step**

In `.github/workflows/frontend-pilot.yml`, im Schritt "Assemble Pages artifact":

```yaml
      - name: Assemble Pages artifact
        run: |
          cp -r frontend/dist/. site/
```

(Zeilen `mkdir -p site/old` und `cp index.html site/old/index.html` entfernen.)

- [ ] **Step 3: Verify the workflow YAML is still valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/frontend-pilot.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/frontend-pilot.yml
git commit -m "Cleanup: alte index.html + /old/-Deploy retiriert (waere nach dem players-Map-Cutover ohnehin nicht-funktional)"
```

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle im Kontext-Abschnitt genannten Punkte (players-Map, dünne Referenz-Listen, clientseitige Ableitung, `owned_by`, Migrationsskript, atomarer Cutover, `/old/`-Retirierung) haben einen Task.
- **Platzhalter-Scan**: keine `TBD`/`implement later`/"analog zu Task N ohne Code" gefunden — jeder Code-Schritt enthält vollständigen Code.
- **Typ-Konsistenz**: `PlayerRecord`/`TransfermarktListing`/`RawWunschkaderTarget` (Task 10) werden in `derive.ts` (Tasks 11-13), `wunschkaderResolve.ts` (Task 14) und allen 5 Tab-Migrationen (Tasks 15-19) identisch benannt verwendet; `ResolvedTarget` (Task 14) wird konsistent in Tasks 18-19 verwendet.
