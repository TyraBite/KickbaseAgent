# Ligaanalyse-Detailansicht — Design

## Kontext

Der Ligaanalyse-Tab zeigt pro Manager eine Karte mit Aggregat-Werten (Platz, Punkte, Kadergröße, Budget etc.), siehe `frontend/src/components/LigaanalyseTab.tsx`. Wer konkret im Kader eines Gegners (oder im eigenen) steht, ist aktuell nirgends direkt sichtbar — das war in HANDOFF.md als offener Punkt vermerkt ("beim Klick auf einen Manager sollen Grundinfos + Kaderliste angezeigt werden, analog zu den Detail-Modals in anderen Tabs").

**Ziel:** Klick auf eine Manager-Karte (eigene wie gegnerische) öffnet ein Detail-Modal mit kurzem Info-Header + einer nach Position gruppierten Kaderliste.

## Abhängigkeit / Sequenzierung

Dieser Plan setzt auf dem **bereits umgesetzten** Stand von `docs/superpowers/plans/2026-07-30-gebotsvorschlaege.md` auf (`_build_ligaanalyse()` nimmt dort `players_map` statt `starting_rank_by_player_id` als letzten Parameter und liefert `{"rows": [...], "position_need": {...}}` statt einer reinen Liste — siehe dessen Task 7). Diese Spec spezifiziert die Erweiterung direkt gegen diesen Zielstand. Wird dieser Plan umgesetzt, BEVOR der Gebotsvorschläge-Branch gemergt ist, muss der Diff entsprechend händisch an die zu diesem Zeitpunkt tatsächlich vorliegende Funktionssignatur angepasst werden (gleiches Muster wie bei den bisherigen players-Map-Merges in diesem Projekt: Konflikt lesen, nicht blind übernehmen).

## Architektur

Kein neuer Kickbase-API-Call. `get_manager_squad()` wird für Gegner-Zeilen bereits aufgerufen (für `squad_size`/`squad_value`/`regular_count`); für die eigene Zeile liegt `own_squad` bereits vollständig vor. Beide liefern schon jetzt Spieler-IDs — die müssen nur zusätzlich in die Row geschrieben werden. Alle Anzeige-Werte (Name, Position, Marktwert, Stammspieler-Status) löst das Frontend über `data.players[id]` auf, exakt das Muster aus dem players-Map-Redesign: Backend liefert rohe IDs, Ableitung passiert client-seitig in `derive.ts`.

## Backend: `_build_ligaanalyse()`

**Datei:** `src/dashboard_export.py`

Neues Feld pro Row: `squad_player_ids: list[str]`.

- **Eigene Zeile:** `[p["player_id"] for p in own_squad]`.
- **Gegner-Zeile:** `[item.get("pi") for item in items]` (`items` ist die bereits vorhandene Variable aus `get_manager_squad()`s `"it"`-Liste im bestehenden `try`-Block).
- **Bei `KickbaseError`** (bestehender `except`-Zweig, setzt schon `squad_size = None` etc.): `squad_player_ids = []`.

`LigaanalyseRow`-Dict im Rückgabe-`rows`-Eintrag um `"squad_player_ids": squad_player_ids,` ergänzen. `position_need`-Logik (Gebotsvorschläge-Plan) bleibt unverändert — reiner Zusatz, keine Kollision.

## Frontend

### `types.ts`

`LigaanalyseRow` um `squad_player_ids: string[];` erweitern.

### `derive.ts`

Neue Funktion, gruppiert eine ID-Liste anhand von `data.players` nach Position, sortiert innerhalb jeder Gruppe nach Marktwert absteigend, IDs ohne Treffer in `players` werden übersprungen:

