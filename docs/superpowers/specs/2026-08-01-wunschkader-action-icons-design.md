# Wunschkader-Aktions-Buttons mit Icons — Design

## Context

Feedback-Eintrag (`feedback/current`, 2026-08-01): "Bei Wunschkader für die Buttons vielleicht einfach icons nutzen, bank für bank, Kreis mit Pfeilen für Wechsel, Papierkorb für entfernen. Startelf braucht eine idee." Betrifft die 3 Aktions-Buttons in `WunschkaderTab.tsx`s `DetailModal` (aktuell reiner Text): Bank/Startelf-Toggle ("Auf Bank verschieben"/"In Startelf verschieben"), "Wechsel", "Entfernen".

Die App hat bereits ein Icon-System (`frontend/src/components/icons.tsx`, 9 handgeschriebene React-SVG-Komponenten, `viewBox="0 0 24 24" fill="currentColor"`) für Positions-/Fitness-Icons (`POSITION_ICON`/`STATUS_ICON` in `ui.tsx`) — keines davon passt für diese 4 Aktionen, alle vier brauchen neue Icons nach demselben Muster.

## Klärung (per Rückfrage)

- **Icon + Text, Text auf ein Wort gekürzt** (nicht reine Icons) — konsistent mit dem bestehenden `PositionBadge`/`FitnessBadge`-Muster (Icon+Text kombiniert). Text kann später weiter gekürzt/entfernt werden, sobald die Icons allein eindeutig genug sind.
- **"Startelf"-Icon**: eine kleine Fußballfeld-Silhouette (Rahmen + Mittellinie + Mittelkreis) — direktes visuelles Gegenstück zum Bank-Icon (Feld = im Spiel, Bank = draußen).

## Architektur

**4 neue Icons in `frontend/src/components/icons.tsx`**, exakt nach dem bestehenden Muster (reine Pfad-Geometrie, `fill="currentColor"`, `role="img"` + `aria-label`):
- `IconActionBank` — Bank-Seitenansicht (Lehne, 2 Stützen, Sitzfläche, 2 Beine — Rechteck-Pfade wie `IconPositionTorwart`s Torpfosten-Technik).
- `IconActionField` — Feld-Silhouette (Rahmen via `evenodd`-Doppelrechteck, Mittellinie, Mittelkreis via `evenodd`-Ring wie `IconPositionSturm`s Ballring).
- `IconActionSwap` — zwei gegenläufige Kreisbogen-Pfeile (Wechsel-Symbol).
- `IconActionTrash` — Mülleimer (Henkel, Deckel, Korpus mit `evenodd`-Rippen-Aussparungen wie `IconPositionMittelfeld`s Zahlen-Technik).

**`WunschkaderTab.tsx`s `DetailModal`-Aktions-Buttons** (aktuell `Zeile 535-557`) bekommen je ein Icon vor dem (gekürzten) Text:
- Toggle-Button: Icon wechselt mit dem Zustand wie der Text es heute schon tut — `IconActionField`+"Startelf" wenn `isBench(target)` (Aktion: zurück in die Startelf), sonst `IconActionBank`+"Bank" (Aktion: auf die Bank).
- "Wechsel"-Button: `IconActionSwap`+"Wechsel" (Text unverändert, war schon ein Wort).
- "Entfernen"-Button: `IconActionTrash`+"Entfernen" (Text unverändert, war schon ein Wort).

## Nicht-Ziele

- Keine Änderung an der Button-Logik/den Callbacks (`onToggleBench`/`onReplace`/`onRemove` unverändert) — reine visuelle Ergänzung.
- Keine reinen Icon-Buttons (per Klärung ausdrücklich zurückgestellt).
- Keine Icons für die Freitext-Suche/Vorschlag-Chips im "Wechsel"-Aufklapp-Bereich — nur die 3 obersten Aktions-Buttons.

## Verification

- `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` — 0 Fehler.
- Manueller Check (User, Sandbox kann kein `npm run dev`): alle 3 Buttons zeigen Icon+Text; Toggle-Button zeigt das jeweils richtige Icon je nach Bank/Startelf-Zustand; Icons erben die Textfarbe korrekt in Light/Dark-Mode (kein hartcodierter Fill).
