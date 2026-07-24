"use client";

import { useEffect, useState } from "react";
import {
  api,
  isUnavailable,
  type PredictEnvelope,
  type PredictRecord,
  type GameEdge,
  type BestBetsEnvelope,
} from "@/lib/api";
import { Unavailable } from "@/components/p6/Primitives";
import { GameCard } from "./GameCard";
import { GAME_SPORTS, sportLabel, matchSlateGame } from "./card-utils";
import { SlateAgeBar } from "./SlateAgeBar";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";
import { fetchSlate, type BoardSport, type Slate } from "@/lib/board";

type SportState = {
  sport: string;
  env: PredictEnvelope | null;
  edges: Record<string, GameEdge>;
  slate: Slate | null;
  err?: string;
};

// SlateCards -- the /games hub body. For every sport it pulls the latest
// predict envelope (/api/predict/{sport}) for the matchups + coherent
// prediction, and the best-bets envelope (/api/v1/bestbets/{sport}) for the
// per-game best-bet chip. Each sport degrades INDEPENDENTLY to an honest empty
// state: an offseason / unavailable sport shows a clear message, NEVER a fake
// slate. UNITS / probability only -- NO $.
export function SlateCards() {
  const [states, setStates] = useState<SportState[]>(
    GAME_SPORTS.map((s) => ({ sport: s, env: null, edges: {}, slate: null })),
  );

  useEffect(() => {
    // Live polling: fan out the per-sport predict + best-bets fetches on an
    // interval. Each tick uses its own AbortController so an unmount / re-tick
    // cancels the prior in-flight requests. Failures degrade per-sport (honest
    // empty state); a failed poll never blanks a previously-good slate.
    const SLATE_POLL_MS = 120_000;
    let cancelled = false;
    let ac = new AbortController();

    const runOnce = () => {
      ac.abort();
      ac = new AbortController();
      const signal = ac.signal;
      GAME_SPORTS.forEach((sport) => {
        // Predict envelope (matchups + the coherent prediction).
        api.getPredict(sport, signal).then((d) => {
          if (cancelled) return;
          setStates((prev) =>
            prev.map((row) =>
              row.sport === sport
                ? isUnavailable(d)
                  ? { ...row, err: d.reason }
                  : { ...row, env: d as PredictEnvelope, err: undefined }
                : row,
            ),
          );
        });
        // Best-bets envelope (per-game best-bet chip). Failures are non-fatal:
        // the card just shows an honest NO BET rather than a fabricated tier.
        api.bestbets(sport, signal).then((d) => {
          if (cancelled || isUnavailable(d)) return;
          const env = d as BestBetsEnvelope;
          const byId: Record<string, GameEdge> = {};
          for (const g of env.games || []) if (g.game_id) byId[g.game_id] = g;
          setStates((prev) =>
            prev.map((row) =>
              row.sport === sport ? { ...row, edges: byId } : row,
            ),
          );
        });
        // Board slate (best price + book per side, from /api/board/slate).
        // Failure is non-fatal -- cards fall back to the predict envelope's
        // own market rows, never a fabricated price.
        fetchSlate(sport as BoardSport)
          .then((slate) => {
            if (cancelled) return;
            setStates((prev) =>
              prev.map((row) => (row.sport === sport ? { ...row, slate } : row)),
            );
          })
          .catch(() => {});
      });
    };

    runOnce();
    const id = setInterval(runOnce, SLATE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
      ac.abort();
    };
  }, []);

  const totalLive = states.reduce(
    (n, s) =>
      n + (s.env && s.env.status === "ok" ? s.env.predictions?.length ?? 0 : 0),
    0,
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <p className="font-data text-[11px] text-faint">
          one coherent prediction per game - units + tier - no $ - vs-close
          UNPROVEN
        </p>
        <span className="border border-border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          {totalLive} live games
        </span>
      </div>

      {/* Sport quick-nav: scrolls to the section below -- every sport stays
          in the DOM at once (independent honest-empty states per sport), this
          is just a fast jump-to. */}
      <nav className="sticky top-0 z-10 flex gap-1 overflow-x-auto border-b border-border bg-background py-2">
        {GAME_SPORTS.map((s) => (
          <a
            key={s}
            href={`#slate-${s}`}
            className="min-h-[32px] shrink-0 border border-border px-3 py-1.5 font-data text-[11px] font-bold uppercase tracking-wider text-muted-foreground hover:border-primary hover:text-foreground"
          >
            {sportLabel(s)}
          </a>
        ))}
      </nav>

      {states.map((s) => (
        <div id={`slate-${s.sport}`} key={s.sport}>
          <SportSlate state={s} />
        </div>
      ))}
    </div>
  );
}

function SportSlate({ state }: { state: SportState }) {
  const { sport, env, edges, slate, err } = state;
  const label = sportLabel(sport);

  let body: React.ReactNode;
  if (err) {
    body = <div className="p-3"><Unavailable reason={err} /></div>;
  } else if (!env) {
    body = <p className="p-3 font-data text-xs text-faint">loading...</p>;
  } else if (env.status !== "ok") {
    // Honest offseason / no-snapshot state -- never a fabricated slate.
    body = (
      <p className="p-3 font-data text-xs text-muted-foreground">
        {env.reason ||
          env.honest_note ||
          `no games available for ${label.toLowerCase()} right now (offseason / no live slate)`}
      </p>
    );
  } else {
    const preds: PredictRecord[] = env.predictions || [];
    if (preds.length === 0) {
      body = (
        <p className="p-3 font-data text-xs text-muted-foreground">
          no games live now ({label.toLowerCase()})
        </p>
      );
    } else {
      body = (
        <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3">
          {preds.map((rec) => (
            <GameCard
              key={rec.game_id}
              sport={sport}
              rec={rec}
              edge={edges[rec.game_id] ?? null}
              slateGame={matchSlateGame(slate, rec)}
            />
          ))}
        </div>
      );
    }
  }

  const count =
    env && env.status === "ok" ? env.predictions?.length ?? 0 : 0;

  return (
    <Panel>
      <PanelHead
        title={label}
        right={
          <>
          <SlateAgeBar generatedAt={env?.generated_at ?? null} />
          <span
            className={cn(
              "border px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider",
              count > 0 ? "border-success text-up" : "border-border text-muted-foreground",
            )}
          >
            {count} games
          </span>
          </>
        }
      />
      {body}
    </Panel>
  );
}
