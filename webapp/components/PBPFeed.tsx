"use client";

import { usePBP } from "@/lib/store";
import type { PBPEvent } from "@/lib/types";

const TOPIC_COLOUR: Record<string, string> = {
  "pbp.made_shot": "text-tier-a",
  "pbp.foul": "text-red-400",
  "pbp.turnover": "text-amber-400",
  "pbp.period_end": "text-sky-400",
  "pbp.sub": "text-slate-300",
  "pbp.timeout": "text-blue-300",
};

export function PBPFeed() {
  const pbp = usePBP();
  return (
    <section className="rounded-xl border border-slate-800 bg-bg-panel">
      <header className="border-b border-slate-800 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Play-by-play
        </h2>
      </header>
      <ul className="max-h-96 overflow-y-auto divide-y divide-slate-800">
        {!pbp.length && (
          <li className="px-5 py-4 text-sm text-slate-500">
            Waiting for first PBP event…
          </li>
        )}
        {pbp.map((ev, i) => (
          <Row key={`${ev.action_number || i}-${ev.topic}`} ev={ev} />
        ))}
      </ul>
    </section>
  );
}

function Row({ ev }: { ev: PBPEvent }) {
  const tag = ev.topic.replace("pbp.", "");
  const colour = TOPIC_COLOUR[ev.topic] || "text-slate-300";
  const time = ev.ts
    ? new Date(ev.ts * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "";
  return (
    <li className="flex gap-3 px-5 py-2 text-sm">
      <span className="w-20 shrink-0 text-xs font-mono text-slate-500 tabular">
        {time}
      </span>
      <span className={`w-20 shrink-0 text-xs font-mono uppercase ${colour}`}>
        {tag}
      </span>
      <span className="min-w-0 flex-1 truncate text-slate-200">
        {ev.player_name ? <strong>{ev.player_name}</strong> : null}
        {ev.player_name ? " · " : ""}
        {ev.description}
      </span>
    </li>
  );
}
