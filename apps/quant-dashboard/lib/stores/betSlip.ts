import { create } from "zustand";
import type { EdgeDetectorEdge } from "@/lib/types/api";

interface SlipEntry {
  edge: EdgeDetectorEdge;
  stake: number;
  kellyFraction: number;
}

interface BetSlipState {
  entries: SlipEntry[];
  addEdge: (edge: EdgeDetectorEdge, bankroll: number) => void;
  removeEdge: (index: number) => void;
  updateStake: (index: number, stake: number) => void;
  clear: () => void;
  isAtLimit: boolean;
}

const MAX_BETS = 20;
const KELLY_FRACTION = 0.25;
const MAX_SINGLE_PCT = 0.04;

function kellyStake(edge: EdgeDetectorEdge, bankroll: number): number {
  const kelly = (edge.kelly ?? 0) * KELLY_FRACTION;
  const raw = bankroll * kelly;
  const cap = bankroll * MAX_SINGLE_PCT;
  return Math.min(raw, cap);
}

export const useBetSlipStore = create<BetSlipState>((set, get) => ({
  entries: [],
  isAtLimit: false,

  addEdge: (edge, bankroll) => {
    const { entries } = get();
    if (entries.length >= MAX_BETS) return;
    const already = entries.some(
      (e) => e.edge.player === edge.player && e.edge.stat === edge.stat
    );
    if (already) return;
    const stake = kellyStake(edge, bankroll);
    set((s) => ({
      entries: [...s.entries, { edge, stake, kellyFraction: KELLY_FRACTION }],
      isAtLimit: s.entries.length + 1 >= MAX_BETS,
    }));
  },

  removeEdge: (index) =>
    set((s) => ({
      entries: s.entries.filter((_, i) => i !== index),
      isAtLimit: false,
    })),

  updateStake: (index, stake) =>
    set((s) => ({
      entries: s.entries.map((e, i) => (i === index ? { ...e, stake } : e)),
    })),

  clear: () => set({ entries: [], isAtLimit: false }),
}));
