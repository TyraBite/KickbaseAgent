import { useMemo, useState, type ReactNode } from "react";

// Generische sortierbare-Tabelle-Anzeige (analog zum alten buildTable()/
// makeSortable() in index.html, hier als React-Komponente statt DOM-
// Manipulation). Spaltenklick-Sortierung (sortValue) ist die feingranulare
// Ergaenzung zu den bestehenden Sortier-Dropdowns pro Tab - Dropdown liefert
// die Ausgangsreihenfolge, ein Spaltenklick ueberschreibt sie clientseitig,
// bis eine andere Spalte geklickt wird.
export interface TableColumn<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  sortValue?: (row: T) => string | number | null;
}

type SortState = { key: string; dir: 1 | -1 } | null;

export function SortableTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
}: {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
}) {
  const [sort, setSort] = useState<SortState>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string" || typeof bv === "string") {
        return String(av).localeCompare(String(bv)) * sort.dir;
      }
      return (av - bv) * sort.dir;
    });
  }, [rows, sort, columns]);

  function handleHeaderClick(col: TableColumn<T>) {
    if (!col.sortValue) return;
    setSort((prev) => (prev?.key === col.key ? { key: col.key, dir: (prev.dir * -1) as 1 | -1 } : { key: col.key, dir: 1 }));
  }

  return (
    <div data-swipe-ignore className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[720px] text-left text-sm text-slate-700 dark:text-slate-200">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => handleHeaderClick(col)}
                className={`px-3 py-3 ${col.align === "right" ? "text-right" : ""} ${
                  col.sortValue ? "cursor-pointer select-none hover:text-slate-700 dark:hover:text-slate-200" : ""
                }`}
              >
                {col.label}
                {sort?.key === col.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={rowKey(row)}
              role={onRowClick ? "button" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={() => onRowClick?.(row)}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
              className={`border-b border-slate-100 last:border-0 dark:border-slate-800/60 ${
                onRowClick ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40" : ""
              }`}
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-3 py-3 ${col.align === "right" ? "text-right tabular-nums" : ""}`}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
