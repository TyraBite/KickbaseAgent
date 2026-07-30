# Gebotsvorschläge-Tracking — Design

## Kontext

Die Gebotsvorschläge (`suggestBid()`, siehe `docs/superpowers/plans/2026-07-30-gebotsvorschlaege.md`) basieren auf historischen Aufschlägen abgeschlossener Systemkäufe (`bid_premium_log`). Live verifiziert (2026-07-30): die Empfehlungen sind plausibel (z.B. Torwart p50/p75/p90 steigend, passend zum Ø-Aufschlag). Der User möchte die Datengrundlage nachträglich um zwei bisher fehlende Signale erweitern, um die Schätzung über Zeit besser einordnen/verbessern zu können:

1. Systemangebote, die **unverkauft ablaufen** — impliziert, dass 0% Aufschlag (der reine Marktwert) gereicht hätte. Aktuell nicht getrackt.
2. Systemangebote, die **der User selbst kauft** — laufen technisch schon heute unmarkiert in `bid_premium_log` mit rein (dieselbe `_is_system_purchase()`-Logik prüft nur "kein Verkäufer", nicht wer der Käufer ist), sollen aber als schwächeres Signal (eigene Preiswahl, echter Mindestpreis bleibt unbekannt) von echten Fremd-Käufen unterscheidbar werden.

## Architektur

Pro Lauf wird verglichen, welche Systemangebote-Spieler-IDs seit dem letzten Lauf aus dem Markt verschwunden sind (neuer Zeiger in `bid_premium_state`). Für jede verschwundene ID wird im ohnehin schon abgerufenen Activity-Feed nach einem passenden Systemkauf gesucht (identische Prüfung wie in `bid_premium.py` bereits vorhanden) — findet sich einer, war es ein normaler Kauf (landet wie gewohnt in `bid_premium_log`, jetzt zusätzlich mit einem `bought_by_self`-Tag). Findet sich keiner, gilt das Angebot als unverkauft abgelaufen und wird in eine neue, separate Collection `bid_premium_unsold_log` geschrieben. Diese neuen Daten fließen **nicht** in `suggestBid()` ein — reine Beobachtung, keine Änderung der aktuell live gezeigten Gebotsempfehlungen. Anzeige erfolgt im (bereits umbenannten) "Modell-Tracking"-Tab (`frontend/src/App.tsx`, vormals "ML-Genauigkeit") als neuer Abschnitt unterhalb des bestehenden Kopf-an-Kopf/Trend-Bereichs.

## Datenfluss im Detail

- **Zeiger-Erweiterung**: `bid_premium_state/current` bekommt ein neues Feld `last_seen_system_listing_ids: list[str]` (zusätzlich zum bestehenden `last_processed_dt`).
- **Erkennung pro Lauf** (`src/bid_premium.py`, neue Funktion `detect_unsold_listings()`):
  - `current_ids = {l["player_id"] for l in market_listings if l["is_system_offer"]}`.
  - `disappeared = last_seen_ids - current_ids`.
  - Für jede `player_id` in `disappeared`: prüfen ob eine Systemkauf-Aktivität (`_is_system_purchase()`) mit dieser `player_id` in den `activities` (dasselbe bereits gefetchte Activity-Feed) vorkommt. Falls ja → wird ohnehin schon von `build_new_entries()` verarbeitet (kein Duplikat-Handling nötig, `bid_premium_log`-Doc-Id ist idempotent). Falls nein → neuer Eintrag in `bid_premium_unsold_log` mit `{player_id, position, market_value_then, average_points_then, detected_at}` (Marktwert/Punkteschnitt aus dem übergebenen `players_map`, zum ZEITPUNKT der Erkennung — bekannte Näherung, gleiche Einschränkung wie bei `bid_premium_log`s `average_points_then`).
  - **Kein Mehrfach-Bestätigungs-Fenster in v1**: ein einzelnes Verschwinden zwischen zwei (jetzt stündlichen) Läufen reicht als Trigger. Bewusste Vereinfachung — falls sich Kickbase-Angebote doch mal ohne echten Verkauf neu listen (unbeobachtet, kein bekannter Fall), wäre das ein seltener Fehleintrag in einer rein beobachtenden, nicht live-wirksamen Collection. Nicht weiter abgesichert, siehe Global Constraints.
  - Zeiger wird danach auf `current_ids` aktualisiert.
- **Self-Tag** (`src/bid_premium.py::build_new_entries()`): bekommt `own_name: str` als neuen Parameter, setzt `bought_by_self = (activity["data"].get("byr") == own_name)` pro Eintrag. Rückwirkend NICHT für die schon existierenden 86 Einträge nachrüstbar (kein `byr` im gespeicherten Log) — die bleiben ohne das Feld (Frontend behandelt fehlendes Feld wie `false`/unbekannt, nicht als Fehler).
- **Snapshot-Erweiterung** (`src/dashboard_export.py`): zwei neue, rein aggregierte Felder (keine Rohdaten-Listen, um das Dokument klein zu halten):
  - `bid_premium_outcome_counts: {position: {rival_purchases: n, self_purchases: n, unsold: n}}`.
- **Frontend** (`frontend/src/components/MlGenauigkeitTab.tsx`): neuer Abschnitt "Gebotsvorschläge-Tracking", eine kleine Tabelle/Kartenliste pro Position mit den drei Zählern.

## Global Constraints

- Fall-2-Daten (`bid_premium_unsold_log`) fließen NICHT in `suggestBid()`/`bid_premium_log` ein — rein additiv, ändert keine bestehende Berechnung oder Anzeige der Gebotsvorschläge selbst.
- Kein neuer Kickbase-API-Call — Erkennung nutzt ausschließlich bereits abgerufene `market_listings` und `activities`.
- Kein Mehrfach-Bestätigungs-Fenster (siehe oben) — akzeptierte Vereinfachung für v1, da die Collection rein beobachtend ist.
- `bought_by_self` fehlt auf allen vor diesem Feature entstandenen `bid_premium_log`-Einträgen (rückwirkend nicht rekonstruierbar) — Frontend/Aggregation muss `entry.bought_by_self` als `false`/unbekannt behandeln, nicht als Pflichtfeld voraussetzen.
- Backend-Tests: `python3 -m unittest discover -s tests -v`, muss nach jedem Task grün bleiben.
- Frontend-Verifikation: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`).

## Out of Scope

- Keine automatische "Verbesserung" von `suggestBid()` basierend auf den neuen Daten (z.B. automatisches Absenken der Perzentile bei vielen unverkauften Angeboten) — reine Anzeige/Beobachtung für jetzt, eine spätere bewusste Entscheidung.
- Keine rückwirkende Rekonstruktion von `bought_by_self` für die schon bestehenden 86 Log-Einträge.
- Kein Mehrfach-Bestätigungs-Fenster/Grace-Period für die Verschwindens-Erkennung (siehe Global Constraints).

## Self-Review

- **Platzhalter-Scan**: keine TBD/offenen Stellen.
- **Konsistenz**: `bid_premium_unsold_log`/`bought_by_self`/`bid_premium_outcome_counts` durchgängig gleich benannt zwischen Architektur- und Datenfluss-Abschnitt.
- **Scope**: fokussiert genug für einen einzelnen Implementierungsplan (ein neues Backend-Modul-Erweiterung + eine neue Collection + ein neuer Frontend-Abschnitt, keine Fremd-Features vermischt).
- **Abgrenzung zu bestehendem Code**: baut direkt auf `src/bid_premium.py`s bestehenden Funktionen auf (`_is_system_purchase()`, `build_new_entries()`), keine Duplikation der Systemkauf-Erkennungslogik.
