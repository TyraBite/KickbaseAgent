# Alle-Spieler-Tab + Editierbarer Wunschkader (Firestore-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Neuer Dashboard-Tab "Alle Spieler" (alle ~450 Liga-Spieler,
filterbar) und ein editierbarer Wunschkader-Tab (Ersetzen/Entfernen/
Hinzufuegen, "Wechsel"-Vorschlag, echtes Speichern aus dem Browser).
**Kompletter `wunschkader.json`-Inhalt zieht dabei in Firestore um**
(`wunschkader/current`) — die lokale Datei wird geloescht, kein Git-Spiegel
(User-Entscheidung: Historie ist nur fuer ML-Ergebnisse relevant, kommt in
Phase 4 separat).

**Architecture:** Firestore wird alleinige Quelle fuer den kompletten
Wunschkader-Datensatz (`targets`, `sell_list`, `markup_rules`,
`login_bonus`, `formation`, `season_start` — alle Top-Level-Keys der
bisherigen Datei als EIN Dokument). Die Python-Pipeline liest/schreibt
per Admin-SDK (umgeht Rules), der Browser schreibt nur `targets` on Save,
aber immer den KOMPLETTEN Wunschkader-Datensatz zurueck (liest den Rest
unveraendert aus dem bereits geladenen `dashboard_snapshot` mit). Kein
Client-seitiges Nachbauen von Fairwert/Status/ML-Logik (bestehendes
Projekt-Prinzip) — nach einem Save zeigt das Dashboard weiterhin den
Stand vom letzten Pipeline-Lauf fuer die BERECHNETEN Wunschkader-Spalten
(Status/Fairwert/ML), erst der naechste 2h-Lauf rechnet den neuen
`targets`-Stand komplett durch.

**Tech Stack:** Python (`firestore_db.py`, `dashboard_export.py`),
Firestore (Client-SDK im Browser + Admin-SDK in der Pipeline), vanilla JS
(`index.html`), `firebase-tools` CLI fuer Rules-Deploy.

## Global Constraints

- `data/wunschkader.json` wird nach der Migration GELOESCHT, kein
  Git-Spiegel — Historie ist bewusst nicht mehr Teil dieses Features
  (User-Entscheidung 2026-07-28).
- `_load_wunschkader()` ist danach Firestore-only (kein lokaler Fallback
  mehr) — ohne `FIRESTORE_ENABLED`/Zugriff gibt es `None` zurueck
  (bestehendes Resilienz-Pattern: Firestore-Ausfall darf Pipeline nie crashen).
- Alle neuen Firestore-Funktionen folgen exakt dem bestehenden Muster in
  `src/firestore_db.py` (siehe `upsert_dashboard_snapshot`/`connect()`).
- Kein neuer `onclick=`-Inline-Handler in `index.html` — Projekt nutzt
  durchgehend `addEventListener` (bestaetigt, aktuell 0 Treffer fuer `onclick=`).
- `data["wunschkader_raw"]` (voller roher Firestore-Dokument-Inhalt) muss
  Teil des `dashboard_snapshot`-Exports werden, damit der Browser beim
  Speichern den Rest des Dokuments (sell_list/markup_rules/login_bonus/
  formation/season_start) unveraendert mitschreiben kann, ohne einen
  zusaetzlichen Firestore-Read zu brauchen.
- Security Rule fuer `wunschkader` erlaubt read+write fuer die eine
  autorisierte UID (`lC85qOItQ1M6bRjzqnYcgBkLVDF2`) — Abweichung vom
  `dashboard_snapshot`-Muster ("nur Pipeline schreibt"), da hier bewusst
  der Browser selbst schreibt.
- **Git-Workflow (siehe HANDOFF.md-Warnings)**: Commits lokal lassen,
  NICHT pushen, keine Feature-Branches — User pusht selbst.

---

### Task 1: Firestore-Backend fuer Wunschkader (`firestore_db.py`)

**Files:**
- Modify: `src/firestore_db.py` (zwei neue Funktionen, ans Dateiende anhaengen)
- Test: `tests/test_firestore_db.py` (neue Test-Klassen)

**Interfaces:**
- Produziert: `get_wunschkader(client: firestore.Client) -> dict | None`,
  `upsert_wunschkader(client: firestore.Client, data: dict) -> None` — von
  Task 2 (`dashboard_export.py`) genutzt.

- [ ] **Schritt 1: Zwei neue Funktionen in `src/firestore_db.py` (Ende der Datei, nach `upsert_dashboard_snapshot`)**

