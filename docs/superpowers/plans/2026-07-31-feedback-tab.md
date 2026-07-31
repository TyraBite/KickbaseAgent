# Feedback-Tab (Bugs & Ideen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Neuer Tab "Bugs & Ideen" — schnelles Erfassungsformular (Typ + Text, speichert sofort) + editierbare Liste bisheriger Einträge, komplett frontend-seitig gegen eine neue Firestore-Collection `feedback/current`.

**Architecture:** Ein Firestore-Dokument `feedback/current` = `{ items: FeedbackItem[] }` (Array-in-Dokument, wie `wunschkader/current`s `targets`). Neue Komponente `FeedbackTab.tsx` liest/schreibt DIREKT gegen diese Collection (kein Umweg über `dashboard_snapshot`/Python-Backend). Firestore-Rules bekommen einen neuen Block, 1:1 identisch zum bestehenden `wunschkader`-Block (gleiche hart-codierte UID).

**Tech Stack:** React/TypeScript, Firebase Firestore Client SDK (`firebase/firestore`), Tailwind CSS.

## Global Constraints

- Kein Python-/Backend-Touch, kein neues `dashboard_snapshot`-Feld.
- Firestore-Rule für `feedback` exakt wie `wunschkader`: `allow read, write: if request.auth != null && request.auth.uid == "lC85qOItQ1M6bRjzqnYcgBkLVDF2";`.
- Neuer Eintrag speichert SOFORT (kein separater Speichern-Klick) — bestehender Eintrag wird über einen Speichern-Klick PRO Eintrag bearbeitet.
- Erledigte Einträge werden als `status: "done"` markiert, nie gelöscht.
- `FeedbackTab` funktioniert unabhängig vom Hauptsnapshot (`data`/`loadState` in `App.tsx`) — muss auch nutzbar sein, wenn der Haupt-Datenabruf noch lädt oder fehlgeschlagen ist.
- Kein Frontend-Test-Runner in diesem Projekt vorhanden (kein Jest/Vitest) — Verifikation ist `tsc --noEmit` + Live-Check nach dem Deploy. **Bekannte Sandbox-Einschränkung:** `npm run dev`/`npm run build` schlagen in dieser Sandbox mit `Cannot find module @rollup/rollup-linux-x64-gnu` fehl (node_modules über Windows-DrvFs-Mount geteilt, plattformfremdes Binary) - betrifft NICHT den GitHub-Actions-Build (frischer `npm ci` auf Linux-Runner), nur lokales Dev-Server-Testen in dieser Sandbox. Kein lokaler Browser-Test durch den Agenten möglich - Live-Verifikation nach Push/Deploy ist Aufgabe des Users.

---

## Task 1: Firestore-Rules für `feedback`-Collection

**Files:**
- Modify: `firestore.rules`

**Interfaces:**
- Produces: neue Collection `feedback` mit `read, write` für die eine bekannte UID — Voraussetzung für Task 2.

- [ ] **Step 1: Rule-Block ergänzen**

In `firestore.rules`, nach dem bestehenden `wunschkader`-Block (vor dem abschließenden Catch-all `match /{document=**} { allow read, write: if false; }`) einfügen:

```
    match /feedback/{document=**} {
      allow read, write: if request.auth != null
                         && request.auth.uid == "lC85qOItQ1M6bRjzqnYcgBkLVDF2";
    }
```

- [ ] **Step 2: Commit + Push (löst automatisches Rules-Deploy aus)**

```bash
git add firestore.rules
git commit -m "firestore.rules: feedback-Collection freigegeben (gleiche UID-Sperre wie wunschkader)"
git push origin main
```

- [ ] **Step 3: Deploy-Workflow verifizieren**

Run: `gh run list --workflow=firestore-rules-deploy.yml --limit 1` (ggf. `gh run watch <id>` falls noch am Laufen)
Expected: Lauf grün — Rules sind live, bevor Task 2 sie braucht.

---

## Task 2: `FeedbackTab`-Komponente + Einbindung

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/FeedbackTab.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `feedback`-Collection aus Task 1 (muss live sein, bevor dieser Task per Browser getestet werden kann — Code lässt sich aber unabhängig davon schreiben/typechecken).
- Produces: `FeedbackTab` (default export, Props `{ now: number }`), `FeedbackItem`-Typ in `types.ts`.

- [ ] **Step 1: `FeedbackItem`-Typ ergänzen**

In `frontend/src/types.ts`, nach `export type PositionNeed = Record<string, PositionNeedEntry>;` (vor `export interface DashboardSnapshot`) einfügen:

```ts
export interface FeedbackItem {
  id: string;
  type: "bug" | "feature";
  text: string;
  created_at: string; // ISO-Timestamp, new Date().toISOString()
  status: "open" | "done";
}
```

