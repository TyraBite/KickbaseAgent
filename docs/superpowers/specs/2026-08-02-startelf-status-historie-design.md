# Startelf-Status-Historie (Phase A: ML-Marktwert-Turning-Points) — Design

**Feedback-Quelle:** `feedback/current` Item `6b08e2cf` (2026-08-02), Backlog-Punkt "Sentiment-Analyse für Marktwert-Turning-Points". Auf User-Wunsch in 3 Phasen zerlegt (D — Frontend-Anzeige — bewusst weggelassen, das Ziel ist ausschließlich eine bessere ML-Prognose, kein neues UI):

- **Phase A (dieses Dokument):** Startelf-Status-Historie sammeln + als ML-Feature verfügbar machen.
- **Phase B (folgt danach, eigene Spec):** Automatisierte News/Sentiment-Ingestion (Transfermarkt.de/Kicker), Sentiment per einfachem lokalem ML-Modell (kein LLM-API-Call — bleibt im 0€-Muster des Projekts).
- **Phase C (folgt danach, eigene Spec):** Sentiment- + Startelf-Historie-Daten aus Phase A+B als neue Trainings-Features ins Marktwert-Prognose-Modell integrieren, Modell ggf. neu tunen.

## Kontext

User-Beobachtung (Amiri-Beispiel): ein Wechsel von Startelf-Status (`starting_rank`) 3→1 (Bank/Rotation → gesetzter Stammspieler) kündigt typischerweise einen baldigen, spürbaren Marktwert-Anstieg an — aktuell fließt das nirgends in die Prognose ein. Bestätigt per Code-Check: `starting_rank` ist weder in `market_predictor.py`s `FEATURES`-Liste noch sonst irgendwo mit Historie verbunden — nur der aktuelle Wert liegt im Snapshot (`PlayerRecord.starting_rank`, genutzt für die "Stammspieler"-Einordnung in Ligaanalyse/Eigenes-Team, `REGULAR_STARTING_RANKS` = `{1, 2}`).

**Wichtige Einschränkung, die die Umsetzung prägt:** genau wie `status_code` (Fitness) liefert Kickbase für `starting_rank` **keine Zeitreihen-API** — nur den aktuellen Wert. Ein rückwirkendes Anwenden des heutigen Werts auf vergangene Trainings-Zeilen ist nicht möglich. Das bedeutet: dieselbe Cold-Start-Situation wie bei den bereits bestehenden Fitness-Features (`days_since_last_status_change`/`status_change_count_90d`, seit 2026-07-31 live, siehe `docs/superpowers/plans/2026-07-31-fitness-historie.md`) — es gibt keine Abkürzung über den aktuellen Wert, die Historie muss ab jetzt Tag für Tag gesammelt werden, bevor die Features etwas Sinnvolles taugen (Wochen/Monate, exakt wie beim Fitness-Vorbild).

## Entscheidung

**1:1 Muster-Mirror der bestehenden Fitness-Historie-Pipeline**, aber mit generalisierter Diff-/Feature-Berechnung statt zweiter Kopie derselben Logik (Feld-Parameter statt Duplikat) — begründet durch [[project_kickbaseagent_state]]-Konvention "ein Bug-Fix muss nur an einer Stelle passieren" (bereits so für `target_col`/`horizon_days` bei den zwei ML-Horizonten gemacht).

## Architektur

### Backend: `src/dashboard_export.py`

`_detect_status_changes(previous_players, all_players)` wird zu einer generischen Funktion umgebaut:

```python
def _detect_field_changes(
    previous_players: dict[str, dict], all_players: list[dict], field: str
) -> list[dict]:
    """Reine Diff-Funktion: vergleicht `field` je Spieler zwischen der
    vorherigen Baseline und den frisch gefetchten all_players. Ersetzt die
    frühere status_code-spezifische _detect_status_changes() - identische
    Logik, jetzt fuer status_code UND starting_rank genutzt (siehe
    docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md)."""
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

Aufrufstellen in `export()` bauen aus dem generischen `{"from": ..., "to": ...}`-Ergebnis das jeweils feldspezifische Schema (bestehendes `fitness_history_log`-Schema `from_status_code`/`to_status_code` bleibt **byte-identisch** — keine Migration, kein Bruch bestehender Firestore-Daten):

```python
status_changes = [
    {"player_id": c["player_id"], "from_status_code": c["from"], "to_status_code": c["to"]}
    for c in _detect_field_changes(previous_players_for_fitness_diff, heavy["all_players"], "status_code")
]
starting_rank_changes = [
    {"player_id": c["player_id"], "from_starting_rank": c["from"], "to_starting_rank": c["to"]}
    for c in _detect_field_changes(previous_players_for_rank_diff, heavy["all_players"], "starting_rank")
]
```

Der komplette Ablauf um `_detect_status_changes()` in `export()` (Zeilen ~479-520: Baseline lesen → Diff → History-Write → Baseline-Write, jeweils mit eigenem Try/Except, das den kritischen `dashboard_snapshot`-Write nie verhindern darf) wird für `starting_rank` **parallel dupliziert**, nicht in eine gemeinsame Schleife gepresst — die beiden Felder haben unterschiedliche Baseline-Dokumente und unterschiedliche Fehlermeldungstexte, ein Versuch, das zu einer Schleife zusammenzufassen, würde die Warnmeldungen unleserlich generisch machen ("Warnung: X-Diff uebersprungen" statt der konkreten, heute schon eingeführten Texte). Nur die eigentliche Diff-Berechnung (`_detect_field_changes`) und die Firestore-Helper (siehe unten) werden geteilt — der Orchestrierungscode in `export()` bleibt zwei parallele, lesbare Blöcke.

### Backend: `src/firestore_db.py`

Analog generalisiert:

```python
def upsert_history_entries(client: firestore.Client, collection: str, entries: list[dict]) -> None:
    # ersetzt upsert_fitness_history_entries() - collection als Parameter statt hardcoded "fitness_history_log"
    ...

