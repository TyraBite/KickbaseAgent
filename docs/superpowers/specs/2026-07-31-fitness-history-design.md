# Fitness-Historie (Sammel-Pipeline + ML-Integration) — Design

## Kontext

Kickbase liefert pro Spieler nur den aktuellen `status_code` (0=fit, 1=Verletzt, 2=Angeschlagen, 4=Im Aufbau) — keine Zeitreihe. Ein früherer Versuch, Verletzungsanfälligkeit über einen Proxy (`mp_avg_3`, rollierender Minutenschnitt) als ML-Feature nutzbar zu machen, hat die Marktwert-Prognose-Genauigkeit leicht verschlechtert (siehe `HANDOFF.md`, Failed Approaches). Eine echte Historie (wann war ein Spieler wie lange verletzt) ist der nächste, vielversprechendere Ansatz — braucht aber erst Wochen/Monate Datenaufbau, bevor sie als Feature nutzbar ist.

**Ziel dieser Spec:** die komplette Kette auf einmal bauen — Sammel-Pipeline (neue Firestore-Collection, protokolliert ab Rollout jeden Statuswechsel jedes Spielers im ~450er-Kandidatenpool), Read-Pfad UND Einbau als Feature in `market_predictor.py`. Explizite User-Entscheidung (2026-07-31): kein zweiter Entwicklungs-Zyklus in ein paar Wochen, das System soll ab Rollout selbstständig laufen und mit wachsender Datenmenge von selbst besser werden (Modell trainiert ohnehin täglich neu). **Wichtige Einschränkung, die dabei bleibt**: welche Feature-Kodierung tatsächlich hilft, ist heute reine Vermutung ohne echte Daten — dieselbe Unsicherheit, die schon beim gescheiterten `mp_avg_3`-Versuch bestand. Diese Spec macht ein zukünftiges "hilft nicht" zu einem Ein-Zeilen-Toggle (Feature schon eingebaut, nur `FEATURES`-Liste anpassen) statt zu einem neuen Bau-Projekt — sie garantiert aber NICHT, dass die gewählte Kodierung sich als nützlich erweist.

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

**Firestore-Kosten:** strukturell klein. Injuries/Rückkehr-Events sind selten (deutlich unter 450/Tag) — anders als der frühere `ml_prediction_log`-Quota-Vorfall (900 Docs/Tag, volle Collection-Scans), der gerade wegen des dortigen Voll-Snapshot-Musters entstand. Kein Pointer/Range-Filter beim Schreiben ODER Lesen nötig, da nur Deltas geschrieben werden und die Collection dadurch dauerhaft klein bleibt (siehe Read-Pfad-Abschnitt unten).

## Cold-Start-Limitation (akzeptiert)

Am ersten Lauf nach Rollout ist für jeden zu diesem Zeitpunkt bereits verletzten Spieler der tatsächliche Beginn der Verletzung unbekannt — die Historie beginnt faktisch erst mit dem ersten Wechsel NACH Rollout. Kein Backfill möglich (Kickbase liefert keine Vergangenheit). Kein Sonderfall im Code nötig — fällt natürlich aus der Diff-Logik heraus (kein Eintrag ≠ "schon immer fit", sondern "unbekannt vor Rollout-Datum").

## Read-Pfad

Neue Funktion `firestore_db.get_fitness_history(client) -> list[dict]`, analog zu `get_bid_premium_history()` — liest die komplette `fitness_history_log`-Collection in einem Read (Volumen bleibt klein, siehe Kosten-Abschnitt oben, kein Pointer/Range-Filter nötig). Aufrufer gruppiert die flache Liste selbst nach `player_id` (kein Bedarf, das schon in `firestore_db.py` zu tun — bleibt dort reine I/O-Funktion, wie beim Rest der Datei üblich).

## ML-Integration (`market_predictor.py`)

**Wichtiger Fund:** der ML-Corpus ist komplett unabhängig vom Firestore-Snapshot der Dashboard-Pipeline — `_build_corpus()`/`_fetch_player_training_frame()` holen Marktwert- und Performance-Historie pro Spieler bei JEDEM Lauf frisch direkt von der Kickbase-API (`market_predictor.py:124-200`). Die Fitness-Events kommen zusätzlich dazu, aus Firestore, nicht aus einem neuen Kickbase-Call.

**Zwei neue Features** in `FEATURES` (`market_predictor.py:63`):
- `days_since_last_status_change` — Tage seit dem letzten Wechsel, als Platzhalter eine grosse Konstante (z.B. 9999) wenn kein Ereignis vor diesem Datum bekannt ist.
- `status_change_count_90d` — Anzahl Wechsel in den letzten 90 Tagen vor diesem Datum, Platzhalter `0`.

