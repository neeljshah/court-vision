import Link from "next/link";
import { Receipt } from "@/components/analytics/Receipt";
import { claimFamilyId } from "@/lib/analytics/claimHistory";

export type VerdictFlipStep = {
  verdict: string;
  status: string;
  corpus: string;
  n: number;
  effect: number | null;
  run_ts: string | null;
};

export type VerdictFlipCase = {
  sport: string;
  hypothesis: string;
  steps: VerdictFlipStep[];
  one_line: string;
};

const ANATOMY_ARTIFACT = "scripts/platformkit/analytics_showcase/out/verdict_flip_anatomy.json";
const SPORT_LABELS: Record<string, string> = {
  basketball_nba: "NBA",
  mlb: "MLB",
  soccer: "Soccer",
  tennis: "Tennis",
};

function labelFor(hypothesis: string): string {
  const label = hypothesis.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function effectLabel(effect: number | null): string {
  return effect === null ? "effect not published" : String(effect);
}

export function VerdictFlipCases({
  flips,
  generatedAt,
  upstreamArtifact,
  undatedRunCount,
}: {
  flips: VerdictFlipCase[];
  generatedAt?: string;
  upstreamArtifact: string;
  undatedRunCount: number;
}) {
  return <section aria-label="Published verdict flip cases">
    <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 28 }}>
      Steps are shown in source order; {undatedRunCount} runs have no recorded date.
    </p>
    <div style={{ display: "grid", gap: 16, marginTop: 14 }}>
      {flips.map(flip => {
        const familyId = claimFamilyId(flip);
        return <article key={familyId} style={{ background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: "var(--radius-card)", padding: "18px 20px" }}>
          <span style={{ border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", color: "var(--ink-3)", display: "inline-block", fontSize: 11, fontWeight: 700, letterSpacing: ".06em", padding: "2px 8px", textTransform: "uppercase" }}>
            {SPORT_LABELS[flip.sport] || flip.sport}
          </span>
          <h2 className="serif" style={{ color: "var(--ink)", fontSize: 20, fontWeight: 500, marginTop: 10 }}>
            {labelFor(flip.hypothesis)}
          </h2>
          <p style={{ color: "var(--ink-2)", fontSize: 15, lineHeight: 1.6, marginTop: 10 }}>{flip.one_line}</p>
          <ol style={{ background: "var(--paper-tint)", border: "1px solid var(--rule)", borderRadius: "var(--radius-card)", listStyle: "none", marginTop: 14, padding: "8px 14px" }}>
            {flip.steps.map((step, index) => <li key={`${step.verdict}-${index}`} style={{ borderBottom: index + 1 === flip.steps.length ? 0 : "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 13, padding: "7px 0" }}>
              <strong style={{ color: "var(--ink)" }}>Run {index + 1}</strong>{" -- "}
              <span className="mono">{step.verdict}</span> on {step.corpus}, n={step.n.toLocaleString("en-US")}, <span className="mono">{effectLabel(step.effect)}</span>
              {step.run_ts ? <> (<span className="mono tnum">{step.run_ts}</span>)</> : " (run date not recorded)"}
            </li>)}
          </ol>
          <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "10px 16px", marginTop: 16 }}>
            <Link href={`/analytics/the-loop#${familyId}`} style={{ fontSize: 13, fontWeight: 700 }}>View full ledger history</Link>
            <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>Case anatomy <Receipt sourceArtifact={ANATOMY_ARTIFACT} asOf={generatedAt} label="case anatomy artifact" verdict="descriptive_only" /></span>
            <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>Upstream scoreboard <Receipt sourceArtifact={upstreamArtifact} label="upstream scoreboard" verdict="descriptive_only" /></span>
          </div>
        </article>;
      })}
    </div>
  </section>;
}

export default VerdictFlipCases;
