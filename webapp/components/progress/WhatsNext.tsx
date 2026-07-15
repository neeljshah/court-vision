"use client";

// WhatsNext -- a compact strip of the AI's OWN next improvements, read from the
// same on-disk improvement backlog the System page uses (top-ranked candidates).
// This is the forward-looking face of honest progress: COMPLETENESS work the
// system has discovered for itself. It is MEASUREMENT-ONLY -- it discovers +
// ranks, it never fixes, ships, or flips a flag. Most items are REJECT-leaning
// (markets are efficient). NO $ field anywhere.

import { useEffect, useState } from "react";
import { Panel, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import {
  systemApi,
  isUnavailable,
  type FunnelArtifacts,
  type RichBacklogCandidate,
} from "@/components/system/systemApi";

const TOP = 6;

export function WhatsNext() {
  const [items, setItems] = useState<RichBacklogCandidate[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    systemApi.artifacts(ac.signal).then((d) => {
      if (isUnavailable(d)) {
        setErr((d as { reason?: string }).reason || "backlog unavailable");
      } else {
        const cands = (d as FunnelArtifacts).backlog?.candidates ?? [];
        const ranked = [...cands].sort(
          (a, b) => (b.priority ?? 0) - (a.priority ?? 0),
        );
        setItems(ranked.slice(0, TOP));
        setErr(null);
      }
    });
    return () => ac.abort();
  }, []);

  return (
    <Panel
      title="what's next (the AI's own discovered improvements)"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Badge tone="slate">measurement-only</Badge>
          <InfoTip
            text="The top-ranked items the system discovered for itself. It DISCOVERS + RANKS only -- it never fixes, ships, or flips a flag. Most close as a recorded REJECT (a success). No $ / edge."
            ariaLabel="what is this strip?"
          />
        </span>
      }
    >
      {err ? (
        <p className="text-sm text-muted-foreground">
          backlog unavailable ({err}) -- honest empty, never a fabricated plan.
        </p>
      ) : !items ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          no next items discovered -- honest empty.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {items.map((c) => (
            <li
              key={c.id}
              className="rounded-lg border border-slate-800 bg-bg-panel/40 p-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-[11px] font-semibold text-foreground">
                  {c.what || c.id}
                </span>
                {typeof c.priority === "number" ? (
                  <Badge tone="slate">p{c.priority}</Badge>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                {c.sport ? <Badge tone="slate">{c.sport}</Badge> : null}
                {c.category ? (
                  <span className="font-mono">{c.category}</span>
                ) : null}
              </div>
              {c.expected_outcome ? (
                <p className="mt-1 text-[10px] leading-relaxed text-faint">
                  expected: {c.expected_outcome}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
