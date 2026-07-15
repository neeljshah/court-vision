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
import { Panel, PanelHead } from "@/components/ui/terminal";

// The stage key whose card embeds the live, concrete example.
const EXAMPLE_STAGE_KEY = "prediction";

export function FunnelDetail() {
  return (
    <section aria-label="the full funnel" className="flex flex-col gap-3">
      <h2 className="microlabel">the full funnel -- data to intelligence</h2>
      <ol className="flex flex-col gap-3">
        {FUNNEL_STAGE_DETAIL.map((s, i) => (
          <li key={s.key}>
            <Panel>
              <PanelHead
                title={s.label}
                right={
                  <span className="font-data text-[11px] text-muted-foreground">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                }
              />
              <div className="p-4">
                <p className="text-xs italic text-muted-foreground">{s.essence}</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>
                {s.tips && s.tips.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="microlabel text-muted-foreground/70">terms:</span>
                    {s.tips.map((t) => (
                      <InfoTip key={t} term={t} />
                    ))}
                  </div>
                )}
                <p className="mt-2 border border-border bg-surface-2 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
                  <span className="microlabel text-foreground/80">discipline: </span>
                  {s.discipline}
                </p>
                {s.key === EXAMPLE_STAGE_KEY && (
                  <div className="mt-3">
                    <LiveExample />
                  </div>
                )}
              </div>
            </Panel>
          </li>
        ))}
      </ol>
    </section>
  );
}
