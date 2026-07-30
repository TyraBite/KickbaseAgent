# Gebotsvorschläge + Positions-Bedarfs-Analyse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Historische Gebotsempfehlungen (50/75/90%-Erfolgsschwellen) für Kickbase-Systemangebote im Transfermarkt- und Spekulation-Tab, plus ein league-weiter "Ligabedarf pro Position"-Kontexthinweis — beides basierend auf Design-Spec `docs/superpowers/specs/2026-07-29-gebotsvorschlaege-design.md`.

**Architecture:** Backend loggt jeden abgeschlossenen Systemkauf (aus dem ohnehin gefetchten Activity-Feed) mit seinem Marktwert-Aufschlag in eine neue, schlanke Firestore-Collection (`bid_premium_log`), inkrementell mit einem Zeiger-Dokument (kein Full-Scan). Die rohen Einträge (~100+, je ein paar Felder) wandern kompakt ins bestehende `dashboard_snapshot`-Dokument. Der Client berechnet Perzentil-Gebotsempfehlungen PRO ANFRAGE aus einer Ähnlichkeits-gewichteten Teilmenge dieser Historie (gleiche Distanzformel wie die bestehende Ersatzspieler-Suche) — keine serverseitig vorgerechneten, zu fein aufgeteilten Buckets. Der Ligabedarf pro Position ist ein separates, rein serverseitig berechnetes Aggregat (aus bereits abgerufenen Gegner-Kader-Daten, keine neuen API-Calls), das NICHT in die Gebotszahlen eingerechnet wird, sondern als eigener Kontext-Hinweis daneben steht.

**Tech Stack:** Python 3.11 (Backend, `src/`), TypeScript/React (Frontend, `frontend/src/`), Firestore, `unittest` (Backend-Tests). Kein Test-Framework im Frontend (Projekt-Konvention) — Frontend-Verifikation über `tsc --noEmit`.

## Global Constraints

- **Explizit außen vor**: Mitspieler-Angebote (Verhandlung zwischen zwei Managern) bekommen KEINE Gebotsempfehlung — nur echte Kickbase-Systemangebote (`is_system_offer`).
- **Keine serverseitig vorgerechneten Perzentile** — die Ähnlichkeits-gewichtete Berechnung läuft ausschließlich client-seitig in `derive.ts`, pro Anfrage. Der Server liefert nur die rohe Historie.
- **Framing im UI**: das ist ein historischer Vergleichswert ("bei N ähnlichen Käufen hätte X gereicht"), NIE als echte Erfolgswahrscheinlichkeit oder Garantie formuliert (echte Konkurrenzgebote sind wegen des blinden Sealed-Bid-Verfahrens grundsätzlich nie beobachtbar).
- **Ligabedarf-Aggregat fließt NICHT rechnerisch in die Gebotszahlen ein** — reiner, separat angezeigter Kontext-Hinweis, keine kalibrierte Gewichtungsformel dafür vorhanden.
- **Kein Firestore-Doppelschreiben, keine Quota-Eskalation**: Backfill der ~104 historischen Käufe ist ein einmaliger Mehraufwand (~104 zusätzliche Kickbase-Calls + Firestore-Writes); der laufende 2h-Zyklus verursacht im Normalfall NULL zusätzliche Calls (Zeiger-basiert, nur echte neue Systemkäufe seit dem letzten Lauf).
- **Backend-Tests**: `python3 -m unittest discover -s tests -v` aus dem Repo-Root, muss nach jedem Backend-Task grün bleiben.
- **Frontend-Verifikation**: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` nach jedem Frontend-Task (funktioniert ohne `npm install`).
- **Kein Push in dieser Session** — Commits bleiben lokal (Standing-Rule `NeverPushOnMain`), der Repo-Owner pusht selbst.
- **Reihenfolge**: Backend (Tasks 1-7) vor Frontend (Tasks 8-13). Task 7 (Ligabedarf-Erweiterung von `_build_ligaanalyse`) ist unabhängig von Tasks 1-6 (Bid-Premium-Pipeline) und könnte parallel laufen, ist hier aber sequenziell danach eingeordnet.
- **Bekannte Simplifikation** (siehe Task 3): `position`/`average_points` in jedem `bid_premium_log`-Eintrag sind der AKTUELLE Stand des Spielers zum Zeitpunkt des Loggens, nicht der historische Stand zum Kaufzeitpunkt (Kickbase liefert keine historischen Punkteschnitt-Daten günstig ab) — für die meisten Spieler ändert sich beides über eine Saison nur langsam, akzeptierte Näherung.
- **Defensive Fallbacks an allen neuen Frontend-Feldern zwingend** (`data.bid_premium_history ?? []`, `data.position_need ?? {}`) — Lektion aus einem echten Vorfall in dieser Session: ein Frontend-Deploy kann live gehen, bevor der Backend-Cron die neuen Snapshot-Felder je geschrieben hat (weißer Bildschirm, siehe `HANDOFF.md`). Neue Felder dürfen nie ungeprüft direkt in `.filter()`/`.map()` o.ä. verwendet werden.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `src/bid_premium.py` | NEU — Systemkauf-Filter, Marktwert-zum-Kaufzeitpunkt-Auflösung, Aufschlags-Berechnung, Orchestrierung des inkrementellen Updates |
| `src/firestore_db.py` | Erweitert um `bid_premium_log`/`bid_premium_state`-Funktionen (Muster wie `ml_prediction_log`) |
| `src/dashboard_export.py` | `export()` ruft `bid_premium.update_and_load(...)` auf, schreibt `bid_premium_history` in den Snapshot; `_build_ligaanalyse()` erweitert um `position_need`-Aggregat |
| `tests/test_bid_premium.py` | NEU — TDD für alle `bid_premium.py`-Funktionen |
| `tests/test_dashboard_export.py` | Erweitert um `BuildLigaanalyseTests` (gab's bisher nicht) |
| `frontend/src/types.ts` | Neue Wire-Typen `BidPremiumEntry`, `PositionNeed`; `DashboardSnapshot` erweitert um `bid_premium_history`/`position_need`; `SpekulationRow` bekommt `market_value` |
| `frontend/src/lib/derive.ts` | NEU: `suggestBid()` (Ähnlichkeits-gewichtete Perzentile) |
| `frontend/src/components/TransfermarktTab.tsx` | Neue Spalte "Gebotsempfehlung" + neues Detail-Modal (Tab hatte bisher keins) |
| `frontend/src/components/SpekulationTab.tsx` | Bestehendes `SpekulationDetailModal` bekommt denselben Gebotsempfehlungs-Abschnitt |

---

## Task 1: `src/bid_premium.py` — Systemkauf-Filter + Aufschlags-Berechnung

**Files:**
- Create: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Produces: `_is_system_purchase(activity: dict) -> bool`, `_compute_premium(price: float, market_value_then: float) -> float | None`, `_filter_new_system_purchases(activities: list[dict], since_dt: str | None) -> list[dict]`. Konsumiert von Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bid_premium.py
import unittest

from src.bid_premium import _compute_premium, _filter_new_system_purchases, _is_system_purchase


def _trade_activity(dt, byr="Fassii", slr=None, trp=1_000_000, pi="p1", pn="Spieler"):
    data = {"byr": byr, "trp": trp, "pi": pi, "pn": pn}
    if slr:
        data["slr"] = slr
    return {"i": f"act_{dt}", "t": 15, "dt": dt, "data": data}


class IsSystemPurchaseTests(unittest.TestCase):
    def test_trade_without_slr_is_system_purchase(self):
        self.assertTrue(_is_system_purchase(_trade_activity("2026-07-01T10:00:00Z")))

    def test_trade_with_slr_is_not_system_purchase(self):
        self.assertFalse(_is_system_purchase(_trade_activity("2026-07-01T10:00:00Z", slr="Rivale")))

    def test_non_trade_activity_type_is_not_system_purchase(self):
        self.assertFalse(_is_system_purchase({"i": "act_1", "t": 22, "dt": "2026-07-01T10:00:00Z", "data": {"bn": 500}}))


class ComputePremiumTests(unittest.TestCase):
    def test_price_above_market_value_is_positive_premium(self):
        self.assertAlmostEqual(_compute_premium(11_000_000, 10_000_000), 0.1)

    def test_price_equal_market_value_is_zero_premium(self):
        self.assertEqual(_compute_premium(10_000_000, 10_000_000), 0.0)

    def test_zero_market_value_returns_none(self):
        self.assertIsNone(_compute_premium(1_000_000, 0))

    def test_none_market_value_returns_none(self):
        self.assertIsNone(_compute_premium(1_000_000, None))


class FilterNewSystemPurchasesTests(unittest.TestCase):
    def test_without_pointer_returns_all_system_purchases(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z"),
            _trade_activity("2026-07-02T10:00:00Z", slr="Rivale"),
            _trade_activity("2026-07-03T10:00:00Z"),
        ]
        result = _filter_new_system_purchases(activities, since_dt=None)
        self.assertEqual(len(result), 2)

    def test_with_pointer_only_returns_purchases_on_or_after_pointer(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z"),
            _trade_activity("2026-07-03T10:00:00Z"),
        ]
        result = _filter_new_system_purchases(activities, since_dt="2026-07-02T00:00:00Z")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["dt"], "2026-07-03T10:00:00Z")

    def test_pointer_boundary_is_inclusive(self):
        # Inklusiv statt exklusiv gewaehlt: idempotente Firestore-Writes
        # (Doc-Id = Activity-Id) machen ein gelegentliches Re-Verarbeiten
        # der Grenz-Aktivitaet harmlos - lieber das als eine echte neue
        # Aktivitaet exakt auf dem Zeiger-Zeitstempel zu verpassen.
        activities = [_trade_activity("2026-07-02T00:00:00Z")]
        result = _filter_new_system_purchases(activities, since_dt="2026-07-02T00:00:00Z")
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.bid_premium'`)