- [ ] **Step 2: `FeedbackTab.tsx` anlegen**

Neue Datei `frontend/src/components/FeedbackTab.tsx`:

```tsx
import { useEffect, useState } from "react";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import { formatRelativeTime } from "../lib/derive";
import type { FeedbackItem } from "../types";

type LoadState = "loading" | "error" | "ready";

const TYPE_LABEL: Record<FeedbackItem["type"], string> = {
  bug: "🐛 Bug",
  feature: "💡 Idee",
};

export default function FeedbackTab({ now }: { now: number }) {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [type, setType] = useState<FeedbackItem["type"]>("bug");
  const [text, setText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    getDoc(doc(db, "feedback", "current"))
      .then((snap) => {
        const data = snap.exists() ? (snap.data() as { items?: FeedbackItem[] }) : {};
        setItems(data.items ?? []);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, []);

  async function persist(next: FeedbackItem[]) {
    setItems(next);
    setSaveError("");
    try {
      await setDoc(doc(db, "feedback", "current"), { items: next });
    } catch (err) {
      setSaveError("Fehler beim Speichern: " + (err as Error).message);
    }
  }

  function handleAdd() {
    const trimmed = text.trim();
    if (!trimmed) return;
    const item: FeedbackItem = {
      id: crypto.randomUUID(),
      type,
      text: trimmed,
      created_at: new Date().toISOString(),
      status: "open",
    };
    persist([item, ...items]);
    setText("");
  }

  function startEdit(item: FeedbackItem) {
    setEditingId(item.id);
    setEditText(item.text);
  }

  function saveEdit() {
    if (!editingId) return;
    const trimmed = editText.trim();
    if (trimmed) {
      persist(items.map((i) => (i.id === editingId ? { ...i, text: trimmed } : i)));
    }
    setEditingId(null);
  }

  if (loadState === "loading") {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Lade Einträge…</p>;
  }
  if (loadState === "error") {
    return <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>;
  }

  const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const open = sorted.filter((i) => i.status === "open");
  const done = sorted.filter((i) => i.status === "done");

  return (
    <div className="max-w-2xl space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setType("bug")}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              type === "bug"
                ? "border-brand-500 bg-brand-50 font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            🐛 Bug
          </button>
          <button
            type="button"
            onClick={() => setType("feature")}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              type === "feature"
                ? "border-brand-500 bg-brand-50 font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            💡 Idee
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={1000}
          placeholder={type === "bug" ? "Was ist kaputt?" : "Was wäre hilfreich?"}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={!text.trim()}
          className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Hinzufügen
        </button>
        {saveError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{saveError}</p>}
      </div>

      <div className="space-y-2">
        {open.length === 0 && done.length === 0 && (
          <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine Einträge.</p>
        )}
        {open.map((item) => (
          <FeedbackRow
            key={item.id}
            item={item}
            now={now}
            isEditing={editingId === item.id}
            editText={editText}
            onEditTextChange={setEditText}
            onStartEdit={() => startEdit(item)}
            onSaveEdit={saveEdit}
          />
        ))}
        {done.length > 0 && (
          <details className="pt-2">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Erledigt ({done.length})
            </summary>
            <div className="mt-2 space-y-2 opacity-60">
              {done.map((item) => (
                <FeedbackRow
                  key={item.id}
                  item={item}
                  now={now}
                  isEditing={editingId === item.id}
                  editText={editText}
                  onEditTextChange={setEditText}
                  onStartEdit={() => startEdit(item)}
                  onSaveEdit={saveEdit}
                />
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function FeedbackRow({
  item,
  now,
  isEditing,
  editText,
  onEditTextChange,
  onStartEdit,
  onSaveEdit,
}: {
  item: FeedbackItem;
  now: number;
  isEditing: boolean;
  editText: string;
  onEditTextChange: (value: string) => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>{TYPE_LABEL[item.type]}</span>
        <span title={item.created_at}>{formatRelativeTime(item.created_at, new Date(now))}</span>
      </div>
      {isEditing ? (
        <div className="mt-2">
          <textarea
            value={editText}
            onChange={(e) => onEditTextChange(e.target.value)}
            rows={3}
            maxLength={1000}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <button
            type="button"
            onClick={onSaveEdit}
            className="mt-2 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Speichern
          </button>
        </div>
      ) : (
        <p
          onClick={onStartEdit}
          className="mt-1 cursor-pointer whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100"
        >
          {item.text}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: In `App.tsx` einbinden**

Import ergänzen (nach dem `WunschkaderTab`-Import):

```tsx
import FeedbackTab from "./components/FeedbackTab";
```

`TABS`-Array (Zeile ~31-39) — neuen Eintrag am Ende ergänzen:

```tsx
const TABS = [
  { key: "team", label: "Eigenes Team" },
  { key: "spekulation", label: "Spekulation" },
  { key: "wunschkader", label: "Wunschkader" },
  { key: "transfermarkt", label: "Transfermarkt" },
  { key: "liga", label: "Ligaanalyse" },
  { key: "alle-spieler", label: "Alle Spieler" },
  { key: "ml-genauigkeit", label: "Modell-Tracking" },
  { key: "feedback", label: "Bugs & Ideen" },
];
```

`ACTIVE_TABS` — `"feedback"` ergänzen:

```tsx
const ACTIVE_TABS = new Set([
  "spekulation",
  "wunschkader",
  "team",
  "alle-spieler",
  "transfermarkt",
  "liga",
  "ml-genauigkeit",
  "feedback",
]);
```

**Wichtig:** `FeedbackTab` darf NICHT wie die anderen Tabs an `loadState === "ready" && data` hängen (braucht `data` gar nicht) — sonst ist der Tab nicht nutzbar, während der Haupt-Snapshot noch lädt oder fehlgeschlagen ist. Die bestehenden `loadState === "loading"`/`"error"`-Absätze rendern aktuell UNABHÄNGIG vom `activeTab` (kein Hidden-Toggle) — ohne Anpassung würden sie zusätzlich zum Feedback-Tab-Inhalt eingeblendet bleiben. Ersetze:

```tsx
        {loadState === "loading" && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Lade Daten…</p>
        )}
        {loadState === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        )}
