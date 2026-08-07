# Manager-Budgets: Exakte Achievement-Erkennung statt Punkte-Skalierung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Für Liga-Manager außer dir selbst wird der Achievement-Bonus-Anteil in der Budget-Schätzung (`manager_budgets.py`, sichtbar im Ligaanalyse-Tab) für bestimmte, live verifizierte Achievement-Typen exakt statt per Punkte-Verhältnis geschätzt.

**Architecture:** Achievement-Rewards fließen granular (pro Achievement-Id, nicht mehr vorsummiert) von `fetcher.py` in `manager_budgets.estimate_all()`. Dort entscheidet eine neue, gegen echte Kickbase-Responses verifizierte Zuordnungstabelle (`_EXACT_ACHIEVEMENTS`) pro Achievement-Id, ob sie anhand bereits vorhandener Manager-Daten (Teamwert, Trade-Count, Liga-Größe) exakt prüfbar ist. Ist sie es: `ac * er` exakt gutschreiben oder nicht. Ist sie es nicht (z. B. profit-basierte Achievements ohne Kauf/Verkaufs-Ledger je Spieler): unverändert die bisherige Punkte-Verhältnis-Skalierung.

**Tech Stack:** Python (`src/manager_budgets.py`, `src/fetcher.py`), `unittest`/`python -m pytest`.

## Global Constraints

- Tests immer mit `python -m pytest tests/ -v` ausführen (nicht bares `pytest` — `tests/` hat kein `__init__.py`).
- Strukturell gleiche Parameter (hier: die drei Metrik-Inputs `team_value`/`trade_count`/`league_size`) werden als Keyword-Argument übergeben.
- Modulinterne Funktionen bekommen einen führenden Unterstrich (`_exact_achievement_hit`, `_fetch_achievement_rewards`).
- Keine Bedeutung erfinden, die nicht verifiziert ist — `_EXACT_ACHIEVEMENTS` darf nur Ids enthalten, deren Name/Beschreibung/Schwelle live gegen `get_achievement_reward()` bestätigt wurden (siehe Recherche unten). Jeder Eintrag bekommt einen Kommentar mit der echten Beschreibung.
- Commits: nur `git commit -m "..."`, kein Co-Authored-By-Trailer.
- Funktionale Änderung in `src/`/`tests/` → läuft über echten PR (`gh pr create` + `gh pr merge --auto --squash`), kein Direkt-Push auf `main`.

**Verifizierte Grundlage (live gegen Kickbase-API geprüft, 2026-08-07):**
- Achievement-Feed-Einträge (Typ 26) und `get_achievement_reward()` sind strikt auf den Token-Owner beschränkt (ein `managerId`-Query-Param wird stillschweigend ignoriert, `/managers/{id}/achievements` → 404) — andere Manager sind nur über die hier gebaute Ableitung erreichbar, nie direkt.
- `ac` ist bei allen bisher beobachteten Achievements `1` (einmalig auslösende Achievements), `er` ist die Belohnung pro Treffer und je Achievement-Id ligaweit identisch.
- Fünf Achievement-Ids sind anhand bereits vorhandener Manager-Daten exakt prüfbar:
  - `400` "Team value bronze" — *"Own a team with a value of 125 mil."* → `team_value >= 125_000_000`
  - `401` "Team value silver" — *"Own a team with a value of 150 mil."* → `team_value >= 150_000_000`
  - `500` "First deal" — *"Sell or buy 1 player during a season"* → `trade_count >= 1`
  - `600` "Kreisliga" — *"Your league has at least 3 managers"* → `league_size >= 3`
  - `601` "Regionalliga" — *"Your league has at least 6 managers"* → `league_size >= 6`