```ts
export interface SquadListEntry {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  is_regular: boolean; // starting_rank 1 oder 2, gleiche Schwelle wie der bestehende Ligaanalyse-Hint-Text
}

const POSITION_ORDER = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];

export function groupSquadByPosition(
  playerIds: string[],
  players: Record<string, PlayerRecord>
): { position: string; entries: SquadListEntry[] }[] {
  const entries: SquadListEntry[] = playerIds
    .map((id) => players[id])
    .filter((p): p is PlayerRecord => !!p)
    .map((p) => ({
      player_id: p.player_id,
      name: p.name,
      position: p.position,
      market_value: p.market_value,
      is_regular: p.starting_rank === 1 || p.starting_rank === 2,
    }));

  return POSITION_ORDER
    .map((position) => ({
      position,
      entries: entries
        .filter((e) => e.position === position)
        .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0)),
    }))
    .filter((group) => group.entries.length > 0);
}
```

### `LigaanalyseTab.tsx`

- `LigaanalyseCard` bekommt `onClick`, öffnet Detail-Modal (State `selected: LigaanalyseRow | null` in der Elternkomponente, gleiches Pattern wie `SpekulationTab`/`TransfermarktTab`).
- Neues `LigaanalyseDetailModal` (Aufbau 1:1 nach `SpekulationDetailModal`-Vorlage: `useEffect`-Escape-Handler, `fixed inset-0`-Overlay, `onClick`-Stop-Propagation-Card):
  - **Header:** Name, `Badge tone="good"` "ich" falls `row.is_self`, darunter kurz `Row`-Zeilen für Platz (`season_placement`), Punkte (`season_points`), Budget (`row.is_self ? "Budget" : "Budget (geschätzt)"` → `estimated_budget`) — bewusst nur diese drei, nicht die volle Karten-Liste (Kadergröße/Kaderwert/Verkaufsangebote/Stammspieler-Zahl bleiben auf der Karte, keine Duplizierung im Modal-Header).
  - **Kaderliste:** `groupSquadByPosition(row.squad_player_ids, data.players)` → pro Positions-Gruppe eine kleine Überschrift (`POSITION_ABBR`-Label wie in anderen Tabs) und darunter je Spieler eine Zeile mit Name, Marktwert (`fmtNum`), Stammspieler-Badge (`is_regular` → `Badge tone="good"`, sonst kein Badge).
  - **Leerfall:** `groupSquadByPosition(...)` liefert `[]` → Text "Keine Kaderdaten verfügbar" statt leerer Liste (deckt sowohl echten Fetch-Fehler als auch — theoretisch — einen leeren Kader ab; keine Unterscheidung nötig, siehe Edge Cases).

## Edge Cases

- **`squad_player_ids` leer** (Fetch-Fehler oder echter Leer-Kader): "Keine Kaderdaten verfügbar" im Modal, kein Crash.
- **ID ohne Treffer in `data.players`:** wird von `groupSquadByPosition()` stillschweigend übersprungen (sollte praktisch nicht vorkommen, da `players_map` alle Kickbase-Spieler enthält — defensiv trotzdem, kein `!` non-null assertion).
- **Neues Feld während Deploy-Fenster fehlt** (bekanntes Muster aus dem White-Screen-Vorfall, siehe HANDOFF.md): `row.squad_player_ids ?? []` an der einzigen Konsumstelle in `LigaanalyseDetailModal`.

## Out of Scope

- Keine Sortierung/Filterung *innerhalb* des Modals (kein Suchfeld, keine Tabelle) — reine Leseansicht.
- Keine zusätzlichen Spieler-Attribute (Punkteschnitt, ML-Prognose, Trend) in der Kaderliste — explizit nicht gewünscht (siehe Q&A).
- Keine Änderung an der bestehenden Karten-Ansicht selbst außer Klickbarkeit.

## Self-Review

- **Platzhalter-Scan:** keine TBD/offenen Stellen.
- **Konsistenz:** `squad_player_ids` durchgängig gleich benannt zwischen Backend-Abschnitt und Frontend-Abschnitt. `groupSquadByPosition()`-Signatur passt zu dem, was `LigaanalyseDetailModal` konsumiert.
- **Abgrenzung zum Gebotsvorschläge-Plan:** beide ändern `_build_ligaanalyse()`, aber an unabhängigen Stellen (neues Feld pro Row vs. neues `position_need`-Aggregat) — keine inhaltliche Kollision, nur ein textueller Merge-Punkt falls beide Branches gleichzeitig offen sind.
