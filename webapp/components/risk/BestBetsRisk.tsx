"use client";

// BestBetsRisk.tsx -- the per-bet RISK list across all sports.
//
// Pulls the best-bets envelope (/api/v1/bestbets/{sport}) for each sport and
// renders ONE BestBetRiskCard per QUALIFYING (decision='bet') pick, sorted by
// units staked. Each sport degrades INDEPENDENTLY to an honest empty/unavailable
// state -- an offseason or down sport NEVER fabricates a pick. When NO pick across
// any sport clears a tier floor, the panel shows an honest "no bets qualify --
// matching the efficient close is a SUCCESS" empty state. UNITS / probability
// only -- NO $.

import { useEffect, useState } from "react";
import {
  api,
  isUnavailable,
  type BestBetsEnvelope,
  type GameEdge,
} from "@/lib/api";
import { GAME_SPORTS, sportLabel } from "@/app/games/card-utils";
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import { BestBetRiskCard } from "./BestBetRiskCard";
import { qualifyingRows, type BetRiskRow } from "./riskUtils";

type SportRisk = {
  sport: string;
  games: GameEdge[] | null;
  err?: string;
};

export function BestBetsRisk() {
  const [states, setStates] = useState<SportRisk[]>(
    GAME_SPORTS.map((s) => ({ sport: s, games: null })),
  );

  useEffect(() => {
    const ac = new AbortController();
    GAME_SPORTS.forEach((sport) => {
      api.bestbets(sport, ac.signal).then((d) => {
        setStates((prev) =>
          prev.map((row) =>
            row.sport === sport
              ? isUnavailable(d)
                ? { ...row, err: d.reason, games: [] }
                : { ...row, games: (d as BestBetsEnvelope).games || [] }
              : row,
          ),
        );
      });
    });
    return () => ac.abort();
  }, []);

  // Flatten qualifying rows with their sport, sorted by units (largest first).
  const all: Array<BetRiskRow & { sport: string }> = [];
  let anyLoaded = false;
  for (const st of states) {
    if (st.games == null) continue;
    anyLoaded = true;
    for (const r of qualifyingRows(st.games)) all.push({ ...r, sport: st.sport });
  }
  all.sort((a, b) => (b.stakeUnits ?? 0) - (a.stakeUnits ?? 0));

  return (
    <Panel
      title="per-bet risk (qualifying paper picks)"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Badge tone="slate">{all.length} qualify</Badge>
          <InfoTip
            text="One card per pick that clears a tier floor: units staked, tier, capped quarter-Kelly fraction, and model probability vs the devigged close. UNITS only -- no money, no edge claimed."
            ariaLabel="what is this list?"
          />
        </span>
      }
    >
      {!anyLoaded ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : all.length === 0 ? (
        <Unavailable reason="No paper pick clears a tier floor right now. Matching the efficient close is a SUCCESS, not a failure -- so there is nothing to risk. (NBA offseason; MLB / World Cup are the live sports.)" />
      ) : (
        <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {all.map((r, i) => (
            <div key={`${r.sport}-${r.gameId}-${r.market}-${i}`}>
              <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-faint">
                {sportLabel(r.sport)}
              </div>
              <ul>
                <BestBetRiskCard row={r} />
              </ul>
            </div>
          ))}
        </ul>
      )}
    </Panel>
  );
}