- `700` "The right touch" (*"Yield 1 mil profit with a player. No transfers between managers."*) ist NICHT exakt prüfbar (bräuchte ein Kauf/Verkaufs-Ledger je Spieler und Manager, das aktuell nicht existiert) — bleibt bei der bisherigen Punkte-Verhältnis-Schätzung.
- Grenze: das deckt nur Achievement-Ids ab, die der eigene Account bereits selbst freigeschaltet hat (nur dann kennen wir Name/Schwelle/Reward). Höhere, noch unerreichte Tiers bleiben unsichtbar und fallen weiter unter die Schätzung.

---

## Task 1: `_exact_achievement_hit()` in `manager_budgets.py`

**Files:**
- Modify: `src/manager_budgets.py` (neue Konstante + neue Funktion, nach `_scale_achievement_bonus`, vor `_overdraft`)
- Test: `tests/test_manager_budgets.py` (neue Klasse `ExactAchievementHitTests`)

**Interfaces:**
- Produces: `_EXACT_ACHIEVEMENTS: dict[int, tuple[str, float]]`, `_exact_achievement_hit(achievement_id: int, *, team_value, trade_count: int, league_size: int) -> bool | None` — `None` heißt "kein verifizierter Typ, Aufrufer muss auf die Punkte-Skalierung zurückfallen".

- [ ] **Step 1: Write the failing tests**

Füge in `tests/test_manager_budgets.py` nach der Klasse `ScaleAchievementBonusTests` folgende neue Klasse ein:

```python
class ExactAchievementHitTests(unittest.TestCase):
    def test_unknown_id_returns_none(self):
        self.assertIsNone(
            mb._exact_achievement_hit(999, team_value=200_000_000, trade_count=5, league_size=8)
        )

    def test_team_value_threshold_hit(self):
        self.assertTrue(
            mb._exact_achievement_hit(400, team_value=125_000_000, trade_count=0, league_size=8)
        )

    def test_team_value_threshold_miss(self):
        self.assertFalse(
            mb._exact_achievement_hit(401, team_value=149_999_999, trade_count=0, league_size=8)
        )

    def test_team_value_none_is_treated_as_zero_not_a_crash(self):
        self.assertFalse(
            mb._exact_achievement_hit(400, team_value=None, trade_count=0, league_size=8)
        )

    def test_trade_count_threshold_hit(self):
        self.assertTrue(
            mb._exact_achievement_hit(500, team_value=0, trade_count=1, league_size=8)
        )

    def test_trade_count_threshold_miss(self):
        self.assertFalse(
            mb._exact_achievement_hit(500, team_value=0, trade_count=0, league_size=8)
        )

    def test_league_size_threshold_hit(self):
        self.assertTrue(
            mb._exact_achievement_hit(601, team_value=0, trade_count=0, league_size=6)
        )

    def test_league_size_threshold_miss(self):
        self.assertFalse(
            mb._exact_achievement_hit(601, team_value=0, trade_count=0, league_size=5)
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_manager_budgets.py -v -k ExactAchievementHit`
Expected: FAIL — `AttributeError: module 'src.manager_budgets' has no attribute '_exact_achievement_hit'`

- [ ] **Step 3: Write minimal implementation**

Füge in `src/manager_budgets.py` nach `_scale_achievement_bonus` (vor `def _overdraft`) ein:

