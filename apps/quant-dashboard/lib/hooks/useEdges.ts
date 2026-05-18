import { useQuery } from "@tanstack/react-query";
import { getEdgesToday } from "@/lib/api";

export function useEdgesToday(minEv?: number) {
  return useQuery({
    queryKey: ["edges-today", minEv],
    queryFn: () => getEdgesToday(minEv),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
