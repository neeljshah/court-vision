"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useState } from "react";
import { usePortfolioSummary, useOpenBets } from "@/lib/hooks/usePortfolio";

function PortfolioSync() {
  usePortfolioSummary();
  useOpenBets();
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <PortfolioSync />
        {children}
      </TooltipProvider>
    </QueryClientProvider>
  );
}