```python
def get_wunschkader(client: firestore.Client) -> dict | None:
    """Liest den kompletten Wunschkader-Datensatz (targets/sell_list/
    markup_rules/login_bonus/formation/season_start als EIN Dokument,
    ehemals data/wunschkader.json). None falls noch kein Dokument existiert
    (vor der einmaligen Migration)."""
    doc = client.collection("wunschkader").document("current").get()
    return doc.to_dict() if doc.exists else None


def upsert_wunschkader(client: firestore.Client, data: dict) -> None:
    """Ueberschreibt den kompletten Wunschkader-Datensatz. Wird sowohl von
    der Pipeline (Migration/Bootstrap) als auch vom Browser (Speichern-
    Button im Dashboard) aufgerufen - client-seitig per Firestore Client-
    SDK, hier nur der Admin-SDK-Pfad."""
    client.collection("wunschkader").document("current").set(data)
```

- [ ] **Schritt 2: Tests in `tests/test_firestore_db.py` (nutzt bestehende `_doc_ids`-Helper, gleiches Muster wie `UpsertDashboardSnapshotTests`)**

```python
class GetWunschkaderTests(unittest.TestCase):
    def test_returns_none_when_document_missing(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        result = firestore_db.get_wunschkader(client)

        self.assertIsNone(result)

    def test_returns_dict_when_document_exists(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"targets": [{"name": "Krauß"}], "formation": "3-4-3"}

        result = firestore_db.get_wunschkader(client)

        client.collection.assert_any_call("wunschkader")
        client.collection.return_value.document.assert_called_with("current")
        self.assertEqual(result["formation"], "3-4-3")


class UpsertWunschkaderTests(unittest.TestCase):
    def test_writes_whole_dict_as_single_doc_named_current(self):
        client = MagicMock()
        data = {"targets": [{"name": "Krauß", "position": "Mittelfeld", "role": "Starter"}], "formation": "3-4-3"}

        firestore_db.upsert_wunschkader(client, data)

        client.collection.assert_any_call("wunschkader")
        client.collection.return_value.document.assert_called_once_with("current")
        client.collection.return_value.document.return_value.set.assert_called_once_with(data)
```

- [ ] **Schritt 3: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle bisherigen Tests weiterhin gruen, plus die 3 neuen (`GetWunschkaderTests` x2, `UpsertWunschkaderTests` x1).

- [ ] **Schritt 4: Commit (lokal, NICHT pushen)**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "Firestore-Backend fuer Wunschkader (get/upsert)"
```

---

### Task 2: Migration + `_load_wunschkader()` auf Firestore umstellen

**Files:**
- Modify: `src/dashboard_export.py` (Zeile 37 `WUNSCHKADER_PATH` entfernen, `_load_wunschkader()` neu schreiben, Docstring-Verweise anpassen)
- Delete: `data/wunschkader.json` (nach einmaliger manueller Migration)
- Modify: `index.html:582` (Fallback-Text erwaehnt noch die Datei)

**Interfaces:**
- Konsumiert: `firestore_db.get_wunschkader`/`upsert_wunschkader` aus Task 1.
- Produziert: `_load_wunschkader() -> dict | None` — unveraendertes Interface
  fuer alle bestehenden Aufrufer (`_build_wunschkader`, `_split_eigenes_team`,
  `_build_budget_plan`), nur die Quelle aendert sich intern.

- [ ] **Schritt 1: Einmalige Migration ausfuehren (KEIN neues Script-File, nur einmalig in der Shell)**

```bash
python3 -c "
import json
from src import firestore_db
data = json.loads(open('data/wunschkader.json', encoding='utf-8').read())
client = firestore_db.connect()
firestore_db.upsert_wunschkader(client, data)
print('Migriert:', list(data.keys()))
"
```
(braucht `GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json` in der Umgebung, wie bei jedem lokalen Firestore-Zugriff)

- [ ] **Schritt 2: Verifizieren, dass die Migration ankam**

```bash
python3 -c "
from src import firestore_db
client = firestore_db.connect()
print(firestore_db.get_wunschkader(client))
"
```
Erwartung: komplettes Dict mit allen 7 Top-Level-Keys (`updated_at`,
`formation`, `season_start`, `sell_list`, `markup_rules`, `login_bonus`,
`targets`) aus der aktuellen `data/wunschkader.json`.

- [ ] **Schritt 3: `_load_wunschkader()` umschreiben (`src/dashboard_export.py:348-354`)**

Von:
```python
def _load_wunschkader() -> dict | None:
    """Handgepflegte Zielspieler-Liste (siehe MDs/kaderplan.md fuer die
    Begruendungen), NICHT automatisch generiert - bei jeder Aenderung des
    Kaderplans auch diese Datei nachziehen."""
    if not WUNSCHKADER_PATH.exists():
        return None
    return json.loads(WUNSCHKADER_PATH.read_text(encoding="utf-8"))
