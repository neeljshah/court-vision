// /desk/model-cards (dir not "models": .gitignore models/) -- one card per sport: how the pregame anchor is built, which
// in-game arms quote live, whether a daily fit exists, and the canonical
// calibration figures with their as_of and source path. Build-time read.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/desk/model-cards/", {
  title: "Desk models",
  description: "Paper only: how each sport's pregame and in-game models work, with calibration figures.",
});

export default function DeskModelsPage() {
  const desk = loadDesk();
  const m = desk?.models ?? null;

  return (
    <DeskShell desk={desk} title="How the models work" active="/desk/model-cards">
      <Section title="Scoreboard arms (scored on every tick against the outcome)" asOf={m?.canonical_as_of}>
        {m ? (
          <T head={["arm", "what it is"]} rows={Object.entries(m.scoreboard_arms).map(([a, w]) => [a, w])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "models")} />}
      </Section>

      {m ? m.cards.map((c) => (
        <Section key={c.sport} title={`${c.sport} model card`} asOf={m.canonical_as_of} source={m.canonical_source}>
          <div className="flex flex-col gap-2 px-3 py-2 text-[12px]">
            <p><span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">pregame</span> <span className="text-muted-foreground">{c.pregame}</span></p>
            <p><span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">in-game daily fit</span>{" "}
              <span className="text-muted-foreground">{c.daily_fit ? "yes" : "no"}: {c.fit_note}</span></p>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">live paper quote arms</span>
              {c.ingame_live_arms ? (
                <ul className="list-disc pl-5 text-muted-foreground">
                  {c.ingame_live_arms.map((a) => <li key={a.arm}><span className="font-data">{a.arm}</span>: {a.what ?? "-"}</li>)}
                </ul>
              ) : <NotAvailable refusals={refusalsFor(desk, "ingame.sport_arms")} />}
            </div>
          </div>
          {c.figures.length ? (
            <T head={["figure", "metric", "model", "reference", "gap", "95% CI", "n", "verdict", "as of", ""]}
              rows={c.figures.map((f) => [f.market ?? f.key, f.metric ?? "-", fmt(f.model ?? null),
                fmt(f.close ?? null), fmt(f.gap ?? null), f.ci95 ? `[${f.ci95[0]}, ${f.ci95[1]}]` : "-",
                f.n ?? "-", f.verdict ?? "-", f.as_of ?? "-",
                f.source ? <ReceiptChip key="r" sourceArtifact={f.source} asOf={f.as_of ?? null}
                  verified="descriptive_only" verdict={f.verdict ?? null} /> : "-"])} />
          ) : (
            <NotAvailable refusals={[{ section: `models.${c.sport}.figures`,
              reason: "no canonical calibration figure for this sport in CANONICAL_FIGURES.json" }]} />
          )}
          {c.figures.map((f) => f.licenses ? (
            <p key={f.key} className="px-3 pb-2 text-[12px] text-faint">{f.licenses} (source {f.source})</p>
          ) : null)}
        </Section>
      )) : (
        <Section title="Model cards"><NotAvailable refusals={refusalsFor(desk, "models")} /></Section>
      )}
    </DeskShell>
  );
}
