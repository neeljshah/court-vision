// components/shell/EvidenceHubLinks.tsx -- the Evidence section's hub links, shown at the
// top of /evidence/ above the claim index.
import Link from "next/link";
import { githubDoc } from "./nav";

const HUB: Array<{ label: string; href: string; note: string; external?: boolean }> = [
  { label: "Receipts ledger", href: "/receipts/", note: "every scored row, losses included" },
  { label: "Model cards", href: githubDoc("docs/evidence/model_cards/INDEX.json"), note: "what each model is scored on", external: true },
  { label: "Retraction record", href: "/evidence/retractions/", note: "withdrawn figures and their replacements" },
  { label: "Reproduce", href: githubDoc("REPRODUCE.md"), note: "commands to re-run the checks", external: true },
  { label: "Evidence packet", href: githubDoc("docs/JOB_EVIDENCE_PACKET.md"), note: "the source for every number", external: true },
];

export function EvidenceHubLinks() {
  return (
    <nav aria-label="Evidence">
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {HUB.map((h) => (
          <li key={h.label} className="rounded-md border border-border bg-card p-3">
            {h.external ? (
              <a href={h.href} className="font-medium text-foreground underline">{h.label}</a>
            ) : (
              <Link href={h.href} prefetch={false} className="font-medium text-foreground underline">{h.label}</Link>
            )}
            <p className="mt-1 text-sm text-muted-foreground">{h.note}</p>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default EvidenceHubLinks;
