"use client";

// A source forecast beside its market references, with snapshot provenance.
//
// HONESTY RAILS: UNITS / probability only, NO $ field; the surface has no price
// column; provenance is shown, not an edge; vs_close is never claimed here.

import { useEffect, useState } from "react";
import { api, isUnavailable } from "@/lib/api";
import type { PredictRecord, PredictMarket } from "@/lib/api";
import {
  MarketSurfaceTable,
  UncertaintyBar,
  InfoTip,
} from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { isSnapshotMode } from "@/lib/fetchHonest";

const exampleTitle = isSnapshotMode ? "a published example" : "a concrete live example";

// The home-win probability lives on the record's pregame_probs map; key names
// vary by engine, so we look it up defensively and fall back to honest empty.
function homeWinProb(rec: PredictRecord): number | null {
  const p = rec.pregame_probs ?? {};
  const keys = ["home_ml", "home", "home_win", "p_home", "H", "1"];
  for (const k of keys) {
    const v = p[k];
    if (typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1) return v;
  }
  return null;
}

// Pick the first prediction that actually carries a coherent market surface so
// the example always shows the full DATA->ONE PREDICTION collapse, not a stub.
function pickExample(
  recs: PredictRecord[] | undefined
): PredictRecord | null {
  if (!recs || recs.length === 0) return null;
  const withMarkets = recs.find((r) => (r.markets?.length ?? 0) > 0);
  return withMarkets ?? recs[0] ?? null;
}

function EmptyExample({ note }: { note?: string }) {
  return (
    <Panel>
      <PanelHead title={exampleTitle} />
      <div className="p-4 text-xs leading-relaxed text-muted-foreground">
        <span className="font-semibold text-foreground">
          {isSnapshotMode ? "No published soccer example." : "No live soccer snapshot right now."}
        </span>{" "}
        {note ??
          "This panel requires a source prediction. The Games page lists available matchups."}
      </div>
    </Panel>
  );
}

export function LiveExample() {
  const [rec, setRec] = useState<PredictRecord | null>(null);
  const [state, setState] = useState<"loading" | "empty" | "ready">("loading");
  const [note, setNote] = useState<string | undefined>();
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .getPredict("soccer", ctrl.signal)
      .then((env) => {
        if (isUnavailable(env)) {
          setNote(env.reason);
          setState("empty");
          return;
        }
        const picked = pickExample(env.predictions);
        if (!picked) {
          setNote(env.honest_note ?? env.note ?? undefined);
          setState("empty");
          return;
        }
        setRec(picked);
        setGeneratedAt(env.generated_at ?? null);
        setState("ready");
      })
      .catch(() => setState("empty"));
    return () => ctrl.abort();
  }, []);

  if (state === "loading") {
    return (
      <Panel>
        <PanelHead title={exampleTitle} />
        <div className="p-4 text-xs text-muted-foreground">Loading a soccer example...</div>
      </Panel>
    );
  }

  if (state === "empty" || !rec) return <EmptyExample note={note} />;

  const prob = homeWinProb(rec);
  const markets: PredictMarket[] = rec.markets ?? [];

  return (
    <Panel>
      <PanelHead
        title={exampleTitle}
        right={
          <span className="text-xs font-semibold tracking-tight text-foreground">
            {rec.home} vs {rec.away}
          </span>
        }
      />
      <div className="flex flex-col gap-3 p-4">
        <p className="font-data text-[11px] text-faint">
          {isSnapshotMode ? "Published snapshot" : "Source generated"}: {generatedAt || "timestamp unavailable"}
        </p>
        <p className="text-xs leading-relaxed text-muted-foreground">
          The source forecast provides a home{" "}
          <span className="inline-flex items-center gap-1">
            win probability
            <InfoTip term="probability" />
          </span>{" "}
          followed by separate market references, each with its own source and capture time.
        </p>
        <UncertaintyBar prob={prob} label="P(home win)" />
        <MarketSurfaceTable
          markets={markets}
          caption="Market reference probabilities for this match, separate from the source forecast."
        />
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Forecasts and market references come from separate source fields. No dollar figure, no
          price, and no edge is shown.
        </p>
      </div>
    </Panel>
  );
}
