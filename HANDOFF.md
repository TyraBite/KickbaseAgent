# Handoff: Firestore-Migration Phase 3-5 + Dashboard-Erweiterungen (Alle-Spieler/Wunschkader-Edit)

**Generated**: 2026-07-27 (Ende der Session, Phase 1+2 fertig committed)
**Branch**: main
**Status**: In Progress — Phase 1+2 done, Phase 3-5 noch zu planen/umzusetzen, danach zwei neue Feature-Requests (bereits geplant, noch nicht umgesetzt)

## Goal

`docs/dashboard.html` von "1x/Tag generierte, self-contained HTML-Datei"
zu einem live-gehosteten, zugriffsgeschuetzten Web-App umbauen (ersetzt
den alten Discord-Daily-Report komplett). 5-Phasen-Architektur, komplett
spezifiziert in
`docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md`.
Phase 1+2 sind fertig; **Phase 3 (Public Hosting), Phase 4 (ML-Historie),
Phase 5 (Mobile/UX)** stehen noch aus. Zusaetzlich hat der User waehrend
dieser Session zwei neue Dashboard-Features gewollt (Alle-Spieler-Tab +
editierbarer Wunschkader mit Firestore-Schreibzugriff aus dem Browser) —
**diese kommen NACH Phase 3-5 dran, nicht davor** (expliziter User-Wunsch,
siehe Resume Instructions).

## Completed (diese Session)

- [x] **Phase 1** (Firestore-Schreibpfad, commit `26546ee`): neues Modul
  `src/firestore_db.py` spiegelt `src/db.py`s `replace_*`/`upsert_*`-
  Funktionen als batched Firestore-Writes, hinter `FIRESTORE_ENABLED`-Flag
  in `src/fetcher.py::run()` und `src/market_predictor.py::
  _append_todays_predictions()` verdrahtet. 32 Tests gruen, live gegen
  echtes Firebase-Projekt "kickbaseagent" verifiziert.
- [x] **Phase 2** (Firebase Auth + Live-Read, commit `401140f`):
  `docs/dashboard.html` ist jetzt eine duenne Shell — Login per Firebase
  Auth (Email/Passwort), danach EINMALIGER `getDoc()` von
  `dashboard_snapshot/latest`, dann die bestehenden `render*`-Funktionen
  unveraendert aufgerufen. Neue `firestore_db.upsert_dashboard_snapshot()`
  schreibt den kompletten berechneten Dashboard-Datensatz als EIN
  Dokument (kein Client-seitiges Nachbauen der Python-Joins/ML-Logik).
  `_HTML_TEMPLATE`/`_render_html()`/`OUTPUT_PATH` aus
  `src/dashboard_export.py` komplett entfernt — `dashboard.html` wird ab
  jetzt NICHT mehr generiert, sondern ist eine normale, handgepflegte
  Quelldatei. Neue Datei `firestore.rules` (deny-all ausser Lesezugriff
  auf `dashboard_snapshot` fuer die eine autorisierte UID). 33 Tests
  gruen.
- [x] **Kaderplanung (Torwart)**: Rönnow-Gebot verloren — an **Fassii**
  (nicht Fleischmanns, wie User zunaechst dachte), fuer 7.900.558
  (`get_activities_feed` bestaetigt, Zeitstempel 2026-07-27T17:33:09Z).
  Marktrecherche + Ligaweite Free-Agent-Analyse (alle ~450 Spieler via
  `player_valuation.fetch_all_players()` + `resolve_ownership()`)
  ergab: **Zentner** (Mainz, Rang 1, 9.68M) als Plan-A — historisch
  starker Stammkeeper (32 Spiele/3740 Pkt in der besten Saison), letzte
  Saison nur 10 Spiele/728 Pkt (Ausreisser-Jahr, vermutlich
  Verletzung/Rotation). **Heuer Fernandes** (Hamburg, Rang 1, 11.15M) als
  Beobachtungs-Kandidat — konstantester der Kandidaten (jede Saison
  27-33 Spiele, Ø 90-110), teurer. Baumann (Fleischmanns' Verkaufsangebot,
  19.08M) und die theoretischen Top-Free-Agents (Kobel, Nicolas, Dahmen
  etc.) wurden verworfen/zurueckgestellt (siehe Failed Approaches).
  **Noch keine Kaufentscheidung final umgesetzt** — User wollte erst mit
  Zentner planen, kein Kauf in dieser Session ausgefuehrt.

