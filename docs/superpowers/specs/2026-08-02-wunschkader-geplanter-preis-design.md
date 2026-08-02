# Wunschkader "Geplanter Preis" live berechnen — Design

**Feedback-Quelle:** `feedback/current` Item `297fc4aa` (2026-08-02): "Im Wunschkader müsste sich der Geplante Preis auch immer live berechnen, es sollten ja pauschal einfach mal 10% Aufpreis sein, theoretisch könnten wir als geplanten Preis auch die Empfehlung nehmen und dann würde ich dort den 75% Schwellenwert nehmen."

## Kontext

`plannedPriceFor()` (`frontend/src/lib/derive.ts:67-71`) berechnet den "Geplanter Preis" pro Wunschkader-Ziel. Aktuelles Verhalten (bereits live, nicht statisch — die Feedback-Formulierung "live berechnen" trifft nicht den eigentlichen Kern, siehe unten):

```ts
export function plannedPriceFor(marketValue: number | null, isOwn: boolean, liveBid: number | null): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  return marketValue;
}
```

Das eigentliche Problem: **kein Aufschlag im dritten Fall.** Wenn kein eigenes laufendes Gebot existiert, wird der reine Marktwert angesetzt — kein "10% Aufpreis" wie in der Rückfrage-Antwort erwähnt (der existiert im Code gar nicht, war eine Fehlannahme über den Ist-Stand). Zwei Aufrufstellen nutzen diese Funktion:
- `WunschkaderTab.tsx:197` — Einzelpreis-Anzeige in der geöffneten Detailansicht.
- `derive.ts:403` (innerhalb `buildBudgetPlan()`) — Summe über ALLE Ziele für die "Eingeplant"-Zeile der Budget-Übersicht.

`suggestBid()` (`derive.ts:429-455`) existiert bereits, live verifiziert, aktuell genutzt in Transfermarkt/Spekulation für Systemangebote: nimmt `{position, market_value, average_points}` + `bid_premium_history` (Ähnlichkeits-gewichtete historische Aufschlags-Perzentile derselben Position), gibt `{p50, p75, p90, n}` zurück oder `null` falls keine historischen Käufe dieser Position existieren. `bid_premium_history` liegt am Snapshot-Root (`data.bid_premium_history`); `WunschkaderTab` erhält bereits die komplette `data`-Prop (`App.tsx:355`) — **keine neue Prop-Verdrahtung auf App.tsx-Ebene nötig**, nur `data.bid_premium_history ?? []` innerhalb `WunschkaderTab.tsx` lesen, exakt wie `TransfermarktTab.tsx` es bereits tut.

## Entscheidungen (aus Rückfrage-Dialog, 2026-08-02)

- **p75 aus `suggestBid()` statt neuer flacher +10%-Logik.** Wiederverwendung der bereits live-verifizierten Perzentil-Schätzung statt einer geratenen Pauschale — reale Aufschläge streuen laut bestehender Gebotstracking-Historie deutlich, je nach Position.
- **Wirkt konsistent auch auf die Budget-"Eingeplant"-Summe**, nicht nur auf die angezeigte Einzelzahl — bewusste Entscheidung für genauere Budgetplanung, auch wenn sich dadurch bestehende Summen-Werte verschieben.
- **Niedrige Datenbasis: bestehende Konvention übernehmen, keine neue erfinden.** Transfermarkt/Spekulation zeigen bei `suggestion.n < MIN_N_FOR_PERCENTILE_SPREAD` (= 6) bereits `"(geringe Datenbasis, n=X)"` statt eines anderen Fallbacks — dasselbe Muster gilt hier.

## Architektur

**Signaturänderung `plannedPriceFor()`:** nimmt statt `marketValue: number | null` jetzt das volle Player-Objekt (`{market_value, position, average_points}`) plus `bidHistory`, da `suggestBid()` mehr als nur den Marktwert braucht. Beide bestehenden Aufrufstellen haben den vollen `PlayerRecord` bereits vorliegen — die Signaturänderung vereinfacht sie eher, als sie zu verkomplizieren (kein separates Herausziehen von `marketValue` mehr nötig).

```ts
export function plannedPriceFor(
  player: { market_value: number | null; position: string; average_points: number | null },
  isOwn: boolean,
  liveBid: number | null,
  bidHistory: BidPremiumEntry[]
): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  const suggestion = suggestBid(player, bidHistory);
  if (suggestion !== null) return suggestion.p75;
  return player.market_value;
}
```

**`buildBudgetPlan()`** (`derive.ts:375-408`) bekommt einen neuen Pflicht-Param `bidHistory: BidPremiumEntry[]` im Params-Objekt, durchgereicht an den `plannedPriceFor()`-Aufruf innerhalb der `committed`-Reduce (Zeile 403).

**`WunschkaderTab.tsx`** — zwei Anpassungen:
1. Der `buildBudgetPlan({...})`-Aufruf (Zeile 148) bekommt `bidHistory: data.bid_premium_history ?? []` ergänzt.
2. Die separate `selectedPlannedPrice`-Berechnung (Zeile 186-197, für die Detailansicht — bewusst separat von `buildBudgetPlan()`, da letztere nur summiert, nicht pro Ziel exponiert) ruft `plannedPriceFor()` jetzt mit dem vollen Player-Objekt + `data.bid_premium_history ?? []` auf.

