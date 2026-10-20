// /desk/model-cards (dir not "models": .gitignore models/) -- one card per sport: how the pregame anchor is built, which
// in-game arms quote live, whether a daily fit exists, and the canonical
// calibration figures with their as_of and source path. Build-time read.

import type { ReactNode } from "react";
import { loadDesk, refusalsFor, fmt, type Figure } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";
import { AsOfBadge } from "@/components/evidence/AsOfBadge";
import { FigureValue, FigureVerdict } from "@/components/evidence/FigureValue";
import { ReceiptChip } from "@/components/evidence/ReceiptChip";
import { COMPARISON_FIGURES, isComparisonFigureKey } from "@/lib/figures";

// A desk-export figure whose key is canonical renders from lib/figures.ts (the generated
// copy of CANONICAL_FIGURES.json), so the desk's own copy of the number cannot drift from
// the packet; an unknown key falls back to the export's values with the same receipt.
function figureRow(f: Figure): ReactNode[] {
  if (isComparisonFigureKey(f.key)) {
    const k = f.key;
    const canon = COMPARISON_FIGURES[k];
    const cell = (field: "model" | "close" | "gap" | "ci95" | "n") =>
      <FigureValue key={field} k={k} field={field} asOf={false} receipt={false} />;
    return [canon.market ?? k, canon.metric ?? "-", cell("model"), cell("close"), cell("gap"), cell("ci95"), cell("n"),
      <FigureVerdict key="v" k={k} />, <AsOfBadge key="d" asOf={canon.as_of} />,
      <ReceiptChip key="r" compact source={canon.source} asOf={canon.as_of} status="edge_claimed:false" />];
  }
  return [f.market ?? f.key, f.metric ?? "-", fmt(f.model ?? null), fmt(f.close ?? null), fmt(f.gap ?? null),
    f.ci95 ? `[${f.ci95[0]}, ${f.ci95[1]}]` : "-", f.n ?? "-", f.verdict ?? "-", <AsOfBadge key="d" asOf={f.as_of} />,
    f.source ? <ReceiptChip key="r" compact source={f.source} asOf={f.as_of ?? null} status="descriptive_only" /> : "-"];
}

export const metadata = {
  title: "Desk models",
  description: "Paper only: how each sport's pregame and in-game models work, with calibration figures.",
};

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
            <p><span className="microlabel">pregame</span> <span className="text-muted-foreground">{c.pregame}</span></p>
            <p><span className="microlabel">in-game daily fit</span>{" "}
              <span className="text-muted-foreground">{c.daily_fit ? "yes" : "no"}: {c.fit_note}</span></p>
            <div>
              <span className="microlabel">live paper quote arms</span>
              {c.ingame_live_arms ? (
                <ul className="list-disc pl-5 text-muted-foreground">
                  {c.ingame_live_arms.map((a) => <li key={a.arm}><span className="font-data">{a.arm}</span>: {a.what ?? "-"}</li>)}
                </ul>
              ) : <NotAvailable refusals={refusalsFor(desk, "ingame.sport_arms")} />}
            </div>
          </div>
          {c.figures.length ? (
            <T head={["figure", "metric", "model", "reference", "gap", "95% CI", "n", "verdict", "as of", ""]}
              rows={c.figures.map(figureRow)} />
          ) : (
            <NotAvailable refusals={[{ section: `models.${c.sport}.figures`,
              reason: "no canonical calibration figure for this sport in CANONICAL_FIGURES.json" }]} />
          )}
          {c.figures.map((f) => {
            const licenses = isComparisonFigureKey(f.key) ? COMPARISON_FIGURES[f.key].licenses : f.licenses;
            const source = isComparisonFigureKey(f.key) ? COMPARISON_FIGURES[f.key].source : f.source;
            return licenses ? (
              <p key={f.key} className="px-3 pb-2 text-[11px] text-faint">{licenses} (source {source})</p>
            ) : null;
          })}
        </Section>
      )) : (
        <Section title="Model cards"><NotAvailable refusals={refusalsFor(desk, "models")} /></Section>
      )}
    </DeskShell>
  );
}