def get_history(client: firestore.Client, collection: str) -> list[dict]:
    # ersetzt get_fitness_history()
    ...

def upsert_baseline(client: firestore.Client, collection: str, doc_id: str, data: dict) -> None:
    # ersetzt upsert_fitness_status_baseline() - collection/doc_id als Parameter statt hardcoded "fitness_status_baseline"/"latest"
    ...

def get_baseline(client: firestore.Client, collection: str, doc_id: str) -> dict:
    # ersetzt get_fitness_status_baseline()
    ...
```

Aufrufstellen: `upsert_history_entries(client, "fitness_history_log", entries)` / `upsert_history_entries(client, "starting_rank_history_log", entries)`, analog für Baseline mit `"fitness_status_baseline"/"latest"` bzw. `"starting_rank_baseline"/"latest"`.

### Backend: `src/market_predictor.py`

`_fitness_features_as_of(events, as_of_date)` wird generalisiert (Feld-Namen der Ergebnis-Keys bleiben per Parameter benennbar, damit sowohl die bestehenden `days_since_last_status_change`/`status_change_count_90d` als auch die neuen `days_since_last_starting_rank_change`/`starting_rank_change_count_90d` erzeugt werden können, ohne zwei fast identische Funktionen zu pflegen):

```python
def _change_recency_features(
    events: list[dict], as_of_date: datetime.date,
    from_key: str, to_key: str, days_feature: str, count_feature: str,
    window_days: int = FITNESS_COUNT_WINDOW_DAYS,
) -> dict:
    """events: EIN Spielers Eintraege aus der jeweiligen History-Collection
    (jeweils {'date': ..., from_key: ..., to_key: ...}). Generalisierte
    Version von _fitness_features_as_of() - identische Formel, jetzt
    parametrisiert fuer status_code UND starting_rank."""
    relevant = [e for e in events if datetime.date.fromisoformat(e["date"]) <= as_of_date]
    if not relevant:
        return {days_feature: FITNESS_NO_HISTORY_DAYS, count_feature: 0}
    last_date = max(datetime.date.fromisoformat(e["date"]) for e in relevant)
    days_since = (as_of_date - last_date).days
    cutoff = as_of_date - datetime.timedelta(days=window_days)
    count = sum(1 for e in relevant if datetime.date.fromisoformat(e["date"]) > cutoff)
    return {days_feature: days_since, count_feature: count}
```

`FITNESS_NO_HISTORY_DAYS`/`FITNESS_COUNT_WINDOW_DAYS` (Konstanten) werden umbenannt auf feldneutrale Namen (`NO_HISTORY_DAYS_PLACEHOLDER`, `CHANGE_COUNT_WINDOW_DAYS`) — reine Umbenennung, gleicher Wert (`9999`/`90`), betrifft nur diese beiden Konstanten, keine sonstige Logik.

Neue `FEATURES`-Einträge: `"days_since_last_starting_rank_change"`, `"starting_rank_change_count_90d"`.

`_load_fitness_events_by_player()` wird generalisiert zu `_load_change_events_by_player(collection: str)`, zweimal aufgerufen (`"fitness_history_log"`, `"starting_rank_history_log"`), Ergebnis getrennt an `_fetch_player_training_frame()` durchgereicht (zwei Parameter statt einem, oder ein `dict[str, dict[str, list[dict]]]` — Detail für den Implementierungsplan).

## Datenfluss

```
Heavy-Cron (1x/Tag) fetcht all_players (bereits vorhanden)
  │
  ├─ status_code-Diff (wie bisher, jetzt ueber _detect_field_changes)
  │    → starting_rank_baseline uebersprungen, nur fitness_status_baseline betroffen
  │    → fitness_history_log
  │
  └─ starting_rank-Diff (NEU, identischer Ablauf)
       → starting_rank_baseline/latest (NEU)
       → starting_rank_history_log (NEU)