```python
# Verifiziert 2026-08-07 gegen echte get_achievement_reward()-Responses des
# eigenen Accounts (Name/Beschreibung/Schwelle live geprueft). Nur Ids, die
# der eigene Account bereits selbst freigeschaltet hat, sind hier bekannt -
# hoehere, noch unerreichte Tiers bleiben unsichtbar und fallen weiter unter
# _scale_achievement_bonus.
_EXACT_ACHIEVEMENTS: dict[int, tuple[str, float]] = {
    400: ("team_value", 125_000_000),  # "Own a team with a value of 125 mil."
    401: ("team_value", 150_000_000),  # "Own a team with a value of 150 mil."
    500: ("trade_count", 1),  # "Sell or buy 1 player during a season"
    600: ("league_size", 3),  # "Your league has at least 3 managers"
    601: ("league_size", 6),  # "Your league has at least 6 managers"
}


def _exact_achievement_hit(
    achievement_id: int, *, team_value, trade_count: int, league_size: int
) -> bool | None:
    """Prueft, ob ein Manager ein verifiziertes Achievement (siehe
    _EXACT_ACHIEVEMENTS) anhand bereits vorhandener Daten exakt erreicht hat.
    None heisst: kein verifizierter Typ, der Aufrufer muss auf
    _scale_achievement_bonus zurueckfallen (z.B. profit-basierte Achievements
    ohne Kauf/Verkaufs-Ledger je Spieler)."""
    entry = _EXACT_ACHIEVEMENTS.get(achievement_id)
    if entry is None:
        return None
    metric, threshold = entry
    if metric == "team_value":
        return (team_value or 0) >= threshold
    if metric == "trade_count":
        return trade_count >= threshold
    return league_size >= threshold
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_manager_budgets.py -v -k ExactAchievementHit`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git checkout -b manager-budgets-exact-achievements
git add src/manager_budgets.py tests/test_manager_budgets.py
git commit -m "Add exact achievement-threshold check for verified achievement ids"
```

---

## Task 2: `_exact_achievement_hit()` in `estimate_all()` verdrahten

**Files:**
- Modify: `src/manager_budgets.py:136-202` (`estimate_all`)
- Test: `tests/test_manager_budgets.py` (`EstimateAllTests` erweitern + bestehende Aufrufe migrieren)

**Interfaces:**
- Consumes: `_exact_achievement_hit()` und `_EXACT_ACHIEVEMENTS` aus Task 1; `_scale_achievement_bonus()` (unveraendert, bereits vorhanden).
- Produces: `estimate_all(..., achievement_rewards: list[dict])` — **ersetzt** den bisherigen Parameter `achievement_bonus_total: float`. Jeder Eintrag in `achievement_rewards` hat die Form `{"id": int, "ac": float, "er": float}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_manager_budgets.py` müssen ALLE bestehenden Aufrufe von `mb.estimate_all(...)` in `EstimateAllTests` von `achievement_bonus_total=0` auf `achievement_rewards=[]` umgestellt werden (4 Stellen: `test_own_row_is_synced_to_exact_budget_not_estimate`, `test_other_manager_is_marked_as_estimate`, `test_trade_count_reflects_participation`, `test_sorted_by_available_budget_descending`). Ersetze in jedem der vier Aufrufe die Zeile `achievement_bonus_total=0,` durch `achievement_rewards=[],`.

Füge danach zwei neue Tests in `EstimateAllTests` hinzu:

```python
    def test_exact_achievement_credited_only_to_managers_who_hit_threshold(self):
        # Bobetinho (team_value=60_000_000) erreicht 125 Mio nicht, Tyra
        # (team_value=80_000_000 im setUp) ebenfalls nicht - beide Zeilen
        # duerfen den exakten Bonus NICHT bekommen.
        results = mb.estimate_all(
            activities=[],
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_rewards=[{"id": 400, "ac": 1, "er": 100_000}],
        )
        other_row = next(r for r in results if r["name"] == "Bobetinho")
        self.assertEqual(other_row["estimated_budget"], 50_000_000)

    def test_exact_achievement_credited_when_threshold_met(self):
        ranking_rows = [
            {"user_id": "1", "name": "Tyra", "team_value": 80_000_000, "season_points": 100},
            {"user_id": "2", "name": "Bobetinho", "team_value": 200_000_000, "season_points": 50},
        ]
        results = mb.estimate_all(
            activities=[],
            ranking_rows=ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_rewards=[{"id": 400, "ac": 1, "er": 100_000}],
        )
        other_row = next(r for r in results if r["name"] == "Bobetinho")
        self.assertEqual(other_row["estimated_budget"], 50_000_000 + 100_000)

    def test_unverified_achievement_id_still_falls_back_to_points_scaling(self):
        # Id 700 ist absichtlich NICHT in _EXACT_ACHIEVEMENTS - muss weiter
        # ueber season_points-Verhaeltnis skaliert werden (bestehendes
        # Verhalten, unveraendert).
        results = mb.estimate_all(
            activities=[],
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_rewards=[{"id": 700, "ac": 1, "er": 100_000}],
        )
        other_row = next(r for r in results if r["name"] == "Bobetinho")
        # own_points=100, target_points=50 -> 50% skaliert
        self.assertEqual(other_row["estimated_budget"], 50_000_000 + 50_000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_manager_budgets.py -v -k EstimateAll`
Expected: FAIL — `TypeError: estimate_all() got an unexpected keyword argument 'achievement_rewards'` (bzw. `missing ... 'achievement_bonus_total'` für die migrierten Altfälle, bis Step 3 umgesetzt ist)

- [ ] **Step 3: Write minimal implementation**

In `src/manager_budgets.py`, Funktion `estimate_all`: Signatur und Achievement-Block ändern.

Signatur (Zeile ~144, `achievement_bonus_total: float,` ersetzen durch):
```python
    achievement_rewards: list[dict],
```

Docstring-Absatz zu `achievement_bonus_total` ersetzen durch:
```python
    achievement_rewards ist die Liste der {id, ac, er}-Dicts aus
    fetcher._fetch_achievement_rewards() fuer alle deduplizierten
    Achievement-Ids des EIGENEN Users. Fuer Ids in _EXACT_ACHIEVEMENTS wird
    der Bonus pro Manager exakt anhand vorhandener Daten geprueft, alle
    anderen werden weiterhin nach Punkte-Verhaeltnis skaliert.
```

Den bisherigen Block
```python
    own_points = next(
        (row.get("season_points") for row in ranking_rows if row.get("name") == own_name),
        None,
    )
    for row in ranking_rows:
        name = row.get("name")
        if not name or name not in budgets:
            continue
        budgets[name] += _scale_achievement_bonus(
            achievement_bonus_total, own_points, row.get("season_points")
        )
```
ersetzen durch:
```python
    league_size = len(known_names)
    own_points = next(
        (row.get("season_points") for row in ranking_rows if row.get("name") == own_name),
        None,
    )
    for row in ranking_rows:
        name = row.get("name")
        if not name or name not in budgets:
            continue
        for reward in achievement_rewards:
            ac = reward.get("ac") or 0
            er = reward.get("er") or 0
            hit = _exact_achievement_hit(
                reward.get("id"),
                team_value=row.get("team_value"),
                trade_count=trade_counts.get(name, 0),
                league_size=league_size,
            )
            if hit is None:
                budgets[name] += _scale_achievement_bonus(ac * er, own_points, row.get("season_points"))
            elif hit:
                budgets[name] += ac * er
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_manager_budgets.py -v`
Expected: PASS (alle Tests der Datei, inkl. der 4 migrierten und 3 neuen)

- [ ] **Step 5: Commit**

```bash
git add src/manager_budgets.py tests/test_manager_budgets.py
git commit -m "Wire exact achievement check into estimate_all, keep scaling as fallback"
```

---

## Task 3: `fetcher.py` — granulare Achievement-Rewards statt vorsummiertem Total

**Files:**
- Modify: `src/fetcher.py:260-276` (`_fetch_achievement_bonus_total` → `_fetch_achievement_rewards`), `src/fetcher.py:431-446` (Aufrufstelle)
- Test: `tests/test_fetcher.py` (neue Klasse `FetchAchievementRewardsTests`)

**Interfaces:**
- Consumes: `get_achievement_reward(token, league_id, achievement_id)` (unveraendert, aus `src.kickbase_client`), `KickbaseError` (unveraendert).
- Produces: `_fetch_achievement_rewards(token: str, league_id: str, achievement_ids: set) -> list[dict]`, jedes Element `{"id": achievement_id, "ac": number, "er": number}`.

- [ ] **Step 1: Write the failing tests**

Füge in `tests/test_fetcher.py` am Ende der Datei (nach der letzten bestehenden Test-Klasse) hinzu, und erweitere den Import-Block oben um `_fetch_achievement_rewards`:

```python
from src.fetcher import (
    _apply_market_value_history,
    _apply_or_reuse_market_value_history,
    _compute_expiry,
    _fetch_achievement_rewards,
    _market_item_to_row,
    _squad_item_to_row,
)
```

```python
class FetchAchievementRewardsTests(unittest.TestCase):
    @patch("src.fetcher.get_achievement_reward")
    def test_returns_id_ac_er_per_achievement(self, mock_get):
        mock_get.side_effect = lambda token, league_id, achievement_id: {
            400: {"t": 400, "ac": 1, "er": 100_000},
            500: {"t": 500, "ac": 1, "er": 100_000},
        }[achievement_id]

        rewards = _fetch_achievement_rewards("tok", "l1", {400, 500})

        self.assertEqual(
            sorted(rewards, key=lambda r: r["id"]),
            [{"id": 400, "ac": 1, "er": 100_000}, {"id": 500, "ac": 1, "er": 100_000}],
        )

    @patch("src.fetcher.get_achievement_reward")
    def test_skips_id_on_failed_call_without_raising(self, mock_get):
        from src.kickbase_client import KickbaseError

        def side_effect(token, league_id, achievement_id):
            if achievement_id == 400:
                raise KickbaseError("boom")
            return {"t": achievement_id, "ac": 1, "er": 50_000}

        mock_get.side_effect = side_effect

        rewards = _fetch_achievement_rewards("tok", "l1", {400, 601})

        self.assertEqual(rewards, [{"id": 601, "ac": 1, "er": 50_000}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetcher.py -v -k FetchAchievementRewards`
Expected: FAIL — `ImportError: cannot import name '_fetch_achievement_rewards' from 'src.fetcher'`

- [ ] **Step 3: Write minimal implementation**

In `src/fetcher.py`, Funktion `_fetch_achievement_bonus_total` (Zeile 260-276) komplett ersetzen durch:

```python
def _fetch_achievement_rewards(token: str, league_id: str, achievement_ids: set) -> list[dict]:
    """Fragt jede (deduplizierte) Achievement-Id einmal ab. Ein einzelner
    fehlgeschlagener Call darf die Budget-Schaetzung nicht komplett
    verhindern, daher try/except pro Id, analog _apply_market_value_history.
    Gibt pro Id ein Dict {id, ac, er} zurueck - die Granularitaet bleibt bis
    manager_budgets.estimate_all() erhalten, damit dort pro Achievement
    exakt statt nur pauschal skaliert werden kann (siehe
    manager_budgets._EXACT_ACHIEVEMENTS)."""
    rewards = []
    for achievement_id in achievement_ids:
        try:
            reward = get_achievement_reward(token, league_id, achievement_id)
        except KickbaseError as exc:
            print(
                f"Warnung: Achievement-Reward fuer Id {achievement_id} fehlgeschlagen: {exc}",
                file=sys.stderr,
            )
            continue
        rewards.append(
            {"id": achievement_id, "ac": reward.get("ac") or 0, "er": reward.get("er") or 0}
        )
    return rewards
```

Aufrufstelle (Zeile ~431-446) ändern von:
```python
        achievement_bonus_total = _fetch_achievement_bonus_total(
            token, league_id, manager_budgets.unique_achievement_ids(activities)
        )
        start_budget = float(
            os.environ.get("KICKBASE_LEAGUE_START_BUDGET", DEFAULT_START_BUDGET)
        )
        league_start_date = os.environ.get("KICKBASE_LEAGUE_START_DATE") or None
        manager_budget_rows = manager_budgets.estimate_all(
            activities=activities,
            ranking_rows=ranking_rows,
            own_name=own_name,
            own_budget=budget,
            start_budget=start_budget,
            league_start_date=league_start_date,
            achievement_bonus_total=achievement_bonus_total,
        )
```
zu:
```python
        achievement_rewards = _fetch_achievement_rewards(
            token, league_id, manager_budgets.unique_achievement_ids(activities)
        )
        start_budget = float(
            os.environ.get("KICKBASE_LEAGUE_START_BUDGET", DEFAULT_START_BUDGET)
        )
        league_start_date = os.environ.get("KICKBASE_LEAGUE_START_DATE") or None
        manager_budget_rows = manager_budgets.estimate_all(
            activities=activities,
            ranking_rows=ranking_rows,
            own_name=own_name,
            own_budget=budget,
            start_budget=start_budget,
            league_start_date=league_start_date,
            achievement_rewards=achievement_rewards,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetcher.py -v -k FetchAchievementRewards`
Expected: PASS (2 tests)

Run zusätzlich die komplette Backend-Suite, um Regressionen in anderen Dateien auszuschließen:
Run: `python -m pytest tests/ -v`
Expected: PASS (alle Tests, keine Fehler)

- [ ] **Step 5: Commit**

```bash
git add src/fetcher.py tests/test_fetcher.py
git commit -m "Fetch achievement rewards per-id instead of pre-summed total"
```

---

## Task 4: PR öffnen und Auto-Merge setzen

**Files:** keine (nur Git/GitHub-Operationen)

- [ ] **Step 1: Branch pushen**

```bash
git push -u origin manager-budgets-exact-achievements
```

- [ ] **Step 2: PR erstellen**

```bash
gh pr create --title "Manager-Budgets: exakte Achievement-Erkennung statt Punkte-Skalierung" --body "$(cat <<'EOF'
## Summary
- Achievement-Bonus fuer andere Liga-Manager wird fuer 5 live verifizierte, exakt pruefbare Achievement-Ids (Teamwert-/Trade-Count-/Liga-Groesse-Schwellen) nicht mehr per Punkte-Verhaeltnis geschaetzt, sondern exakt anhand bereits vorhandener Manager-Daten geprueft.
- Nicht exakt pruefbare Achievements (z.B. profit-basiert) fallen weiterhin auf die bisherige Skalierung zurueck - kein Verhaltensbruch dort.
- Plan: docs/superpowers/plans/2026-08-07-manager-budgets-exact-achievements.md

## Test plan
- [x] python -m pytest tests/ -v (lokal gruen)
- [x] Neue Tests fuer _exact_achievement_hit, estimate_all-Integration, _fetch_achievement_rewards
EOF
)"
```

- [ ] **Step 3: Auto-Merge aktivieren**

```bash
gh pr merge --auto --squash
```

- [ ] **Step 4: Checks beobachten**

Run: `gh pr checks --watch`
Expected: alle 4 Required Checks grün, PR merged.

---

## Self-Review-Notizen (bereits eingearbeitet)

- Alle 4 bestehenden `estimate_all(...)`-Testaufrufe mit `achievement_bonus_total=0` migrieren, sonst brechen sie durch die Signaturänderung (Task 2, Step 1).
- `_exact_achievement_hit` gibt bewusst `None` (nicht `False`) für unbekannte Ids zurück, damit `estimate_all` zwischen "kein Treffer" und "kein verifizierter Typ" unterscheiden kann.
- Kein Firestore-Schema-Impact: `estimate_all()`-Rückgabewert (Feldnamen je Row) bleibt unverändert, daher kein Contract-Test (`AssembleSnapshotContractTests`) und kein Frontend-Änderungsbedarf.
