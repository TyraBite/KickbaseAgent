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

export const FORMATIONS = {
  "3-4-3": { Torwart: 1, Abwehr: 3, Mittelfeld: 4, Sturm: 3 },
  "4-3-3": { Torwart: 1, Abwehr: 4, Mittelfeld: 3, Sturm: 3 },
  "3-5-2": { Torwart: 1, Abwehr: 3, Mittelfeld: 5, Sturm: 2 },
  "4-4-2": { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 },
} as const satisfies Record<string, FormationSlots>;

export type FormationKey = keyof typeof FORMATIONS;

export const FORMATION_KEYS = Object.keys(FORMATIONS) as FormationKey[];

export const DEFAULT_FORMATION: FormationKey = "3-4-3";

export function isFormationKey(value: string | null | undefined): value is FormationKey {
  return !!value && value in FORMATIONS;
}

export function slotsFor(formation: string | null | undefined, position: Position): number {
  const key = isFormationKey(formation) ? formation : DEFAULT_FORMATION;
  return FORMATIONS[key][position];
}
