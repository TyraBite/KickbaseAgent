# Tabellen/Karten-Toggle für Transfermarkt + Alle Spieler (+ Spekulation-Verbesserung) — Design

## Context

Feedback-Eintrag (`feedback/current`, 2026-08-01): "Transfermarkt und Alle Spieler auch Kartenansicht, hier auch togglebar. Auf dem Handy sind die Karten viel besser Desktop sind die Tabellen aber teilweise auch von Vorteil." `SpekulationTab.tsx` hat bereits genau so einen Toggle (`ViewMode = "cards" | "table"`), aber ohne automatische Bildschirmbreiten-Erkennung und ohne Persistenz (`useState<ViewMode>("cards")` — immer hart auf Karten, geht bei jedem Reload verloren). User-Wunsch bei der Klärung: dieselbe Verbesserung (Auto-Default + Merken) auch auf Spekulation nachziehen.

## Architektur

**Ein geteilter Hook `useViewMode(storageKey: string)`** (neu, `frontend/src/lib/useViewMode.ts`): beim ersten Mount `localStorage.getItem(storageKey)`; falls kein gespeicherter Wert vorhanden, einmaliger `window.matchMedia("(max-width: 639px)").matches`-Check (Tailwind-`sm`-Breakpoint, konsistent mit dem Rest der App) — `true` → `"cards"`, sonst `"table"`. Rückgabe `[viewMode, setViewMode]`, wobei `setViewMode` zusätzlich in `localStorage` schreibt. Kein Resize-Listener (YAGNI) — der Default wird einmal beim Laden bestimmt, danach zählt nur noch die manuelle/gespeicherte Wahl.

**Drei Tabs, ein Muster, je EIGENER Storage-Key** (kein geteilter globaler Zustand — Transfermarkt/Alle Spieler/Spekulation merken sich unabhängig voneinander):
- `SpekulationTab.tsx`: bestehendes `useState<ViewMode>("cards")` durch `useViewMode("kickbaseagent_view_spekulation")` ersetzen. Toggle-Buttons, `SpekulationCard`, `SpekulationTable` bleiben unverändert.
- `TransfermarktTab.tsx`: neuer `useViewMode("kickbaseagent_view_transfermarkt")`, gleiche Toggle-Button-UI (1:1 aus `SpekulationTab.tsx` übernommen), neue `TransfermarktCard`-Komponente.
- `AlleSpielerTab.tsx`: neuer `useViewMode("kickbaseagent_view_alle_spieler")`, gleiches Muster, neue `AlleSpielerCard`-Komponente.
- Karten-Klick ruft denselben `onSelect`/`setSelected`-Callback auf, der heute schon per Zeilen-Klick das bestehende Detail-Modal öffnet — keine neue Modal-Logik in diesem Vorhaben.

**Kartenfelder — kuratiert, nicht 1:1 alle Tabellenspalten** (Vorbild `SpekulationCard`: 5 von ~8 Tabellenspalten):
- `TransfermarktCard`: Preis, ML-Prognose, Signal, Trend 7T, Auktion, Gebotsempfehlung.
- `AlleSpielerCard`: Verfügbarkeit, Fitness, Schnitt, Signal, Marktwert.
- Beide Karten übernehmen den bestehenden Karten-Header-Stil (Vereinswappen + Name + Positions-Badge, siehe `SpekulationCard`s `CardHeader`) und dieselben Tailwind-Klassen für Karte/Grid (`rounded-2xl border ... hover:-translate-y-0.5 ...`, Grid `grid-cols-[repeat(auto-fill,minmax(260px,1fr))]`).

## Nicht-Ziele

- Keine neuen Felder/Daten — reine Layout-Alternative zu bereits vorhandenen Tabellenspalten.
- Kein geteilter/globaler Toggle-Zustand über alle drei Tabs hinweg.
- Kein Resize-Listener/dynamische Neubewertung während der Session.

## Verification

- `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` — 0 Fehler (kein Test-Framework fürs Frontend, etabliert).
- Manueller Check (User, Sandbox kann kein `npm run dev`): Handy-Breite → beide neuen Tabs UND Spekulation starten mit Karten; Desktop-Breite → alle drei starten mit Tabelle; manueller Toggle in jedem der drei Tabs bleibt nach Reload erhalten UND ist je Tab unabhängig (z.B. Transfermarkt auf Tabelle lassen, Alle Spieler auf Karten).
