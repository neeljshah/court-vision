"use client";

// LiveExample.tsx -- a CONCRETE live example wired into the funnel walkthrough.
//
// Pulls a REAL soccer prediction from the live snapshot (api.getPredict) and
// shows what the funnel actually produces: ONE anchored win probability with its
// held-out uncertainty band, plus the full coherent market surface read off the
// SAME engine matrix (moneyline / handicap / totals all spined by one anchor).
// This turns the abstract "ONE PREDICTION" stage into something the reader can
// see. Nothing here is invented -- every number is the live API's, and when no
// snapshot exists we render an HONEST empty state (never a fabricated game).
//
// HONESTY RAILS: UNITS / probability only, NO $ field; the surface has no price
// column; provenance is shown, not an edge; vs_close is never claimed here.

import { useEffect, useState } from "react";
import { api, isUnavailable } from "@/lib/api";
import type { PredictRecord, PredictMarket } from "@/lib/api";
import {
  MarketSurfaceTable,
  UncertaintyBar,
  ProvenanceBadge,
  InfoTip,
} from "@/components/depth";
import { Panel, PanelHead } from "@/components/ui/terminal";

// The home-win probability lives on the record's pregame_probs map; key names
// vary by engine, so we look it up defensively and fall back to honest empty.
function homeWinProb(rec: PredictRecord): number | null {
  const p = rec.pregame_probs ?? {};
  const keys = ["home", "home_win", "p_home", "H", "1"];
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
      <PanelHead title="a concrete live example" />
      <div className="p-4 text-xs leading-relaxed text-muted-foreground">
        <span className="font-semibold text-foreground">No live soccer snapshot right now.</span>{" "}
        {note ??
          "There is no fabricated game to show -- this panel only renders a real " +
            "prediction off the live engine. Check the Games page when a match is on the board."}
      </div>
    </Panel>
  );
}

export function LiveExample() {
  const [rec, setRec] = useState<PredictRecord | null>(null);
  const [state, setState] = useState<"loading" | "empty" | "ready">("loading");
  const [note, setNote] = useState<string | undefined>();

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
        setState("ready");
      })
      .catch(() => setState("empty"));
    return () => ctrl.abort();
  }, []);

  if (state === "loading") {
    return (
      <Panel>
        <PanelHead title="a concrete live example" />
        <div className="p-4 text-xs text-muted-foreground">Loading a live soccer example...</div>
      </Panel>
    );
  }

  if (state === "empty" || !rec) return <EmptyExample note={note} />;

  const prob = homeWinProb(rec);
  const markets: PredictMarket[] = rec.markets ?? [];

  return (
    <Panel>
      <PanelHead
        title="a concrete live example"
        right={
          <span className="text-xs font-semibold tracking-tight text-foreground">
            {rec.home} vs {rec.away}
          </span>
        }
      />
      <div className="flex flex-col gap-3 p-4">
        <ProvenanceBadge model="Dixon-Coles" phase="pregame" />
        <p className="text-xs leading-relaxed text-muted-foreground">
          This is the real output of the funnel for a live soccer match: one anchored{" "}
          <span className="inline-flex items-center gap-1">
            win probability
            <InfoTip term="probability" />
          </span>{" "}
          with its held-out band, then the FULL coherent market surface below -- every
          row read off the SAME engine matrix, so the marginals cannot disagree.
        </p>
        <UncertaintyBar prob={prob} label="P(home win)" />
        <MarketSurfaceTable
          markets={markets}
          model="Dixon-Coles"
          phase="pregame"
          caption="The coherent surface for this match -- probability only, no price."
        />
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Every number above is the live engine's own output. No dollar figure, no
          price, and no edge is shown -- only the calibrated probability and where it
          came from.
        </p>
      </div>
    </Panel>
  );
}
