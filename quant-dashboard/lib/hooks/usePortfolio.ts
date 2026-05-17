import { useQuery } from "@tanstack/react-query";
import { getPortfolioSummary, getOpenBets } from "@/lib/api";
import { usePortfolioStore } from "@/lib/stores/portfolio";
import { useEffect } from "react";

export function usePortfolioSummary() {
  const setSummary = usePortfolioStore((s) => s.setSummary);
  const query = useQuery({
    queryKey: ["portfolio-summary"],
    queryFn: getPortfolioSummary,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  useEffect(() => {
    if (query.data) setSummary(query.data);
  }, [query.data, setSummary]);
  return query;
}

export function useOpenBets() {
  const setOpenBets = usePortfolioStore((s) => s.setOpenBets);
  const query = useQuery({
    queryKey: ["open-bets"],
    queryFn: getOpenBets,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  useEffect(() => {
    if (query.data) setOpenBets(query.data.bets);
  }, [query.data, setOpenBets]);
  return query;
}
