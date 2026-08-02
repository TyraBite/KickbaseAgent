# ML-Charts Mobile-Lesbarkeit Design

**Feedback-Quelle:** `feedback/current` Item `5a182f9d` (2026-08-01): "Mobil kann man bei Ml-Modell Charts kaum was erkennen, vielleicht sollte man den Zeitraum da verkleinern. Wenn man einen Punkt auswählt, dann ist der Tooltip so positioniert, dass man es fast nicht lesen kann. Zusätzlich dazu ist es sehr schwierig ist einen Punkt auszuwählen, mobil sollten wir also deutlich weniger punkte anzeigen."

## Kontext

`frontend/src/components/MlGenauigkeitTab.tsx` zeigt zwei `TrendChart`-Instanzen (1-Tages- und 3-Tages-Horizont-Genauigkeit über Zeit), beide über dieselbe Komponente. `TrendChart` ist ein handgebautes SVG (kein Chart-Library, `viewBox="0 0 760 240"`, skaliert per CSS auf Container-Breite), keine externe Chart-Bibliothek im Projekt (`grep` bestätigt: kein `recharts`/`d3`/etc. in `frontend/package.json`).

**Drei konkrete Probleme, alle in `TrendChart` (Zeilen ~167-341):**

1. **Nur Maus-Interaktion.** `onMouseMove`/`onMouseLeave` auf dem `<svg>` (Zeilen 256-262) berechnen den nächsten Datenpunkt-Index aus der Mausposition und setzen `hoverIndex`. Touch-Events lösen `onMouseMove` nicht zuverlässig aus — daher ist ein Punkt mobil kaum auswählbar.
2. **Tooltip läuft rechts aus dem Bildschirm.** Der Tooltip (Zeilen 324-336) wird per `style={{ left: \`${(xFor(hoverIndex) / CHART_WIDTH) * 100}%\` }}` positioniert — reine Prozent-Position ohne jede Rand-Klemmung. Bei `hoverIndex` nahe dem rechten Rand (x ≈ 88% der Breite) landet der Tooltip auf schmalen Mobile-Viewports außerhalb des sichtbaren Bereichs.
3. **Zu viele Punkte auf zu wenig Platz.** `trend` enthält bis zu ~90 Tage (siehe `EVALUATION_LOOKBACK_DAYS` im Backend); alle werden ungekürzt geplottet. Auf einem ~343px breiten Mobile-Viewport (nach `PAD.left`/`PAD.right`-Abzug) liegen die Punkte extrem eng beieinander.

## Entscheidungen (aus Rückfrage-Dialog, 2026-08-02)

- **Kürzerer Zeitraum statt Punkte-Downsampling:** Chart zeigt auf Mobile nur die letzten **14 Einträge** von `trend` (nicht alle ~90). Löst Problem 3 vollständig, ohne Downsampling-Logik zu brauchen — 14 Punkte auf ~343px sind bereits komfortabel lesbar.
- **Nur der Chart wird gekürzt, nicht die Tabellen-Ansicht.** Der bestehende "Als Tabelle anzeigen"-Toggle (`showTable`) zeigt weiterhin die volle Historie — dort gibt es kein Lesbarkeits-Problem (sortierbare `SortableTable`, kein Platzproblem).
- **Touch-Interaktion: Tap UND Drag.** Tippen auf/nahe einen Punkt setzt den Tooltip fest (bleibt sichtbar bis woanders getippt wird); Ziehen über die Linie scrubbt live wie der Maus-Hover. Beides mappt (wie die bestehende Maus-Logik) die Touch-X-Position auf den **nächstgelegenen** Index — kein präzises Treffen des kleinen `r=3`-Kreises nötig.
- **Tooltip-Fix: Rand-Klemmung, nicht Fixposition.** Tooltip bleibt konzeptionell an der X-Position des gewählten Punkts, wird aber so geklemmt, dass er nie über den rechten (oder linken) Rand des Chart-Containers hinausragt.
- **Scope: nur Mobile.** Desktop-Verhalten (voller Zeitraum, reine Maus-Interaktion, unlimitierte Tooltip-Position — dort bisher nie als Problem gemeldet) bleibt unverändert. Mobile-Erkennung nutzt denselben Breakpoint wie der Rest der App: `window.matchMedia("(max-width: 639px)")` (siehe `frontend/src/lib/useViewMode.ts`), damit konsistent zu Tabellen/Karten-Toggle und Burger-Menü.

