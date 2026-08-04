# Feedback-Typ entfernen (Bug/Idee-Toggle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das `type`-Feld (`"bug" | "feature"`) auf `FeedbackItem` sowie den zugehörigen Bug/Idee-Toggle im Feedback-Tab entfernen, weil `type` app-weit keine Verhaltenswirkung hat (nur Badge-Icon + Placeholder-Text) und Nutzer sich beim Kategorisieren regelmäßig vertun (`feedback/current` Item `cf5108f5`).

**Architecture:** Reine Frontend-Änderung. `type` raus aus `frontend/src/types.ts` (`FeedbackItem`), Toggle-Buttons + `TYPE_LABEL`-Badge raus aus `frontend/src/components/FeedbackTab.tsx`. Bereits in Firestore gespeicherte Items behalten ihr altes `type`-Feld (Firestore ist schemalos, totes Zusatzfeld ist harmlos) — keine Migration nötig, es wird nur nicht mehr geschrieben/gelesen.

**Tech Stack:** React + TypeScript, Firestore Web SDK, Playwright Component Tests (`@playwright/experimental-ct-react`).

## Global Constraints

- `player_id`/Namens-Matching irrelevant hier — keine Berührung.
- Keine `<form>`-Tags, Interaktion über `onClick`/`onChange` (bereits eingehalten, nicht ändern).
- `localStorage`-Keys nicht betroffen.
- Tote Felder werden gelöscht, nicht kommentiert (`CLAUDE.md`) — `type` ist genau so ein Feld.
- Jeder Bugfix/Feature braucht einen automatisierten Test, TDD (erst rot, dann grün).
- Kein Test-Only-Export aus Produktivcode (siehe Kommentar in `WunschkaderTabAutoSave.ct.tsx:6-8` zum gleichen Prinzip).

---

## File Structure

- Modify: `frontend/src/types.ts` — `FeedbackItem`-Interface, `type`-Zeile entfernen.
- Modify: `frontend/src/components/FeedbackTab.tsx` — `TYPE_LABEL`, `type`-State, Toggle-Buttons, Placeholder-Logik, Badge-Anzeige entfernen.
- Create: `frontend/tests-ct/FeedbackTab.ct.tsx` — Regressionstest (Toggle weg, kein `type` im Firestore-Write).

---

### Task 1: `type` aus `FeedbackItem` und `FeedbackTab.tsx` entfernen + Regressionstest

**Files:**
- Modify: `frontend/src/types.ts:146-152`
- Modify: `frontend/src/components/FeedbackTab.tsx` (Zeilen 10-13, 28, 70-91, 135-158, 164, 250)
- Test: `frontend/tests-ct/FeedbackTab.ct.tsx`

**Interfaces:**
- Consumes: `firebase/firestore`-Mock (`doc`, `setDoc`, `getDoc`, `arrayUnion`) aus `frontend/src/test-fixtures/firestore.mock.ts` (bereits vorhanden, Calls landen in `window.__ctFirestoreCalls`, Typ `RecordedSetDocCall` aus derselben Datei). `../firebase`-Mock aus `frontend/src/test-fixtures/firebase.mock.ts` (bereits vorhanden, per Vite-Alias in `playwright-ct.config.ts` eingehängt — kein Setup nötig).
- Produces: `FeedbackItem` ohne `type`-Feld — von keinem anderen Modul im Repo referenziert (verifiziert: nur `types.ts` und `FeedbackTab.tsx` lesen/schreiben `type` auf `FeedbackItem`).

- [ ] **Step 1: Failing Test schreiben**

`frontend/tests-ct/FeedbackTab.ct.tsx`:

```tsx
import { test, expect } from "@playwright/experimental-ct-react";
import FeedbackTab from "../src/components/FeedbackTab";
import type { RecordedSetDocCall } from "../src/test-fixtures/firestore.mock";

test.describe("Feedback-Typ (Bug/Idee) ist entfernt", () => {
  test("kein Bug/Idee-Toggle im Formular, neues Item hat kein type-Feld", async ({ mount, page }) => {
    const component = await mount(<FeedbackTab now={Date.now()} />);

    await expect(component.getByRole("button", { name: "🐛 Bug" })).toHaveCount(0);
    await expect(component.getByRole("button", { name: "💡 Idee" })).toHaveCount(0);

    await component.getByPlaceholder(/./).fill("Testeintrag ohne Typ");
    await component.getByRole("button", { name: "Hinzufügen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);

    const calls: RecordedSetDocCall[] = await page.evaluate(() => (window as any).__ctFirestoreCalls ?? []);
    const written = (calls[0].data as { items: { __ctArrayUnion?: unknown[] } & Record<string, unknown> }).items;
    const item = ((written as unknown as { __ctArrayUnion: Record<string, unknown>[] }).__ctArrayUnion)[0];
    expect(item).not.toHaveProperty("type");
    expect(item.text).toBe("Testeintrag ohne Typ");
  });
});
```

