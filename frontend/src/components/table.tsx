import type { ReactNode } from "react";

// Generische sortierbare-Tabelle-Anzeige (Sortierung selbst bleibt wie bei
// SpekulationTab ueber ein externes Sortier-Dropdown, kein Klick-auf-Spalte -
// gleiches Muster wie schon etabliert, kein neues UI-Konzept). Ersetzt den
// Bedarf, fuer jeden neu migrierten Tab eine eigene <table> von Hand zu
// bauen (analog zum alten buildTable()/makeSortable() in index.html, hier
// als React-Komponente statt DOM-Manipulation).
export interface TableColumn<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
}

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
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400">
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={`px-3 py-2 ${col.align === "right" ? "text-right" : ""}`}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
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
                <td key={col.key} className={`px-3 py-2 ${col.align === "right" ? "text-right tabular-nums" : ""}`}>
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
