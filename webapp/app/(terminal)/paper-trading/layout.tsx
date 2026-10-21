// Server layout: the page is a client component, so the title lives here.
import type { ReactNode } from "react";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/paper-trading/", { title: "Paper record",
  description: "The forward paper record: every paper fill with its settlement and CLV status, nights and coverage. Paper units only; not a verdict on the model.",
});

export default function PaperTradingLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
