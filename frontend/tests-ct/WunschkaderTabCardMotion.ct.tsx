import { test, expect, type Page } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";
import { FADE_ENTER_S, FADE_EXIT_S, STAGGER_STEP_S } from "../src/lib/motionVariants";

// Statt gegen echte Animation-Frames zu racen (flaky - haengt vom
// Sample-Zeitpunkt ab), lesen wir die KONFIGURIERTEN Timing-Werte der
// Web-Animations-API direkt aus getAnimations() aus. Framer Motion nutzt fuer
// diese Opacity/Y-Tweens native WAAPI-Animationen; deren `delay` ist
// deterministisch aus der uebergebenen Transition abgeleitet, unabhaengig vom
// Sample-Zeitpunkt (im Gegensatz zum aktuellen Fortschritt/`opacity`-Wert, der
// sich mit echter Zeit aendert). Empirisch gegen diese Seite verifiziert
// (2026-08-05): getAnimations() liefert fuer die Karten-Wrapper zuverlaessig
// genau ein Animation-Objekt mit dem konfigurierten delay/duration.
// Nur ".grid > div"-Elemente MIT <dl> sind Karten-Wrapper (TargetCard nutzt
// <dl> fuer Marktwert/Schnitt/etc.) - schliesst die "+ Ziel"-Buttons und die
// Budget-Planungs-Karte (hat ein eigenes ".grid", aber keine <dl>) sicher aus.
async function readCardDelaysMs(page: Page): Promise<(number | null)[]> {
  return page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
    return cards.map((el) => {
      const anim = (el as HTMLElement).getAnimations()[0];
      return anim?.effect?.getComputedTiming().delay ?? null;
    });
  });
}

