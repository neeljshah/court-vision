// Shared inline styles for the Ask Scout envelopes (AskBox, AskAnswerEnvelope,
// AskNoMatch). Kept in one place so the answer and no-answer states match.
import type { CSSProperties } from "react";

export const pill: CSSProperties = {
  fontSize: 13, color: "var(--accent)", border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-pill, 999px)", display: "inline-flex", alignItems: "center",
  minHeight: 44, padding: "6px 14px", background: "var(--paper-raised)", cursor: "pointer",
  fontFamily: "var(--font-sans)", textAlign: "left", lineHeight: 1.35,
};
export const answerStyle: CSSProperties = { fontSize: 15.5, color: "var(--ink-2)", lineHeight: 1.6 };
export const questionStyle: CSSProperties = { fontSize: 13, color: "var(--ink-3)", marginBottom: 6 };
export const chipRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 10 };
export const chipLink: CSSProperties = { fontSize: 12, fontWeight: 700, color: "var(--accent)" };
export const strong: CSSProperties = { color: "var(--ink)" };

export function envelope(neutral: boolean): CSSProperties {
  return {
    background: "var(--paper-tint)", borderLeft: `2px solid ${neutral ? "var(--null)" : "var(--accent)"}`,
    borderRadius: "var(--radius-card, 10px)", padding: "20px 22px", display: "flex", gap: 14,
  };
}

export function markerStyle(neutral: boolean): CSSProperties {
  return {
    width: 26, height: 26, borderRadius: "50%", flex: "0 0 auto", opacity: 0.9,
    background: neutral ? "var(--null)" : "var(--signal)",
  };
}

export const PACK_LABELS: Record<string, string> = {
  calibration: "Calibration checkpoints",
  mlb_batters: "MLB batters",
  mlb_pitch: "MLB pitch types",
  nba_players: "NBA players",
  nba_teams: "NBA teams",
  soccer: "Soccer teams",
  tennis: "Tennis players",
};

export function profilePath({ pack, slug }: { pack: string; slug: string }): string {
  return `/analytics/players/${pack}/${slug}`;
}
