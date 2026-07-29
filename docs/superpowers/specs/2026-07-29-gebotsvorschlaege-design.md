# Gebotsvorschläge für Kickbase-Systemangebote — Design

## Context

Kickbase-Systemangebote (freie Spieler, die Kickbase selbst zum Kauf anbietet) laufen als **blindes Sealed-Bid-Auktionsverfahren**: mehrere Manager können innerhalb der Angebotsfrist (`expires_at`) ein Gebot abgeben, das höchste gewinnt. Während der Frist ist für niemanden sichtbar, ob und wie viel andere Manager bieten — man sieht nur das eigene Gebot, und rückwirkend (über die Kickbase-Aktivitäten-Historie) den tatsächlichen Gewinnbetrag abgeschlossener Käufe. Aktuell hat der User keine Entscheidungsgrundlage dafür, wie viel er bieten muss, um einen bestimmten Spieler mit einiger Sicherheit zu gewinnen, statt entweder zu wenig zu bieten (verliert) oder unnötig viel zu bieten (verschwendet Budget).

**Ziel**: eine Gebotsempfehlung mit mehreren Sicherheits-Schwellen ("biete mind. X für ~Y% historische Erfolgsquote"), basierend auf tatsächlich abgeschlossenen Käufen dieser Liga.

**Explizit außen vor**: Mitspieler-Angebote (echte Verhandlung zwischen zwei Managern, komplett anderer Mechanismus, keine Historie mit vergleichbarer Aussagekraft).

## Datengrundlage (verifiziert, 2026-07-29)

Der Kickbase-Aktivitäten-Feed (`get_activities_feed`, wird pro Lauf ohnehin schon für die Budget-Schätzung gefetcht) enthält Typ-15-Trade-Einträge mit `data: {byr, slr, trp, pi, pn, tid, ...}`. Fehlt `slr` (Verkäufer), war es ein **Systemkauf** — `byr` = Käufer, `trp` = gezahlter Preis, `pi`/`pn` = Spieler-Id/Name. Live-Check dieser Liga: **321 Aktivitäten, 227 Trades, davon 104 Systemkäufe**. Der Feed enthält NICHT den Marktwert des Spielers zum Kaufzeitpunkt — der lässt sich aber über `get_market_value_history()` (bereits für den 7-Tage-Trend genutzt) nachträglich pro Spieler auflösen.

## Datenpipeline

### Backfill (einmalig)

Neues, einmaliges Skript (Muster wie `src/migrate_wunschkader_player_ids.py` — nach Gebrauch löschbar):

1. `get_activities_feed()` lesen, auf Systemkäufe filtern (`slr` fehlt).
2. Pro Kauf: `get_market_value_history(token, league_id, player_id)` aufrufen, Marktwert zum Kaufdatum (`dt` des Activity-Eintrags) aus der Historie herauslesen.
3. Aufschlag% = `trp / marktwert_damals - 1` berechnen.
4. Ein Firestore-Doc pro Kauf in neue Collection `bid_premium_log` schreiben, gekeyt über die Activity-Id (verhindert Doppel-Verarbeitung), Muster wie `ml_prediction_log`. Feld-Inhalt: `player_id, position, market_value_then, average_points_then, premium_pct, purchased_at`.

Kosten: ~104 zusätzliche Kickbase-Calls + ~104 Firestore-Writes, einmalig.

### Laufendes Update (im bestehenden 2h-Light-Cron, `dashboard.yml`)

- Activity-Feed wird pro Lauf ohnehin gefetcht (kein neuer Call).
- Ein kleiner Zeiger (letzte verarbeitete Activity-Id, 1 Firestore-Read) markiert, bis wohin `bid_premium_log` aktuell ist.
- Nur echte neue Systemkäufe seit dem Zeiger werden verarbeitet (Normalfall: 0, selten 1-2 pro 2h-Fenster) — für jeden davon 1 `get_market_value_history()`-Call + 1 Firestore-Write, dann Zeiger aktualisieren.
- Ein einzelner fehlgeschlagener `get_market_value_history()`-Call bricht die Verarbeitung der übrigen neuen Käufe nicht ab (try/except pro Kauf, Muster wie `_apply_market_value_history` in `src/fetcher.py`) — Warnung loggen, diesen einen Kauf beim nächsten Lauf erneut versuchen (Zeiger nur bei Erfolg weiterschieben).

### Speicherung im Snapshot

Die rohen Einträge aus `bid_premium_log` (Position, Marktwert-damals, Punkteschnitt-damals, Aufschlag%) werden als kompaktes Array direkt ins bestehende `dashboard_snapshot`-Dokument aufgenommen (neues Feld, z.B. `bid_premium_history`) — bei aktuell ~104 Einträgen mit 4 kleinen Feldern nur wenige KB, kein zusätzlicher Client-Read nötig (der Client liest den Snapshot ohnehin einmal pro Seitenaufruf). Keine eigene Firestore-Collection wird an den Client exponiert — `bid_premium_log` bleibt rein backend-intern (Rohdaten-Historie + Dedup-Schutz), der Snapshot bekommt nur die für die Client-Berechnung nötigen Felder.