## Not Yet Done

- [ ] **Phase 3** (Hosting/Deploy): Repo public machen (User muss das
  bewusst entscheiden, siehe Warnings), GitHub Pages einrichten, Cron auf
  alle 2h umstellen, `firebase-service-account.json`-Inhalt als GitHub-
  Actions-Secret hinterlegen, `.github/workflows/dashboard.yml` um
  `FIRESTORE_ENABLED`+Secret erweitern, alten Discord-Job
  (`.github/workflows/daily.yml`) ablösen/entfernen.
- [ ] **Phase 4** (ML-Historie nutzen): `ml_prediction_log`-Collection
  (aus Phase 1) fuer Genauigkeits-Trend-Anzeige im Dashboard nutzen,
  perspektivisch datengetriebene Modell-/Hyperparameter-Wahl.
- [ ] **Phase 5** (Mobile/UI-UX): braucht laut Spec einen dedizierten
  User-Interview-Schritt VOR dem Design (nicht aus Annahmen heraus
  gestalten) — noch nicht begonnen.
- [ ] **Feature-Request 1 — Alle-Spieler-Tab**: neuer Dashboard-Tab mit
  allen ~450 Liga-Spielern, filterbar (Position/Verein/Verfuegbarkeit).
  Plan bereits fertig geschrieben und vom User freigegeben, siehe Code
  Context unten.
- [ ] **Feature-Request 2 — Editierbarer Wunschkader**: Zielspieler im
  Dashboard direkt ersetzen/entfernen/hinzufuegen koennen, inkl.
  "Wechsel"-Button (3 Vorschlaege: gleiche Position, aktuell von
  niemandem gehalten, marktwert-/punkteschnitt-nah). User will ECHTES
  In-Browser-Speichern (neuer Firestore-Schreibpfad vom Client, nicht nur
  Anzeige+Chat-Edit). Plan ebenfalls fertig und freigegeben.
  **Explizite Reihenfolge-Vorgabe vom User: diese zwei Feature-Requests
  erst NACH Phase 3-5, nicht davor.**
- [ ] **Torwart-Kaufentscheidung**: Zentner tatsaechlich bieten/kaufen
  (noch nicht ausgefuehrt), `data/wunschkader.json`s Rönnow-Eintrag
  (`targets[0]`, Zeile 22) ist noch NICHT aktualisiert — zeigt weiterhin
  faelschlich "Gebot fuehrend" obwohl das Gebot an Fassii verloren ging.

## Failed Approaches (Don't Repeat These)

