"use client";

import { create } from "zustand";
import type {
  Bet,
  BusMessage,
  HelloPayload,
  PBPEvent,
  Projection,
  Snapshot,
} from "./types";

type AlertEntry = { ts: number; severity: string; msg: string };

type EVPoint = { ts: number; ev: number };

type State = {
  // connection
  wsReady: boolean;
  lastEventTs: number | null;

  // per-game state
  snapshots: Record<string, Snapshot>;
  projections: Record<string, Projection[]>;

  // bets — keyed by (player_id, stat, side) so we can de-dup across replays
  bets: Record<string, Bet>;
  evHistory: Record<string, EVPoint[]>;

  // play-by-play rolling buffer (last N events)
  pbp: PBPEvent[];

  // alerts (last N)
  alerts: AlertEntry[];

  // ── mutators ──
  applyHello: (h: HelloPayload) => void;
  applyMessage: (m: BusMessage) => void;
  pushAlert: (a: AlertEntry) => void;
  reset: () => void;
};

const MAX_PBP = 30;
const MAX_ALERTS = 12;
const MAX_EV_HISTORY = 48;

const keyForBet = (b: Pick<Bet, "player_id" | "stat" | "side">) =>
  `${b.player_id}|${b.stat}|${b.side}`;

export const useLiveStore = create<State>((set, get) => ({
  wsReady: false,
  lastEventTs: null,
  snapshots: {},
  projections: {},
  bets: {},
  evHistory: {},
  pbp: [],
  alerts: [],

  applyHello: (h) => {
    const bets: Record<string, Bet> = {};
    const evHistory: Record<string, EVPoint[]> = {};
    for (const b of h.recent_bets || []) {
      const k = keyForBet(b);
      bets[k] = b;
      evHistory[k] = [{ ts: Date.now() / 1000, ev: b.ev }];
    }
    set({
      snapshots: h.snapshots || {},
      projections: h.projections || {},
      bets,
      evHistory,
      alerts: (h.recent_alerts || []) as AlertEntry[],
      lastEventTs: Date.now() / 1000,
    });
  },

  applyMessage: (m) => {
    const now = Date.now() / 1000;
    if (m.topic === "hello") {
      get().applyHello(m.event as HelloPayload);
      return;
    }
    if (m.topic === "snapshot.updated") {
      const ev = m.event as { game_id: string; snapshot: Snapshot };
      set((s) => ({
        snapshots: { ...s.snapshots, [ev.game_id]: ev.snapshot },
        lastEventTs: now,
      }));
      return;
    }
    if (m.topic === "projection.updated") {
      const ev = m.event as { game_id: string; rows: Projection[] };
      set((s) => ({
        projections: { ...s.projections, [ev.game_id]: ev.rows },
        lastEventTs: now,
      }));
      return;
    }
    if (m.topic === "bet.recommended") {
      const b = m.event as Bet;
      const k = keyForBet(b);
      set((s) => {
        const hist = s.evHistory[k] || [];
        const nextHist = [...hist, { ts: now, ev: b.ev }].slice(-MAX_EV_HISTORY);
        return {
          bets: { ...s.bets, [k]: b },
          evHistory: { ...s.evHistory, [k]: nextHist },
          lastEventTs: now,
        };
      });
      return;
    }
    if (m.topic.startsWith("pbp.")) {
      const ev = m.event as PBPEvent;
      ev.topic = m.topic;
      ev.ts = ev.ts || now;
      set((s) => ({
        pbp: [ev, ...s.pbp].slice(0, MAX_PBP),
        lastEventTs: now,
      }));
      return;
    }
    if (m.topic === "lines.refreshed") {
      set({ lastEventTs: now });
      return;
    }
  },

  pushAlert: (a) =>
    set((s) => ({ alerts: [a, ...s.alerts].slice(0, MAX_ALERTS) })),

  reset: () =>
    set({
      wsReady: false,
      lastEventTs: null,
      snapshots: {},
      projections: {},
      bets: {},
      evHistory: {},
      pbp: [],
      alerts: [],
    }),
}));

export const useReady = () => useLiveStore((s) => s.wsReady);
export const useBets = () =>
  useLiveStore((s) =>
    Object.values(s.bets).sort((a, b) => (b.ev || 0) - (a.ev || 0)),
  );
export const useEVHistory = (key: string) =>
  useLiveStore((s) => s.evHistory[key] || []);
export const usePBP = () => useLiveStore((s) => s.pbp);
export const useSnapshots = () => useLiveStore((s) => s.snapshots);
export const useProjections = () => useLiveStore((s) => s.projections);
export const useAlerts = () => useLiveStore((s) => s.alerts);
export const useLastEventTs = () => useLiveStore((s) => s.lastEventTs);