## Client-seitige Berechnung (`frontend/src/lib/derive.ts`)

Bewusst **keine** serverseitig vorgerechneten Perzentil-Schwellen (ursprünglich erwogen, dann verworfen): starre Buckets (z.B. Position × Marktwert-Klasse) zerschneiden die ~104 Samples zu fein für verlässliche Perzentile. Stattdessen: **Ähnlichkeits-gewichtete Perzentile pro Anfrage**, mit der bereits im Code etablierten Distanzformel aus `scoreReplacementPool()` (`WunschkaderTab.tsx`, wandert im players-Map-Redesign nach `derive.ts`):

```ts
function suggestBid(
  listing: { position: string; market_value: number; average_points: number | null },
  history: BidPremiumEntry[],
  k = 20
): { p50: number; p75: number; p90: number; n: number } | null {
  const samePosition = history.filter((h) => h.position === listing.position);
  if (samePosition.length === 0) return null;
  const mv = listing.market_value || 0;
  const pts = listing.average_points || 0;
  const ranked = samePosition
    .map((h) => ({
      ...h,
      distance:
        (mv ? Math.abs(h.market_value_then - mv) / mv : 0) +
        (pts ? Math.abs((h.average_points_then || 0) - pts) / pts : 0),
    }))
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

`n` (tatsächlich genutzte Vergleichskäufe, ≤ k) wird immer mit angezeigt — Transparenz bei kleiner Stichprobe statt falscher Präzision.

**Wichtiges Framing für die UI**: das ist ein historischer Vergleichswert ("bei N ähnlichen Käufen hätte dieser Betrag gereicht"), **keine echte Erfolgswahrscheinlichkeit dieser einen Auktion** — echte Konkurrenzgebote sind wegen des blinden Verfahrens grundsätzlich nie beobachtbar. Muss so kommuniziert werden (z.B. "historisch ausreichend bei N/A Vergleichskäufen"), nicht als Garantie.

## UI-Platzierung

- **Transfermarkt-Tab**: neue Tabellenspalte "Gebotsempfehlung" zeigt die 75%-Schwelle auf einen Blick; bei Mitspieler-Angeboten `n/v` (etabliertes Platzhalter-Muster, wie schon bei `starting_rank`). Klick auf eine Zeile öffnet ein neues Detail-Modal (neu für diesen Tab, Muster wie die bestehenden Detail-Modals in `EigenesTeamTab`/`WunschkaderTab`/`SpekulationTab`) mit allen drei Schwellen (50/75/90%) + `n`.
- **Spekulation-Tab**: das bestehende `SpekulationDetailModal` bekommt denselben Abschnitt (alle Zeilen dort sind ohnehin Systemangebote, nie `n/v`). Keine neue Spalte/Kachel-Feld hier — nur die Detailansicht.

## Testing

- Backend (Backfill + laufendes Update): TDD wie gewohnt (`unittest`, gemockte `get_activities_feed`/`get_market_value_history`/Firestore) — Tests für: Systemkauf-Filter (kein `slr`), Aufschlag-Berechnung, Zeiger-Fortschreibung nur bei Erfolg, Fehlerresistenz bei einem fehlschlagenden Einzel-Call.
- Frontend (`suggestBid()` in `derive.ts`): kein Test-Framework im Projekt vorhanden (Konvention dieser Session) — Verifikation über `tsc --noEmit` + manuelle Prüfung mit echten Daten nach Implementierung.

## Out of Scope / Spätere Ideen (nicht Teil dieser Runde)

- **Budget-Cross-Check der Konkurrenz** (erwogen, dann verworfen): Hinweis wie "X von Y Managern könnten laut verfügbarem Budget mehr bieten" wäre mit den schon vorhandenen `ligaanalyse`-Daten (`available_budget` pro Manager) ohne neue Felder machbar, wurde aber zurückgestellt — sagt nichts über tatsächliches Interesse am Spieler aus, nur über die theoretische Fähigkeit zu überbieten.
- **Positions-Bedarfs-Analyse über die Liga** (User-Idee, 2026-07-29): der tatsächliche Aufschlag für einen freien Spieler dürfte auch davon abhängen, wie viele Gegner-Kader für diese Position bereits einen Stammspieler haben. Beispiel Torwart: haben schon alle Gegner einen planmäßigen Stamm-Torwart, ist die Konkurrenz um einen neuen Torwart auf dem Markt vermutlich geringer, als wenn die meisten noch einen brauchen. Für Torwart (nur 1 Startplatz, klar abgrenzbar) relativ einfach zu modellieren; für die anderen Positionen (Abwehr/Mittelfeld/Sturm, mehrere Plätze + Rotation) deutlich komplexer, da "Bedarf" dort weniger eindeutig ist als ein einzelner Stammplatz. Explizit als eigene, spätere Erweiterung vorgemerkt — nicht Teil dieser ersten Umsetzung, würde eine eigene Analyse/Planung brauchen (z.B. auf Basis von `_build_ligaanalyse()`s `regular_count`/`starting_rank`-Daten, die schon pro Gegner-Kader vorhanden sind).
