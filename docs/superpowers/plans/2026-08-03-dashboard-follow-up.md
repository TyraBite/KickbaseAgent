# Dashboard-Follow-up: Volle Spielerkarten + Investment-Praezisierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live-Feedback zum grad gemergten Tages-Dashboard (`docs/superpowers/plans/2026-08-03-tages-dashboard.md`) umsetzen: einheitliche volle Spielerkarten (inkl. Fitness-Status) in allen drei Kader-Sektionen, Investment-Sektion schliesst Wunschkader-Ziele von den Verkaufs-Vorschlaegen aus und zeigt bei den Kauf-Vorschlaegen nur noch Auktionen, die vor dem naechsten 22-Uhr-Cutoff enden.

**Architecture:** Reine Wiederverwendung bereits existierender Komponenten (`PlayerCard`/`PlayerDetailModal`/`StatusLabelRow` aus `EigenesTeamTab.tsx`, `TransfermarktCard`/`TransfermarktDetailModal` aus `TransfermarktTab.tsx`, beide bereits fuer Cross-Component-Nutzung exportiert bzw. werden es hier) statt neuer eigener Kartenkomponenten in `DashboardTab.tsx`. Keine neuen Backend-Aenderungen, keine neuen Firestore-Felder.

**Tech Stack:** React/TypeScript/Vitest. Keine neuen Dependencies.

## Global Constraints

- Alle Aenderungen sind Chat-Feedback zum bereits live gemergten Dashboard-Feature (`main`, Commit-Reihe ab `ac865d3`) — kein neuer Spec-Zyklus, Kontext steht vollstaendig in diesem Plan.
- **Nur die Investment-Sektion** schliesst Wunschkader-Ziele aus — die "Verkaufen"-Sektion bleibt bewusst unveraendert bei "ALLE eigenen Spieler mit sellSignal==='verkaufen'", unabhaengig vom Wunschkader-Status (explizite fruehere User-Entscheidung, nicht anfassen).
- Push-Policy dieses Repos: direkt auf `main` pushen, sobald Tests gruen (kein PR-Umweg, siehe [[project_kickbaseagent_git_workflow]]).
- Vor Merge/Push `git log origin/main --oneline -5` + `git worktree list` pruefen (Race-Condition-Risiko, siehe [[feedback_check_worktrees_before_fresh_plan_dispatch]]) — main ist in dieser Session bereits mehrfach durch parallele Sessions weitergelaufen.
- Keine neuen Unit-Tests fuer reines UI-Rewiring (Kartentausch) noetig — die zugrundeliegenden `buildDashboardSellCandidates`/`buildInvestmentSwaps`-Funktionen bleiben unveraendert (Filterung passiert am Call-Site in `DashboardTab.tsx`, nicht in den Funktionen selbst, siehe Task 3).

---

## Task 1: `PlayerCard`/`PlayerDetailModal`/`StatusLabelRow` aus `EigenesTeamTab.tsx` exportieren

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Produziert: `export function PlayerCard({row, onSelect}: {row: EigenesTeamRow; onSelect: () => void})`,
  `export function PlayerDetailModal({row, thresholds, mae, mae3d, players, calibration, onClose}: {...})`,
  `export function StatusLabelRow({value}: {value: string | null})` — alle drei Signaturen bleiben exakt wie
  aktuell, nur `export` ergaenzt.

- [ ] **Step 1: Drei Funktionsdeklarationen mit `export` versehen**

`function PlayerCard({` (Zeile 212) → `export function PlayerCard({`
`function PlayerDetailModal({` (Zeile 321) → `export function PlayerDetailModal({`
`function StatusLabelRow({` (Zeile 204) → `export function StatusLabelRow({`

Keine weitere Aenderung — alle drei werden weiterhin genauso von `EigenesTeamTab`s eigenem Default-Export genutzt,
nur zusaetzlich von aussen importierbar.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 0 Fehler.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/EigenesTeamTab.tsx
git commit -m "PlayerCard/PlayerDetailModal/StatusLabelRow exportieren fuer Wiederverwendung im Dashboard-Tab"
```

---

## Task 2: `StatusLabelRow` in `TransfermarktCard` ergaenzen

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

- [ ] **Step 1: Import ergaenzen**

Am Kopf der Datei, `StatusLabelRow` aus `./EigenesTeamTab` importieren:

```ts
import { StatusLabelRow } from "./EigenesTeamTab";
```

- [ ] **Step 2: `StatusLabelRow` in `TransfermarktCard` einbauen**

In `TransfermarktCard` (aktuell Zeile 388-...), direkt nach der bestehenden `<Row label="Signal">`-Zeile (Zeile
432-434) ergaenzen:

```tsx
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <StatusLabelRow value={row.status_label} />
```

(Rest der Karte unveraendert.)

- [ ] **Step 3: Typecheck + Build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: beides erfolgreich.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktCard zeigt jetzt auch Fitness-Status"
```

