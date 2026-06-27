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
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { GameCard } from "./GameCard";
import { GAME_SPORTS, sportLabel } from "./card-utils";

type SportState = {
  sport: string;
  env: PredictEnvelope | null;
  edges: Record<string, GameEdge>;
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
    GAME_SPORTS.map((s) => ({ sport: s, env: null, edges: {} })),
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
        <p className="font-mono text-[11px] text-slate-500">
          one coherent prediction per game · units + tier · no $ · vs-close
          UNPROVEN
        </p>
        <Badge tone="slate">{totalLive} live games</Badge>
      </div>

      {states.map((s) => (
        <SportSlate key={s.sport} state={s} />
      ))}
    </div>
  );
}

function SportSlate({ state }: { state: SportState }) {
  const { sport, env, edges, err } = state;
  const label = sportLabel(sport);

  let body: React.ReactNode;
  if (err) {
    body = <Unavailable reason={err} />;
  } else if (!env) {
    body = <p className="text-xs text-slate-600">loading...</p>;
  } else if (env.status !== "ok") {
    // Honest offseason / no-snapshot state -- never a fabricated slate.
    body = (
      <p className="text-xs text-slate-500">
        {env.reason ||
          env.honest_note ||
          `no games available for ${label.toLowerCase()} right now (offseason / no live slate)`}
      </p>
    );
  } else {
    const preds: PredictRecord[] = env.predictions || [];
    if (preds.length === 0) {
      body = (
        <p className="text-xs text-slate-500">
          no games live now ({label.toLowerCase()})
        </p>
      );
    } else {
      body = (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {preds.map((rec) => (
            <GameCard
              key={rec.game_id}
              sport={sport}
              rec={rec}
              edge={edges[rec.game_id] ?? null}
            />
          ))}
        </div>
      );
    }
  }

  const count =
    env && env.status === "ok" ? env.predictions?.length ?? 0 : 0;

  return (
    <Panel
      title={label}
      right={
        <span className="inline-flex items-center gap-2">
          {env?.generated_at ? (
            <span className="font-mono text-[10px] text-slate-600">
              {env.generated_at}
            </span>
          ) : null}
          <Badge tone={count > 0 ? "green" : "slate"}>{count} games</Badge>
        </span>
      }
    >
      {body}
    </Panel>
  );
}
