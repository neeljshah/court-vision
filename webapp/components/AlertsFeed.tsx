"use client";

import { useAlerts } from "@/lib/store";
import { timeAgo } from "@/lib/utils";

export function AlertsFeed() {
  const alerts = useAlerts();
  return (
    <section className="rounded-xl border border-slate-800 bg-bg-panel">
      <header className="border-b border-slate-800 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Alerts
        </h2>
      </header>
      <ul className="max-h-64 overflow-y-auto divide-y divide-slate-800">
        {!alerts.length && (
          <li className="px-5 py-4 text-sm text-slate-500">No alerts yet…</li>
        )}
        {alerts.map((a, i) => (
          <li key={i} className="flex gap-3 px-5 py-2 text-sm">
            <span
              className={`mt-2 h-2 w-2 shrink-0 rounded-full ${
                a.severity === "high"
                  ? "bg-red-500"
                  : a.severity === "medium"
                  ? "bg-amber-400"
                  : "bg-slate-500"
              }`}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-slate-200">{a.msg}</p>
              <p className="text-xs text-slate-500 tabular">{timeAgo(a.ts)} ago</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
