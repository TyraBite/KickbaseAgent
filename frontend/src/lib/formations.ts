// Formations-Notation Verteidigung-Mittelfeld-Sturm (Torwart immer 1,
// nicht Teil der Notation) - Standardkonvention im deutschen Fussball.
export const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"] as const;
export type Position = (typeof POSITIONS)[number];

export interface FormationSlots {
  Torwart: number;
  Abwehr: number;
  Mittelfeld: number;
  Sturm: number;
}

// Alle 10 in Kickbase erlaubten Formationen (Recherche 2026-08-01, siehe
// docs/superpowers/specs/2026-08-01-wunschkader-formationen-design.md fuer
// Quellen - Drittquelle, keine offizielle Kickbase-Dokumentation, aber
// intern konsistent: jede Formation summiert exakt auf 10 Feldspieler +
// 1 Torwart, passt zum bestaetigten Minimum "mind. 3 Abwehr/2 Mittelfeld/
// 1 Sturm").
export const FORMATIONS = {
  "3-4-3": { Torwart: 1, Abwehr: 3, Mittelfeld: 4, Sturm: 3 },
  "3-5-2": { Torwart: 1, Abwehr: 3, Mittelfeld: 5, Sturm: 2 },
  "3-6-1": { Torwart: 1, Abwehr: 3, Mittelfeld: 6, Sturm: 1 },
  "4-2-4": { Torwart: 1, Abwehr: 4, Mittelfeld: 2, Sturm: 4 },
  "4-3-3": { Torwart: 1, Abwehr: 4, Mittelfeld: 3, Sturm: 3 },
  "4-4-2": { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 },
  "4-5-1": { Torwart: 1, Abwehr: 4, Mittelfeld: 5, Sturm: 1 },
  "5-2-3": { Torwart: 1, Abwehr: 5, Mittelfeld: 2, Sturm: 3 },
  "5-3-2": { Torwart: 1, Abwehr: 5, Mittelfeld: 3, Sturm: 2 },
  "5-4-1": { Torwart: 1, Abwehr: 5, Mittelfeld: 4, Sturm: 1 },
} as const satisfies Record<string, FormationSlots>;

export type FormationKey = keyof typeof FORMATIONS;

export const FORMATION_KEYS = Object.keys(FORMATIONS) as FormationKey[];

export type PositionCounts = Record<Position, number>;

// True, wenn mindestens eine der 10 Formationen mit den aktuellen
// Zaehlungen PLUS einem weiteren Starter in `position` noch erreichbar
// ist (in jeder anderen Position muss die Formation mindestens die
// aktuelle Zaehlung zulassen, in `position` mindestens Zaehlung+1) -
// ersetzt die alte starre Combobox-Auswahl (ehemals slotsFor()).
export function canAddStarter(counts: PositionCounts, position: Position): boolean {
  return FORMATION_KEYS.some((key) => {
    const f = FORMATIONS[key];
    return POSITIONS.every((p) => f[p] >= counts[p] + (p === position ? 1 : 0));
  });
}

// Liefert den Namen der exakt passenden Formation, falls die Zaehlungen
// GENAU einer der 10 entsprechen - sonst null (Belegung noch nicht
// komplett). Torwart ist in jeder Formation fix 1, faellt automatisch mit
// rein. Jede ueber canAddStarter() erreichte 11er-Belegung (inkl.
// Torwart) entspricht zwangslaeufig genau einer Formation (Teilmenge +
// gleiche Summe = Gleichheit) - kein Fall, in dem hier unerwartet null
// zurueckkaeme, sobald die Summe 11 erreicht.
export function matchedFormation(counts: PositionCounts): FormationKey | null {
  return FORMATION_KEYS.find((key) => POSITIONS.every((p) => FORMATIONS[key][p] === counts[p])) ?? null;
}