- [ ] **Step 3: Implement**

```python
# src/bid_premium.py
"""Historische Gebotsaufschlaege fuer Kickbase-Systemangebote (freie Spieler,
von Kickbase selbst zum Kauf angeboten) - Basis fuer clientseitige
Gebotsempfehlungen (siehe frontend/src/lib/derive.ts::suggestBid()).

Kickbase-Systemangebote laufen als blindes Sealed-Bid-Verfahren: echte
Konkurrenzgebote sind waehrend der Frist nie sichtbar, nur rueckwirkend der
tatsaechliche Gewinnbetrag (ueber den Liga-Activity-Feed, Typ-15-Trade-
Eintraege ohne 'slr'/Verkaeufer-Feld = Systemkauf). Dieses Modul loggt jeden
abgeschlossenen Systemkauf mit seinem Marktwert-Aufschlag in Firestore
(bid_premium_log), inkrementell per Zeiger-Dokument (kein Full-Scan bei
jedem 2h-Lauf)."""

TRADE_ACTIVITY_TYPE = 15


def _is_system_purchase(activity: dict) -> bool:
    if activity.get("t") != TRADE_ACTIVITY_TYPE:
        return False
    return not activity.get("data", {}).get("slr")


def _compute_premium(price: float | None, market_value_then: float | None) -> float | None:
    if not market_value_then or price is None:
        return None
    return price / market_value_then - 1


def _filter_new_system_purchases(activities: list[dict], since_dt: str | None) -> list[dict]:
    """since_dt ist der ISO-Timestamp der zuletzt verarbeiteten Aktivitaet
    (Zeiger, siehe firestore_db.get_bid_premium_state) - None beim allerersten
    Lauf (dann werden ALLE bisherigen Systemkaeufe verarbeitet, das ist der
    Backfill). Grenze ist INKLUSIV (>=), nicht exklusiv - siehe Test-
    Docstring fuer die Begruendung."""
    return [
        a
        for a in activities
        if _is_system_purchase(a) and (since_dt is None or a.get("dt", "") >= since_dt)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: Systemkauf-Filter und Aufschlags-Berechnung"
```

---

## Task 2: `src/bid_premium.py` — Marktwert-zum-Kaufzeitpunkt aus der Historie

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: `get_market_value_history()`'s Response-Form `{"it": [{"dt": <Tage-seit-Epoch-Integer>, "mv": <Marktwert>}], ...}` (bestätigt in `src/kickbase_client.py::get_market_value_history`'s Docstring — `dt` dort ist NICHT ISO, sondern Tage seit 1970-01-01).
- Produces: `_days_since_epoch(iso_date: str) -> int`, `_market_value_at(history: dict, target_days: int) -> float | None`. Konsumiert von Task 3.

- [ ] **Step 1: Write the failing tests**

```python
class DaysSinceEpochTests(unittest.TestCase):
    def test_known_date_matches_kickbase_confirmed_value(self):
        # 2026-07-26 == 20660 Tage seit Epoch, bestaetigt im Docstring von
        # get_market_value_history() (27.07.2026 live gegengecheckt).
        self.assertEqual(_days_since_epoch("2026-07-26T12:00:00Z"), 20660)


class MarketValueAtTests(unittest.TestCase):
    def test_returns_value_for_exact_matching_day(self):
        history = {"it": [{"dt": 20660, "mv": 10_000_000}, {"dt": 20661, "mv": 10_100_000}]}
        self.assertEqual(_market_value_at(history, 20660), 10_000_000)

    def test_returns_none_when_day_not_in_history(self):
        history = {"it": [{"dt": 20660, "mv": 10_000_000}]}
        self.assertIsNone(_market_value_at(history, 20500))

    def test_returns_none_for_empty_history(self):
        self.assertIsNone(_market_value_at({"it": []}, 20660))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium.DaysSinceEpochTests tests.test_bid_premium.MarketValueAtTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

```python
import datetime

EPOCH = datetime.date(1970, 1, 1)


def _days_since_epoch(iso_date: str) -> int:
    date_part = iso_date.split("T")[0]
    return (datetime.date.fromisoformat(date_part) - EPOCH).days


def _market_value_at(history: dict, target_days: int) -> float | None:
    for entry in history.get("it") or []:
        if entry.get("dt") == target_days:
            return entry.get("mv")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium.DaysSinceEpochTests tests.test_bid_premium.MarketValueAtTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: Marktwert-zum-Kaufzeitpunkt aus der Tage-seit-Epoch-Historie"
