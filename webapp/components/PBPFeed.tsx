"use client";

import { usePBP } from "@/lib/store";
import type { PBPEvent } from "@/lib/types";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

const TOPIC_COLOUR: Record<string, string> = {
  "pbp.made_shot": "text-up",
  "pbp.foul": "text-down",
  "pbp.turnover": "text-stale",
  "pbp.period_end": "text-s-market",
  "pbp.sub": "text-muted-foreground",
  "pbp.timeout": "text-s-market",
};

export function PBPFeed() {
  const pbp = usePBP();
  return (
    <Panel>
      <PanelHead title="Play-by-play" />
      <ul className="max-h-96 divide-y divide-border overflow-y-auto">
        {!pbp.length && (
          <li className="px-3 py-4 text-sm text-muted-foreground">
            Waiting for first PBP event...
          </li>
        )}
        {pbp.map((ev, i) => (
          <Row key={`${ev.action_number || i}-${ev.topic}`} ev={ev} />
        ))}
      </ul>
    </Panel>
  );
}

function Row({ ev }: { ev: PBPEvent }) {
  const tag = ev.topic.replace("pbp.", "");
  const colour = TOPIC_COLOUR[ev.topic] || "text-muted-foreground";
  const time = ev.ts
    ? new Date(ev.ts * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "";
  return (
    <li className="flex gap-3 px-3 py-1.5 text-sm hover:bg-surface-2">
      <Num className="w-20 shrink-0 text-xs text-faint">{time}</Num>
      <span className={`w-20 shrink-0 font-data text-xs uppercase ${colour}`}>
        {tag}
      </span>
      <span className="min-w-0 flex-1 truncate text-foreground">
        {ev.player_name ? <strong>{ev.player_name}</strong> : null}
        {ev.player_name ? " - " : ""}
        {ev.description}
      </span>
    </li>
  );
}
