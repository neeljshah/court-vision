"use client";

import { useLastEventTs, useReady } from "@/lib/store";
import { timeAgo } from "@/lib/utils";
import { Dot } from "@/components/ui/terminal";

export function StatusBar() {
  const ready = useReady();
  const last = useLastEventTs();
  return (
    <div className="flex items-center justify-between border border-border bg-card px-4 py-2 text-xs">
      <span className="flex items-center gap-2">
        <Dot state={ready ? "ok" : "bad"} />
        {ready ? "WS connected" : "reconnecting..."}
      </span>
      <span className="font-data tabular text-muted-foreground">
        {last ? `last event ${timeAgo(last)} ago` : "no events yet"}
      </span>
    </div>
  );
}
