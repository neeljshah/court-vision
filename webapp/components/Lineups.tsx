"use client";

import { useSnapshots } from "@/lib/store";

export function Lineups() {
  const snaps = useSnapshots();
  const gid = Object.keys(snaps)[0];
  const snap = gid ? snaps[gid] : undefined;
  const players = (snap?.players || []).filter((p) => (p.min ?? 0) > 0);
  players.sort((a, b) => (b.pts ?? 0) - (a.pts ?? 0));

  return (
    <section className="rounded-xl border border-slate-800 bg-bg-panel">
      <header className="border-b border-slate-800 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          On court
        </h2>
      </header>
      <ul className="max-h-96 overflow-y-auto divide-y divide-slate-800">
        {!players.length && (
          <li className="px-5 py-4 text-sm text-slate-500">No lineup yet…</li>
        )}
        {players.slice(0, 10).map((p) => (
          <li
            key={`${p.player_id}-${p.name}`}
            className="flex items-center gap-3 px-5 py-2 text-sm"
          >
            <div className="min-w-0 flex-1 truncate">
              <span className="text-slate-100">{p.name}</span>{" "}
              <span className="text-xs text-slate-500">({p.team})</span>
            </div>
            <span className="w-10 text-right tabular text-slate-400">
              {Math.round(p.min ?? 0)}m
            </span>
            <span className="w-10 text-right tabular text-slate-200">
              {p.pts ?? 0}
            </span>
            <span
              className={`w-8 text-right tabular ${
                (p.pf ?? 0) >= 4
                  ? "text-red-400"
                  : (p.pf ?? 0) >= 3
                  ? "text-amber-300"
                  : "text-slate-400"
              }`}
            >
              {p.pf ?? 0}f
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
