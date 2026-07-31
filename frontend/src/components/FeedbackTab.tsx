import { useEffect, useState } from "react";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import { formatRelativeTime } from "../lib/derive";
import type { FeedbackItem } from "../types";

type LoadState = "loading" | "error" | "ready";

const TYPE_LABEL: Record<FeedbackItem["type"], string> = {
  bug: "🐛 Bug",
  feature: "💡 Idee",
};

export default function FeedbackTab({ now }: { now: number }) {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [type, setType] = useState<FeedbackItem["type"]>("bug");
  const [text, setText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    getDoc(doc(db, "feedback", "current"))
      .then((snap) => {
        const data = snap.exists() ? (snap.data() as { items?: FeedbackItem[] }) : {};
        setItems(data.items ?? []);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, []);

  async function persist(next: FeedbackItem[]) {
    setItems(next);
    setSaveError("");
    try {
      await setDoc(doc(db, "feedback", "current"), { items: next });
    } catch (err) {
      setSaveError("Fehler beim Speichern: " + (err as Error).message);
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
    persist([item, ...items]);
    setText("");
  }

  function startEdit(item: FeedbackItem) {
    setEditingId(item.id);
    setEditText(item.text);
  }

  function saveEdit() {
    if (!editingId) return;
    const trimmed = editText.trim();
    if (trimmed) {
      persist(items.map((i) => (i.id === editingId ? { ...i, text: trimmed } : i)));
    }
    setEditingId(null);
  }

  if (loadState === "loading") {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Lade Einträge…</p>;
  }
  if (loadState === "error") {
    return <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>;
  }

  const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
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
          maxLength={1000}
          placeholder={type === "bug" ? "Was ist kaputt?" : "Was wäre hilfreich?"}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={!text.trim()}
          className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Hinzufügen
        </button>
        {saveError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{saveError}</p>}
      </div>

      <div className="space-y-2">
        {open.length === 0 && done.length === 0 && (
          <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine Einträge.</p>
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
            maxLength={1000}
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