## Architektur

Keine neue Chart-Bibliothek — `TrendChart` bleibt handgebautes SVG, wird um drei fokussierte Ergänzungen erweitert. Zwei neue, unabhängig testbare **pure functions** (kein React/DOM) werden aus der bestehenden Inline-Logik extrahiert, damit sie TDD-fähig sind (Muster wie `normalizeSearchText`/`nextHeaderVisible` aus der vorherigen Session):

1. **`nearestTrendIndex(relX: number, plotW: number, padLeft: number, pointCount: number): number`** — reine Extraktion der bereits bestehenden Inline-Rechnung aus dem `onMouseMove`-Handler (Zeile 258-260), unverändert in ihrer Formel, nur benannt und wiederverwendbar für Maus- UND Touch-Handler. Kein neues Verhalten, nur DRY (dieselbe Formel würde sonst zweimal geschrieben — einmal für Maus, einmal für Touch).
2. **`clampTooltipLeftPercent(pointXPercent: number, tooltipWidthPercent: number): number`** — reine Klemmlogik: gibt eine Prozent-Position zurück, die den Tooltip innerhalb `[0, 100 - tooltipWidthPercent]` hält (und clamped nach unten auf `0`, falls `tooltipWidthPercent > 100`, was bei sehr schmalen Containern theoretisch möglich ist). `tooltipWidthPercent` wird vom Aufrufer übergeben, berechnet als `(TOOLTIP_WIDTH_PX / containerWidthPx) * 100`, wobei:
   - `TOOLTIP_WIDTH_PX = 140` (fester Schätzwert, neue Konstante direkt neben `CHART_WIDTH`/`CHART_HEIGHT` — der Tooltip zeigt ein Datum + bis zu 2 Modell-Zeilen in `text-xs`, 140px deckt den längsten realistischen Inhalt ab, keine dynamische Messung nötig)
   - `containerWidthPx` per `useRef` auf dem äußeren `<div className="relative ...">` (Zeile 252) und `.getBoundingClientRect().width`, einmal pro Render ausgelesen (kein `ResizeObserver` — Breite ändert sich nur bei Fenster-Resize, das ist wie oben beschrieben ein akzeptiertes Nicht-Ziel)

`useViewMode.ts`-Pattern wird nicht direkt importiert (dieser Hook ist an einen `storageKey` für Tabelle/Karten-Persistenz gebunden, hier wird kein Persistenz-State gebraucht) — statt dessen ein simpler, lokaler `isMobile`-Check per `window.matchMedia("(max-width: 639px)").matches`, einmalig beim Mount ermittelt (identisches Muster zu `useViewMode.ts`s Default-Erkennung, aber ohne dessen `localStorage`-Persistenz-Teil, der hier nicht gebraucht wird).

## Datenfluss

```
trend (voll, bis ~90 Einträge)
  │
  ├─ showTable === true  → SortableTable(trend)              [ungekürzt]
  │
  └─ showTable === false → chartTrend = isMobile ? trend.slice(-14) : trend
                              │
                              ├─ xFor/yFor/paths/tickIndices/endLabels
                              │    (alle bestehenden useMemo-Berechnungen,
                              │     jetzt über chartTrend statt trend)
                              │
                              ├─ onMouseMove/onMouseLeave (Desktop, unverändert)
                              │
                              ├─ onTouchStart/onTouchMove/onTouchEnd (neu, Mobile)
                              │    → nearestTrendIndex(...) → setHoverIndex
                              │    → onTouchEnd: hoverIndex bleibt gesetzt (Lock),
                              │      kein setHoverIndex(null)
                              │
                              └─ Tooltip-Render:
                                   left = clampTooltipLeftPercent(xFor(hoverIndex)/CHART_WIDTH*100, TOOLTIP_WIDTH_PERCENT_ESTIMATE)
```