Hinweis: `arrayUnion(...)` liefert im Mock `{ __ctArrayUnion: items }` (siehe `firestore.mock.ts`) — deshalb das Auspacken über `__ctArrayUnion[0]` statt direkt `data.items[0]`.

- [ ] **Step 2: Test laufen lassen, rot bestätigen**

Run (in einer isolierten Worktree, NICHT im Haupt-Checkout `/workspace/work` — `npm install` dort bricht die Windows/Rider-Seite):
```bash
cd frontend && npx playwright test -c playwright-ct.config.ts FeedbackTab.ct.tsx
```
Expected: FAIL — `🐛 Bug`-Button existiert noch (Count ist 1, nicht 0), Test bricht am ersten `expect` ab.

- [ ] **Step 3: `types.ts` ändern**

In `frontend/src/types.ts`, `FeedbackItem` (aktuell Zeilen 146-152):

```ts
export interface FeedbackItem {
  id: string;
  text: string;
  created_at: string; // ISO-Timestamp, new Date().toISOString()
  status: "open" | "done";
}
```

(Nur die `type: "bug" | "feature";`-Zeile entfernt, Rest unverändert.)

- [ ] **Step 4: `FeedbackTab.tsx` ändern**

1. `TYPE_LABEL`-Konstante (Zeilen 10-13) komplett entfernen.
2. State-Deklaration `const [type, setType] = useState<FeedbackItem["type"]>("bug");` (Zeile 28) entfernen.
3. In `handleAdd()` (Zeilen 70-91): `type,` aus dem `item`-Objekt-Literal entfernen (Zeile 75 löschen).
4. Die zwei Toggle-Buttons (Zeilen 135-158, der gesamte `<div className="mb-3 flex gap-2">...</div>`-Block) komplett entfernen.
5. `placeholder={type === "bug" ? "Was ist kaputt?" : "Was wäre hilfreich?"}` (Zeile 164) ersetzen durch einen festen Text:
   ```tsx
   placeholder="Was ist kaputt oder was wäre hilfreich?"
   ```
6. In `FeedbackRow` (Zeilen 248-252): den Badge-Span `<span>{TYPE_LABEL[item.type]}</span>` entfernen und den Wrapper-Div anpassen, da er sonst nur noch ein Kind hat:
   ```tsx
   <div className="text-xs text-slate-400 dark:text-slate-500">
     <span title={item.created_at}>{formatRelativeTime(item.created_at, new Date(now))}</span>
   </div>
   ```
   (ersetzt den bisherigen `<div className="flex items-center justify-between ...">`-Block.)

- [ ] **Step 5: Test laufen lassen, grün bestätigen**

```bash
cd frontend && npx playwright test -c playwright-ct.config.ts FeedbackTab.ct.tsx
```
Expected: PASS.

- [ ] **Step 6: Mutation-Check**

Fix temporär zurücknehmen (z. B. `git stash` nur für `FeedbackTab.tsx`, Toggle-Block wieder einfügen ODER einfach `git diff` der Buttons rückgängig machen), Test erneut laufen lassen → muss wieder ROT werden (Beweis, dass der Test nicht vakuos ist). Danach den Fix wiederherstellen (`git stash pop` bzw. Änderung erneut anwenden).

- [ ] **Step 7: Vollen Frontend-Testlauf + Build**

```bash
cd frontend && npm run build && npx vitest run && npx playwright test -c playwright-ct.config.ts
```
Expected: Build ohne TS-Fehler (bestätigt, dass kein anderer Code mehr `FeedbackItem["type"]` referenziert), alle Vitest- und Playwright-CT-Tests grün.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/FeedbackTab.tsx frontend/tests-ct/FeedbackTab.ct.tsx
git commit -m "Feedback-Typ (Bug/Idee) entfernt - Toggle ohne Verhaltenswirkung, Nutzer vertut sich beim Kategorisieren"
```

---

## Nach Abschluss (Haupt-Thread, kein Subagent)

- Live im Browser verifizieren: Dev-Server starten, Feedback-Tab öffnen, neuen Eintrag anlegen, in Firestore (`feedback/current`) prüfen, dass das neue Item kein `type`-Feld hat und die UI keinen Bug/Idee-Toggle mehr zeigt.
- Erst nach dieser Live-Verifikation `feedback/current`-Item `cf5108f5` per Admin-SDK-Skript auf `status: "done"` setzen (Skript-Datei, kein inline `python3 -c` — wird geblockt).
- `HANDOFF.md` bei dieser Gelegenheit auch gleich korrigieren: `5a182f9d` (ML-Charts mobil) ist in Firestore bereits `"done"`, aus der offenen Liste raus; `f686c8db` (Public-Domain-Marktwert-Idee) als neuer offener Punkt rein.
