// FigureValue.tsx -- renders a canonical figure BY KEY from lib/figures.ts (generated from
// docs/evidence/CANONICAL_FIGURES.json), with its as-of date and its receipt, so a page
// never retypes a number the claim_consistency gate checks. A count figure renders its
// value; a comparison figure renders one named field (model, close, gap, ci95, n, mde...),
// optionally with the packet's verdict label. The value inherits the surrounding type
// size and colour; the badges keep the kit style. Server-safe.
import "./evidence.css";
import {
  COMPARISON_FIGURES, FIGURES, FIGURES_SOURCE, isComparisonFigureKey,
  type CanonicalFigure, type ComparisonFigureKey, type CountFigureKey,
} from "@/lib/figures";
import { AsOfBadge } from "./AsOfBadge";
import { ReceiptChip } from "./ReceiptChip";
import { VerdictLabel, toPacketVerdict, type PacketVerdict } from "./VerdictLabel";
import { formatFigureField, isRepoPath } from "./kit";

type Common = {
  /** Show the figure's as-of badge (default true). */
  asOf?: boolean;
  /** Show the receipt chip (default true). */
  receipt?: boolean;
  /** Show the packet verdict label when the figure carries one (default false). */
  verdict?: boolean;
  /** Override the formatter (the default is the kit's one format per field). */
  format?: (value: unknown) => string;
  className?: string;
};

/** The fields of one comparison figure; for the union key, any field some comparison figure carries. */
export type ComparisonField<K extends ComparisonFigureKey = ComparisonFigureKey> =
  K extends ComparisonFigureKey ? Exclude<keyof (typeof COMPARISON_FIGURES)[K], "kind" | "key"> : never;

export type FigureValueProps<K extends ComparisonFigureKey = ComparisonFigureKey> =
  | ({ k: CountFigureKey; field?: undefined } & Common)
  | ({ k: K; field: ComparisonField<K> } & Common);

/** The receipt for a figure: its source path when that is a repo path, else the canonical JSON with the derivation in the note. */
export function figureReceipt(fig: CanonicalFigure): { source: string; note?: string } {
  return isRepoPath(fig.source) ? { source: fig.source } : { source: FIGURES_SOURCE, note: fig.source };
}

export function figureText<K extends ComparisonFigureKey>(props: FigureValueProps<K>): string {
  const fig = FIGURES[props.k] as CanonicalFigure;
  const field = props.field ? String(props.field) : "value";
  const raw = (fig as unknown as Record<string, unknown>)[field];
  return props.format ? props.format(raw) : formatFigureField(field, raw);
}

/** A comparison figure's packet verdict (null when the artifact word is not a packet label) and its MDE. */
export function figureVerdict(k: ComparisonFigureKey): { verdict: PacketVerdict | null; mde: number | null } {
  const fig = COMPARISON_FIGURES[k];
  return { verdict: toPacketVerdict(fig.verdict), mde: "mde" in fig && typeof fig.mde === "number" ? fig.mde : null };
}

/** The verdict label of a comparison figure, qualified by the packet; a non-packet word renders as plain text. */
export function FigureVerdict({ k }: { k: ComparisonFigureKey }) {
  const { verdict, mde } = figureVerdict(k);
  return verdict ? <VerdictLabel verdict={verdict} mde={mde} /> : <span data-figure-key={k}>{COMPARISON_FIGURES[k].verdict}</span>;
}

export function FigureValue<K extends ComparisonFigureKey>(props: FigureValueProps<K>) {
  const fig = FIGURES[props.k] as CanonicalFigure;
  const field = props.field ? String(props.field) : "value";
  const text = figureText(props);
  const receipt = figureReceipt(fig);
  const { verdict, mde } = props.verdict && isComparisonFigureKey(props.k) ? figureVerdict(props.k) : { verdict: null, mde: null };
  const status = fig.kind === "comparison" ? "edge_claimed:false" : "descriptive_only";
  return (
    <span className={["ev-figure", props.className ?? ""].filter(Boolean).join(" ")} data-figure-key={fig.key} data-figure-field={field}>
      <span className="ev-figure__value" title={`${fig.key}.${field}`}>{text}</span>
      {verdict ? <VerdictLabel verdict={verdict} mde={mde} /> : null}
      {props.asOf === false ? null : <AsOfBadge asOf={fig.as_of} />}
      {props.receipt === false ? null : (
        <ReceiptChip compact source={receipt.source} note={receipt.note} asOf={fig.as_of} status={status} />
      )}
    </span>
  );
}

export default FigureValue;
