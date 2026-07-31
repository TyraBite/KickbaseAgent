# Feedback-Tab (Bugs & Ideen) — Design

## Kontext

User will unterwegs (v.a. am Handy) Bugs/Ideen sofort in der App anlegen können, statt sie sich woanders zu merken. Zu Beginn der nächsten Claude-Code-Session werden die offenen Einträge ausgelesen, abgearbeitet (Ideen übernommen, Bugs sofort gefixt) und als erledigt markiert (nicht gelöscht — passt zum bestehenden Projekt-Stil, siehe `bid_premium_log`/`fitness_history_log`, die ebenfalls nie gelöscht werden).

**Ziel:** ein neuer Tab "Bugs & Ideen" mit einem schnellen Erfassungsformular (Typ + Text, speichert sofort) und einer Liste aller bisherigen Einträge (bearbeitbar, um später mehr Kontext zu ergänzen).

## Sicherheits-Einordnung (kein neuer Angriffsvektor)

`firestore.rules` sperrt aktuell jede client-schreibbare Collection (`dashboard_snapshot` lesend, `wunschkader` lesend+schreibend) auf die EINE bekannte, hart-codierte `request.auth.uid` — nicht nur "irgendein eingeloggter User". Die neue `feedback`-Collection bekommt exakt denselben Rule-Block. Da Firebase-Auth-Signup theoretisch von jedem mit dem (ohnehin öffentlichen) Client-API-Key umgangen werden könnte, schützt NICHT "eingeloggt sein", sondern die exakte UID-Prüfung — dieser Schutz existiert schon für `wunschkader`, wird hier nur wiederverwendet, kein neues Sicherheitsproblem.

## Architektur

Komplett Frontend-only. Anders als `wunschkader` (liest über den vom Python-Backend geschriebenen `dashboard_snapshot`, schreibt aber direkt in die eigene Collection — ein asymmetrischer Round-trip über die Pipeline) braucht Feedback **keine** Backend-/Cron-Anbindung: liest UND schreibt direkt gegen `feedback/current`. Kein neues Snapshot-Feld, kein neuer Python-Code, kein `export()`-Touch.

## Datenmodell

Ein Dokument `feedback/current` = `{ items: FeedbackItem[] }` (Array-in-einem-Dokument-Muster wie bei `wunschkader/current`s `targets`).

```ts
export interface FeedbackItem {
  id: string;            // crypto.randomUUID(), client-generiert
  type: "bug" | "feature";
  text: string;
  created_at: string;    // ISO-Timestamp, new Date().toISOString()
  status: "open" | "done";
}
```

Bei diesem Umfang (einzelner Hobby-User, wenige Einträge zwischen zwei Sessions) ist ein Array-in-einem-Dokument einer eigenen Collection-mit-vielen-Docs vorzuziehen — kein Query-Overhead, ein Read/Write pro Aktion, konsistent mit dem etablierten Wunschkader-Muster.

## Firestore Rules

`firestore.rules`, neuer Block analog zu `wunschkader` (gleiche UID, gleiche read+write-Freigabe):

```
match /feedback/{document=**} {
  allow read, write: if request.auth != null
                     && request.auth.uid == "lC85qOItQ1M6bRjzqnYcgBkLVDF2";
}
```

## Frontend

### `types.ts`

Neues Interface `FeedbackItem` (siehe Datenmodell oben) — **kein** neues Feld auf `DashboardSnapshot`, da komplett unabhängig von diesem Dokument gelesen/geschrieben wird.

### Neue Komponente `FeedbackTab.tsx`

- Liest `feedback/current` per `getDoc(doc(db, "feedback", "current"))` beim Mount (analog zu `App.tsx`s Top-Level-Fetch-Pattern, nicht `onSnapshot` — Single-User, kein Multi-Device-Live-Sync-Bedarf), hält `items: FeedbackItem[]` als lokalen State.
- **Formular oben:** Typ-Toggle (🐛 Bug / 💡 Idee) + `<textarea>` + "Hinzufügen"-Button. Klick baut ein neues `FeedbackItem` (`id: crypto.randomUUID()`, `created_at: new Date().toISOString()`, `status: "open"`), hängt es an den lokalen `items`-State an und schreibt SOFORT das komplette Array per `setDoc(doc(db, "feedback", "current"), { items: nextItems })` — kein "erst Speichern-Klick nötig", damit eine schnelle unterwegs erfasste Idee nicht durch einen vergessenen Klick verloren geht.
- **Liste darunter:** neueste zuerst (`created_at` absteigend sortiert), Zeitangabe über das schon vorhandene `formatRelativeTime()` (`lib/derive.ts`, aus dem Aktualisierungszeitpunkt-Feature). Offene Einträge (`status: "open"`) normal dargestellt, erledigte (`status: "done"`) ausgegraut, unten in der Liste oder eingeklappt.
- **Eintrag bearbeiten:** Klick auf einen Eintrag öffnet eine editierbare `<textarea>` (vorbefüllt mit dem bisherigen Text, zum Ergänzen von mehr Kontext) + ein "Speichern"-Button PRO Eintrag — mutiert den Text im lokalen Array, schreibt das komplette Array erneut (gleiches `setDoc`-Muster wie beim Anlegen).
- Kein separates "Als erledigt markieren" durch den User nötig für den beschriebenen Workflow (das macht die nächste Claude-Code-Session per Admin-SDK) — trotzdem kein Schaden, wenn später gewünscht, einfach denselben Mutate-und-setDoc-Mechanismus für ein Statusfeld zu nutzen (nicht Teil dieser Spec, YAGNI).

### `App.tsx`

- `TABS`-Array: neuer Eintrag `{ key: "feedback", label: "Bugs & Ideen" }`.
- `ACTIVE_TABS`: `"feedback"` hinzufügen.
- Neuer bedingter Render-Block (`activeTab === "feedback"`) analog zu den bestehenden Tab-Blöcken, rendert `<FeedbackTab />` — **kein** `data`/`data.players`-Bedarf, die Komponente ist komplett unabhängig vom Hauptsnapshot, funktioniert also auch dann, wenn `data` noch lädt (kein Warten auf `loadState === "ready"` nötig — abweichend von den anderen Tabs, die alle an `data` hängen).

## Nächste Session (Lese-/Abarbeitungs-Workflow, kein neues Tooling)

Direkter Firestore-Read über die schon etablierte Sandbox-Live-Zugriff-Route (`GOOGLE_APPLICATION_CREDENTIALS=.../firebase-service-account.json`, Admin SDK umgeht Rules): `client.collection("feedback").document("current").get()`, `items` mit `status == "open"` filtern, abarbeiten, danach per Admin-SDK-Write `status` auf `"done"` setzen (kein Löschen).

## Out of Scope (bewusst)

- Keine Backend-/Python-Anbindung, kein neues `dashboard_snapshot`-Feld.
- Kein Rate-Limiting/Abuse-Schutz über die bestehende UID-Sperre hinaus — bei diesem Bedrohungsmodell (eine bekannte, hart-codierte UID) nicht nötig.
- Kein "Als erledigt markieren"-Button für den User selbst (macht die nächste Session).
- Kein Live-Sync (`onSnapshot`) zwischen mehreren gleichzeitig offenen Tabs/Geräten.