- **Baumann (Fleischmanns' aktives Verkaufsangebot, 19.08M, Rang 1) als
  Torwart-Empfehlung vorgeschlagen**, bevor der User praezisierte: er
  wollte nur Spieler sehen, die aktuell bei KEINEM anderen Manager im
  Kader sind (reine Free-Agent-Analyse). Baumann faellt aus diesem Filter
  raus (gehoert Fleischmanns) — bleibt aber die einzige SOFORT kaufbare
  Rang-1-Option, da alle echten Free-Agent-Rang-1-Keeper (Kobel, Nicolas,
  Dahmen etc.) grad nicht im System-Markt gelistet sind, nur zufaellig
  alle 2h auftauchen koennten.
- **Hein (Bremen) wirkte auf den ersten Blick wie ein Steal** (Ø 164
  Punkte laut `fetch_all_players()`) — bei genauerem Hinsehen war das ein
  2-Spiele-Sample (`get_player_performance`), praktisch Rauschen. Sein
  echtes Niveau aus der Vorsaison (31 Spiele) liegt bei Ø 73.2 — kein
  Steal mehr. **Lehre: `points_avg`/`ap`-Feld aus `fetch_all_players()`
  IMMER gegen `get_player_performance()`s tatsaechliche Spielanzahl
  gegenchecken, bevor man es als belastbaren Wert zitiert** — kleine
  Stichproben verzerren den Durchschnitt massiv.
- **User erinnerte sich, Backhaus sei Bremens Torwart** — live gegen
  `fetch_all_players()` geprüft: Backhaus spielt inzwischen fuer
  **Freiburg** (Rang 1 dort). Immer gegen Live-Daten pruefen statt alte
  Erinnerungen/Annahmen fortzuschreiben (siehe
  `feedback_verify_data_before_asserting`-Memory).
- **Plan-Mode-Subagent konnte Phase-2-Implementierung nicht ausfuehren**,
  weil der Sub-Agent-Prozess den Plan-Mode-Zustand der Hauptsession erbte
  (kein `ExitPlanMode`-Tool im Sub-Agent verfuegbar) — er schrieb nur
  einen Ausfuehrungs-Checklisten-Plan statt Code. Fix: erst im Hauptthread
  `ExitPlanMode` aufrufen (User-Freigabe einholen), DANACH den
  Implementierungs-Agenten neu dispatchen — Plan-Mode-Status muss VOR dem
  Dispatch aufgeloest sein, nicht danach.
- **Phase 2 wurde urspruenglich so geplant, dass `docs/dashboard.html`
  weiterhin bei jedem Pipeline-Lauf neu generiert wird** (nur ohne
  Daten-Blob) — User entschied sich stattdessen fuer "Generierung
  stoppen", die Datei ist jetzt eine normale handgepflegte Quelldatei.
  `_HTML_TEMPLATE` wurde komplett aus `dashboard_export.py` entfernt statt
  nur den Daten-Platzhalter zu aendern.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `dashboard_snapshot/latest` als EIN Firestore-Dokument (voller berechneter `data`-Dict, 64 KB) statt Client liest die 6 rohen Phase-1-Collections | Vermeidet Duplizierung von `dashboard_export.py`s Join-/ML-/Fairwert-Logik in Client-JS; 64 KB weit unter Firestores 1-MiB-Limit |
| Einmaliger Read (kein `onSnapshot`-Live-Listener) | Passt zum echten 2h-Update-Takt; verhindert Reset von Filter/Sortierung/Suche waehrend Nutzung, da jede `render*`-Funktion ihren State bei jedem Aufruf neu baut |
| Firebase Auth Email/Passwort (Pseudo-Mail `tyrabite@kickbaseagent.de`, Platzhalter-Passwort `passwort1234`) statt Google Sign-In | Gleiche Konvention wie f1-tipping-game-Projekt; Passwort ist bewusster Platzhalter, User rotiert spaeter selbst |
| `docs/dashboard.html` wird NICHT mehr generiert, ist ab jetzt handgepflegt | User-Entscheidung — kein zweiter Ort (Python-Template vs. generierte Datei), an dem der Stand auseinanderlaufen kann |
| Kein Logout-Button in Phase 2 | Sicherheits-Property haengt an Firestore Rules, nicht an UI; einziger Nutzer, auf Phase 5 verschoben |
| Editierbarer Wunschkader bekommt ECHTEN Client-Schreibpfad nach Firestore (nicht nur Anzeige+Chat-Edit) | Expliziter User-Wunsch (AskUserQuestion beantwortet) — braucht neue Security Rule + Datenfluss-Umkehr (Browser schreibt zuerst, Pipeline liest zurueck und spiegelt nach `data/wunschkader.json` fuer Git-Historie) |
| Feature-Requests (Alle-Spieler/Wunschkader-Edit) erst NACH Phase 3-5 | Expliziter User-Wunsch in dieser Session, überschreibt die urspruengliche Reihenfolge "gleich nach Phase 2" |

## Current State

**Working**: Phase 1+2 committed und verifiziert (33 Unit-Tests gruen,
live gegen echtes Firebase-Projekt getestet). `docs/dashboard.html` hat
Login-Form + Firestore-Read-Logik, alle bestehenden `render*`-Funktionen
unveraendert.

**Broken/Offen**:
- `firestore.rules` hat noch den Platzhalter
  `"REPLACE_WITH_UID_FROM_FIREBASE_CONSOLE"` statt der echten UID — die
  Regel ist noch NICHT in der Firebase Console published (siehe TODO-
  Kommentar im Dateikopf). Ohne echte UID + Publish funktioniert der
  Login/Read-Flow nicht.
- Interaktives Browser-Testen (Login-Formular durchklicken) wurde NICHT
  gemacht — der Implementierungs-Agent hatte keinen echten Browser zur
  Verfuegung, nur statische Code-Verifikation (IDs/Funktionsnamen
  gegengeprueft, kein `__DASHBOARD_DATA__`-Rest gefunden).
- `data/wunschkader.json`s Rönnow-Eintrag zeigt noch faelschlich "Gebot
  fuehrend" — noch nicht auf "verloren an Fassii" aktualisiert.

**Uncommitted Changes**: `MDs/*.md` (5 Dateien) und `data/kickbase.db` —
wie in der vorherigen HANDOFF.md-Version dokumentiert, reine CRLF-
Zeilenende-Aenderungen (Windows-Tool auf dem geteilten DrvFs-Mount), kein
inhaltlicher Unterschied, bewusst unangetastet gelassen.

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md` | Die volle 5-Phasen-Architektur — Phase 3/4/5 stehen dort nur als Kurzabsatz, brauchen jeweils eigenen Plan->Umsetzungs-Zyklus |
| `/home/node/.claude/plans/hol-dir-den-rest-indexed-clover.md` | **Der fertige, freigegebene Plan fuer die zwei Feature-Requests** (Alle-Spieler-Tab + editierbarer Wunschkader) — komplett ausgearbeitet, noch NICHT umgesetzt. Kommt erst nach Phase 3-5 dran |
| `firestore.rules` | Neue Datei, Platzhalter-UID muss noch ersetzt + in Firebase Console published werden |
| `src/dashboard_export.py` | `export()` gibt jetzt `data`-Dict zurueck (nicht mehr `Path`); `_HTML_TEMPLATE` existiert nicht mehr |
| `docs/dashboard.html` | Ab jetzt handgepflegte Quelldatei, NICHT mehr generiert — Aenderungen direkt hier machen |
| `data/wunschkader.json` | `targets[0]` (Rönnow) muss auf "verloren an Fassii, 7.900.558" aktualisiert werden, sobald User eine Torwart-Entscheidung final trifft |
| `.github/workflows/dashboard.yml` | Fuer Phase 3 relevant: braucht noch `FIRESTORE_ENABLED`+Service-Account-Secret, committet aktuell noch `docs/dashboard.html` obwohl die Datei nicht mehr generiert wird (harmloser No-Op-Schritt, siehe Plan-Datei) |

## Code Context

**Aktueller `export()`-Rueckgabewert-Wechsel** (relevant fuer alles, was
`dashboard_export.export()` aufruft):
```python
def export() -> dict:  # vorher: -> Path
    ...
    return data  # vorher: return OUTPUT_PATH
```

**Firestore-Snapshot-Schreibpfad** (Muster fuer jeden weiteren
Firestore-Write, z.B. den geplanten Wunschkader-Schreibpfad):
```python
if os.environ.get("FIRESTORE_ENABLED"):
    try:
        fs_client = firestore_db.connect()
        firestore_db.upsert_dashboard_snapshot(fs_client, data)
    except Exception as exc:
        print(f"Warnung: Firestore-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)
```

**Client-seitiger Read-Flow** (`docs/dashboard.html`, ab Zeile ~687):
```js
onAuthStateChanged(auth, async (user) => {
  if (!user) { showState("login-gate"); return; }
  showState("loading-state");
  const snap = await getDoc(doc(db, "dashboard_snapshot", "latest"));
  if (!snap.exists()) { showState("load-error-state"); return; }
  DATA = snap.data();
  showState("dashboard-content");
  renderAll();
});
```

## Resume Instructions

1. **Sofort noetig, bevor Phase 2 wirklich nutzbar ist**: User muss in
   der Firebase Console (Authentication -> Users) die UID von
   `tyrabite@kickbaseagent.de` kopieren, in `firestore.rules` den
   Platzhalter `REPLACE_WITH_UID_FROM_FIREBASE_CONSOLE` ersetzen, dann
   den Regel-Inhalt in Firestore Database -> Rules -> Publish einfuegen.
2. Dann Browser-Test: `cd docs && python -m http.server 8000`, im
   Browser `http://localhost:8000/dashboard.html` oeffnen, mit
   `tyrabite@kickbaseagent.de`/`passwort1234` einloggen.
   - Erwartung: kurzer "Lade Daten…"-Zustand, dann das gewohnte Dashboard
     mit allen Tabs.
   - Falls Fehler: Firestore Console pruefen, ob `dashboard_snapshot/
     latest` ueberhaupt existiert (ggf. einmal
     `FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python -m src.dashboard_export`
     laufen lassen).
3. **Danach mit Phase 3 weitermachen** (Spec-Doc als Ausgangspunkt,
   eigener Plan->Umsetzungs-Zyklus noetig): Repo-public-Entscheidung mit
   User klaeren, GitHub Pages, Cron auf 2h, CI-Secret fuer Service-Account.
4. Phase 4, dann Phase 5 (mit User-Interview-Schritt) danach, jeweils
   eigener Plan.
5. **Erst danach** die zwei Feature-Requests aus
   `/home/node/.claude/plans/hol-dir-den-rest-indexed-clover.md`
   umsetzen (Plan ist fertig, nur noch Implementierung + Verifikation
   noetig, siehe Verifikations-Abschnitt dort).
6. Torwart-Entscheidung mit User abschliessen (Zentner bieten?),
   `data/wunschkader.json`s Rönnow-Eintrag korrigieren sobald final
   entschieden.

## Setup Required

- Firebase-Console-Schritt aus Resume Instructions #1 (UID + Rules
  Publish) — ohne das ist Phase 2 nicht live nutzbar, auch wenn der Code
  fertig ist.
- Sonst nichts Neues gegenueber der letzten HANDOFF.md-Version (Firebase-
  Projekt/Service-Account/Firestore bereits vollstaendig eingerichtet).

## Warnings

- **Repo ist weiterhin privat** — Phase 3 (public machen) braucht
  explizite User-Zustimmung, nicht automatisch ausfuehren.
- **`firebase-service-account.json` niemals committen** — weiterhin
  gitignored, weiterhin sicherheitsaequivalent zu `KICKBASE_PASSWORD`.
- Reihenfolge fuer morgen ist explizit vom User vorgegeben: **Phase 3-5
  VOR** den zwei Feature-Requests, auch wenn deren Plan bereits fertig
  daliegt — nicht aus Bequemlichkeit die Reihenfolge tauschen.
- `MDs/*.md` und `data/kickbase.db` zeigen als "modified" — das ist die
  bekannte CRLF-Sache aus der letzten Session, kein neues Problem, nicht
  versehentlich mitcommitten ohne nachzuschauen was drin steht.