```
Zu:
```python
def _load_wunschkader() -> dict | None:
    """Wunschkader lebt komplett in Firestore (wunschkader/current, siehe
    MDs/kaderplan.md fuer die Begruendungen der Eintraege) - der Browser
    kann targets direkt editieren (Alle-Spieler/Wunschkader-Feature).
    Ohne Firestore-Zugriff (kein FIRESTORE_ENABLED lokal) gibt es keinen
    Fallback mehr - Aufrufer behandeln None wie bisher (kein Wunschkader
    hinterlegt)."""
    if not os.environ.get("FIRESTORE_ENABLED"):
        return None
    try:
        return firestore_db.get_wunschkader(firestore_db.connect())
    except Exception as exc:
        print(f"Warnung: Wunschkader-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)
        return None
```

- [ ] **Schritt 4: `WUNSCHKADER_PATH`-Konstante entfernen (Zeile 37)**

```python
WUNSCHKADER_PATH = Path(__file__).resolve().parent.parent / "data" / "wunschkader.json"
```
komplett loeschen. Pruefen ob `Path`-Import (Zeile 29) noch woanders
gebraucht wird, bevor der Import entfernt wird (`grep -n "Path(" src/dashboard_export.py`).

- [ ] **Schritt 5: `data/wunschkader.json` loeschen**

```bash
git rm data/wunschkader.json
```

- [ ] **Schritt 6: `index.html:582` Fallback-Text anpassen**

Von:
```javascript
'<p class="section-hint">Kein Wunschkader hinterlegt (data/wunschkader.json fehlt oder ist leer).</p>';
```
Zu:
```javascript
'<p class="section-hint">Kein Wunschkader hinterlegt.</p>';
```

- [ ] **Schritt 7: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle gruen (kein bestehender Test mockt `WUNSCHKADER_PATH` direkt,
laut Recherche - falls doch, Mock auf `firestore_db.get_wunschkader` umstellen).

- [ ] **Schritt 8: Lokalen End-to-End-Testlauf machen**

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3 -m src.dashboard_export
```
Erwartung: laeuft durch, `wunschkader`/`wunschkader_watchlist`/`budget_plan`
im Ergebnis unveraendert befuellt (Daten kommen jetzt aus Firestore statt Datei).

- [ ] **Schritt 9: Commit (lokal, NICHT pushen)**

```bash
git add src/dashboard_export.py index.html data/wunschkader.json
git commit -m "Wunschkader komplett nach Firestore migrieren, lokale Datei entfernen"
```

---

### Task 3: `firestore.rules` — Wunschkader-Block (read+write)

**Files:** Modify: `firestore.rules`

- [ ] **Schritt 1: Neuen Block einfuegen (vor dem Catch-all `match /{document=**}`)**

```
match /wunschkader/{document=**} {
  allow read, write: if request.auth != null
                     && request.auth.uid == "lC85qOItQ1M6bRjzqnYcgBkLVDF2";
}
```

- [ ] **Schritt 2: Deployen (gleiches Muster wie Phase 2, `firebase-tools` bereits installiert)**

```bash
GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json firebase deploy --only firestore:rules --project kickbaseagent
```
Erwartung: `✔ Deploy complete!`

- [ ] **Schritt 3: Commit (lokal, NICHT pushen)**

```bash
git add firestore.rules
git commit -m "Firestore Rules: Browser darf wunschkader lesen+schreiben"
```

---

### Task 4: Backend fuer "Alle Spieler"-Tab (`_build_alle_spieler`)

**Files:**
- Modify: `src/dashboard_export.py` (neue Funktion, `export()`-Verdrahtung, `owned_by`/`own_squad_names` unconditional berechnen)
- Test: neue Datei `tests/test_dashboard_export.py` (existiert noch nicht — pruefen mit `ls tests/` ob doch, sonst neu anlegen)

**Interfaces:**
- Konsumiert: `player_valuation.fetch_all_players`, `player_valuation.resolve_ownership`,
  `src.kickbase_client.status_label`, `_valuation()` (bereits vorhanden, Zeile 50).
- Produziert: `_build_alle_spieler(all_players, owned_by, own_squad_names, calibration) -> list[dict]`,
  eingehaengt als `data["alle_spieler"]`.

- [ ] **Schritt 1: Import ergaenzen (Zeile 35)**

Von:
```python
from src.kickbase_client import KickbaseError, get_manager_squad, get_me, login
```
Zu:
```python
from src.kickbase_client import KickbaseError, get_manager_squad, get_me, login, status_label
```

- [ ] **Schritt 2: Neue Funktion (nach `_build_wunschkader`, vor `_build_budget_plan`, ca. Zeile 468)**

```python
def _build_alle_spieler(
    all_players: list[dict], owned_by: dict, own_squad_names: set, calibration: dict | None
) -> list[dict]:
    """Alle Liga-Spieler (~450) fuer den 'Alle Spieler'-Tab - reine
    Umformung von player_valuation.fetch_all_players(), das export() ohnehin
    schon fuer Wunschkader/Ligaanalyse laedt, keine neuen API-Calls."""
    rows = []
    for p in all_players:
        fairwert, signal = _valuation(p["market_value"], p["points_avg"], p["position"], calibration)
        if p["name"] in own_squad_names:
            owner = "Eigener Kader"
        else:
            owner = owned_by.get(p["player_id"], "Frei")
        rows.append(
            {
                "player_id": p["player_id"],
                "name": p["name"],
                "position": p["position"],
                "team_name": p["team_name"],
                "market_value": p["market_value"],
                "points_avg": p["points_avg"],
                "starting_rank": p["starting_rank"],
                "status_label": status_label(p["status_code"]),
                "owner": owner,
                "fairwert": fairwert,
                "signal": signal,
            }
        )
    return rows
```

- [ ] **Schritt 3: `owned_by`/`own_squad_names` in `export()` unconditional berechnen (aktuell nur innerhalb `if wunschkader_config:`)**

Aktuell (ca. Zeile 567-580):
```python
    wunschkader_config = _load_wunschkader()
    wunschkader_rows = []
    if wunschkader_config:
        own_name = own_budget_row["name"] if own_budget_row else None
        owned_by = (
            player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
            if own_name
            else {}
        )
        own_squad_names = {r["name"] for r in own_squad}
        market_by_name = {r["name"]: r for r in transfermarkt_rows}
        wunschkader_rows = _build_wunschkader(
            wunschkader_config, all_players, owned_by, own_squad_names, market_by_name, calibration, predictions
        )
```
Neu (owned_by/own_squad_names IMMER berechnen, Alle-Spieler-Tab braucht sie unabhaengig vom Wunschkader):
```python
    own_name = own_budget_row["name"] if own_budget_row else None
    owned_by = (
        player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
        if own_name
        else {}
    )
    own_squad_names = {r["name"] for r in own_squad}

    wunschkader_config = _load_wunschkader()
    wunschkader_rows = []
    if wunschkader_config:
        market_by_name = {r["name"]: r for r in transfermarkt_rows}
        wunschkader_rows = _build_wunschkader(
            wunschkader_config, all_players, owned_by, own_squad_names, market_by_name, calibration, predictions
        )
```

- [ ] **Schritt 4: In `data`-Dict einhaengen (ca. Zeile 596, neben `"wunschkader": wunschkader_rows`)**

```python
        "alle_spieler": _build_alle_spieler(all_players, owned_by, own_squad_names, calibration),
        "wunschkader_raw": wunschkader_config,
```

- [ ] **Schritt 5: Testdatei anlegen falls `tests/test_dashboard_export.py` noch nicht existiert**

```python
import unittest

from src.dashboard_export import _build_alle_spieler


class BuildAlleSpielerTests(unittest.TestCase):
    def test_marks_own_squad_players(self):
        players = [{"player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
                    "team_name": "Bremen", "market_value": 10_000_000,
                    "points_avg": 150, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names={"Krauß"}, calibration=None)

        self.assertEqual(rows[0]["owner"], "Eigener Kader")
        self.assertIsNone(rows[0]["status_label"])

    def test_marks_other_manager_ownership(self):
        players = [{"player_id": "p2", "name": "Zentner", "position": "Torwart",
                    "team_name": "Mainz", "market_value": 9_000_000,
                    "points_avg": 100, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={"p2": "Fleischmanns"}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Fleischmanns")

    def test_marks_free_agent(self):
        players = [{"player_id": "p3", "name": "Heuer Fernandes", "position": "Torwart",
                    "team_name": "Hamburg", "market_value": 11_000_000,
                    "points_avg": 90, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Frei")
```

- [ ] **Schritt 6: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle gruen, inkl. 3 neuer `BuildAlleSpielerTests`.

- [ ] **Schritt 7: Lokalen Testlauf machen (bestaetigt echte Feld-Shapes)**

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3 -m src.dashboard_export
```
Danach kurz per Python pruefen: `data["alle_spieler"]` hat ~450 Eintraege,
jeder mit `owner` in {"Eigener Kader", ein Managername, "Frei"}.

- [ ] **Schritt 8: Commit (lokal, NICHT pushen)**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "Alle-Spieler-Datensatz fuer neuen Dashboard-Tab bauen"
```

---

### Task 5: Frontend "Alle Spieler"-Tab (`index.html`)

**Files:** Modify: `index.html`

**Interfaces:**
- Konsumiert: `DATA.alle_spieler` (Shape aus Task 4).

- [ ] **Schritt 1: Tab-Button + Panel ergaenzen (Zeilen 184-195)**

```html
<nav class="tabs">
  <button class="tab-btn active" data-tab="transfermarkt">Transfermarkt</button>
  <button class="tab-btn" data-tab="spekulation">Spekulation</button>
  <button class="tab-btn" data-tab="team">Eigenes Team</button>
  <button class="tab-btn" data-tab="wunschkader">Wunschkader</button>
  <button class="tab-btn" data-tab="alle-spieler">Alle Spieler</button>
  <button class="tab-btn" data-tab="liga">Ligaanalyse</button>
</nav>
<main>
  <section id="tab-transfermarkt" class="tab-panel active"></section>
  <section id="tab-spekulation" class="tab-panel"></section>
  <section id="tab-team" class="tab-panel"></section>
  <section id="tab-wunschkader" class="tab-panel"></section>
  <section id="tab-alle-spieler" class="tab-panel"></section>
  <section id="tab-liga" class="tab-panel"></section>
</main>
```

- [ ] **Schritt 2: `renderAlleSpieler()` (nach `renderWunschkader()`, gleiches Filter-Muster wie `renderTransfermarkt()` Zeile 319-331)**

```javascript
function renderAlleSpieler() {
  const allRows = DATA.alle_spieler || [];
  const filters = { position: "all", verfuegbarkeit: "all", search: "" };
  const positions = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
  function getRows() {
    return allRows.filter((r) => {
      if (filters.position !== "all" && r.position !== filters.position) return false;
      if (filters.verfuegbarkeit === "frei" && r.owner !== "Frei") return false;
      if (filters.verfuegbarkeit === "eigen" && r.owner !== "Eigener Kader") return false;
      if (filters.verfuegbarkeit === "andere" && (r.owner === "Frei" || r.owner === "Eigener Kader")) return false;
      if (filters.search && !`${r.name} ${r.team_name ?? ""}`.toLowerCase().includes(filters.search)) return false;
      return true;
    });
  }
  const columns = [
    { key: "name", label: "Spieler" },
    { key: "position", label: "Pos." },
    { key: "team_name", label: "Verein" },
    { key: "market_value", label: "Marktwert", numeric: true },
    { key: "points_avg", label: "Schnitt", numeric: true },
    { key: "signal", label: "Signal", numeric: true },
    { key: "starting_rank", label: "Startelf-Rang", numeric: true },
    { key: "owner", label: "Status" },
    { key: "status_label", label: "Fitness" },
  ];
  const renderRow = (r) => `<tr>
    <td>${r.name}</td>
    <td>${r.position}</td>
    <td>${r.team_name ?? ""}</td>
    <td class="num">${fmtNum(r.market_value)}</td>
    <td class="num">${fmtNum(r.points_avg)}</td>
    <td class="num">${signalPill(r.signal)}</td>
    <td class="num">${r.starting_rank ?? '<span class="muted">n/v</span>'}</td>
    <td>${r.owner === "Frei" ? '<span class="pill pill-good">Frei</span>' : r.owner === "Eigener Kader" ? '<span class="pill pill-warn">Eigener Kader</span>' : `<span class="pill pill-crit">${r.owner}</span>`}</td>
    <td>${r.status_label ? `<span class="pill pill-warn">${r.status_label}</span>` : ""}</td>
  </tr>`;

  const filterBar = `<div class="filter-bar">
    <select id="alle-spieler-filter-position">
      <option value="all">Alle Positionen</option>
      ${positions.map((p) => `<option value="${p}">${p}</option>`).join("")}
    </select>
    <select id="alle-spieler-filter-verfuegbarkeit">
      <option value="all">Alle</option>
      <option value="frei">Nur freie</option>
      <option value="eigen">Nur eigene</option>
      <option value="andere">Nur bei anderen Managern</option>
    </select>
    <input type="search" id="alle-spieler-filter-search" placeholder="Suche Spieler/Verein...">
  </div>`;

  function redraw() {
    buildTable("tab-alle-spieler", columns, getRows, renderRow,
      `${allRows.length} Liga-Spieler insgesamt, ${getRows().length} nach Filter sichtbar.`, filterBar);
    wireFilters();
  }
  function wireFilters() {
    document.getElementById("alle-spieler-filter-position").value = filters.position;
    document.getElementById("alle-spieler-filter-position").addEventListener("change", (e) => {
      filters.position = e.target.value;
      redraw();
    });
    document.getElementById("alle-spieler-filter-verfuegbarkeit").value = filters.verfuegbarkeit;
    document.getElementById("alle-spieler-filter-verfuegbarkeit").addEventListener("change", (e) => {
      filters.verfuegbarkeit = e.target.value;
      redraw();
    });
    document.getElementById("alle-spieler-filter-search").value = filters.search;
    document.getElementById("alle-spieler-filter-search").addEventListener("input", (e) => {
      filters.search = e.target.value.trim().toLowerCase();
      redraw();
    });
  }
  redraw();
}
```

- [ ] **Schritt 3: In `renderAll()` einhaengen (Zeile 669-677)**

```javascript
function renderAll() {
  renderMeta();
  renderTransfermarkt();
  renderSpekulation();
  renderTeam();
  renderWunschkader();
  renderAlleSpieler();
  renderLiga();
  updateTabBadges();
}
```

- [ ] **Schritt 4: `updateTabBadges()` um `alle-spieler`-Zaehler ergaenzen (siehe bestehendes `counts`-Objekt)**

```javascript
    "alle-spieler": (DATA.alle_spieler || []).length,
```
(als weiterer Eintrag im `counts`-Objekt, gleiche Stelle wie `transfermarkt`/`team`/`wunschkader`)

- [ ] **Schritt 5: Browser-Test**

`cd /workspace/work && python3 -m http.server 8000` (User fuehrt den
eigentlichen Login-Test aus, siehe Phase-2-Verifikationsmuster) — neuer
Tab "Alle Spieler" zeigt ~450 Zeilen, Filter funktionieren.

- [ ] **Schritt 6: Commit (lokal, NICHT pushen)**

```bash
git add index.html
git commit -m "Neuen Alle-Spieler-Tab im Dashboard ergaenzen"
```

---

### Task 6: Frontend editierbarer Wunschkader (`index.html`)

**Files:** Modify: `index.html`

**Interfaces:**
- Konsumiert: `DATA.alle_spieler` (Task 4/5), `DATA.wunschkader_raw` (Task 2).
- Produziert: Save-Flow schreibt nach `wunschkader/current` per `setDoc`.

- [ ] **Schritt 1: `setDoc` importieren + exponieren (Zeile 199-217)**

Von:
```javascript
  import { getFirestore, doc, getDoc } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";
  ...
  window.__kickbaseAuth = {
    auth: getAuth(app), db: getFirestore(app),
    signInWithEmailAndPassword, onAuthStateChanged, doc, getDoc,
  };
```
Zu:
```javascript
  import { getFirestore, doc, getDoc, setDoc } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";
  ...
  window.__kickbaseAuth = {
    auth: getAuth(app), db: getFirestore(app),
    signInWithEmailAndPassword, onAuthStateChanged, doc, getDoc, setDoc,
  };
```

- [ ] **Schritt 2: Destructure-Zeile ergaenzen (Zeile 679)**

Von:
```javascript
const { auth, db, signInWithEmailAndPassword, onAuthStateChanged, doc, getDoc } = window.__kickbaseAuth;
```
Zu:
```javascript
const { auth, db, signInWithEmailAndPassword, onAuthStateChanged, doc, getDoc, setDoc } = window.__kickbaseAuth;
```

- [ ] **Schritt 3: Wechsel-Vorschlag-Funktion (neue Funktion, vor `renderWunschkader()`)**

```javascript
function suggestReplacements(target, count = 3) {
  const pool = (DATA.alle_spieler || []).filter((p) =>
    p.position === target.position && p.name !== target.name && p.owner === "Frei"
  );
  const mv = target.market_value || 0;
  const pts = target.points_avg || 0;
  const scored = pool.map((p) => {
    const mvDist = mv ? Math.abs((p.market_value || 0) - mv) / mv : 0;
    const ptsDist = pts ? Math.abs((p.points_avg || 0) - pts) / pts : 0;
    return { ...p, distance: mvDist + ptsDist };
  });
  scored.sort((a, b) => a.distance - b.distance);
  return scored.slice(0, count);
}
```

- [ ] **Schritt 4: `renderWunschkader()` komplett auf editierbar umbauen (ersetzt Zeilen 578-592)**

```javascript
let wunschkaderEditState = null; // lokale Arbeitskopie von DATA.wunschkader_raw.targets waehrend des Editierens

function renderWunschkader() {
  const rows = DATA.wunschkader;
  const container = document.getElementById("tab-wunschkader");
  if (!wunschkaderEditState) {
    wunschkaderEditState = DATA.wunschkader_raw ? [...DATA.wunschkader_raw.targets] : [];
  }
  if (!rows || !rows.length) {
    container.innerHTML = '<p class="section-hint">Kein Wunschkader hinterlegt.</p>';
    return;
  }
  const formation = DATA.wunschkader_formation ? ` (${DATA.wunschkader_formation})` : "";
  const updated = DATA.wunschkader_updated_at ? `, Stand ${DATA.wunschkader_updated_at}` : "";

  const editRows = wunschkaderEditState.map((t, idx) => {
    const computed = rows.find((r) => r.name === t.name) || {};
    return `<tr>
      <td>${t.position}</td>
      <td><input type="text" data-idx="${idx}" class="wk-name-input" value="${t.name}"></td>
      <td>${t.role}</td>
      <td>${wunschStatusPill(computed.status || "unbekannt")}</td>
      <td class="num">${fmtNum(computed.market_value)}</td>
      <td class="num">${fmtNum(computed.points_avg)}</td>
      <td><button type="button" class="wk-wechsel-btn" data-idx="${idx}">Wechsel</button></td>
      <td><button type="button" class="wk-remove-btn" data-idx="${idx}">Entfernen</button></td>
    </tr>
    <tr class="wk-suggestions" data-idx="${idx}" style="display:none;"><td colspan="8"></td></tr>`;
  }).join("");

  container.innerHTML = `
    <p class="section-hint">Ziel-Kader${formation}${updated} - siehe MDs/kaderplan.md fuer die volle Begruendung.
      Aenderungen wirken sich erst nach dem naechsten Pipeline-Lauf (alle 2h) auf Status/Fairwert/ML-Prognose aus.</p>
    <table>
      <thead><tr><th>Pos.</th><th>Spieler</th><th>Rolle</th><th>Status</th><th>Marktwert</th><th>Schnitt</th><th></th><th></th></tr></thead>
      <tbody id="wk-edit-body">${editRows}</tbody>
    </table>
    <div class="wk-add-form">
      <input type="text" id="wk-add-name" placeholder="Name">
      <select id="wk-add-position">
        <option value="Torwart">Torwart</option>
        <option value="Abwehr">Abwehr</option>
        <option value="Mittelfeld">Mittelfeld</option>
        <option value="Sturm">Sturm</option>
      </select>
      <select id="wk-add-role">
        <option value="Starter">Starter</option>
        <option value="Bank">Bank</option>
        <option value="Backup">Backup</option>
      </select>
      <button type="button" id="wk-add-btn">Hinzufuegen</button>
    </div>
    <div><button type="button" id="wk-save-btn">Speichern</button> <span id="wk-save-status" class="muted"></span></div>
    ${renderBudgetPlan(DATA.budget_plan)}`;

  container.querySelectorAll(".wk-name-input").forEach((el) => {
    el.addEventListener("change", (e) => {
      wunschkaderEditState[e.target.dataset.idx].name = e.target.value;
    });
  });
  container.querySelectorAll(".wk-remove-btn").forEach((el) => {
    el.addEventListener("click", (e) => {
      wunschkaderEditState.splice(e.target.dataset.idx, 1);
      renderWunschkader();
    });
  });
  container.querySelectorAll(".wk-wechsel-btn").forEach((el) => {
    el.addEventListener("click", (e) => {
      const idx = e.target.dataset.idx;
      const target = wunschkaderEditState[idx];
      const suggestionsRow = container.querySelector(`.wk-suggestions[data-idx="${idx}"]`);
      const suggestions = suggestReplacements(target);
      suggestionsRow.querySelector("td").innerHTML = suggestions.length
        ? "Vorschlaege: " + suggestions.map((s) =>
            `<button type="button" class="wk-pick-btn" data-idx="${idx}" data-name="${s.name}">${s.name} (${fmtNum(s.market_value)}, Ø${fmtNum(s.points_avg)})</button>`
          ).join(" ")
        : "Keine freien Alternativen gleicher Position gefunden.";
      suggestionsRow.style.display = "";
      suggestionsRow.querySelectorAll(".wk-pick-btn").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          wunschkaderEditState[ev.target.dataset.idx].name = ev.target.dataset.name;
          renderWunschkader();
        });
      });
    });
  });
  document.getElementById("wk-add-btn").addEventListener("click", () => {
    const name = document.getElementById("wk-add-name").value.trim();
    if (!name) return;
    wunschkaderEditState.push({
      name,
      position: document.getElementById("wk-add-position").value,
      role: document.getElementById("wk-add-role").value,
    });
    renderWunschkader();
  });
  document.getElementById("wk-save-btn").addEventListener("click", async () => {
    const statusEl = document.getElementById("wk-save-status");
    statusEl.textContent = "Speichere...";
    try {
      const updated = { ...DATA.wunschkader_raw, targets: wunschkaderEditState };
      await setDoc(doc(db, "wunschkader", "current"), updated);
      DATA.wunschkader_raw = updated;
      statusEl.textContent = "Gespeichert. Aenderungen erscheinen im naechsten Pipeline-Lauf (~2h).";
    } catch (err) {
      statusEl.textContent = "Fehler beim Speichern: " + err.message;
    }
  });
}
```

- [ ] **Schritt 5: Browser-Test (User fuehrt aus)**

Wunschkader-Tab oeffnen, einen Namen ersetzen, "Speichern" klicken —
Firestore-Console zeigt aktualisiertes `wunschkader/current`-Dokument mit
neuem `targets`-Eintrag, Rest des Dokuments (sell_list etc.) unveraendert.
"Wechsel" fuer einen Torwart-Eintrag testen — 3 freie Torwart-Vorschlaege
erscheinen, Klick uebernimmt den Namen.

- [ ] **Schritt 6: Commit (lokal, NICHT pushen)**

```bash
git add index.html
git commit -m "Wunschkader-Tab editierbar machen (Ersetzen/Entfernen/Hinzufuegen/Wechsel/Speichern)"
```

---

### Task 7: HANDOFF.md aktualisieren + End-to-End-Verifikation

**Files:** Modify: `HANDOFF.md`

- [ ] **Schritt 1:** Feature-Requests als erledigt markieren, neue
  Firestore-`wunschkader`-Collection dokumentieren, `data/wunschkader.json`-
  Erwaehnungen als "existiert nicht mehr, siehe Firestore" korrigieren.

- [ ] **Schritt 2: Volle Verifikation**

```bash
python3 -m unittest discover -s tests -v
```
Erwartung: alle Tests gruen (bisherige 33 + neue aus Task 1/4).

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3 -m src.dashboard_export
```
Erwartung: laeuft durch, `alle_spieler` (~450 Eintraege) und
`wunschkader_raw` im Ergebnis vorhanden.

- [ ] **Schritt 3: Commit (lokal, NICHT pushen)**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Alle-Spieler-Tab + editierbarer Wunschkader als erledigt markieren"
```

---

## Verifikation (Gesamt)

- `python3 -m unittest discover -s tests -v` — alle Tests gruen.
- `data/wunschkader.json` existiert nicht mehr im Repo.
- Firestore-Console zeigt `wunschkader/current`-Dokument mit allen 7 Feldern.
- Browser: neuer "Alle Spieler"-Tab zeigt ~450 Spieler, Filter funktionieren.
- Browser: Wunschkader-Tab editierbar, Speichern schreibt nach Firestore
  (verifiziert per Reload + Firestore-Console), Wechsel-Button schlaegt
  plausible freie Alternativen vor.
- `firestore.rules` deployed, `wunschkader`-Block read+write fuer die eine UID.
