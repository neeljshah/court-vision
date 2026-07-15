"use client";

import { useAlerts } from "@/lib/store";
import { timeAgo } from "@/lib/utils";
import { Panel, PanelHead } from "@/components/ui/terminal";

// Severity configuration -- text label + ring color so cue is never color-only.
// danger/warning tokens only (color = meaning); LOW stays neutral/faint.
const SEVERITY_CONFIG: Record<
  string,
  { label: string; dotClass: string; ringClass: string }
> = {
  high: {
    label: "HIGH",
    dotClass: "bg-danger",
    ringClass: "ring-1 ring-danger/40",
  },
  medium: {
    label: "MED",
    dotClass: "bg-warning",
    ringClass: "ring-1 ring-warning/40",
  },
  low: {
    label: "LOW",
    dotClass: "bg-faint",
    ringClass: "",
  },
};

function getSeverityConfig(severity: string) {
  return SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.low;
}

export function AlertsFeed() {
  const alerts = useAlerts();
  return (
    <div aria-label="Alerts feed">
      <Panel>
        <PanelHead title="Alerts" />

        {/* Empty state -- honest framing: feed reached, no events yet (not an error) */}
        {!alerts.length && (
          <div
            role="status"
            aria-live="polite"
            className="flex flex-col items-center gap-1 px-5 py-6 text-center"
          >
            <p className="text-sm font-medium text-muted-foreground">No alerts yet</p>
            <p className="text-xs text-faint">
              The feed is connected -- alerts appear here when the system flags an event.
            </p>
          </div>
        )}

        {alerts.length > 0 && (
          <ul
            role="feed"
            aria-label="Recent alerts"
            aria-live="polite"
            className="max-h-64 divide-y divide-border overflow-y-auto"
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
                    <span className="mr-1.5 inline-block font-data text-[10px] font-bold uppercase tracking-wider text-faint">
                      [{sev.label}]
                    </span>
                    <span className="text-foreground">{a.msg}</span>
                    <p className="mt-0.5 font-data text-xs tabular text-faint">
                      {timeAgo(a.ts)} ago
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
