import { useState } from "react";
import type { PlayerRecord } from "../types";
import { normalizeSearchText } from "../lib/derive";
import { fmtNum } from "../format";

const MAX_RESULTS = 20;

export default function PlayerNamePicker({
  players,
  excludePlayerId,
  onSelect,
}: {
  players: Record<string, PlayerRecord>;
  excludePlayerId?: string;
  onSelect: (playerId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const q = normalizeSearchText(query.trim());
  const results = q
    ? Object.values(players)
        .filter((p) => p.player_id !== excludePlayerId && normalizeSearchText(p.name).includes(q))
        .slice(0, MAX_RESULTS)
    : [];

  return (
    <div>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Spieler suchen…"
        className="mb-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      {q && (
        <div className="flex flex-wrap gap-2">
          {results.length ? (
            results.map((p) => (
              <button
                key={p.player_id}
                type="button"
                onClick={() => onSelect(p.player_id)}
                className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {p.name} ({fmtNum(p.market_value)})
              </button>
            ))
          ) : (
            <span className="text-xs text-slate-400 dark:text-slate-500">Keine Treffer.</span>
          )}
        </div>
      )}
    </div>
  );
}