```

---

## Task 3: `src/bid_premium.py` — Orchestrierung (Aktivitäten → Firestore-Einträge)

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: `token: str`, `league_id: str`, `activities: list[dict]`, `since_dt: str | None`, `players_map: dict[str, dict]` (aus `_build_players_map()`, `dashboard_export.py`), `get_market_value_history: Callable` (injiziert für Testbarkeit, Default `src.kickbase_client.get_market_value_history`).
- Produces: `build_new_entries(token, league_id, activities, since_dt, players_map, get_history=get_market_value_history) -> tuple[list[dict], str | None]` — gibt `(neue_entries, neuer_zeiger)` zurück; `neuer_zeiger` ist `None` wenn keine neuen Systemkäufe gefunden wurden (Zeiger bleibt dann unverändert). Konsumiert von Task 6.
- **Timeframe-Entscheidung**: `get_market_value_history(..., timeframe=365)` statt des Standard-`92` — Systemkäufe reichen in dieser Liga bis März 2026 zurück (~5 Monate), ein 92-Tage-Fenster von heute aus würde das nicht abdecken. Historische Käufe älter als 365 Tage werden übersprungen (Warnung), nicht rückwirkend nachgeholt — akzeptierter Kompromiss, betrifft aktuell keinen echten Kauf dieser Liga.

- [ ] **Step 1: Write the failing tests**

```python
class BuildNewEntriesTests(unittest.TestCase):
    def _players_map(self):
        return {"p1": {"player_id": "p1", "position": "Sturm", "average_points": 120}}

    def test_builds_entry_with_premium_and_current_player_attrs(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        def fake_get_history(token, league_id, player_id, timeframe=365):
            return {"it": [{"dt": target_days, "mv": 10_000_000}]}

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=fake_get_history,
        )

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["player_id"], "p1")
        self.assertEqual(entry["position"], "Sturm")
        self.assertEqual(entry["average_points_then"], 120)
        self.assertEqual(entry["market_value_then"], 10_000_000)
        self.assertAlmostEqual(entry["premium_pct"], 0.1)
        self.assertEqual(entry["purchased_at"], "2026-07-01T10:00:00Z")
        self.assertEqual(entry["activity_id"], "act_2026-07-01T10:00:00Z")
        self.assertEqual(pointer, "2026-07-01T10:00:00Z")

    def test_skips_purchase_when_player_not_in_players_map(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", pi="unknown")]

        def fake_get_history(token, league_id, player_id, timeframe=365):
            raise AssertionError("sollte fuer unbekannten Spieler nicht aufgerufen werden")

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=fake_get_history,
        )

        self.assertEqual(entries, [])
        self.assertIsNone(pointer)

    def test_single_failing_history_call_does_not_abort_others(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1"),
            _trade_activity("2026-07-02T10:00:00Z", trp=12_000_000, pi="p1"),
        ]
        target_days = _days_since_epoch("2026-07-02T10:00:00Z")
        call_count = {"n": 0}

        def flaky_get_history(token, league_id, player_id, timeframe=365):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("API down")
            return {"it": [{"dt": target_days, "mv": 10_000_000}]}

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=flaky_get_history,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["purchased_at"], "2026-07-02T10:00:00Z")
        # Zeiger geht trotz des einen Fehlers bis zur letzten VERARBEITETEN
        # Aktivitaet weiter (kein endloses Retry auf einen dauerhaft
        # fehlenden Marktwert - siehe Global Constraints).
        self.assertEqual(pointer, "2026-07-02T10:00:00Z")

    def test_no_new_activities_returns_empty_and_none_pointer(self):
        entries, pointer = build_new_entries(
            "tok", "l1", [], since_dt="2026-07-01T00:00:00Z", players_map=self._players_map(),
            get_history=lambda *a, **k: {"it": []},
        )
        self.assertEqual(entries, [])
        self.assertIsNone(pointer)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_bid_premium.BuildNewEntriesTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

```python
import sys

from src.kickbase_client import get_market_value_history

HISTORY_TIMEFRAME_DAYS = 365


def build_new_entries(
    token: str,
    league_id: str,
    activities: list[dict],
    since_dt: str | None,
    players_map: dict[str, dict],
    get_history=get_market_value_history,
) -> tuple[list[dict], str | None]:
    """Filtert neue Systemkaeufe seit since_dt, loest pro Kauf den Marktwert
    zum Kaufzeitpunkt auf und baut daraus bid_premium_log-Eintraege.
    position/average_points_then kommen bewusst aus dem AKTUELLEN players_map-
    Stand (keine guenstige historische Punkteschnitt-Quelle vorhanden, siehe
    Global Constraints in der Plan-Datei) - Naeherung, kein exakter
    historischer Wert.

    Der Zeiger wandert bis zur letzten tatsaechlich VERARBEITETEN Aktivitaet
    (auch wenn eine einzelne History-Abfrage fehlschlug) - ein dauerhaft
    fehlender Marktwert (z.B. Kauf aelter als HISTORY_TIMEFRAME_DAYS) soll
    nicht bei jedem 2h-Lauf erneut versucht werden."""
    new_purchases = _filter_new_system_purchases(activities, since_dt)
    if not new_purchases:
        return [], None

    entries = []
    last_processed_dt = None
    for activity in new_purchases:
        data = activity["data"]
        player_id = data.get("pi")
        player = players_map.get(player_id)
        last_processed_dt = activity["dt"]
        if not player:
            print(
                f"Warnung: bid_premium - Spieler {player_id!r} nicht in players_map, "
                "Kauf uebersprungen",
                file=sys.stderr,
            )
            continue

        try:
            history = get_history(token, league_id, player_id, timeframe=HISTORY_TIMEFRAME_DAYS)
        except Exception as exc:
            print(f"Warnung: bid_premium - Marktwert-Historie fuer {player_id!r} fehlgeschlagen: {exc}", file=sys.stderr)
            continue

        target_days = _days_since_epoch(activity["dt"])
        market_value_then = _market_value_at(history, target_days)
        premium_pct = _compute_premium(data.get("trp"), market_value_then)
        if premium_pct is None:
            print(
                f"Warnung: bid_premium - kein Marktwert am Kauftag fuer {player_id!r} "
                f"(Tag {target_days}), Kauf uebersprungen",
                file=sys.stderr,
            )
            continue

        entries.append({
            "activity_id": activity["i"],
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": market_value_then,
            "average_points_then": player.get("average_points"),
            "premium_pct": premium_pct,
            "purchased_at": activity["dt"],
        })

    return entries, last_processed_dt
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: build_new_entries() - Orchestrierung Aktivitaeten zu Firestore-Eintraegen"
```

---

## Task 4: `src/firestore_db.py` — `bid_premium_log`/`bid_premium_state`

**Files:**
- Modify: `src/firestore_db.py`
- Test: `tests/test_firestore_db.py`

