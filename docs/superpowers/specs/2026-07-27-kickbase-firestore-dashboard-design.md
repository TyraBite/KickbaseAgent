# KickbaseAgent: Firestore-Migration, Firebase-Auth-Login, Public-Hosting

## Warum

Das Dashboard (`docs/dashboard.html`, `src/dashboard_export.py`) ist bisher
eine 1x/Tag per GitHub-Actions-Cron generierte, self-contained HTML-Datei
mit allen Daten fest als JSON eingebacken - lokal committed, nirgends live
gehostet. Der bisherige taegliche Discord-Report-Job (`src/main.py`,
`.github/workflows/daily.yml`) wird durch das Dashboard komplett ersetzt.

Der User will das Dashboard jetzt:
- **live gehostet** sehen (nicht nur eine Datei im Repo),
- **immer aktuell** halten (alle 2 Stunden statt 1x/Tag - passt zum
  Kickbase-eigenen Rhythmus, mit dem alle 2h ein neuer Systemspieler auf
  den Markt kommt),
- **zugriffsgeschuetzt**, obwohl es oeffentlich erreichbar sein wird (nur
  der User selbst soll die Daten sehen koennen).

## Recherche-Ergebnis: warum nicht "einfach" GitHub Pages privat

GitHub Pages mit echtem Zugriffsschutz (Site nur fuer Personen mit
Repo-Lesezugriff sichtbar) ist laut aktueller GitHub-Dokumentation
(docs.github.com, live abgerufen 27.07.2026) nur verfuegbar, wenn:
- der Repo einer **Organisation** gehoert (nicht einem persoenlichen
  Account), UND
- diese Organisation **GitHub Enterprise Cloud** gebucht hat.

Fuer einen privaten Personal-Account (auch mit GitHub Pro) ist das nicht
erreichbar. Das KickbaseAgent-Repo gehoert `TyraBite` persoenlich, nicht
einer Organisation - diese Option scheidet damit aus, ohne das Repo in
eine (kostenpflichtige) Enterprise-Organisation umzuziehen.

## Entscheidung

Nach mehreren Rueckfragen hat sich der User fuer folgenden Ansatz
entschieden:

1. **Repo wird public.** Risiko wird als gering eingeschaetzt ("glaube
   nicht, dass sich jemand aus meiner Liga dafuer interessiert"). Wichtig
   ist NUR, dass keine echten Geheimnisse im Git landen (Kickbase-Login,
   Firebase-Service-Account-Key - beides bereits/wird per `.gitignore`
   ausgeschlossen, analog zu `.env` heute).
2. **Firebase Authentication** statt eines eigenen Kickbase-Login-Gates.
   Ein Kickbase-Login-Gate haette bedeutet, fremde Kickbase-Passwoerter
   ueber eine inoffizielle, selbstgebaute API-Bruecke entgegenzunehmen -
   abgelehnt. Firebase Auth ist der bereits im Schwester-Projekt
   f1-tipping-game bewaehrte, kostenlose Standardweg.
3. **Firestore als primaerer neuer Datenspeicher.** Bewusste Entscheidung
   FUER Firestore (NoSQL) statt einer SQL-Alternative (Cloud SQL: keine
   echte Dauer-Gratis-Stufe, widerspraeche dem 0€-Hobbyprojekt-Anspruch;
   Turso/LibSQL: kein natives "Firebase Auth prueft direkt beim Lesen",
   bräuchte zusaetzlich eine selbstgebaute Backend-Funktion). Der
   bestehende SQL-Gebrauch in `src/db.py` ist ohnehin nicht relational
   komplex (keine JOINs, nur `SELECT * WHERE fetched_at = ?` pro Tabelle) -
   passt gut zu einem Dokumenten-Modell.
4. **Neues, separates Firebase-Projekt** ("KickbaseAgent", vom User
   bereits angelegt) statt Wiederverwendung des f1-tipping-game-Projekts -
   saubere Trennung der beiden Hobby-Projekte.
5. **SQLite bleibt bestehen.** Firestore ist eine ZUSAETZLICHE
   Persistenz-Schicht, kein Ersatz - nichts an der bestehenden
   Fetch-/ML-/Budget-Pipeline wird geloescht oder umgebaut.
6. **Update-Takt: alle 2 Stunden** statt 1x/Tag.

### Kernerkenntnis, die die Architektur bestimmt

Ein Firebase-Auth-Login schuetzt nur dann wirklich etwas, wenn die
ausgelieferte Seite die Daten NICHT mehr fertig eingebacken mitbringt.
Solange `docs/dashboard.html` ein einziger JSON-Blob ist, sieht JEDER mit
dem Link alle Daten, Login hin oder her (ein Login-Formular vor einer
Datei, die trotzdem komplett im Seitenquelltext steht, waere reine
Kosmetik). Echter Schutz heisst: die Seite wird zu einer duennen Shell,
die sich NACH einem erfolgreichen Firebase-Login client-seitig gegen
Firestore verbindet und live liest - Firestore Security Rules pruefen
dabei serverseitig, ob die anfragende UID die eine bekannte, autorisierte
ist. Das ist der Grund, warum dieses Projekt in Phasen aufgeteilt ist:
Phase 1 (Daten nach Firestore schreiben) muss VOR Phase 2 (Login + Live-
Lesen) stehen.

## Die 5 Phasen

Jede Phase bekommt ihren eigenen Plan->Umsetzungs-Zyklus, sobald die
vorherige steht. Nur Phase 1 ist hier im Detail spezifiziert.

### Phase 1 - Firestore-Datenmodell + Schreib-Pfad (JETZT)

Ziel: die bestehende Python-Pipeline schreibt zusaetzlich (nicht anstatt)
nach Firestore. Kein Client liest zu diesem Zeitpunkt von dort.

**Firebase-Setup** (manuell durch den User, keine CLI in dieser Sandbox
verfuegbar):
1. Firestore aktivieren (Native Mode) im bereits angelegten Projekt
   "KickbaseAgent".
2. Service-Account mit Firestore-Schreibzugriff ("Cloud Datastore User")
   anlegen, JSON-Key herunterladen.
3. Key lokal ablegen unter `firebase-service-account.json` (Repo-Root,
   neuer `.gitignore`-Eintrag, analog `.env`), Zugriff ueber die
   Standard-Google-Cloud-Env-Variable `GOOGLE_APPLICATION_CREDENTIALS` -
   `google-cloud-firestore` liest das automatisch, keine eigene
   Credential-Lade-Logik.
4. GitHub-Actions-Secret mit dem gleichen JSON-Inhalt erst relevant, sobald
   Phase 3 (Deploy) ansteht.

**Getestet wird in Phase 1 direkt gegen das echte Firebase-Projekt** (User-
Wunsch, kein Emulator noetig) - unschaedlich, da Phase 1 nur schreibt.

**Datenmodell** - 1:1-Port der bestehenden SQLite-Tabellen, keine
Neuerfindung. Neues Modul `src/firestore_db.py`, spiegelt `src/db.py`s
Funktionsformen:
- `connect()` -> Firestore-Client statt sqlite3-Connection.
- Collections analog zu den bestehenden Tabellen (`own_squad`,
  `market_listings`, `league_ranking`, `manager_budgets`,
  `season_context`), Dokument-Id `{fetched_at}_{player_id}` bzw.
  `{fetched_at}_{user_id}` (bei `season_context` reicht `fetched_at`).
  Jede `replace_*`-Funktion aus `db.py` bekommt ein Firestore-Pendant mit
  identischer Signatur (nimmt dieselben Row-Dicts entgegen), Batched
  Writes (Firestore-`WriteBatch`, max. 500/Batch).
- Neue Collection `ml_prediction_log` (Dokument-Id `{date}_{player_id}`) -
  Pendant zu `data/ml_prediction_log.jsonl`. Die lokale Datei bleibt
  zusaetzlich bestehen (kein Cutover).

**Aufrufstellen** (minimal-invasiv, hinter Feature-Flag
`FIRESTORE_ENABLED`, damit lokale Laeufe ohne Firebase-Credentials
unveraendert funktionieren):
- `src/fetcher.py`s `run()`: nach den bestehenden `db.replace_*`-Aufrufen
  dieselben Row-Listen zusaetzlich an `firestore_db.replace_*` uebergeben.
- `src/market_predictor.py`s `_save_prediction_log()`/
  `_append_todays_predictions()`: gleiches Muster.
- Fehlerresilienz wie ueberall im Projekt: ein fehlgeschlagener
  Firestore-Write darf den Rest der Pipeline nicht crashen (try/except +
  stderr-Warnung, analog `_apply_market_value_history`).

**Security Rules in Phase 1**: bewusst deny-all fuer Client-Reads (nur der
Admin-SDK-Schreibzugriff aus der Pipeline funktioniert). Echte Lese-Rules
kommen erst mit Phase 2.

**Verifikation**:
1. Lauf mit `FIRESTORE_ENABLED=1` + `GOOGLE_APPLICATION_CREDENTIALS` gegen
   das echte Projekt, Collections/Dokumente in der Firebase-Console
   pruefen.
2. Lauf ohne das Flag: unveraendertes Verhalten, keine Firebase-
   Abhaengigkeit noetig, bestehende Tests bleiben gruen.
3. Neuer Unit-Test fuer die reine Row-Dict -> Firestore-Dokument-Formung
   mit gemocktem Client (kein echter Netzwerkzugriff im Test).
4. `requirements.txt` um `google-cloud-firestore` ergaenzen.

### Phase 2 - Firebase Auth + Security Rules + Live-Dashboard

`docs/dashboard.html` wird von "ein JSON-Blob" zu einer duennen Shell:
laedt Firebase-Auth-SDK, zeigt einen Login (vermutlich Google-Sign-In,
beschraenkt auf den einen bekannten Account - Details bei Planung dieser
Phase), verbindet sich nach erfolgreichem Login client-seitig gegen
Firestore und liest live. Security Rules lassen nur die eine bekannte UID
lesen (deny-all fuer alle anderen). Die Render-Funktionen (`buildTable`,
`renderTransfermarkt()` usw.) aus dem heutigen Dashboard bleiben inhaltlich
wiederverwendbar - nur die Datenquelle wechselt von "inline JSON" zu
"Firestore-Query-Ergebnis".

### Phase 3 - Hosting/Deploy

GitHub Pages auf dem jetzt oeffentlichen Repo, Cron-Takt auf alle 2 Stunden
umstellen, `daily.yml` (alter Discord-Job) entfernen/abloesen. Firebase-
Service-Account-Secret in GitHub Actions hinterlegen.

### Phase 4 - ML-Verbesserung nutzt Historie

Die jetzt in Firestore abfragbare `ml_prediction_log`-Historie (statt nur
lokaler JSONL mit 90-Tage-Pruning) ermoeglicht: Genauigkeits-Trend-Anzeige
im Dashboard, perspektivisch eine datengetriebene Modell-/Hyperparameter-
Auswahl statt der heutigen taeglich-frischen RandomForest-vs-
HistGradientBoosting-Wahl auf nur einem synthetischen Split.

### Phase 5 - Mobile Version + UI/UX-Ueberarbeitung

Dedizierter Review-Schritt: ein Durchlauf, der den User aktiv zu aktueller
Nutzung und Painpoints befragt (nicht nur aus Annahmen heraus gestaltet),
danach mobile Ansicht + darauf aufbauende UI/UX-Verbesserungen.

## Firebase-Web-Config (fuer Phase 2, jetzt schon gesichert)

Firebase-Projekt "KickbaseAgent" hat eine Web-App registriert
("KickbaseAgent Dashboard", ohne Firebase Hosting). Config-Snippet:

```js
const firebaseConfig = {
  apiKey: "AIzaSyDaKr1cKLxqqA8EGauwSaNNOpsPQedHRQs",
  authDomain: "kickbaseagent.firebaseapp.com",
  projectId: "kickbaseagent",
  storageBucket: "kickbaseagent.firebasestorage.app",
  messagingSenderId: "622019870310",
  appId: "1:622019870310:web:45410188371a0327a1b7a7"
};
```

`apiKey` ist HIER kein Geheimnis (live gegen die offizielle Firebase-Doku
verifiziert, 27.07.2026: "API keys restricted to Firebase services do not
need to be treated as secrets, and it's safe to include them in your code
or configuration files" - Autorisierung laeuft ausschliesslich ueber
Firebase Security Rules/App Check, nicht ueber Geheimhaltung dieses
Strings). Bedenkenlos im Repo/Client-Code verwendbar, sobald Phase 2 die
Shell-Seite baut.

## Nicht Teil dieses Plans

- Kein Cutover von SQLite zu Firestore (Parallelbetrieb bleibt bestehen,
  auf unbestimmte Zeit - kein festes Ablaufdatum vereinbart).
- Keine Aenderung an der bestehenden ML-Trainings-/Budget-Schaetzungs-
  Logik in Phase 1 - reine Zusatz-Persistenz.
- Kein Kickbase-eigener Login (bewusst verworfen, siehe oben).
