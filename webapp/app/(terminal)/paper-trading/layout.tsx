// Server layout: the page is a client component, so the title lives here.
import type { ReactNode } from "react";

export const metadata = { title: "Paper record" };

export default function PaperTradingLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