**Interfaces:**
- Produces: `upsert_bid_premium_entries(client, entries: list[dict]) -> None` (Doc-Id = `entry["activity_id"]`, Muster wie `upsert_prediction_log_entries`), `get_bid_premium_history(client) -> list[dict]` (liest die komplette Collection — bei ~100-200 kleinen Docs unkritisch, analog `get_accuracy_daily`), `get_bid_premium_pointer(client) -> str | None`, `upsert_bid_premium_pointer(client, dt: str) -> None` (ein Dokument `bid_premium_state/current`, Feld `last_processed_dt`).

- [ ] **Step 1: Write the failing tests**

```python
# In tests/test_firestore_db.py, am Ende ergaenzen (gleiche Imports/Muster wie
# bestehende UpsertPredictionLogEntriesTests-Klasse in dieser Datei)
class UpsertBidPremiumEntriesTests(unittest.TestCase):
    def test_writes_docs_keyed_by_activity_id(self):
        client = MagicMock()
        entries = [
            {"activity_id": "act_1", "player_id": "p1", "premium_pct": 0.1},
            {"activity_id": "act_2", "player_id": "p2", "premium_pct": 0.05},
        ]

        firestore_db.upsert_bid_premium_entries(client, entries)

        batch = client.batch.return_value
        self.assertEqual(batch.set.call_count, 2)
        batch.commit.assert_called_once()

    def test_empty_entries_writes_nothing(self):
        client = MagicMock()
        firestore_db.upsert_bid_premium_entries(client, [])
        client.batch.assert_not_called()


class BidPremiumPointerTests(unittest.TestCase):
    def test_get_pointer_returns_none_when_no_doc(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        self.assertIsNone(firestore_db.get_bid_premium_pointer(client))

    def test_get_pointer_returns_stored_value(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"last_processed_dt": "2026-07-01T00:00:00Z"}

        self.assertEqual(firestore_db.get_bid_premium_pointer(client), "2026-07-01T00:00:00Z")

    def test_upsert_pointer_writes_expected_doc(self):
        client = MagicMock()
        firestore_db.upsert_bid_premium_pointer(client, "2026-07-01T00:00:00Z")
        client.collection.assert_called_with("bid_premium_state")
        client.collection.return_value.document.assert_called_with("current")
        client.collection.return_value.document.return_value.set.assert_called_once_with(
            {"last_processed_dt": "2026-07-01T00:00:00Z"}
        )


class GetBidPremiumHistoryTests(unittest.TestCase):
    def test_returns_all_docs_as_dicts(self):
        client = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {"activity_id": "act_1"}
        doc2.to_dict.return_value = {"activity_id": "act_2"}
        client.collection.return_value.stream.return_value = [doc1, doc2]

        result = firestore_db.get_bid_premium_history(client)

        self.assertEqual(result, [{"activity_id": "act_1"}, {"activity_id": "act_2"}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_firestore_db.UpsertBidPremiumEntriesTests tests.test_firestore_db.BidPremiumPointerTests tests.test_firestore_db.GetBidPremiumHistoryTests -v`
Expected: FAIL (`AttributeError`)

- [ ] **Step 3: Implement**

```python
# In src/firestore_db.py ergaenzen

def upsert_bid_premium_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Ein Dokument pro abgeschlossenem Systemkauf, Doc-Id = Activity-Id
    (macht Re-Laeufe idempotent, analog upsert_prediction_log_entries)."""
    docs = {e["activity_id"]: e for e in entries}
    _write_in_batches(client, "bid_premium_log", docs)


def get_bid_premium_history(client: firestore.Client) -> list[dict]:
    """Liest die komplette bid_premium_log-Collection - bei ~100-200 kleinen
    Dokumenten (4-5 Felder je Eintrag) unkritisch fuer die Read-Quota,
    analog get_accuracy_daily. Wird EINMAL pro Lauf gelesen, nicht pro
    Spieler/Anfrage."""
    return [doc.to_dict() for doc in client.collection("bid_premium_log").stream()]


def get_bid_premium_pointer(client: firestore.Client) -> str | None:
    """Letzte verarbeitete Activity-Id/Datum (siehe src/bid_premium.py) -
    ein einziges kleines Dokument statt eines Full-Scans der wachsenden
    bid_premium_log-Collection bei jedem 2h-Lauf."""
    doc = client.collection("bid_premium_state").document("current").get()
    return doc.to_dict().get("last_processed_dt") if doc.exists else None


def upsert_bid_premium_pointer(client: firestore.Client, dt: str) -> None:
    client.collection("bid_premium_state").document("current").set({"last_processed_dt": dt})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_firestore_db -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "firestore_db: bid_premium_log/bid_premium_state Collections"
```

---

## Task 5: `src/bid_premium.py` — Update-Einstiegspunkt (Firestore-Verdrahtung)

**Files:**
- Modify: `src/bid_premium.py`
- Test: `tests/test_bid_premium.py`

**Interfaces:**
- Consumes: `firestore_db.get_bid_premium_pointer`, `firestore_db.upsert_bid_premium_entries`, `firestore_db.upsert_bid_premium_pointer`, `firestore_db.get_bid_premium_history` (Task 4).
- Produces: `update_and_load(client, token, league_id, activities, players_map) -> list[dict]` — führt das inkrementelle Update aus (falls `client` nicht `None`, sonst No-Op) und gibt IMMER die volle (ggf. aktualisierte) Historie zurück, für den Snapshot. Konsumiert von Task 6 (`dashboard_export.py`).

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock, patch


