// RetractionCard.tsx -- one retracted-vs-honest pair.
//
// THE ONLY component that renders a retracted number, and only ever inside this
// explicit retraction framing (a struck-through "RETRACTED" number paired with
// its honest replacement and a receipt back to docs/JOB_EVIDENCE_PACKET.md, the
// single truth-source). Props contract fixed by COMPONENTS.md. No edge/ROI is
// claimed by any honest replacement -- calibration language only. See
// .claude/rules/no-edge-claims.md.

import { Panel } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

// The public origin path the receipt links to (repo-relative, clone-safe).
const PACKET = "docs/JOB_EVIDENCE_PACKET.md";
const PACKET_HREF =
  "https://github.com/neeljshah/court-vision/blob/main/docs/JOB_EVIDENCE_PACKET.md";

export interface RetractionCardProps {
  /** The retracted headline number/claim, verbatim. Rendered struck-through. */
  retracted: string;
  /** Why it was wrong -- the measurement artifact, in one honest sentence. */
  whatWasWrong: string;
  /** The artifact / packet section that proves the retraction. */
  proofArtifact: string;
  /** The honest, calibration-only replacement. Never an edge/ROI claim. */
  honestReplacement: string;
  /** Packet amendment date shown on the receipt chip. */
  asOf: string;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="microlabel">{label}</div>
      <div className="mt-1 text-sm leading-relaxed text-foreground">{children}</div>
    </div>
  );
}

export function RetractionCard({
  retracted,
  whatWasWrong,
  proofArtifact,
  honestReplacement,
  asOf,
}: RetractionCardProps) {
  return (
    <Panel className="p-4">
      <div className="grid gap-4 md:grid-cols-2">
        {/* Left: the retracted number, struck out, honest-red. */}
        <div className="border-l-2 border-danger/60 pl-3">
          <div className="microlabel text-down">retracted</div>
          <div className="mt-1 font-data text-sm leading-relaxed text-down line-through decoration-danger/70">
            {retracted}
          </div>
          <div className="mt-3">
            <Field label="what was wrong">{whatWasWrong}</Field>
          </div>
        </div>

        {/* Right: the honest replacement, calibration-only. */}
        <div className="border-l-2 border-success/60 pl-3">
          <div className="microlabel text-up">honest replacement</div>
          <div className="mt-1 text-sm leading-relaxed text-foreground">
            {honestReplacement}
          </div>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-1">
            <span className="microlabel">proof</span>
            <span className="font-data text-[11px] text-faint">{proofArtifact}</span>
            <ReceiptChip
              sourceArtifact={PACKET}
              asOf={asOf}
              verified="descriptive_only"
              href={PACKET_HREF}
            />
          </div>
        </div>
      </div>
    </Panel>
  );
}
