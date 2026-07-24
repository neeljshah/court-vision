// app/lab/layout.tsx -- route group wrapper for /lab/*.
// ponytail: no shared chrome lives here -- each /lab/* page renders its own
// <LabShell active="..."> so the active tab can be set per-page without a
// client-side usePathname read. This layout only exists to give the route
// group a metadata title.
import type { ReactNode } from "react";

export const metadata = {
  title: "Lab",
  description: "Descriptive instruments and counterfactual replays -- edge_claimed:false.",
};

export default function LabLayout({ children }: { children: ReactNode }) {
  return children;
}