class UpdateAndLoadTests(unittest.TestCase):
    @patch("src.bid_premium.firestore_db")
    def test_writes_new_entries_and_advances_pointer_when_found(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = None
        mock_fs.get_bid_premium_history.return_value = [{"activity_id": "act_1", "player_id": "p1"}]
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")
        client = MagicMock()

        result = update_and_load(
            client=client, token="tok", league_id="l1", activities=activities,
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "average_points": 100}},
            get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        mock_fs.upsert_bid_premium_entries.assert_called_once()
        mock_fs.upsert_bid_premium_pointer.assert_called_once_with(client, "2026-07-01T10:00:00Z")
        self.assertEqual(result, [{"activity_id": "act_1", "player_id": "p1"}])

    @patch("src.bid_premium.firestore_db")
    def test_no_new_purchases_skips_writes_but_still_returns_history(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = [{"activity_id": "act_old"}]

        result = update_and_load(
            client=MagicMock(), token="tok", league_id="l1", activities=[],
            players_map={}, get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_bid_premium_entries.assert_not_called()
        mock_fs.upsert_bid_premium_pointer.assert_not_called()
        self.assertEqual(result, [{"activity_id": "act_old"}])

    def test_none_client_is_noop_and_returns_empty(self):
        result = update_and_load(
            client=None, token="tok", league_id="l1", activities=[{"anything": True}],
            players_map={},
        )
        self.assertEqual(result, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_bid_premium.UpdateAndLoadTests -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Implement**

```python
from src import firestore_db


def update_and_load(
    client,
    token: str,
    league_id: str,
    activities: list[dict],
    players_map: dict[str, dict],
    get_history=get_market_value_history,
) -> list[dict]:
    """Zentraler Einstiegspunkt, von dashboard_export.export() aufgerufen.
    client=None (FIRESTORE_ENABLED fehlt, lokaler Testlauf) ist ein reines
    No-Op - kein bid_premium_history im Snapshot in diesem Fall."""
    if client is None:
        return []

    pointer = firestore_db.get_bid_premium_pointer(client)
    new_entries, new_pointer = build_new_entries(
        token, league_id, activities, pointer, players_map, get_history=get_history
    )
    if new_entries:
        firestore_db.upsert_bid_premium_entries(client, new_entries)
    if new_pointer:
        firestore_db.upsert_bid_premium_pointer(client, new_pointer)

    return firestore_db.get_bid_premium_history(client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_bid_premium -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bid_premium.py tests/test_bid_premium.py
git commit -m "bid_premium: update_and_load() - Firestore-Verdrahtung fuer export()"
```

---

## Task 6: `src/dashboard_export.py` — `bid_premium_history` in den Snapshot verdrahten

**Files:**
- Modify: `src/dashboard_export.py`

**Interfaces:**
- Consumes: `bid_premium.update_and_load` (Task 5). Braucht einen frischen `get_activities_feed(token, league_id)`-Call (NEUER, aber sehr billiger einzelner API-Call - siehe Hinweis unten) und `players_map` (bereits in `export()` vorhanden).
- Produces: `data["bid_premium_history"]` im Snapshot.

**Wichtiger Hinweis (Abweichung von der Spec-Formulierung)**: Die Spec sagt "Activity-Feed wird pro Lauf ohnehin gefetcht (kein neuer Call)" - das bezieht sich auf `fetcher.run()`s INTERNEN Activity-Feed-Call fuer die Budget-Schaetzung (`src/manager_budgets.py`), der aber NICHT nach aussen (an `export()`) durchgereicht wird. Diesen internen Call umzubauen, um ihn zu teilen, waere ein groesserer Eingriff in `fetcher.py`s Rueckgabe-Vertrag (betrifft auch `tests/test_fetcher.py`) fuer das Einsparen EINES einzelnen, billigen HTTP-Calls alle 2h. Diese Implementierung macht deshalb bewusst einen zweiten, eigenen `get_activities_feed()`-Call - trivialer Mehraufwand (1 Call), der Sinn der Spec (Kosten niedrig halten) bleibt gewahrt.

- [ ] **Step 1: Update the module imports and call `update_and_load` in `export()`**

In `src/dashboard_export.py`, Import ergänzen:

```python
from src import bid_premium
from src.kickbase_client import KickbaseError, get_activities_feed, get_manager_squad, get_me, login
```

In `export()`, nach der Stelle, wo `players_map` fertig gebaut ist (nach `_build_players_map(...)`-Aufruf) und vor dem finalen `data = {...}`-Dict, ergänzen:

```python
    fs_client = firestore_db.connect() if os.environ.get("FIRESTORE_ENABLED") else None
    activities = get_activities_feed(token, league_id) if fs_client else []
    bid_premium_history = bid_premium.update_and_load(fs_client, token, league_id, activities, players_map)
```

- [ ] **Step 2: Add `bid_premium_history` to the `data` dict**

```python
        "players": players_map,
        "bid_premium_history": bid_premium_history,
        "transfermarkt_listings": _build_transfermarkt_listings(market_listings),
```

- [ ] **Step 3: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün (kein bestehender Test ruft `export()` end-to-end ohne Mocks auf, siehe `_finalize_firestore_write`-Test-Konvention — falls doch ein Test bricht, `firestore_db.connect`/`get_activities_feed` dort zusätzlich mocken)

- [ ] **Step 4: Commit**

```bash
git add src/dashboard_export.py
git commit -m "dashboard_export: bid_premium_history in den Snapshot verdrahtet"
```

---

## Task 7: `_build_ligaanalyse()` — Ligabedarf pro Position

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py` (neue Klasse `BuildLigaanalyseTests` — gab es bisher nicht)

**Interfaces:**
- Consumes (Signaturänderung): `_build_ligaanalyse(token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad, players_map)` — **ersetzt** den bisherigen letzten Parameter `starting_rank_by_player_id` durch `players_map` direkt (spart eine zweite Lookup-Struktur, siehe Step 1). Rückgabe ändert sich von `list[dict]` zu `dict` mit zwei Schlüsseln: `{"rows": list[dict], "position_need": dict[str, dict]}`.
- Produces: `data["ligaanalyse"]` = `result["rows"]`, `data["position_need"]` = `result["position_need"]` (neu).

- [ ] **Step 1: Write the failing tests**

```python
# In tests/test_dashboard_export.py ergaenzen (Import von _build_ligaanalyse ergaenzen)
class BuildLigaanalyseTests(unittest.TestCase):
    def _players_map(self):
        return {
            "p1": {"player_id": "p1", "position": "Torwart", "starting_rank": 1},
            "p2": {"player_id": "p2", "position": "Abwehr", "starting_rank": 1},
            "p3": {"player_id": "p3", "position": "Abwehr", "starting_rank": 3},
            "p4": {"player_id": "p4", "position": "Mittelfeld", "starting_rank": 2},
        }

    def _ranking_row(self, user_id, name, lineup_ids, is_self=False):
        return {
            "user_id": user_id, "name": name, "season_points": 0, "matchday_points": 0,
            "team_value": 0, "season_placement": 1, "matchday_placement": 1,
            "current_lineup_player_ids": ",".join(lineup_ids),
            "recent_matchday_points": "",
        }

    def test_rival_full_coverage_at_position(self):
        # Rivale hat 1 Torwart in der Startelf, players_map zeigt ihn als
        # Stammspieler (starting_rank 1) -> Deckungsgrad 100% fuer Torwart.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p1", "mv": 10_000_000}], "nps": 1}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["position_need"]["Torwart"]["avg_coverage"], 1.0)
        self.assertEqual(result["position_need"]["Torwart"]["n_rivals"], 1)

    def test_rival_partial_coverage_at_position(self):
        # 2 Abwehrspieler in der Startelf (p2, p3), aber nur p2 ist
        # Stammspieler (starting_rank 1) -> Deckungsgrad 50%.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p2", "p3"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p2"}, {"pi": "p3"}], "nps": 2}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["position_need"]["Abwehr"]["avg_coverage"], 0.5)

    def test_coverage_is_capped_at_one(self):
        # 1 Stammspieler-Torwart im ganzen Kader, aber die Startelf enthaelt
        # ihn nur einmal -> Deckungsgrad darf trotz theoretisch "mehr
        # Stammspieler als Startelf-Plaetze" nicht ueber 1.0 gehen.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]
        players_map = {**self._players_map(), "p1b": {"player_id": "p1b", "position": "Torwart", "starting_rank": 2}}

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p1"}, {"pi": "p1b"}], "nps": 2}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=players_map,
            )

        self.assertLessEqual(result["position_need"]["Torwart"]["avg_coverage"], 1.0)

    def test_own_row_excluded_from_position_need(self):
        # is_self=True -> zaehlt NICHT in position_need (nur "Gegner"
        # relevant fuer die Markt-Konkurrenz-Einschaetzung).
        ranking_rows = [self._ranking_row("u_self", "Ich", ["p1"])]
        budget_rows = [{"user_id": "u_self", "is_own_exact": True}]

        result = _build_ligaanalyse(
            "tok", "l1", ranking_rows, budget_rows, market_listings=[],
            own_squad=[{"player_id": "p1", "market_value": 1, "starting_rank": 1}],
            players_map=self._players_map(),
        )

        self.assertEqual(result["position_need"]["Torwart"]["n_rivals"], 0)

    def test_rival_with_zero_lineup_players_at_position_excluded_from_average(self):
        # Rivale hat gar keinen Spieler dieser Position in der Startelf -
        # darf den Durchschnitt nicht per Division-durch-Null verzerren.
        ranking_rows = [self._ranking_row("u1", "Rivale", [])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [], "nps": 0}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertNotIn("Torwart", result["position_need"])

    def test_rows_key_preserves_existing_ligaanalyse_row_shape(self):
        ranking_rows = [self._ranking_row("u_self", "Ich", ["p1"])]
        budget_rows = [{"user_id": "u_self", "is_own_exact": True, "estimated_budget": 1, "available_budget": 1, "trade_count": 0}]

        result = _build_ligaanalyse(
            "tok", "l1", ranking_rows, budget_rows, market_listings=[],
            own_squad=[{"player_id": "p1", "market_value": 1, "starting_rank": 1}],
            players_map=self._players_map(),
        )

        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["name"], "Ich")
        self.assertTrue(result["rows"][0]["is_self"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export.BuildLigaanalyseTests -v`
Expected: FAIL (aktuelle Funktion hat noch die alte Signatur/Rückgabeform)

- [ ] **Step 3: Implement**

```python
POSITIONS_FOR_NEED = ("Torwart", "Abwehr", "Mittelfeld", "Sturm")


def _build_ligaanalyse(
    token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad, players_map
) -> dict:
    budgets_by_user = {b["user_id"]: b for b in manager_budget_rows}
    sell_counts: dict[str, int] = {}
    for listing in market_listings:
        uid = listing["offering_user_id"]
        if uid:
            sell_counts[uid] = sell_counts.get(uid, 0) + 1

    # Deckungsgrad(Gegner, Position) = Stammspieler dieser Position im Kader
    # (starting_rank in REGULAR_STARTING_RANKS) / tatsaechlich in der echten
    # Startelf aufgestellte Spieler dieser Position - keine Formation-
    # Annahme noetig, current_lineup_player_ids verraet das direkt. NUR
    # Gegner (nicht is_self) fliessen ein, siehe Global Constraints.
    coverage_sums: dict[str, float] = {}
    coverage_counts: dict[str, int] = {}

    rows = []
    for r in ranking_rows:
        user_id = r["user_id"]
        budget_row = budgets_by_user.get(user_id)
        is_self = bool(budget_row and budget_row["is_own_exact"])

        if is_self:
            squad_size = len(own_squad)
            squad_value = sum((p["market_value"] or 0) for p in own_squad)
            regular_count = _count_regulars(p["starting_rank"] for p in own_squad)
        else:
            try:
                squad = get_manager_squad(token, league_id, user_id)
                items = squad.get("it", [])
                squad_size = squad.get("nps") or len(items)
                squad_value = sum((item.get("mv") or 0) for item in items)
                squad_players = [players_map.get(item.get("pi")) for item in items]
                regular_count = _count_regulars(
                    p["starting_rank"] for p in squad_players if p
                )

                lineup_ids = [pid for pid in r["current_lineup_player_ids"].split(",") if pid]
                lineup_positions_count: dict[str, int] = {}
                for pid in lineup_ids:
                    player = players_map.get(pid)
                    if player:
                        lineup_positions_count[player["position"]] = lineup_positions_count.get(player["position"], 0) + 1
                regulars_by_position: dict[str, int] = {}
                for p in squad_players:
                    if p and p["starting_rank"] in REGULAR_STARTING_RANKS:
                        regulars_by_position[p["position"]] = regulars_by_position.get(p["position"], 0) + 1

                for position in POSITIONS_FOR_NEED:
                    lineup_count = lineup_positions_count.get(position, 0)
                    if lineup_count == 0:
                        continue
                    coverage = min(regulars_by_position.get(position, 0) / lineup_count, 1.0)
                    coverage_sums[position] = coverage_sums.get(position, 0.0) + coverage
                    coverage_counts[position] = coverage_counts.get(position, 0) + 1
            except KickbaseError as exc:
                print(f"Warnung: Kader von Manager {r['name']} nicht ladbar: {exc}", file=sys.stderr)
                squad_size, squad_value, regular_count = None, None, None

        rows.append(
            {
                "name": r["name"],
                "is_self": is_self,
                "season_placement": r["season_placement"],
                "season_points": r["season_points"],
                "team_value": r["team_value"],
                "matchday_points": r["matchday_points"],
                "recent_matchday_points": r["recent_matchday_points"],
                "estimated_budget": budget_row["estimated_budget"] if budget_row else None,
                "available_budget": budget_row["available_budget"] if budget_row else None,
                "trade_count": budget_row["trade_count"] if budget_row else None,
                "squad_size": squad_size,
                "squad_value": squad_value,
                "sell_count": sell_counts.get(user_id, 0),
                "regular_count": regular_count,
            }
        )
    rows.sort(key=lambda row: (row["season_placement"] is None, row["season_placement"] or 0))

    position_need = {
        position: {
            "avg_coverage": round(coverage_sums[position] / coverage_counts[position], 2),
            "n_rivals": coverage_counts[position],
        }
        for position in POSITIONS_FOR_NEED
        if coverage_counts.get(position)
    }

    return {"rows": rows, "position_need": position_need}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export.BuildLigaanalyseTests -v`
Expected: PASS

- [ ] **Step 5: Update the call site in `export()`**

```python
        ligaanalyse_result = _build_ligaanalyse(
            token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad, players_map,
        )
```

Und im `data`-Dict:

```python
        "ligaanalyse": ligaanalyse_result["rows"],
        "position_need": ligaanalyse_result["position_need"],
```

- [ ] **Step 6: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün

- [ ] **Step 7: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _build_ligaanalyse() liefert position_need (Deckungsgrad pro Position)"
```

---

## Task 8: `types.ts` — neue Wire-Typen

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `BidPremiumEntry`, `PositionNeed`; `DashboardSnapshot` erweitert um `bid_premium_history`/`position_need`; `SpekulationRow` (in `derive.ts`, siehe Task 9) bekommt zusätzlich `market_value`.

- [ ] **Step 1: Add the new wire types**

```ts
export interface BidPremiumEntry {
  player_id: string;
  position: string;
  market_value_then: number;
  average_points_then: number | null;
  premium_pct: number;
  purchased_at: string;
}

export interface PositionNeedEntry {
  avg_coverage: number;
  n_rivals: number;
}

export type PositionNeed = Record<string, PositionNeedEntry>;
```

- [ ] **Step 2: Extend `DashboardSnapshot`**

```ts
export interface DashboardSnapshot {
  // ... bestehende Felder unveraendert ...
  bid_premium_history: BidPremiumEntry[];
  position_need: PositionNeed;
  [key: string]: unknown;
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: keine neuen Fehler (nur der Fehler aus Task 9, falls diese Reihenfolge übersprungen wird — sonst 0 Fehler)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: BidPremiumEntry/PositionNeed neu, DashboardSnapshot erweitert"
```

---

## Task 9: `derive.ts` — `suggestBid()` (Ähnlichkeits-gewichtete Perzentile)

**Files:**
- Modify: `frontend/src/lib/derive.ts`
- Modify: `frontend/src/types.ts` (kleine `SpekulationRow`-Erweiterung, gehört inhaltlich zu dieser Aufgabe)

**Interfaces:**
- Consumes: `BidPremiumEntry[]` (Task 8).
- Produces: `BidSuggestion` (`{p50, p75, p90, n}` oder `null`), `suggestBid(listing, history, k=20) -> BidSuggestion | null`. Konsumiert von Tasks 10-11.

- [ ] **Step 1: Add `market_value` to `SpekulationRow` and its builder**

In `derive.ts`:

```ts
export interface SpekulationRow {
  player_id: string; name: string; position: string; team_name: string | null; price: number;
  market_value: number | null;
  roi_pct: number; average_points: number | null; market_value_change_7d: number | null;
  market_value_low_92d: number | null; market_value_high_92d: number | null;
  ml_prediction: number | null; auction_status: string | null; auction_urgent: boolean;
  auction_remaining_seconds: number | null; auction_expires_at: string | null;
  is_hype_gipfel: boolean; near_floor: boolean;
}
```

In `buildSpekulationRows()`, im Objekt-Literal ergänzen: `market_value: r.market_value,` (direkt neben `player_id: r.player_id,`).

- [ ] **Step 2: Implement `suggestBid()`**

```ts
export interface BidSuggestion { p50: number; p75: number; p90: number; n: number }

// Ael-Distanz-Formel identisch zu scoreReplacementPool() (WunschkaderTab.tsx)
// - bewusst hier separat implementiert statt importiert, da
// scoreReplacementPool() gegen AlleSpielerRow/Ersatzspieler-Suche
// spezialisiert ist und komponentenlokal bleiben soll; die Formel selbst
// ist aber identisch (Marktwert- + Punkteschnitt-Distanz, normalisiert).
export function suggestBid(
  listing: { position: string; market_value: number | null; average_points: number | null },
  history: BidPremiumEntry[],
  k = 20
): BidSuggestion | null {
  const samePosition = history.filter((h) => h.position === listing.position);
  if (samePosition.length === 0) return null;

  const mv = listing.market_value || 0;
  const pts = listing.average_points || 0;
  const ranked = samePosition
    .map((h) => {
      const mvDist = mv ? Math.abs(h.market_value_then - mv) / mv : 0;
      const ptsDist = pts ? Math.abs((h.average_points_then ?? 0) - pts) / pts : 0;
      return { ...h, distance: mvDist + ptsDist };
    })
    .sort((a, b) => a.distance - b.distance)
    .slice(0, k);

  const premiums = ranked.map((r) => r.premium_pct).sort((a, b) => a - b);
  const pct = (p: number) => premiums[Math.floor(p * (premiums.length - 1))];

  return {
    p50: Math.round(mv * (1 + pct(0.5))),
    p75: Math.round(mv * (1 + pct(0.75))),
    p90: Math.round(mv * (1 + pct(0.9))),
    n: ranked.length,
  };
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 4: Manual sanity check (kein Test-Framework im Frontend)**

Nach Abschluss von Task 10/11 (echte Anzeige): mit den realen Daten aus `bid_premium_history` (nach dem ersten Produktions-Lauf, siehe Task 14) für 2-3 echte Transfermarkt-Angebote den `n`-Wert und die Schwellen auf Plausibilität prüfen (z.B. `p50` sollte nahe am Marktwert liegen, `p90` deutlich darüber, `n` sollte bei gängigen Positionen zweistellig sein).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/derive.ts frontend/src/types.ts
git commit -m "derive.ts: suggestBid() - Aehnlichkeits-gewichtete Gebotsempfehlung"
```

---

## Task 10: `TransfermarktTab.tsx` — Spalte + Detail-Modal

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Consumes: `suggestBid` (Task 9), `data.bid_premium_history`/`data.position_need` (Task 8).

- [ ] **Step 1: Add the compact column**

Import ergänzen: `import { suggestBid } from "../lib/derive";`. Neue Spalte in `columns` (vor der `auction`-Spalte einfügen):

```ts
    {
      key: "bid_suggestion",
      label: "Gebotsempfehlung",
      align: "right",
      sortValue: (r) => (r.is_system_offer ? suggestBid(r, data.bid_premium_history ?? [])?.p75 ?? null : null),
      render: (r) => {
        if (!r.is_system_offer) return <span className="text-slate-400 dark:text-slate-500">n/v</span>;
        const suggestion = suggestBid(r, data.bid_premium_history ?? []);
        if (!suggestion) return <span className="text-slate-400 dark:text-slate-500">n/v</span>;
        return `${fmtNum(suggestion.p75)} (n=${suggestion.n})`;
      },
    },
```

- [ ] **Step 2: Add row-click state and detail modal**

Im Komponenten-Body ergänzen: `const [selected, setSelected] = useState<TransfermarktRow | null>(null);` (Import `useState` bereits vorhanden). `<SortableTable ... onRowClick={setSelected} />` ergänzen (Prop existiert schon, siehe `SpekulationTab.tsx`s Nutzung). Am Ende der Komponente, vor dem schließenden `</div>`:

```tsx
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
```

- [ ] **Step 3: Implement `TransfermarktDetailModal`**

Neue Funktion am Ende der Datei, Muster 1:1 von `SpekulationDetailModal` (`SpekulationTab.tsx`) übernommen:

```tsx
import { useEffect } from "react";
import type { BidPremiumEntry, PositionNeed } from "../types";

function TransfermarktDetailModal({
  row,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: TransfermarktRow;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const suggestion = row.is_system_offer ? suggestBid(row, bidHistory) : null;
  const need = positionNeed[row.position];

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <Row label="Preis">{fmtNum(row.price)}</Row>
          {row.is_system_offer ? (
            suggestion ? (
              <>
                <Row label="Gebot für ~50%">{fmtNum(suggestion.p50)}</Row>
                <Row label="Gebot für ~75%">{fmtNum(suggestion.p75)}</Row>
                <Row label="Gebot für ~90%">{fmtNum(suggestion.p90)}</Row>
                <Row label="Basis">{suggestion.n} ähnliche historische Käufe</Row>
              </>
            ) : (
              <Row label="Gebotsempfehlung">Keine historischen Vergleichskäufe dieser Position</Row>
            )
          ) : (
            <Row label="Gebotsempfehlung">Nur für Kickbase-Systemangebote verfügbar</Row>
          )}
          {need && <Row label={`Ligabedarf ${row.position}`}>{Math.round(need.avg_coverage * 100)}% Deckung bei {need.n_rivals} Gegnern</Row>}
        </dl>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Historischer Vergleichswert aus abgeschlossenen Käufen dieser Liga — keine Garantie, echte Konkurrenzgebote sind beim blinden Verfahren nie sichtbar.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktTab: Gebotsempfehlungs-Spalte + neues Detail-Modal"
```

---

## Task 11: `SpekulationTab.tsx` — Gebotsempfehlung im bestehenden Detail-Modal

**Files:**
- Modify: `frontend/src/components/SpekulationTab.tsx`

**Interfaces:**
- Consumes: `suggestBid` (Task 9). `SpekulationTab` bekommt zwei neue Props: `bidHistory: BidPremiumEntry[]`, `positionNeed: PositionNeed` (von `App.tsx` durchgereicht, siehe Task 12).

- [ ] **Step 1: Extend the component's props and pass them to the detail modal**

```tsx
import { suggestBid } from "../lib/derive";
import type { BidPremiumEntry, PositionNeed } from "../types";

export default function SpekulationTab({
  rows,
  now,
  bidHistory,
  positionNeed,
}: {
  rows: SpekulationRow[];
  now: number;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
}) {
```

Am Ende der Komponente, den bestehenden Aufruf ergänzen:

```tsx
      {selected && (
        <SpekulationDetailModal row={selected} now={now} bidHistory={bidHistory} positionNeed={positionNeed} onClose={() => setSelected(null)} />
      )}
```

- [ ] **Step 2: Extend `SpekulationDetailModal`**

```tsx
function SpekulationDetailModal({
  row,
  now,
  bidHistory,
  positionNeed,
  onClose,
}: {
  row: SpekulationRow;
  now: number;
  bidHistory: BidPremiumEntry[];
  positionNeed: PositionNeed;
  onClose: () => void;
}) {
  // ... bestehender useEffect-Escape-Handler unveraendert ...
  const suggestion = suggestBid(row, bidHistory);
  const need = positionNeed[row.position];

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        {/* ... bestehender Header + bestehende Row-Elemente unveraendert ... */}
        <dl className="space-y-2 text-sm">
          {/* ... bestehende Rows (ML-Prognose/Rendite%/Preis/Trend 7T/Auktion/Tief/Hoch) unveraendert ... */}
          {suggestion ? (
            <>
              <Row label="Gebot für ~50%">{fmtNum(suggestion.p50)}</Row>
              <Row label="Gebot für ~75%">{fmtNum(suggestion.p75)}</Row>
              <Row label="Gebot für ~90%">{fmtNum(suggestion.p90)}</Row>
              <Row label="Basis">{suggestion.n} ähnliche historische Käufe</Row>
            </>
          ) : (
            <Row label="Gebotsempfehlung">Keine historischen Vergleichskäufe dieser Position</Row>
          )}
          {need && <Row label={`Ligabedarf ${row.position}`}>{Math.round(need.avg_coverage * 100)}% Deckung bei {need.n_rivals} Gegnern</Row>}
        </dl>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Historischer Vergleichswert — keine Garantie, echte Konkurrenzgebote sind beim blinden Verfahren nie sichtbar.
        </p>
      </div>
    </div>
  );
}
```

(Der `fmtNum`-Import ist in dieser Datei bereits vorhanden.)

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: Fehler in `App.tsx` (Task 12 noch nicht gemacht — `SpekulationTab` bekommt jetzt Pflicht-Props, die `App.tsx` noch nicht reicht). Das ist erwartet, wird in Task 12 aufgelöst.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SpekulationTab.tsx
git commit -m "SpekulationTab: Gebotsempfehlung + Ligabedarf im bestehenden Detail-Modal"
```

---

## Task 12: `App.tsx` — neue Props durchreichen

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `data.bid_premium_history`, `data.position_need`.

- [ ] **Step 1: Pass the new fields to `SpekulationTab`**

Am Aufruf von `<SpekulationTab ... />` ergänzen:

```tsx
<SpekulationTab rows={spekulationRows} now={now} bidHistory={data.bid_premium_history ?? []} positionNeed={data.position_need ?? {}} />
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "App.tsx: bid_premium_history/position_need an SpekulationTab durchgereicht"
```

---

## Task 13: Backfill gegen Produktion + Live-Verifikation (manuelle Schritte, kein Code)

**Files:** keine (operative Schritte gegen die echte Produktionsumgebung)

- [ ] **Step 1**: Backend-Commits (Tasks 1-7) und Frontend-Commits (Tasks 8-12) pushen (User macht das selbst).
- [ ] **Step 2**: `gh workflow run dashboard.yml` (Light reicht, `bid_premium.update_and_load` läuft in beiden Modi) manuell anstoßen — erster Lauf ohne Zeiger verarbeitet automatisch ALLE ~104 historischen Systemkäufe (Backfill).
- [ ] **Step 3**: `gh run watch <run-id> --exit-status` — Erfolg abwarten. Bei diesem ersten Lauf werden ~104 zusätzliche `get_market_value_history()`-Calls erwartet — Laufzeit wird entsprechend länger sein als gewohnt, das ist normal.
- [ ] **Step 4**: Live prüfen: Firestore `bid_premium_log`-Collection hat ~100+ Dokumente, `bid_premium_state/current` hat einen `last_processed_dt`-Wert, `dashboard_snapshot/latest` hat ein `bid_premium_history`-Array + `position_need`-Objekt.
- [ ] **Step 5**: `gh workflow run dashboard.yml` ein zweites Mal anstoßen — sollte diesmal SCHNELL laufen (0 neue Systemkäufe seit dem ersten Lauf, kein Backfill mehr).
- [ ] **Step 6**: Echter Browser-Test durch den User (Sandbox kann kein `npm run dev`): Transfermarkt-Tab → neue Spalte zeigt Werte bei System-Angeboten, `n/v` bei Mitspieler-Angeboten; Zeile anklicken → Detail-Modal mit allen 3 Schwellen + Ligabedarf. Spekulation-Tab → Detail-Modal (Karte oder Zeile anklicken) zeigt denselben Abschnitt.

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: Datenpipeline (Backfill+Incremental+Speicherung), client-seitige Perzentil-Berechnung, UI-Platzierung (beide Tabs), Positions-Bedarfs-Analyse — alle Abschnitte der Spec haben einen Task. "Out of Scope"-Punkte (Budget-Cross-Check, Pro-Gegner-Detailansicht) bewusst nicht eingeplant.
- **Platzhalter-Scan**: keine TBD/"add validation"/"analog zu Task N ohne Code" gefunden.
- **Typ-Konsistenz**: `BidPremiumEntry`/`PositionNeed`/`BidSuggestion` durchgängig gleich benannt zwischen Tasks 8-12. `_build_ligaanalyse()`s neue Signatur (`players_map` statt `starting_rank_by_player_id`, Rückgabe `dict` statt `list`) ist in Task 7 vollständig, inkl. Call-Site-Update.
- **Abweichung von der Spec explizit dokumentiert**: zweiter `get_activities_feed()`-Call statt Wiederverwendung von `fetcher.run()`s internem Call (Task 6), `average_points_then`/`position` als aktuelle statt historische Werte (Global Constraints), `timeframe=365` statt Standard-`92` bei `get_market_value_history()` (Task 3).
