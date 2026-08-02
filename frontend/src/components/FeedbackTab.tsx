import { useEffect, useRef, useState } from "react";
import { arrayUnion, doc, getDoc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import { IconEmptyState } from "./icons";
import { formatRelativeTime } from "../lib/derive";
import type { FeedbackItem } from "../types";

type LoadState = "loading" | "error" | "ready";

const TYPE_LABEL: Record<FeedbackItem["type"], string> = {
  bug: "🐛 Bug",
  feature: "💡 Idee",
};

// Nach dieser Zeit ohne Antwort vom Server gilt ein Save als "haengt"
// (typischerweise offline) - Firestores Web-SDK loest das Promise dann
// weder auf noch ab, weil der Write lokal in die Offline-Queue wandert und
// erst bei wiederhergestellter Verbindung tatsaechlich committet.
const SLOW_SAVE_HINT_MS = 6000;

export default function FeedbackTab({ now }: { now: number }) {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveIsSlow, setSaveIsSlow] = useState(false);
  const [type, setType] = useState<FeedbackItem["type"]>("bug");
  const [text, setText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const slowSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getDoc(doc(db, "feedback", "current"))
      .then((snap) => {
        const data = snap.exists() ? (snap.data() as { items?: unknown }) : {};
        setItems(Array.isArray(data.items) ? (data.items as FeedbackItem[]) : []);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, []);

  useEffect(
    () => () => {
      if (slowSaveTimer.current) clearTimeout(slowSaveTimer.current);
    },
    []
  );

  async function withSaveIndicator(work: () => Promise<void>) {
    setSaveError("");
    setSaveIsSlow(false);
    setIsSaving(true);
    slowSaveTimer.current = setTimeout(() => setSaveIsSlow(true), SLOW_SAVE_HINT_MS);
    try {
      await work();
    } catch (err) {
      setSaveError("Fehler beim Speichern: " + (err as Error).message);
    } finally {
      if (slowSaveTimer.current) clearTimeout(slowSaveTimer.current);
      setIsSaving(false);
      setSaveIsSlow(false);
    }
  }

  function handleAdd() {
    const trimmed = text.trim();
    if (!trimmed) return;
    const item: FeedbackItem = {
      id: crypto.randomUUID(),
      type,
      text: trimmed,
      created_at: new Date().toISOString(),
      status: "open",
    };
    setItems((prev) => [item, ...prev]);
    setText("");
    // arrayUnion ist ein atomarer serverseitiger Append - braucht KEIN
    // vorheriges getDoc, kann also nie einen zwischenzeitlich von einer
    // anderen Session (z.B. der naechsten Claude-Code-Session per Admin-SDK)
    // geaenderten Stand ueberschreiben. setDoc+merge legt das Dokument beim
    // allerersten Eintrag ueberhaupt automatisch an (updateDoc wuerde das
    // nicht tun, das Dokument existiert dann noch nicht).
    withSaveIndicator(() =>
      setDoc(doc(db, "feedback", "current"), { items: arrayUnion(item) }, { merge: true })
    );
  }

  function startEdit(item: FeedbackItem) {
    setEditingId(item.id);
    setEditText(item.text);
  }

  function saveEdit() {
    if (!editingId) return;
    const id = editingId;
    const trimmed = editText.trim();
    setEditingId(null);
    if (!trimmed) return;
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, text: trimmed } : i)));
    // Bearbeiten ist (anders als Hinzufuegen) kein reiner Append - braucht
    // echtes Read-Modify-Write. Absichtlich frisch gelesen statt den
    // lokalen (evtl. veralteten) items-State zu schreiben, sonst wuerde ein
    // zwischenzeitlich von einer anderen Session gesetztes status:"done"
    // wieder verworfen (genau das war der Bug vor diesem Fix).
    withSaveIndicator(async () => {
      const ref = doc(db, "feedback", "current");
      const snap = await getDoc(ref);
      const remote = snap.exists() ? (snap.data() as { items?: unknown }) : {};
      const remoteItems = Array.isArray(remote.items) ? (remote.items as FeedbackItem[]) : [];
      const merged = remoteItems.map((i) => (i.id === id ? { ...i, text: trimmed } : i));
      await setDoc(ref, { items: merged }, { merge: true });
      setItems(merged);
    });
  }

  if (loadState === "loading") {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Lade Einträge…</p>;
  }
  if (loadState === "error") {
    return <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>;
  }

  const sorted = [...items].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  const open = sorted.filter((i) => i.status === "open");
  const done = sorted.filter((i) => i.status === "done");

  return (
    <div className="max-w-2xl space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setType("bug")}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              type === "bug"
                ? "border-brand-500 bg-brand-50 font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            🐛 Bug
          </button>
          <button
            type="button"
            onClick={() => setType("feature")}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              type === "feature"
                ? "border-brand-500 bg-brand-50 font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            💡 Idee
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder={type === "bug" ? "Was ist kaputt?" : "Was wäre hilfreich?"}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            onClick={handleAdd}
            disabled={!text.trim()}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Hinzufügen
          </button>
          {isSaving && (
            <span className="text-xs text-slate-400 dark:text-slate-500">
              {saveIsSlow ? "Dauert ungewöhnlich lange – evtl. offline?" : "Wird gespeichert…"}
            </span>
          )}
        </div>
        {saveError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{saveError}</p>}
      </div>

      <div className="space-y-2">
        {open.length === 0 && done.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-6 text-slate-400 dark:text-slate-500">
            <IconEmptyState className="h-12 w-12" />
            <p className="text-sm">Noch keine Einträge.</p>
          </div>
        )}
        {open.map((item) => (
          <FeedbackRow
            key={item.id}
            item={item}
            now={now}
            isEditing={editingId === item.id}
            editText={editText}
            onEditTextChange={setEditText}
            onStartEdit={() => startEdit(item)}
            onSaveEdit={saveEdit}
          />
        ))}
        {done.length > 0 && (
          <details className="pt-2">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Erledigt ({done.length})
            </summary>
            <div className="mt-2 space-y-2 opacity-60">
              {done.map((item) => (
                <FeedbackRow
                  key={item.id}
                  item={item}
                  now={now}
                  isEditing={editingId === item.id}
                  editText={editText}
                  onEditTextChange={setEditText}
                  onStartEdit={() => startEdit(item)}
                  onSaveEdit={saveEdit}
                />
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function FeedbackRow({
  item,
  now,
  isEditing,
  editText,
  onEditTextChange,
  onStartEdit,
  onSaveEdit,
}: {
  item: FeedbackItem;
  now: number;
  isEditing: boolean;
  editText: string;
  onEditTextChange: (value: string) => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>{TYPE_LABEL[item.type]}</span>
        <span title={item.created_at}>{formatRelativeTime(item.created_at, new Date(now))}</span>
      </div>
      {isEditing ? (
        <div className="mt-2">
          <textarea
            value={editText}
            onChange={(e) => onEditTextChange(e.target.value)}
            rows={3}
            maxLength={2000}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <button
            type="button"
            onClick={onSaveEdit}
            className="mt-2 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Speichern
          </button>
        </div>
      ) : (
        <p
          onClick={onStartEdit}
          className="mt-1 cursor-pointer whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100"
        >
          {item.text}
        </p>
      )}
    </div>
  );
}
