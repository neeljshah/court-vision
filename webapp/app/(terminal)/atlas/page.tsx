// Retired route (DESIGN_BRIEF 2026-10-20 section 3a): static redirect stub; the map is lib/redirects.ts.
import { RedirectStub, stubMetadata } from "@/components/shell/RedirectStub";

export const metadata = stubMetadata("/atlas/");

export default function Page() {
  return <RedirectStub from="/atlas/" />;
}
