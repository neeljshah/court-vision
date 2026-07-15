"use client";

import { useCallback, useMemo, useState } from "react";
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import { useLiveData } from "@/lib/useLiveData";
import {
  systemApi,
  type FunnelArtifacts,
  type RichBacklogCandidate,
} from "./systemApi";

// BacklogPanel -- the IMPROVEMENT BACKLOG as a ranked "what the AI will get
// better at next" list, read straight from the on-disk
// .planning/product/meta/improvement_backlog.json via the page-local Next route.
// Each candidate shows category | sport | priority | expected-outcome |
// gate-action. MEASUREMENT-ONLY: it discovers + ranks; it NEVER fixes, ships, or
// flips a flag. Most candidates are REJECT-leaning (markets are efficient) -- a
// REJECT is a closed dead-end, never force-fed. NO $ field anywhere.

const DEFAULT_LIMIT = 12;

// Plain-language gloss per category so a reader understands the work-type.
const CATEGORY_TIP: Record<string, string> = {
  UNTESTED_DATA: "data on disk not yet run through the leak-free gate; expected REJECT-leaning",
  EXPOSE_COHERENT_MARKET: "extra markets already computed off one engine matrix -- pure coherent re-exposure, no edge",
  SURFACE_VALIDATED_PRIOR: "attach as scouting/provenance only -- NEVER promoted to a feature without a both-direction cross-corpus PASS",
  STALE_GREEN_RISK: "re-confirm a previously-green result is still green on fresh settled data; no edge",
  COHERENCE_GAP: "reconcile two engines so all markets stay internally consistent; same calibration",
  FRAGILITY: "robustness hardening, not an edge",
  LOC_VIOLATION: "pure refactor to <=300 LOC; no behavior change",
  ORPHAN_MODULE: "wire or retire an unreferenced module",
  MISSING_TEST: "add a per-file test; robustness, not edge",
  TIER3_ACQUISITION: "acquire harder data; REJECT-leaning, realistic survivor is calibrated scouting",
  PARITY_GAP: "close a platform-completeness cell; not a gate verdict",
};

function priorityTone(p?: number): "gold" | "green" | "slate" {
  if (typeof p !== "number") return "slate";
  if (p >= 85) return "gold";
  if (p >= 65) return "green";
  return "slate";
}

function Candidate({ c }: { c: RichBacklogCandidate }) {
  return (
    <li className="rounded-lg border border-slate-800 bg-bg-panel/40 p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-[11px] font-semibold text-foreground">
          {c.what || c.id}
        </span>
        {typeof c.priority === "number" ? (
          <Badge tone={priorityTone(c.priority)}>p{c.priority}</Badge>
        ) : null}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {c.sport ? <Badge tone="slate">{c.sport}</Badge> : null}
        {c.category ? (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
            {c.category}
            <InfoTip
              text={CATEGORY_TIP[c.category] || "discovered backlog item; measurement-only"}
              ariaLabel={`what is ${c.category}?`}
            />
          </span>
        ) : null}
      </div>
      {c.expected_outcome ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <span className="text-faint">expected: </span>
          {c.expected_outcome}
        </p>
      ) : null}
      {c.gate_action ? (
        <p className="mt-1 text-[10px] leading-relaxed text-faint">
          <span className="font-mono uppercase tracking-wide">gate action: </span>
          {c.gate_action}
        </p>
      ) : null}
    </li>
  );
}

export function BacklogPanel() {
  const [showAll, setShowAll] = useState(false);
  const [cat, setCat] = useState<string>("ALL");

  // Poll the funnel-artifacts backlog (was one-shot). useLiveData keeps the
  // last-good ranked list and backs off on failure; the backlog refreshes slowly.
  const fetcher = useCallback(
    (signal: AbortSignal) => systemApi.artifacts(signal),
    [],
  );
  const { data, error: err } = useLiveData<FunnelArtifacts>(fetcher, {
    intervalMs: 120_000,
    staleAfterSec: 30 * 60,
  });

  const backlog = data?.backlog ?? null;
  // Wrap in its own useMemo so the array identity is stable across renders
  // (a bare `?? []` makes a fresh [] every render and churns the ranked memo).
  const all = useMemo(() => backlog?.candidates ?? [], [backlog]);
  const categories = backlog?.categories ?? [];

  const ranked = useMemo(() => {
    const filtered = cat === "ALL" ? all : all.filter((c) => c.category === cat);
    return [...filtered].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
  }, [all, cat]);
  const shown = showAll ? ranked : ranked.slice(0, DEFAULT_LIMIT);

  return (
    <Panel
      title="improvement backlog (what the AI will get better at next)"
      right={
        backlog ? (
          <span className="inline-flex items-center gap-1.5">
            <Badge tone="slate">{backlog.count ?? all.length} ranked</Badge>
            <InfoTip text="Measurement-only: this list DISCOVERS + RANKS candidates. It never fixes, ships, or flips a feature flag. Most are REJECT-leaning because the markets are efficient." ariaLabel="what is the backlog?" />
          </span>
        ) : null
      }
    >
      {err ? (
        <Unavailable reason={err} />
      ) : !data ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : !backlog || all.length === 0 ? (
        <Unavailable reason="no backlog candidates discovered yet" />
      ) : (
        <>
          <p className="mb-3 text-[11px] leading-relaxed text-faint">
            {backlog.note ||
              "Measurement-only: discovers + ranks; never fixes / ships / flips a flag."}
          </p>
          {categories.length ? (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(["ALL", ...categories] as string[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setCat(k);
                    setShowAll(false);
                  }}
                  aria-pressed={cat === k}
                  className={
                    "rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide " +
                    "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel " +
                    (cat === k
                      ? "border-slate-500 bg-slate-700 text-slate-200"
                      : "border-slate-800 bg-slate-900 text-slate-500 hover:text-slate-300")
                  }
                >
                  {k}
                </button>
              ))}
            </div>
          ) : null}
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {shown.map((c) => (
              <Candidate key={c.id} c={c} />
            ))}
          </ul>
          {ranked.length > DEFAULT_LIMIT ? (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
              className="mt-3 rounded-sm font-mono text-[11px] text-muted-foreground underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel"
            >
              {showAll ? "show top 12" : `show all ${ranked.length}`}
            </button>
          ) : null}
        </>
      )}
    </Panel>
  );
}
