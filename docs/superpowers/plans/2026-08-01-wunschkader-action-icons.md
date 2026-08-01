# Wunschkader-Aktions-Buttons mit Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die 3 Aktions-Buttons in `WunschkaderTab.tsx`s `DetailModal` (Bank/Startelf-Toggle, Wechsel, Entfernen) bekommen je ein Icon vor einem auf ein Wort gekürzten Text.

**Architecture:** 4 neue Icons in `frontend/src/components/icons.tsx`, exakt nach dem bestehenden Muster der 9 vorhandenen Icons (reine SVG-Pfad-Geometrie, `fill="currentColor"`). `WunschkaderTab.tsx` importiert sie und ergänzt sie in den bestehenden Button-JSX-Block, Callbacks/Logik unverändert.

**Tech Stack:** React/TypeScript, kein neues Package. Kein Test-Framework fürs Frontend (etabliert) — Verifikation über `tsc --noEmit` + manuellen Browser-Check durch den User.

## Global Constraints

- Icon + Text (nicht reine Icons) — Text auf ein Wort gekürzt ("Bank"/"Startelf" statt "Auf Bank verschieben"/"In Startelf verschieben"; "Wechsel"/"Entfernen" waren schon je ein Wort).
- Alle Icons nutzen `fill="currentColor"` (keine hartcodierte Farbe) — erben Light/Dark-Mode-Textfarbe automatisch, wie die bestehenden 9 Icons.
- Keine Änderung an Button-Logik/Callbacks (`onToggleBench`/`onReplace` via `setWechselOpen`/`onRemove`) — reine visuelle Ergänzung.
- Nach JEDEM Task: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` muss weiterhin fehlerfrei durchlaufen.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`) - Repo-Owner pusht selbst.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/components/icons.tsx` | 4 neue Icon-Komponenten ergänzt |
| `frontend/src/components/WunschkaderTab.tsx` | 3 Aktions-Buttons bekommen Icon + gekürzten Text |

---

## Task 1: 4 neue Icons in `icons.tsx`

**Files:**
- Modify: `frontend/src/components/icons.tsx`

**Interfaces:**
- Produces: `IconActionBank`, `IconActionField`, `IconActionSwap`, `IconActionTrash` (alle `(props: SVGProps<SVGSVGElement>) => JSX.Element`, exportiert). Konsumiert von Task 2.

- [ ] **Step 1: Icons ergänzen**

Am Ende von `frontend/src/components/icons.tsx` (nach der bestehenden `IconEmptyState`-Funktion) ergänzen:

```tsx
export function IconActionBank(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Bank" {...props}>
      <path d="M4 8 H20 V9.5 H4 Z" />
      <path d="M3 13 H21 V14.5 H3 Z" />
      <path d="M4.5 9.5 H6 V13 H4.5 Z" />
      <path d="M18 9.5 H19.5 V13 H18 Z" />
      <path d="M4.5 14.5 H6 V20 H4.5 Z" />
      <path d="M18 14.5 H19.5 V20 H18 Z" />
    </svg>
  );
}

export function IconActionField(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Startelf" {...props}>
      <path fillRule="evenodd" clipRule="evenodd" d="M2.8 4.4 H21.2 V19.6 H2.8 Z M4 5.6 H20 V18.4 H4 Z" />
      <path d="M11.4 5.6 H12.6 V18.4 H11.4 Z" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 9.8 A2.2 2.2 0 1 1 12 14.2 A2.2 2.2 0 1 1 12 9.8 Z M12 10.8 A1.2 1.2 0 1 1 12 13.2 A1.2 1.2 0 1 1 12 10.8 Z"
      />
    </svg>
  );
}

export function IconActionSwap(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Wechseln" {...props}>
      <path d="M12 3.4 A8.6 8.6 0 0 1 20.2 10.4 L18.1 9.7 A6.5 6.5 0 0 0 12 5.4 Z" />
      <path d="M17.2 7.3 L21.4 8.7 L20.2 12.9 Z" />
      <path d="M12 20.6 A8.6 8.6 0 0 1 3.8 13.6 L5.9 14.3 A6.5 6.5 0 0 0 12 18.6 Z" />
      <path d="M6.8 16.7 L2.6 15.3 L3.8 11.1 Z" />
    </svg>
  );
}

