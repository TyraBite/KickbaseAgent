import type { SVGProps } from "react";

// Alle Icons hier nutzen fill="currentColor" (aus den Rohdateien in
// frontend/public/icons-src/ uebernommen) - passen sich dadurch automatisch
// an die Textfarbe der Umgebung an (Hell-/Dunkelmodus, verschiedene Badge-
// Tones), ohne eigene Farb-Deklaration. className steuert Groesse+Farbe wie
// bei jedem anderen SVG-Icon ueblich.

export function IconPositionTorwart(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Torwart" {...props}>
      <path d="M9.3 7.3 L10.5 7.3 L10.5 19.6 L9.3 19.6 Z" />
      <path d="M13.5 7.3 L14.7 7.3 L14.7 19.6 L13.5 19.6 Z" />
      <path d="M5.7 10.8 L18.3 10.8 L18.3 12 L5.7 12 Z" />
      <path d="M5.7 14.9 L18.3 14.9 L18.3 16.1 L5.7 16.1 Z" />
      <path d="M3.5 4.4 H20.5 A0.7 0.7 0 0 1 21.2 5.1 V6.6 A0.7 0.7 0 0 1 20.5 7.3 H3.5 A0.7 0.7 0 0 1 2.8 6.6 V5.1 A0.7 0.7 0 0 1 3.5 4.4 Z" />
      <path d="M3.5 4.4 H5 A0.7 0.7 0 0 1 5.7 5.1 V18.9 A0.7 0.7 0 0 1 5 19.6 H3.5 A0.7 0.7 0 0 1 2.8 18.9 V5.1 A0.7 0.7 0 0 1 3.5 4.4 Z" />
      <path d="M19 4.4 H20.5 A0.7 0.7 0 0 1 21.2 5.1 V18.9 A0.7 0.7 0 0 1 20.5 19.6 H19 A0.7 0.7 0 0 1 18.3 18.9 V5.1 A0.7 0.7 0 0 1 19 4.4 Z" />
    </svg>
  );
}

export function IconPositionAbwehr(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Abwehr" {...props}>
      <path d="M3.9 2.5 H20.1 V12.0 C20.1 16.4 13.4 18.0 12 21.5 C10.6 18.0 3.9 16.4 3.9 12.0 Z" />
    </svg>
  );
}

export function IconPositionMittelfeld(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Mittelfeld" {...props}>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M9.2 2.8 H14.8 L21.7 6.4 L19.3 11.7 L17.5 10.8 V21.6 H6.5 V10.8 L4.7 11.7 L2.3 6.4 Z M9.2 2.5 Q12 5.6 14.8 2.5 Z M8.79 18.40V11.23H8.21L8.18 10.74L9.08 10.00H10.19V18.40Z M13.53 18.49Q12.54 18.49 11.99 18.00Q11.45 17.50 11.43 16.58Q11.41 15.72 11.41 14.91Q11.40 14.11 11.41 13.33Q11.42 12.56 11.43 11.81Q11.45 10.89 11.99 10.40Q12.54 9.91 13.53 9.91Q14.51 9.91 15.05 10.40Q15.59 10.89 15.62 11.81Q15.64 12.44 15.65 13.04Q15.66 13.65 15.66 14.24Q15.66 14.84 15.65 15.42Q15.64 16.01 15.62 16.58Q15.59 17.53 15.04 18.01Q14.49 18.49 13.53 18.49ZM13.53 17.39Q14.22 17.39 14.25 16.85Q14.29 15.92 14.30 15.06Q14.31 14.19 14.30 13.34Q14.29 12.48 14.25 11.56Q14.23 11.01 13.53 11.01Q12.82 11.01 12.81 11.56Q12.78 12.30 12.77 12.95Q12.76 13.60 12.76 14.22Q12.76 14.83 12.77 15.47Q12.78 16.11 12.81 16.82Q12.82 17.39 13.53 17.39Z"
      />
    </svg>
  );
}