market_predictor.py (naechster Trainings-/Prognose-Lauf, unabhaengig vom Cron-Timing)
  │
  ├─ _load_change_events_by_player("fitness_history_log")   → wie bisher
  └─ _load_change_events_by_player("starting_rank_history_log")  → NEU
       │
       └─ pro Trainings-Zeile: _change_recency_features(...) fuer beide Felder
            → 4 Feature-Spalten total (2 bestehend, 2 neu) in FEATURES
```

## Fehlerfälle

- **Baseline-Lesefehler** (Firestore down, Quota) — identisch zum bestehenden Fitness-Muster: Diff wird für diesen Lauf übersprungen (kein Crash), Warnung auf stderr, Baseline-Write läuft trotzdem unbedingt weiter (selbstheilend für den nächsten Lauf).
- **History-Schreibfehler** — abgefangen, darf den kritischen `dashboard_snapshot`-Write nicht verhindern (gleiche `try/except`-Kapselung wie bei Fitness).
- **`starting_rank` fehlt/ist `None`** für einen Spieler (z.B. Kickbase liefert es für bestimmte Randfälle nicht) — `_detect_field_changes` überspringt das (`old_value is None or new_value is None`-Guard), kein Sonderfall nötig.
- **Cold-Start** (keine Historie vorhanden) — Platzhalter `9999`/`0`, wie bei Fitness. Feature ist für Wochen/Monate praktisch konstant und damit für das Modell wertlos, aber nicht schädlich — **explizit erwartet, kein Bug**, wie beim Fitness-Vorbild.

## Testing

Bestehende Tests für `_detect_status_changes`/`_fitness_features_as_of` (falls vorhanden in `tests/test_dashboard_export.py`/`tests/test_market_predictor.py`) werden auf die generalisierten Funktionsnamen umgezogen, decken aber weiterhin exakt denselben `status_code`-Fall ab (keine Verhaltensänderung). Neue Tests:
- `_detect_field_changes` mit `field="starting_rank"`: Wechsel erkannt, `None`-Werte übersprungen, kein Wechsel bei Gleichstand.
- `_change_recency_features` mit den neuen Feature-Namen: Cold-Start-Platzhalter, Tage-seit-Berechnung, 90-Tage-Fenster-Zählung — identische Testfälle wie die bestehenden Fitness-Tests, nur mit den neuen Parametern durchgereicht (beweist, dass die Generalisierung die alte Fitness-Berechnung nicht verändert hat — Regressionsschutz für den Umbau selbst).
- `upsert_history_entries`/`get_history`/`upsert_baseline`/`get_baseline` (falls dafür bereits Tests existieren): Collection-Name als Parameter statt hardcoded, Verhalten sonst unverändert.

## Betroffene Dateien

- Modify: `src/dashboard_export.py` (`_detect_field_changes()` statt `_detect_status_changes()`, neuer `starting_rank`-Diff-Block in `export()`)
- Modify: `src/firestore_db.py` (generalisierte `upsert_history_entries`/`get_history`/`upsert_baseline`/`get_baseline`)
- Modify: `src/market_predictor.py` (`_change_recency_features()` statt `_fitness_features_as_of()`, `_load_change_events_by_player()` statt `_load_fitness_events_by_player()`, zwei neue `FEATURES`-Einträge, `_fetch_player_training_frame()` nimmt beide Event-Quellen)
- Modify: `tests/test_dashboard_export.py`, `tests/test_market_predictor.py` (Tests umbenannt/erweitert)

## Out of Scope (bewusst, für spätere Phasen)

- Phase B (News/Sentiment-Ingestion) und Phase C (ML-Integration von Sentiment) — eigene Specs, bauen auf diesem Dokument nicht technisch auf, nur thematisch verwandt (beide sind Zulieferer für dasselbe Ziel: bessere Marktwert-Prognose durch "ahead of the curve"-Signale).
- Keine Frontend-Anzeige des Startelf-Wechsels irgendwo (User-Entscheidung: Punkt D explizit weggelassen, rein ML-intern).
- Kein Feature-Tuning/Neubewertung, ob die neuen Features das Modell tatsächlich verbessern — das ist derselbe "erst nach Wochen/Monaten Datenaufbau messen"-Vorbehalt wie bei den Fitness-Features, gehört in Phase C bzw. den ohnehin schon im HANDOFF vermerkten "Modelle nochmal tunen sobald genug Daten da sind"-Punkt.
