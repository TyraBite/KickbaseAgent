# Fitness-Historie (Sammel-Pipeline) — Design

## Kontext

Kickbase liefert pro Spieler nur den aktuellen `status_code` (0=fit, 1=Verletzt, 2=Angeschlagen, 4=Im Aufbau) — keine Zeitreihe. Ein früherer Versuch, Verletzungsanfälligkeit über einen Proxy (`mp_avg_3`, rollierender Minutenschnitt) als ML-Feature nutzbar zu machen, hat die Marktwert-Prognose-Genauigkeit leicht verschlechtert (siehe `HANDOFF.md`, Failed Approaches). Eine echte Historie (wann war ein Spieler wie lange verletzt) ist der nächste, vielversprechendere Ansatz — braucht aber erst Wochen/Monate Datenaufbau, bevor sie als Feature nutzbar ist.

**Ziel dieser Spec:** ausschließlich die Sammel-Pipeline aufbauen — eine neue Firestore-Collection, die ab Rollout jeden Statuswechsel jedes Spielers im ~450er-Kandidatenpool protokolliert. Die spätere Nutzung als ML-Feature (Auswertung, Feature-Engineering, Einbau in `market_predictor.py`) ist bewusst **nicht** Teil dieser Spec — eigener, späterer Plan, sobald genug Historie vorliegt.

## Scope

Alle ~450 Spieler im Kandidatenpool (`player_valuation.py::fetch_all_players()`), nicht nur eigener Kader/Wunschkader-Ziele — nötig, damit die Historie später als generelles Feature für die Marktwert-Prognose über den gesamten Trainings-Pool nutzbar ist.

## Architektur

Kein neuer Kickbase-API-Call. `fetch_all_players()` läuft bereits 1×/Tag im Heavy-Cron (`dashboard-marktwerte.yml`, `_resolve_heavy_data()` in `src/dashboard_export.py`) und liefert `status_code` für den gesamten Pool. Der Light-Cron (`dashboard.yml`, stündlich) aktualisiert nur den eigenen Kader (~15-20 Spieler) und lässt `all_players` auf `None` — Statuswechsel für Nicht-eigene Spieler sind zwischen zwei Heavy-Läufen ohnehin nicht sichtbar. Diese Spec diffed deshalb **ausschließlich im Heavy-Zweig, 1×/Tag, für alle Spieler gleich** — bewusste Vereinfachung (YAGNI): keine zweite, feinere Diff-Kadenz nur für den eigenen Kader.

**Diff-Quelle:** `export()` (`src/dashboard_export.py`) hat über `cached_snapshot.get("players", {})` bereits vollen Zugriff auf die players-Map des VORHERIGEN Snapshots, unabhängig von `is_light` — bestätigt im Code (`dashboard_export.py:427`, `previous_players = cached_snapshot.get("players", {}) if is_light else None` liest `cached_snapshot` bereits vor dieser Zeile ein). Dieser alte Stand wird gegen das frisch gefetchte `all_players` verglichen, **bevor** `_build_players_map()` läuft und der Snapshot überschrieben wird.

**Neue reine Funktion** `_detect_status_changes(previous_players, all_players) -> list[dict]` in `dashboard_export.py`:

- Für jeden Eintrag in `all_players`: `pid = p["player_id"]`, `new_status = p["status_code"]`.
- Kein Eintrag für `pid` in `previous_players` → skip (neuer Spieler im Pool, kein Vorstand zum Vergleichen).
- `previous_players[pid]["status_code"] == new_status` → skip (kein Wechsel).
- Sonst → Event-Dict anhängen: `{"player_id": pid, "from_status_code": <alt>, "to_status_code": new_status}`.
- Spieler, die aus `all_players` verschwunden sind (z.B. abgestiegen), werden nicht behandelt — kein Crash, einfach kein Event.

**Aufruf in `export()`:** im Heavy-Zweig (`all_players is not None`), nach dem Fetch, vor/unabhängig von `_build_players_map()`. Ergebnis-Events bekommen `date`/`recorded_at` (aktueller Lauf-Zeitpunkt) angehängt und werden bei `FIRESTORE_ENABLED` über eine neue Funktion `firestore_db.upsert_fitness_history_entries()` geschrieben. Kein Firestore-Write, keine neuen Kickbase-Calls im Light-Zweig.

## Datenmodell

Neue Collection **`fitness_history_log`** (Name an die im Frontend bereits etablierte "Fitness"-Terminologie angelehnt statt "injury" — deckt auch Rückkehr zu fit ab). Analog zum bestehenden `bid_premium_log`-mit-idempotentem-Doc-Key-Muster (`firestore_db.py`):

```
doc_id: "{date}_{player_id}"      # idempotent - erneuter Lauf am selben Tag ueberschreibt statt zu duplizieren
{
  "player_id": str,
  "date": str,               # ISO-Datum (YYYY-MM-DD) des Heavy-Laufs
  "from_status_code": int,
  "to_status_code": int,
  "recorded_at": str,        # ISO-Timestamp UTC
}
```

Kein `name`/`team_name`-Feld — bei Bedarf später per `player_id` gegen die players-Map join-bar, keine Duplizierung von Stammdaten in einem reinen Event-Log.

**Firestore-Kosten:** strukturell klein. Injuries/Rückkehr-Events sind selten (deutlich unter 450/Tag) — anders als der frühere `ml_prediction_log`-Quota-Vorfall (900 Docs/Tag, volle Collection-Scans), der gerade wegen des dortigen Voll-Snapshot-Musters entstand. Kein Pointer/Range-Filter beim Schreiben nötig, da nur Deltas geschrieben werden. Ein Read-Pfad existiert in dieser Spec noch nicht (siehe Out of Scope) — Kosten dafür sind Teil des späteren Feature-Engineering-Plans.

## Cold-Start-Limitation (akzeptiert)

Am ersten Lauf nach Rollout ist für jeden zu diesem Zeitpunkt bereits verletzten Spieler der tatsächliche Beginn der Verletzung unbekannt — die Historie beginnt faktisch erst mit dem ersten Wechsel NACH Rollout. Kein Backfill möglich (Kickbase liefert keine Vergangenheit). Kein Sonderfall im Code nötig — fällt natürlich aus der Diff-Logik heraus (kein Eintrag ≠ "schon immer fit", sondern "unbekannt vor Rollout-Datum").

## Testing

TDD, neue Testklasse in `tests/test_dashboard_export.py` für `_detect_status_changes()` — reine Funktion, kein Mocking nötig:

- Kein Wechsel → leere Liste.
- Ein Wechsel (z.B. 0→1) → genau ein Event mit korrekten `from`/`to`-Codes.
- Mehrere Spieler, gemischt (manche Wechsel, manche nicht) → nur die tatsächlichen Wechsel als Events.
- Spieler ohne Vorstand in `previous_players` → kein Event, kein Crash.
- Spieler aus `all_players` fehlt komplett → kein Event, kein Crash.

Zusätzlich ein Test für `firestore_db.upsert_fitness_history_entries()` analog zum bestehenden `upsert_bid_premium_entries()`-Testmuster (Batch-Write, idempotenter Doc-Key).

## Out of Scope (bewusst, für spätere Spec)

- Kein Read-Pfad (`get_fitness_history()` o.ä.) — erst wenn ein Konsument existiert.
- Keine Nutzung als ML-Feature in `market_predictor.py` — braucht erst Wochen/Monate Datenaufbau.
- Keine Frontend-Anzeige/UI für diese Daten.
- Keine feinere Diff-Kadenz für den eigenen Kader (siehe Architektur-Abschnitt).