test.describe("Wunschkader-Kartenliste mit Motion-Wrapper", () => {
  test("Klick auf eine Karte oeffnet weiterhin das Detail-Modal", async ({ mount }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await expect(component.getByLabel("Notiz")).toBeVisible();
  });

  test("Entfernen loescht die Karte weiterhin und schreibt korrekt nach Firestore", async ({ mount, page }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0, { timeout: 1000 });
  });

  // Regression-Fang fuer den Live-Review-Fund (2026-08-05): der urspruengliche
  // Task-4-Stagger war strukturell tot - jede Karte war ueber initial/animate/
  // exit "self-controlling" (noetig fuer den Einzel-Exit beim Entfernen), und
  // ein self-controlling Kind wird von Framer Motion NICHT ins
  // variantChildren-Set des Elternteils aufgenommen, wodurch dessen
  // staggerChildren wirkungslos blieb - alle Karten kamen gleichzeitig rein.
  // Der Fix ersetzt das durch einen manuellen Delay pro Karten-Index
  // (custom-Prop + dynamische Variante in motionVariants.ts).
  test("Stagger: Enter-Delay ist pro Karten-Index gestaffelt, nicht gleichzeitig", async ({ mount, page }) => {
    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion1.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion2.player_id, role: "Starter" },
    ];
    await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    // Alle drei Ziele sind "Abwehr" (siehe FIXTURE_PLAYERS) - landen also in
    // derselben Positionsgruppe, in Eingabereihenfolge (Index 0/1/2). Ein
    // wirklich toter Stagger wuerde hier [0, 0, 0] liefern.
    const stepMs = STAGGER_STEP_S * 1000;
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs, stepMs * 2]);
  });

  // Regression-Fang fuer den zweiten, unabhaengigen Fund: WunschkaderTab
  // bleibt seit einem spaeteren Task permanent gemountet (App.tsx), eine
  // reine "beim Mount einmal animieren"-Loesung waere deshalb fuer den Nutzer
  // NIE sichtbar (die Animation liefe laengst hinter display:none ab, bevor
  // der Tab je besucht wird). isActive (von App.tsx als
  // `activeTab === "wunschkader"` durchgereicht) gated deshalb animate/initial
  // pro Karte, damit der Stagger bei jedem (Wieder-)Besuch neu ablaeuft.
  test("Stagger: Enter-Animation wird bei jedem (Wieder-)Aktivieren des Tabs neu abgespielt", async ({
    mount,
    page,
  }) => {
    const targets = [
      { player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" },
      { player_id: FIXTURE_PLAYERS.suggestion1.player_id, role: "Starter" },
    ];
    const stepMs = STAGGER_STEP_S * 1000;

    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    // Erster Besuch: Stagger laeuft, dann vollstaendig fertig (keine
    // Animation mehr aktiv - Framer Motion raeumt WAAPI-Animationen nach
    // Abschluss aus getAnimations() auf).
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs]);
    await expect.poll(() => readCardDelaysMs(page)).toEqual([null, null]);

    // Tab verlassen: isActive faellt auf false, Karten fallen auf den
    // initial-State (opacity 0) zurueck (im echten App.tsx laengst hinter
    // display:none, hier direkt sichtbar simuliert). Erst NACH diesem
    // vollstaendigen Ruecksprung wieder aktivieren, damit der naechste Schritt
    // eindeutig ein frischer Neustart ist, kein blosses Weiterlaufen einer
    // schon laufenden Animation.
    await component.update(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={false} />
    );
    await expect
      .poll(() =>
        page.evaluate(() => {
          const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
          return cards.map((el) => getComputedStyle(el).opacity);
        })
      )
      .toEqual(["0", "0"]);

    // Tab erneut betreten: der Stagger MUSS erneut mit denselben
    // index-basierten Delays ablaufen - das ist der eigentliche Beweis fuer
    // den zweiten Fix (kein "nur beim allerersten Mount"-Verhalten mehr).
    await component.update(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );
    await expect.poll(() => readCardDelaysMs(page)).toEqual([0, stepMs]);
  });

  // Reorder-Interaktions-Beleg (Review-Fund 2026-08-06: die urspruengliche
  // Version dieses Tests pruefte nur den bereits SETTLEDen Endzustand
  // (opacity "1"), nicht die eigentliche Behauptung "die layoutId-Reorder-
  // Animation kollidiert nicht mit dem index-basierten Delay"). Ground Truth
  // per DOM-Untersuchung waehrend der Transition (nicht angenommen):
  // Bank und Positionsgruppe sind unterschiedliche Eltern-Grids, ein
  // Wechsel per Button ist deshalb ein GENUINER React-Unmount+Mount (zwei
  // verschiedene DOM-Knoten), keine Wiederverwendung desselben Knotens -
  // layoutId sorgt nur dafuer, dass Framer Motion den neuen Knoten optisch
  // an der Bildschirmposition des alten starten laesst (sichtbar an einem
  // sich kontinuierlich aendernden `transform`, das NICHT ueber
  // getAnimations() laeuft - Framer Motions eigene rAF-getriebene
  // Projektion, kein natives WAAPI-Objekt). Die opacity/y-Variante (unser
  // Exit/Enter) LAEUFT dagegen als eigenes natives WAAPI-Animation-Objekt
  // (Element.animate()), getrennt von dieser Projektion.
  //
  // Zweiter Review-Fund, diesmal ein ECHTER CI-Fehlschlag (2026-08-06): eine
  // erste Version dieses Tests las die Timings per getAnimations() NACH dem
  // Klick, ungepollt. Auf einem langsameren Runner war das Zeitfenster
  // (130ms/180ms) zwischen Klick und Read bereits geschlossen - Framer Motion
  // hatte die fertigen WAAPI-Animationen schon aus getAnimations() entfernt,
  // delay/duration kamen als null zurueck (kein Produktbug, reine
  // Test-Racing-Schwaeche). Pollen loest das NICHT zuverlaessig: ist das
  // Zeitfenster bereits VOR dem ersten Poll-Versuch geschlossen, liefert auch
  // jeder weitere Versuch dauerhaft null - mehr Versuche helfen nicht gegen
  // ein Fenster, das sich nicht wieder oeffnet. Stattdessen faengt dieser Test
  // jeden Element.animate()-Aufruf SYNCHRON beim Erzeugen ab (Element.prototype.
  // animate patchen, bevor der Klick ausgeloest wird) - der jeweilige Wert
  // wird in dem Moment eingefangen, in dem Framer Motion animate() aufruft,
  // und bleibt danach unveraendert im Testkontext erhalten, unabhaengig
  // davon, wie viel Zeit bis zum Read vergeht.
  //
  // Der `transform`-Beleg (siehe oben, "Positions-Projektion tatsaechlich
  // aktiv") wird an derselben Stelle mitgenommen - kein zweiter, separat
  // racender Read noetig. Empirisch verifiziert (2026-08-06): im selben
  // Moment, in dem Framer Motion Element.animate() fuer die Opacity/Y-
  // Transition aufruft, hat die rAF-Projektion bereits eine von der Ruhelage
  // abweichende Matrix gesetzt (z.B. "matrix(1, 0, 0, 1, 0, 1.34006)" /
  // "matrix(1, 0, 0, 1, 0, -442.66)") - die Projektion laeuft also bereits,
  // bevor die WAAPI-Animation ueberhaupt gestartet ist.
  //
  // Dritter Review-Fund, live auf dem echten CI-Runner reproduziert (2026-08-
  // 06, siehe Kommentar direkt vor dem Poll unten): WANN Framer Motion
  // Element.animate() ueberhaupt zum ersten Mal aufruft, ist selbst nicht
  // synchron mit dem Klick - das haengt an einem eigenen rAF-Tick fuer die
  // Rect-Messung der layoutId-Projektion, dessen Zeitpunkt runner-abhaengig
  // ist. Der erste, ungepollte Anlauf dieses Fixes kam auf dem CI-Runner
  // deshalb mit einem komplett LEEREN captured-Array zurueck (0 statt 2
  // Eintraege), nicht mit den urspruenglichen null-Werten. Die Werte selbst
  // sind weiterhin racefrei erfasst (siehe oben) - nur das "ist der Capture
  // ueberhaupt schon passiert" braucht ein Warten. Anders als bei
  // getAnimations() ist dieses Warten aber ungefaehrlich: das Array WAECHST
  // nur, ein einmal gepushter Eintrag verschwindet nie wieder - "auf 2
  // Eintraege pollen" ist eine monotone Bedingung (genau einmal wahr, danach
  // fuer immer wahr), kein Wettlauf gegen ein sich wieder schliessendes
  // Fenster wie beim urspruenglichen getAnimations()-Bug.
  test("Reorder: Exit- und Enter-Timing bleiben waehrend der layoutId-Positions-Projektion unveraendert, danach genau eine sichtbare Instanz", async ({
    mount,
    page,
  }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} isActive={true} />
    );

    await expect.poll(() => readCardDelaysMs(page)).toEqual([null]);

    // Aktuellen (einzigen) Karten-Knoten markieren, damit wir ihn nach dem
    // Wechsel zweifelsfrei vom neuen Knoten unterscheiden koennen - das
    // Attribut bleibt auch nach dem Entfernen aus dem DOM lesbar (haengt nicht
    // an der Dokument-Anbindung).
    await page.evaluate(() => {
      document.querySelectorAll(".grid > div").forEach((el) => {
        if (el.querySelector("dl")) el.setAttribute("data-pre-move", "true");
      });
    });

    // Patch VOR dem Klick installieren, damit beide durch den Wechsel
    // ausgeloesten animate()-Aufrufe (Exit des alten, Enter des neuen Knotens)
    // sicher erfasst werden.
    await page.evaluate(() => {
      (window as any).__capturedCardAnims = [] as {
        isPreMoveNode: boolean;
        delay: number | null;
        duration: number | null;
        transform: string;
      }[];
      const originalAnimate = Element.prototype.animate;
      Element.prototype.animate = function (this: Element, keyframes: unknown, options: unknown) {
        const anim = originalAnimate.call(this, keyframes as Keyframe[], options as KeyframeAnimationOptions);
        if (this.querySelector("dl")) {
          const timing = anim.effect?.getComputedTiming();
          (window as any).__capturedCardAnims.push({
            isPreMoveNode: this.hasAttribute("data-pre-move"),
            delay: timing?.delay ?? null,
            duration: timing?.duration ?? null,
            transform: getComputedStyle(this).transform,
          });
        }
        return anim;
      };
    });

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Bank" }).click();

    // Dritter Review-Fund (2026-08-06, live auf dem CI-Runner reproduziert,
    // nicht nur theoretisch): ein SOFORTIGER Read direkt nach den Klicks kam
    // dort mit einem VOELLIG LEEREN captured-Array zurueck (0 statt 2
    // Eintraege) - nicht die urspruengliche null-Werte-Symptomatik. Ursache:
    // die layoutId-Projektion muss die Rects beider Knoten zuerst messen
    // (getBoundingClientRect nach Layout/Paint), bevor Framer Motion die
    // Element.animate()-Aufrufe fuer Exit/Enter ausloest - dieser Schritt
    // haengt an einem eigenen rAF-Tick, nicht mehr an derselben synchronen
    // Turn wie der Klick. Wie viele Ticks das braucht, ist runner-abhaengig
    // (auf einem schnellen Rechner faellt der Tick in dieselbe JS-Turn wie
    // der nachfolgende Read, auf einem 2-Worker-CI-Runner nicht zuverlaessig).
    // Der Unterschied zu getAnimations() bleibt aber bestehen: das Array
    // WAECHST nur (bereits gepushte Eintraege verschwinden nie wieder) -
    // "auf 2 Eintraege warten" ist deshalb, anders als das urspruengliche
    // Pollen auf getAnimations(), kein Wettlauf gegen ein sich wieder
    // schliessendes Fenster, sondern eine monotone Bedingung, die exakt einmal
    // wahr wird und dann wahr bleibt.
    await expect
      .poll(() => page.evaluate(() => (window as any).__capturedCardAnims.length))
      .toBe(2);

    // Sortiert nach isPreMoveNode statt sich auf eine bestimmte
    // Aufruf-Reihenfolge zu verlassen.
    const captured = await page.evaluate(() =>
      (
        (window as any).__capturedCardAnims as {
          isPreMoveNode: boolean;
          delay: number | null;
          duration: number | null;
          transform: string;
        }[]
      )
        .slice()
        .sort((a, b) => Number(b.isPreMoveNode) - Number(a.isPreMoveNode))
    );

    expect(captured).toEqual([
      // Alter (exiting) Knoten, noch in der Positionsgruppe: seine eigene
      // Exit-Animation, unveraendert.
      { isPreMoveNode: true, delay: 0, duration: FADE_EXIT_S * 1000, transform: expect.any(String) },
      // Neuer (entering) Knoten, jetzt auf der Bank: seine eigene
      // Enter-Animation mit dem fuer SEINEN Index (0) korrekten Delay,
      // unveraendert.
      { isPreMoveNode: false, delay: 0, duration: FADE_ENTER_S * 1000, transform: expect.any(String) },
    ]);
    // Die Positions-Projektion muss dabei tatsaechlich aktiv sein (sonst waere
    // "keine Kollision" nur, weil gar nichts gleichzeitig laeuft) - erkennbar
    // an einem von der Ruhelage ("none") abweichenden transform auf
    // mindestens einem der beiden Knoten. Derselbe synchrone Erfassungspunkt
    // wie delay/duration (siehe Kommentar oben) - kein zusaetzlicher,
    // zeitabhaengiger Read.
    expect(captured.some((c) => c.transform !== "none")).toBe(true);

    await component.getByRole("button", { name: "Schließen" }).click();

    await expect
      .poll(() =>
        page.evaluate(() => {
          const cards = Array.from(document.querySelectorAll(".grid > div")).filter((el) => el.querySelector("dl"));
          return cards.map((el) => getComputedStyle(el).opacity);
        })
      )
      .toEqual(["1"]);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(1);
  });
});