---

## Task 3: `DashboardTab.tsx` — volle Karten in allen 3 Sektionen + Investment-Praezisierung

**Files:**
- Modify: `frontend/src/components/DashboardTab.tsx`

**Interfaces:**
- Konsumiert: `PlayerCard`/`PlayerDetailModal` (Task 1, aus `./EigenesTeamTab`), `TransfermarktCard`/
  `TransfermarktDetailModal` (bereits vorhanden, aus `./TransfermarktTab`), `EigenesTeamRow` (Typ, aus
  `../lib/derive`).

- [ ] **Step 1: Imports anpassen**

Bestehende Imports:

```ts
import { TransfermarktCard, TransfermarktDetailModal } from "./TransfermarktTab";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { PositionBadge, TeamCrest } from "./ui";
```

→ ersetzen/ergaenzen zu:

```ts
import { TransfermarktCard, TransfermarktDetailModal } from "./TransfermarktTab";
import { PlayerCard, PlayerDetailModal } from "./EigenesTeamTab";
import { fmtNum } from "../format";
```

(`fmtSigned`/`trendArrow`/`trendClass`/`PositionBadge`/`TeamCrest` waren nur fuer die jetzt geloeschte
`PlayerRowCard`/die alte Investment-Text-Zeile noetig, siehe Step 5/6 — `fmtNum` bleibt, wird noch von
`FeedSection` gebraucht.)

`EigenesTeamRow`-Typ (fuer den `sell_signal`-Cast in Step 3) in den bestehenden `../lib/derive`-Import-Block
aufnehmen, keine separate Import-Zeile:

```ts
import {
  buildDashboardBuyCandidates,
  buildDashboardSellCandidates,
  buildInvestmentSwaps,
  buildPlayerRow,
  formatRelativeTime,
  liveModelMae,
  recentTransfersWithin24h,
  type EigenesTeamRow,
  type TransfermarktRow,
} from "../lib/derive";
```

- [ ] **Step 2: Zweiten Selection-State fuer eigene Spieler ergaenzen**

Direkt neben dem bestehenden `const [selected, setSelected] = useState<TransfermarktRow | null>(null);`:

```ts
  const [selectedOwned, setSelectedOwned] = useState<EigenesTeamRow | null>(null);
```

- [ ] **Step 3: Sell-Candidates mit `sell_signal` versehen (fuer `PlayerCard`s Badge)**

Direkt nach der bestehenden Zeile `const sellCandidates = buildDashboardSellCandidates(...)`:

```ts
  const sellCandidatesWithSignal: EigenesTeamRow[] = sellCandidates.map((r) => ({ ...r, sell_signal: "verkaufen" as const }));
```

- [ ] **Step 4: Investment-Kandidaten praezisieren (Wunschkader-Ausschluss + Auktions-Cutoff)**

Den bestehenden Block

```ts
  const ownPlayerRows = data.own_squad_ids
    .map((pid) => data.players[pid])
    .filter((p): p is (typeof data.players)[string] => !!p)
    .map((p) => buildPlayerRow(p, data.calibration));
  const investmentSwaps = buildInvestmentSwaps(ownPlayerRows, transfermarktRows, ML_PREDICTION_3D_THRESHOLDS.strong);
```

ersetzen durch:

```ts
  const ownPlayerRows = data.own_squad_ids
    .map((pid) => data.players[pid])
    .filter((p): p is (typeof data.players)[string] => !!p)
    .map((p) => buildPlayerRow(p, data.calibration));
  // Investment schliesst Wunschkader-Ziele aus - das sind Spieler, die fest im
  // Kader eingeplant sind, keine reinen Kapitalanlagen-Verkaufskandidaten
  // (User-Feedback 2026-08-03, nach dem initialen Dashboard-Merge).
  const wunschkaderTargetIds = new Set(wunschkader.targets.map((t) => t.player_id));
  const investmentOwnRows = ownPlayerRows.filter((r) => !wunschkaderTargetIds.has(r.player_id));
  // Nur Auktionen, die vor dem naechsten 22-Uhr-Marktwert-Update enden, sind
  // heute noch handlungsrelevant - laeuft eine Auktion erst danach aus, gibt
  // es keinen Zeitdruck fuer heute (User-Feedback 2026-08-03). auction_urgent
  // ist exakt dieses bestehende Signal (siehe buildTransfermarktRows()).
  const investmentMarketRows = transfermarktRows.filter((r) => r.auction_urgent);
  const investmentSwaps = buildInvestmentSwaps(investmentOwnRows, investmentMarketRows, ML_PREDICTION_3D_THRESHOLDS.strong);
```

- [ ] **Step 5: `SellSection` auf `PlayerCard` umstellen**