**Datenfluss:**
1. `predict_market_value_changes()`: einmal `firestore_db.get_fitness_history(firestore_db.connect())` lesen (ein Read pro Lauf, gleiches Muster wie die bestehenden `firestore_db.connect()`-Aufrufe an anderer Stelle in dieser Datei, z.B. Zeile 554/593/635/830/837). Ergebnis zu `events_by_player: dict[str, list[dict]]` gruppiert und pro Spieler nach `date` aufsteigend sortiert.
2. Durchgereicht durch `_build_corpus()` → `_fetch_player_training_frame()` (neuer Parameter) — kein zusätzlicher Firestore-Read pro Spieler/Thread, nur ein In-Memory-Dict-Lookup.
3. In `_fetch_player_training_frame()`, direkt neben dem bestehenden `pd.merge_asof(mv_df, p_df, on="date", direction="backward")` (Zeile 193): dieselbe Technik für die Fitness-Events pro Spieler — `merge_asof(direction="backward")` liefert das jüngste Ereignis auf/vor jedem Datum, daraus `days_since_last_status_change` per Datumsdifferenz. `status_change_count_90d` separat über eine Fenster-Zählung auf den sortierten Event-Daten (kein `merge_asof`-Fall, da eine Summe über ein Zeitfenster, nicht ein einzelner Treffer).
4. Beide Spalten in `_engineer_features()` (Zeile 238) mit den Platzhaltern per `.fillna()` versehen, analog zur bestehenden Zeile 310 (`market_divergence`, `mp_avg_3` etc. werden dort schon so behandelt).
5. **Live-Prognose-Pfad** (`today_df`, dieselbe Funktion) bekommt automatisch dieselben zwei Spalten mit — kein separater Code-Pfad nötig, `_engineer_features()` behandelt `history_df` und `today_df` gemeinsam aus demselben `df`.

**Auswirkung auf den Walk-Forward-Backtest**: für Trainings-Zeilen aus der Zeit vor Rollout sind beide Features konstant (Platzhalter) — trägt keine Information, aber auch kein Risiko (baumbasierte Modelle wie RF/HGB wählen an einer konstanten Spalte schlicht keinen Split). Erst mit echten, nach Rollout gesammelten Ereignissen entsteht Varianz. Da `predict_market_value_changes()` bei jedem Heavy-Lauf neu trainiert, verbessert sich das potenzielle Signal von selbst — kein weiterer Eingriff nötig, um es "wirken zu lassen".

## Testing

TDD, neue Testklasse in `tests/test_dashboard_export.py` für `_detect_status_changes()` — reine Funktion, kein Mocking nötig:

- Kein Wechsel → leere Liste.
- Ein Wechsel (z.B. 0→1) → genau ein Event mit korrekten `from`/`to`-Codes.
- Mehrere Spieler, gemischt (manche Wechsel, manche nicht) → nur die tatsächlichen Wechsel als Events.
- Spieler ohne Vorstand in `previous_players` → kein Event, kein Crash.
- Spieler aus `all_players` fehlt komplett → kein Event, kein Crash.

Zusätzlich ein Test für `firestore_db.upsert_fitness_history_entries()` analog zum bestehenden `upsert_bid_premium_entries()`-Testmuster (Batch-Write, idempotenter Doc-Key), sowie für `get_fitness_history()` (liest zurück, was geschrieben wurde).

Für die ML-Integration: neue Tests in `tests/test_market_predictor.py` für die Feature-Berechnung (isoliert, ohne echten API-Call) — Fälle: kein Ereignis vor dem Datum (Platzhalter), ein Ereignis (korrekte Tage-Differenz), mehrere Ereignisse (nur die innerhalb der 90-Tage-Zählung berücksichtigt), Ereignis exakt an der 90-Tage-Grenze (Boundary-Test). Bestehende `_engineer_features()`/`_build_candidates()`-Tests müssen weiterhin grün bleiben (neue Features dürfen bestehende Spalten/Verhalten nicht verändern).

## Out of Scope (bewusst, auch weiterhin)

- Keine Frontend-Anzeige/UI für diese Daten.
- Keine feinere Diff-Kadenz für den eigenen Kader (siehe Architektur-Abschnitt).
- Keine Auswertung/Tuning der Feature-Kodierung selbst — das ist explizit erst nach echtem Datenaufbau sinnvoll möglich, siehe Einschränkung im Kontext-Abschnitt. Ändert sich nach Datenaufbau nur, dass eine Kodierung sich als nutzlos herausstellt: dann Umschalten (`FEATURES`-Liste), nicht Neubau.
