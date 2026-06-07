"use client";

import { useLastEventTs, useReady } from "@/lib/store";
import { timeAgo } from "@/lib/utils";

export function StatusBar() {
  const ready = useReady();
  const last = useLastEventTs();
  return (
    <div className="flex items-center justify-between rounded-md border border-slate-800 bg-bg-subtle px-4 py-2 text-xs">
      <span className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            ready ? "bg-tier-a animate-pulse" : "bg-red-500"
          }`}
        />
        {ready ? "WS connected" : "reconnecting…"}
      </span>
      <span className="text-slate-500 tabular">
        {last ? `last event ${timeAgo(last)} ago` : "no events yet"}
      </span>
    </div>
  );
}