```tsx
  const SellSection = (
    <Section key="verkaufen" title="Verkaufen" emptyText="Aktuell keine Verkaufskandidaten." isEmpty={sellCandidatesWithSignal.length === 0}>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        {sellCandidatesWithSignal.map((r) => (
          <PlayerCard key={r.player_id} row={r} onSelect={() => setSelectedOwned(r)} />
        ))}
      </div>
    </Section>
  );
```

- [ ] **Step 6: `InvestmentSection` auf zwei Karten + Pfeil umstellen**

```tsx
  const InvestmentSection = (
    <Section key="investment" title="Investment" emptyText="Aktuell keine Kapitalanlage-Swaps mit ausreichendem Abstand." isEmpty={investmentSwaps.length === 0}>
      <div className="space-y-4">
        {investmentSwaps.map((pair) => (
          <div key={pair.sell.player_id + pair.buy.player_id} className="flex flex-wrap items-center gap-3">
            <div className="w-56 shrink-0">
              <PlayerCard row={{ ...pair.sell, sell_signal: "verkaufen" }} onSelect={() => setSelectedOwned({ ...pair.sell, sell_signal: "verkaufen" })} />
            </div>
            <span className="text-2xl text-slate-400 dark:text-slate-500" aria-hidden="true">→</span>
            <div className="w-56 shrink-0">
              <TransfermarktCard row={pair.buy} bidHistory={data.bid_premium_history ?? []} thresholds={data.signal_thresholds} onSelect={() => setSelected(pair.buy)} />
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
```

- [ ] **Step 7: `PlayerDetailModal` fuer `selectedOwned` rendern**

Direkt neben dem bestehenden `{selected && <TransfermarktDetailModal ... />}`-Block, im `return`-JSX:

```tsx
      {selectedOwned && (
        <PlayerDetailModal
          row={selectedOwned}
          thresholds={data.signal_thresholds}
          mae={mae}
          mae3d={liveModelMae(data.ml_metrics_3d ?? null)}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelectedOwned(null)}
        />
      )}
```

- [ ] **Step 8: Jetzt ungenutzte `PlayerRowCard`-Funktion loeschen**

Die komplette `function PlayerRowCard({...}) {...}`-Definition am Dateiende entfernen (wird durch `PlayerCard`
ersetzt, siehe Step 5/6).

- [ ] **Step 9: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 0 Fehler (inkl. keiner ungenutzten Imports mehr aus Step 1).

- [ ] **Step 10: Volle Vitest-Suite + Build**

Run: `cd frontend && npm run test -- --run && npm run build`
Expected: alle Tests weiterhin gruen (keine neuen/geaenderten Testfaelle in diesem Task — reines UI-Rewiring),
Build erfolgreich.

- [ ] **Step 11: Manueller Dev-Server-Check**

Dev-Server starten, Dashboard-Tab oeffnen:
- Verkaufen-Sektion zeigt jetzt volle Karten (Wappen/Badge "Jetzt verkaufen"/Prognose 1T+3T/Startelf-Rang/Fitness/
  Schnitt/Marktwert), klickbar → oeffnet Detailmodal (inkl. "Vergleichen mit..."-Funktion, die automatisch
  mitkommt).
- Kaufen-Karten zeigen jetzt zusaetzlich eine Fitness-Zeile.
- Investment-Paare zeigen zwei Karten nebeneinander mit Pfeil dazwischen, beide klickbar, beide Kartentypen zeigen
  Fitness.
- Investment-Kaufseite zeigt nur noch Spieler, deren Auktion vor dem naechsten 22-Uhr-Cutoff endet (falls aktuell
  kein Investment-Paar diese Bedingung erfuellt, ist der Empty-State normal, kein Bug).
- Investment-Verkaufsseite enthaelt keinen Spieler, der aktuell im Wunschkader steht (gegen die eigene
  Wunschkader-Zielliste gegenchecken).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/components/DashboardTab.tsx
git commit -m "Dashboard: volle Spielerkarten in allen Sektionen, Investment-Praezisierung (Wunschkader-Ausschluss + 22-Uhr-Cutoff)"
```

## Self-Review-Hinweis fuer den Implementierer

`PlayerCard`/`PlayerDetailModal` erwarten `EigenesTeamRow` (= `PlayerRow & {sell_signal?: ...}`) — `pair.sell` in
Step 6 ist ein reines `PlayerRow` (aus `buildInvestmentSwaps()`s `InvestmentSwap`-Typ), daher der `{...pair.sell,
sell_signal: "verkaufen"}`-Spread an beiden Stellen (Karte UND `onSelect`). Nicht vergessen, beide synchron zu
halten, sonst zeigt die Karte "Jetzt verkaufen", aber das Detailmodal (falls `selectedOwned` aus einem anderen
Klick-Pfad staemme) nicht — aktuell kein Risiko, da beide im selben JSX-Ausdruck gesetzt werden, aber bei
kuenftigen Aenderungen im Hinterkopf behalten.
