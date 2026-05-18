import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { OpenBet, PortfolioSummary } from "@/lib/types/api";

interface PortfolioState {
  bankroll: number;
  summary: PortfolioSummary | null;
  openBets: OpenBet[];
  setBankroll: (amount: number) => void;
  setSummary: (s: PortfolioSummary) => void;
  setOpenBets: (bets: OpenBet[]) => void;
}

const DEFAULT_SUMMARY: PortfolioSummary = {
  bankroll: 10000,
  total_pnl: 0,
  roi: 0,
  clv_avg: 0,
  open_count: 0,
  drawdown_pct: 0,
  win_rate: 0,
  sharpe: 0,
};

export const usePortfolioStore = create<PortfolioState>()(
  persist(
    (set) => ({
      bankroll: 10000,
      summary: DEFAULT_SUMMARY,
      openBets: [],
      setBankroll: (amount) => set({ bankroll: amount }),
      setSummary: (summary) => set({ summary }),
      setOpenBets: (openBets) => set({ openBets }),
    }),
    { name: "cv-portfolio" }
  )
);