**"Woanders hintippen löst den Tooltip":** ein Tap außerhalb des `<svg>`-Elements (z.B. auf einen anderen Chart-Bereich oder die Buttons darüber) löst ohnehin keinen der SVG-`onTouch*`-Handler aus — der Tooltip bleibt dann bestehen, bis das SVG erneut berührt wird. Das ist für diesen Anwendungsfall ausreichend (kein Overlay/Backdrop-Klick-Handler nötig) — ein Tap auf einen ANDEREN Punkt im selben SVG bewegt den Lock ganz natürlich über `onTouchStart`.

## Fehlerfälle

- **`trend.length === 0`:** bereits behandelt (Zeile 213-215, "Noch keine Trend-Daten vorhanden…"), von diesem Feature nicht berührt.
- **`trend.length < 14`:** `trend.slice(-14)` ist dann ein No-Op (gibt das ganze Array zurück) — kein Sonderfall nötig.
- **`hoverIndex` außerhalb der (gekürzten) `chartTrend`-Länge nach einem Mobile/Desktop-Wechsel:** `isMobile` wird einmalig beim Mount ermittelt (kein Resize-Listener, gleiches Muster wie `useViewMode.ts` — ein Wechsel während der Sitzung durch Fenster-Resize ist ein bekanntes, akzeptiertes Nicht-Ziel dieser App an anderen Stellen, hier konsistent übernommen).

## Testing

Beide neuen reinen Funktionen bekommen `vitest`-Unit-Tests (gleiches Muster wie `derive.test.ts`/`useHideOnScroll.test.ts` aus der vorherigen Session):

- `nearestTrendIndex`: Testfälle für Mitte, linker Rand, rechter Rand, und Clamping bei Werten außerhalb `[0, pointCount-1]`.
- `clampTooltipLeftPercent`: Testfälle für "Punkt weit links" (keine Klemmung nötig), "Punkt weit rechts" (Klemmung greift, Ergebnis ≤ `100 - tooltipWidthPercent`), "Punkt in der Mitte" (keine Klemmung nötig).

Touch-Event-Verdrahtung selbst (JSX-Handler-Zuordnung) ist ohne echten Browser nicht sinnvoll unit-testbar — Verifikation dafür ist `npm run typecheck` + `npm run build`, wie bei den rein-präsentativen Tasks der letzten Session.

## Betroffene Dateien

- Modify: `frontend/src/components/MlGenauigkeitTab.tsx` (beide `TrendChart`-Aufrufe profitieren automatisch, da geteilte Komponente)
- Create: `frontend/src/lib/mlChartMobile.ts` (die zwei pure functions, eigene Datei statt in `derive.ts` — thematisch enger an dieser einen Komponente, nicht app-weit wie `derive.ts`s Bewertungs-/Budget-Logik)
- Create: `frontend/src/lib/mlChartMobile.test.ts`

## Out of Scope

- Kein Wechsel auf eine Chart-Bibliothek (recharts o.ä.) — YAGNI, das bestehende SVG deckt alle drei Probleme gezielt ab.
- Kein Resize-Listener für `isMobile` (Fenster-Resize während der Sitzung ändert die Chart-Darstellung nicht nachträglich) — konsistent mit `useViewMode.ts`.
- Keine Änderung an der Tabellen-Ansicht (`showTable`) — zeigt weiterhin die volle Historie.
- Keine Änderung an Desktop-Verhalten.