export function IconActionTrash(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Entfernen" {...props}>
      <path d="M9.5 3.5 H14.5 V5 H9.5 Z" />
      <path d="M4.5 5 H19.5 V6.5 H4.5 Z" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M6.3 7 H17.7 L16.7 20.2 A1.4 1.4 0 0 1 15.3 21.5 H8.7 A1.4 1.4 0 0 1 7.3 20.2 Z M9.6 9.5 H10.9 V19 H9.6 Z M13.1 9.5 H14.4 V19 H13.1 Z"
      />
    </svg>
  );
}
```

(`SVGProps` ist schon oben in der Datei importiert (`import type { SVGProps } from "react";`) — kein neuer Import nötig.)

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/icons.tsx
git commit -m "icons.tsx: 4 neue Aktions-Icons (Bank/Startelf/Wechsel/Entfernen)"
```

---

## Task 2: Icons in `WunschkaderTab.tsx`s Aktions-Buttons verdrahten

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `IconActionBank`, `IconActionField`, `IconActionSwap`, `IconActionTrash` (Task 1).

- [ ] **Step 1: Import ergänzen**

In `frontend/src/components/WunschkaderTab.tsx`, nach der bestehenden Zeile `import PlayerCompareModal from "./PlayerCompareModal";` (Zeile 11) ergänzen:

```ts
import { IconActionBank, IconActionField, IconActionSwap, IconActionTrash } from "./icons";
```

- [ ] **Step 2: Die 3 Buttons ersetzen**

Der bestehende Block (aktuell Zeilen 535-557):

```tsx
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onToggleBench}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isBench(target) ? "In Startelf verschieben" : "Auf Bank verschieben"}
          </button>
          <button
            type="button"
            onClick={() => setWechselOpen((v) => !v)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Wechsel
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
          >
            Entfernen
          </button>
        </div>
```

ersetzen durch:

```tsx
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onToggleBench}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isBench(target) ? (
              <>
                <IconActionField className="h-4 w-4" />
                Startelf
              </>
            ) : (
              <>
                <IconActionBank className="h-4 w-4" />
                Bank
              </>
            )}
          </button>
          <button
            type="button"
            onClick={() => setWechselOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <IconActionSwap className="h-4 w-4" />
            Wechsel
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="flex items-center gap-1.5 rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
          >
            <IconActionTrash className="h-4 w-4" />
            Entfernen
          </button>
        </div>
```

(Nur `className` bekommt zusätzlich `flex items-center gap-1.5` für die Icon+Text-Ausrichtung — Rahmen/Padding/Farben aller 3 Buttons bleiben exakt wie vorher. `onClick`-Handler unverändert.)

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: Icons + gekuerzter Text fuer Bank/Startelf/Wechsel/Entfernen-Buttons"
```

---

## Nach diesem Plan (kein Task — manueller Schritt)

- [ ] Browser-Test durch den User (Sandbox kann kein `npm run dev`): alle 3 Buttons zeigen Icon+Text; Toggle-Button zeigt `IconActionField`+"Startelf" wenn das Ziel auf der Bank ist, sonst `IconActionBank`+"Bank"; Icons erben die Textfarbe korrekt in Light/Dark-Mode. Falls ein Icon optisch nicht überzeugt (v.a. `IconActionSwap`s Bogen-Pfeile, ohne Vorschau blind konstruiert) — Rückmeldung geben, Pfad-Werte sind isoliert in Task 1 leicht nachjustierbar.

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: alle 4 Icons + Verdrahtung an allen 3 Buttons + Text-Kürzung sind abgedeckt (Task 1 + Task 2).
- **Platzhalter-Scan**: keine TBD/"analog zu"-ohne-Code gefunden — vollständiger SVG-Code für alle 4 Icons ausgeschrieben.
- **Typ-Konsistenz**: Icon-Namen (`IconActionBank`/`IconActionField`/`IconActionSwap`/`IconActionTrash`) identisch zwischen Task 1 (Definition) und Task 2 (Import + Nutzung).
- **Gegen den echten Code verifiziert**: `icons.tsx`s bestehende Icons (`IconPositionTorwart`/`IconPositionSturm`/`IconPositionMittelfeld`) wurden für Stil/Technik-Referenz vollständig gelesen (Rechteck-Pfade, `evenodd`-Ringe/Aussparungen). `WunschkaderTab.tsx`s Button-Block wurde exakt an der aktuellen Zeile (535-557, main-Stand) gelesen, nicht aus Erinnerung übernommen. `IconActionSwap`s Bogen-Pfade sind eine plausible, aber ohne visuelle Vorschau konstruierte Näherung — explizit im "Nach diesem Plan"-Abschnitt als der eine Punkt markiert, der beim Browser-Test am ehesten Nachschärfen braucht.