export function IconPositionSturm(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Sturm" {...props}>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2.6 A9.4 9.4 0 1 1 12 21.4 A9.4 9.4 0 1 1 12 2.6 Z M12 5.8 A6.2 6.2 0 1 1 12 18.2 A6.2 6.2 0 1 1 12 5.8 Z"
      />
      <path d="M12 9 A3 3 0 1 1 12 15 A3 3 0 1 1 12 9 Z" />
    </svg>
  );
}

export function IconStatusVerletzt(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" fillRule="evenodd" clipRule="evenodd" role="img" aria-label="Verletzt" {...props}>
      <path d="M8 1 A7 7 0 1 1 8 15 A7 7 0 1 1 8 1 Z M6.75 3.7 L9.25 3.7 L9.25 6.75 L12.3 6.75 L12.3 9.25 L9.25 9.25 L9.25 12.3 L6.75 12.3 L6.75 9.25 L3.7 9.25 L3.7 6.75 L6.75 6.75 Z" />
    </svg>
  );
}

export function IconStatusAngeschlagen(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" fillRule="evenodd" clipRule="evenodd" role="img" aria-label="Angeschlagen" {...props}>
      <path d="M8 1.6 L15.3 14.4 L0.7 14.4 Z M8 5.1 H8 A0.95 0.95 0 0 1 8.95 6.05 V9.05 A0.95 0.95 0 0 1 8 10 H8 A0.95 0.95 0 0 1 7.05 9.05 V6.05 A0.95 0.95 0 0 1 8 5.1 Z M8 11.05 A1.05 1.05 0 1 1 8 13.15 A1.05 1.05 0 1 1 8 11.05 Z" />
    </svg>
  );
}

export function IconStatusAufbau(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" role="img" aria-label="Im Aufbau" {...props}>
      <path d="M3.9 1.6 H12.1 A0.7 0.7 0 0 1 12.8 2.3 V2.7 A0.7 0.7 0 0 1 12.1 3.4 H3.9 A0.7 0.7 0 0 1 3.2 2.7 V2.3 A0.7 0.7 0 0 1 3.9 1.6 Z" />
      <path d="M3.9 12.6 H12.1 A0.7 0.7 0 0 1 12.8 13.3 V13.7 A0.7 0.7 0 0 1 12.1 14.4 H3.9 A0.7 0.7 0 0 1 3.2 13.7 V13.3 A0.7 0.7 0 0 1 3.9 12.6 Z" />
      <path d="M4.5 3.4 L11.5 3.4 L8 8.4 Z" />
      <path d="M11.5 12.6 L4.5 12.6 L8 7.6 Z" />
    </svg>
  );
}

export function IconStatusFit(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" role="img" aria-label="Fit" {...props}>
      <path d="M1.59 9.63 L5.59 13.53 L7.41 11.67 L3.41 7.77 Z M7.5 13.43 L14.6 4.83 L12.6 3.17 L5.5 11.77 Z M6.5 11.3 A1.3 1.3 0 1 0 6.5 13.9 A1.3 1.3 0 1 0 6.5 11.3 Z" />
    </svg>
  );
}

export function IconEmptyState(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="Noch keine Einträge"
      {...props}
    >
      <path d="M11.5 11 H36.5 A5 5 0 0 1 41.5 16 V32 A5 5 0 0 1 36.5 37 H11.5 A5 5 0 0 1 6.5 32 V16 A5 5 0 0 1 11.5 11 Z" />
      <path d="M6.5 25 H16.5 L19.5 30 H28.5 L31.5 25 H41.5" />
    </svg>
  );
}

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

export function IconMenu(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Menü" {...props}>
      <path d="M3.5 5.5 H20.5 V7 H3.5 Z" />
      <path d="M3.5 11.25 H20.5 V12.75 H3.5 Z" />
      <path d="M3.5 17 H20.5 V18.5 H3.5 Z" />
    </svg>
  );
}
