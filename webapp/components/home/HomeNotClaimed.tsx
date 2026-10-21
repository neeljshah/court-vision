// HomeNotClaimed -- the "what this is not" block (P2.1 item 4).
import Link from "next/link";

export function HomeNotClaimed({ asOf }: { asOf: string | null }) {
  return (
    <section aria-label="What this is not" data-testid="not-claimed"
      className="border border-border border-l-[3px] border-l-primary bg-card px-3 py-2 text-sm text-muted-foreground">
      <b className="text-foreground">What this is not.</b> Not a betting product and not a track record: no
      edge, ROI or profit claim, paper units only, and a static snapshot{asOf ? ` (as of ${asOf})` : ""}.
      Retracted figures appear only on the <Link href="/evidence/retractions/" className="text-primary underline underline-offset-2 hover:no-underline">retraction record</Link>.
    </section>
  );
}
