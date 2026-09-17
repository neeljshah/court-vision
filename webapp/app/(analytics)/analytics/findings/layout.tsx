import type { ReactNode } from "react";
import { FindingsBackLink } from "@/components/analytics/findings/FindingsBackLink";

export default function FindingsLayout({ children }: { children: ReactNode }) {
  return <><FindingsBackLink />{children}<FindingsBackLink /></>;
}