```

durch:

```tsx
        {loadState === "loading" && activeTab !== "feedback" && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Lade Daten…</p>
        )}
        {loadState === "error" && activeTab !== "feedback" && (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        )}
```

Nach dem letzten bestehenden Tab-Block (`ml-genauigkeit`, endet vor `</main>`) einen neuen, von `data`/`loadState` unabhängigen Block ergänzen:

```tsx
        <div className={activeTab === "feedback" ? "" : "hidden"}>
          <FeedbackTab now={now} />
        </div>
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 5: Commit + Push**

```bash
git add frontend/src/types.ts frontend/src/components/FeedbackTab.tsx frontend/src/App.tsx
git commit -m "Neuer Tab 'Bugs & Ideen': schnelle Bug-/Feature-Erfassung, editierbare Liste, frontend-only gegen feedback/current"
git push origin main
```

- [ ] **Step 6: Deploy verifizieren**

Run: `gh run list --workflow=frontend-pilot.yml --limit 1` (ggf. `gh run watch <id>`)
Expected: Lauf grün.

- [ ] **Step 7: Live-Browser-Test durch den User (Agent kann das in dieser Sandbox nicht selbst, siehe Global Constraints)**

Checkliste für den User: Tab "Bugs & Ideen" öffnen, Bug anlegen (speichert sofort, taucht in der Liste auf), Idee anlegen, einen Eintrag anklicken und Text ergänzen + Speichern, Seite neu laden (Reload) — Einträge müssen erhalten bleiben. Dark Mode prüfen (Kontrast der Typ-Buttons/Textarea).

---

## Verification (gesamt)

- [ ] `tsc --noEmit` grün nach Task 2.
- [ ] Beide Deploy-Workflows (`firestore-rules-deploy.yml`, `frontend-pilot.yml`) grün nach ihrem jeweiligen Push.
- [ ] Live-Browser-Test durch den User (Task 2, Step 7) — Task 2 gilt erst danach als abgeschlossen, nicht nach reinem Typecheck.

## Self-Review

- **Spec-Abdeckung:** Sicherheits-Einordnung (Task 1), Datenmodell (Task 2 Step 1), Frontend-Komponente inkl. Formular/Liste/Bearbeiten (Task 2 Step 2), App-Einbindung (Task 2 Step 3) — alle Spec-Abschnitte gedeckt. "Nächste Session"-Lese-Workflow ist reine Admin-SDK-Nutzung ohne Code-Änderung, kein eigener Task nötig.
- **Kein Placeholder:** jeder Schritt hat vollständigen Code.
- **Real gefundenes Risiko eingearbeitet:** die `loadState`-Absätze ohne Hidden-Toggle hätten den neuen Tab kaputt gemacht (Überlappung mit "Lade Daten…") - beim Lesen von `App.tsx` gefunden, nicht nur aus der Spec übernommen, expliziter Fix-Schritt in Task 2.
- **Sandbox-Limitation ehrlich benannt:** kein lokaler Dev-Server/Build in dieser Sandbox möglich (bekanntes Windows-DrvFs-Problem) - Verifikation stützt sich auf `tsc` + echten CI-Build + User-Browser-Test, nicht auf eine hier nicht mögliche lokale Behauptung.
