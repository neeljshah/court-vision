"use client";

import { useAlerts } from "@/lib/store";
import { timeAgo } from "@/lib/utils";

// Severity configuration -- text label + ring color so cue is never color-only.
const SEVERITY_CONFIG: Record<
  string,
  { label: string; dotClass: string; ringClass: string }
> = {
  high: {
    label: "HIGH",
    dotClass: "bg-red-500",
    ringClass: "ring-1 ring-red-500/40",
  },
  medium: {
    label: "MED",
    dotClass: "bg-amber-400",
    ringClass: "ring-1 ring-amber-400/40",
  },
  low: {
    label: "LOW",
    dotClass: "bg-slate-500",
    ringClass: "",
  },
};

function getSeverityConfig(severity: string) {
  return SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.low;
}

export function AlertsFeed() {
  const alerts = useAlerts();
  return (
    <section
      className="rounded-xl border border-slate-800 bg-bg-panel"
      aria-label="Alerts feed"
    >
      <header className="border-b border-slate-800 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Alerts
        </h2>
      </header>

      {/* Empty state -- honest framing: feed reached, no events yet (not an error) */}
      {!alerts.length && (
        <div
          role="status"
          aria-live="polite"
          className="px-5 py-6 flex flex-col items-center gap-1 text-center"
        >
          <p className="text-sm font-medium text-slate-400">No alerts yet</p>
          <p className="text-xs text-slate-600">
            The feed is connected -- alerts appear here when the system flags an event.
          </p>
        </div>
      )}

      {alerts.length > 0 && (
        <ul
          role="feed"
          aria-label="Recent alerts"
          aria-live="polite"
          className="max-h-64 overflow-y-auto divide-y divide-slate-800"
        >
          {alerts.map((a, i) => {
            const sev = getSeverityConfig(a.severity);
            return (
              <li
                key={i}
                className={`flex gap-3 px-5 py-2.5 text-sm ${sev.ringClass}`}
                aria-label={`${sev.label} alert: ${a.msg}`}
              >
                {/* Severity dot -- decorative only; text label carries the cue */}
                <span
                  aria-hidden="true"
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sev.dotClass}`}
                />
                <div className="min-w-0 flex-1">
                  {/* Severity text badge -- not color-only */}
                  <span className="inline-block mr-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    [{sev.label}]
                  </span>
                  <span className="text-slate-200">{a.msg}</span>
                  <p className="mt-0.5 text-xs text-slate-500 tabular-nums">
                    {timeAgo(a.ts)} ago
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
