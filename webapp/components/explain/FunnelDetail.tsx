"use client";

// FunnelDetail.tsx -- the in-depth, stage-by-stage funnel explainer.
//
// Renders DATA -> SIGNALS -> MODELS -> ENGINES -> ONE PREDICTION -> INTELLIGENCE
// with what each stage IS, the honest discipline carried on it, and an InfoTip
// row of the load-bearing terms for that stage so every word is decodable. The
// "ONE PREDICTION" stage embeds a CONCRETE live example (LiveExample) pulling a
// real soccer prediction off the engine. Consumes the static narrative in
// funnelStages.ts plus the depth primitives. No numbers, no $ field, no edge.

import { FUNNEL_STAGE_DETAIL } from "./funnelStages";
import { InfoTip } from "@/components/depth";
import { LiveExample } from "./LiveExample";

// The stage key whose card embeds the live, concrete example.
const EXAMPLE_STAGE_KEY = "prediction";

export function FunnelDetail() {
  return (
    <section aria-label="the full funnel" className="flex flex-col gap-3">
      <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
        the full funnel -- data to intelligence
      </h2>
      <ol className="flex flex-col gap-3">
        {FUNNEL_STAGE_DETAIL.map((s, i) => (
          <li
            key={s.key}
            className="relative rounded-lg border border-border bg-surface-1/60 p-4 pl-16"
          >
            <span className="absolute left-4 top-4 font-mono text-lg font-semibold text-muted-foreground">
              {`0${i + 1}`}
            </span>
            {i < FUNNEL_STAGE_DETAIL.length - 1 && (
              <span
                aria-hidden
                className="absolute left-[26px] top-12 h-[calc(100%-1rem)] w-px bg-border"
              />
            )}
            <div className="text-sm font-semibold tracking-tight text-foreground">
              {s.label}
            </div>
            <p className="mt-0.5 text-xs italic text-muted-foreground">{s.essence}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>
            {s.tips && s.tips.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
                  terms:
                </span>
                {s.tips.map((t) => (
                  <InfoTip key={t} term={t} />
                ))}
              </div>
            )}
            <p className="mt-2 rounded border border-border/60 bg-background/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
              <span className="font-mono uppercase tracking-wider text-foreground/80">
                discipline:{" "}
              </span>
              {s.discipline}
            </p>
            {s.key === EXAMPLE_STAGE_KEY && (
              <div className="mt-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  a concrete live example
                </p>
                <LiveExample />
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
