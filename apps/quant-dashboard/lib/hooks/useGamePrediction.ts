import { useQuery } from "@tanstack/react-query";
import { getPredictionsToday, predictGame, getWinProb } from "@/lib/api";
import type { GamePredictionRequest } from "@/lib/types/api";

export function usePredictionsToday(season?: string) {
  return useQuery({
    queryKey: ["predictions-today", season],
    queryFn: () => getPredictionsToday(season),
    staleTime: 120_000,
    refetchInterval: 120_000,
  });
}

export function useGamePrediction(req: GamePredictionRequest | null) {
  return useQuery({
    queryKey: ["game-prediction", req?.home_team, req?.away_team, req?.season],
    queryFn: () => predictGame(req!),
    enabled: !!req,
    staleTime: 300_000,
  });
}

export function useWinProb(gameId: string | null, home?: string, away?: string) {
  return useQuery({
    queryKey: ["win-prob", gameId, home, away],
    queryFn: () => getWinProb(gameId!, { home, away }),
    enabled: !!gameId,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
