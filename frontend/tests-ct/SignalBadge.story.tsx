import { SignalBadge } from "../src/components/ui";

// "Test story" (siehe https://playwright.dev/docs/test-components#test-stories):
// haelt die Fixture-Werte UND die SignalBadge-Instanzen selbst im normalen
// App-Bundle (kein Node->Browser-Props-Crossing ueber mount() noetig) - der
// CT-Test importiert nur diese fertig konfigurierte Story und mountet sie
// ohne eigene Props. Grund: SignalBadge direkt mit Props aus der Testdatei zu
// mounten schlug in CI fehl (component-tests-Check, PR #7) - Umstellung auf
// eine Story-Datei folgt exakt dem Muster der bereits gruenen
// AlleSpielerTab.ct.tsx/WunschkaderTab.ct.tsx (die ebenfalls eine importierte,
// nicht test-lokal definierte Komponente mounten).
export const THRESHOLDS = { good: 1.1, critical: 0.9 };

export default function SignalBadgeStory() {
  return (
    <div>
      <div data-testid="at-good">
        <SignalBadge signal={THRESHOLDS.good} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="at-critical">
        <SignalBadge signal={THRESHOLDS.critical} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="between">
        <SignalBadge signal={1.0} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="above-good">
        <SignalBadge signal={1.11} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="below-critical">
        <SignalBadge signal={0.89} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="null-signal">
        <SignalBadge signal={null} thresholds={THRESHOLDS} />
      </div>
      <div data-testid="undefined-signal">
        <SignalBadge signal={undefined} thresholds={THRESHOLDS} />
      </div>
    </div>
  );
}