**Anzeige-Erweiterung** (`WunschkaderTab.tsx:554`, `<Row label="Geplanter Preis">`): da der Wert jetzt teils eine echte Zahl (liveBid), teils eine Schätzung (p75) ist, wird die Zeile um einen Zusatz erweitert, analog zur bestehenden Transfermarkt/Spekulation-Konvention:
- `isOwn` (0) oder `liveBid` vorhanden → unverändert, reine Zahl, kein Zusatz (ist eine echte Zahl, keine Schätzung).
- `suggestBid()`-Ergebnis mit `n >= MIN_N_FOR_PERCENTILE_SPREAD` → `"{Zahl} (Schätzung)"`.
- `suggestBid()`-Ergebnis mit `n < MIN_N_FOR_PERCENTILE_SPREAD` → `"{Zahl} (geringe Datenbasis, n={n})"` — identischer Text wie in Transfermarkt/Spekulation, ersetzt den `"(Schätzung)"`-Zusatz (impliziert Schätzung bereits).
- Kein `suggestBid()`-Ergebnis (keine Historie dieser Position) → unverändert, reiner Marktwert, kein Zusatz (heutiges Verhalten für diesen Fall bleibt unkommentiert, wie bisher).

Um diese vier Fälle zu unterscheiden, braucht die Anzeige-Stelle Zugriff auf das rohe `suggestBid()`-Ergebnis (nicht nur den finalen Preis) — `selectedPlannedPrice` wird daher von einer einzelnen Zahl zu einem kleinen Objekt `{ price: number | null; isEstimate: boolean; suggestionN: number | null }`, lokal in `WunschkaderTab.tsx` zusammengebaut (kein neuer Export in `derive.ts` nötig, reine Anzeige-Aufbereitung).

## Datenfluss

```
data.bid_premium_history (Snapshot-Root, bereits vorhanden)
  │
  ├─ WunschkaderTab.tsx: buildBudgetPlan({ ..., bidHistory: data.bid_premium_history ?? [] })
  │     └─ committed = Σ plannedPriceFor(player, isOwn, liveBid, bidHistory) über alle Ziele
  │
  └─ WunschkaderTab.tsx: selectedPlannedPrice (Detailansicht, einzelnes Ziel)
        └─ plannedPriceFor(selectedPlayer, isOwn, liveBid, data.bid_premium_history ?? [])
        └─ zusaetzlich: suggestBid(selectedPlayer, bidHistory) direkt aufgerufen fuer isEstimate/suggestionN
```

## Fehlerfälle

- **Ziel-Spieler ohne `position`/`average_points`** (sollte laut `PlayerRecord`-Typ nicht vorkommen, `position` ist non-optional, `average_points` ist `number | null` — bereits von `suggestBid()` intern über `pts = listing.average_points || 0` abgefangen) — kein neuer Fehlerfall.
- **`bid_premium_history` leer/fehlt** (Cold-Start, ganz frisches Setup ohne Kaufhistorie) — `data.bid_premium_history ?? []`, `suggestBid()` gibt dann für jede Position `null` zurück (leeres `samePosition`-Array) → Fallback auf Marktwert greift, identisch zum heutigen Verhalten. Kein Sonderfall nötig.
- **`isOwn === true`** — unverändert Priorität 1, `suggestBid()` wird gar nicht aufgerufen (kurze Rückgabe vor dem restlichen Code).

## Testing

`derive.test.ts` (bereits vorhanden aus der vorherigen Session) bekommt neue `describe("plannedPriceFor")`-Fälle:
- `isOwn === true` → `0`, unabhängig von allen anderen Parametern.
- `liveBid` gesetzt → gewinnt gegenüber einer vorhandenen `suggestBid()`-Historie (liveBid hat Vorrang).
- Kein `liveBid`, passende Historie vorhanden → Ergebnis entspricht `suggestBid(...).p75`.
- Kein `liveBid`, keine Historie für diese Position → Fallback auf `market_value`.

Die vier UI-Textvarianten (`""`/`"(Schätzung)"`/`"(geringe Datenbasis, n=X)"`) sind reine Anzeige-Logik in `WunschkaderTab.tsx` — kein neuer Test nötig, Verifikation über `npm run typecheck` + `npm run build` wie bei den rein-präsentativen Tasks der letzten Session.

## Betroffene Dateien

- Modify: `frontend/src/lib/derive.ts` (`plannedPriceFor()`-Signatur, `buildBudgetPlan()`-Param)
- Modify: `frontend/src/lib/derive.test.ts` (neue Testfälle)
- Modify: `frontend/src/components/WunschkaderTab.tsx` (beide Aufrufstellen + Anzeige-Erweiterung)

## Out of Scope

- Keine neue Chart-/UI-Komponente — reine Logik- und Anzeige-Erweiterung bestehender Stellen.
- `EigenesTeamTab.tsx` ruft `buildBudgetPlan()` nicht selbst auf (nur `WunschkaderTab.tsx` tut das) — keine Änderung dort nötig.
- Keine Änderung an `suggestBid()` selbst oder an dessen bestehender Nutzung in Transfermarkt/Spekulation.
