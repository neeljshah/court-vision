# Direction A "Amber Console" -- binding design spec for every webapp page

The user picked this direction (2026-07-15). Reference mockup: amber terminal
on cool near-black. Tokens are LIVE in `app/globals.css`; primitives in
`components/ui/terminal.tsx` (Panel, PanelHead, AsOf, TrustPill, Num, Delta, Dot).

## Rules (apply to every page/component)

1. ONE container: `<Panel>` (flat, 1px border, bg-card, square corners).
   No Card-with-shadow, no rounded-lg, no gradients, no glow.
2. Every panel gets `<PanelHead title asOf stale>` -- microlabel uppercase
   title + "as of HH:MM:SS" stamp. Stale data turns the stamp amber via
   `stale`, NEVER silently green. If a feed timestamp is available, wire it;
   if not, pass the fetch time.
3. Numbers: ALWAYS `font-data` (mono) + `tabular`, right-aligned in tables
   (`<Num>`). Probabilities as .XXX (3 dp) or XX.X%; be consistent per table.
4. Color = meaning ONLY:
   - text-up / text-down for direction (green/red)
   - text-stale (amber) for freshness violations
   - bg-s-model (amber #C9821A) vs bg-s-market (blue #3E9BE0) for
     model-vs-market series in bars/charts -- never decorative color.
   - Accent amber (--primary) only for: active nav, focus ring, key CTAs.
5. Trust tiers use `<TrustPill tier>` (PROVEN / SHADOW / WATCH).
6. Tables: dense (py-1.5 px-3), microlabel column headers, row hover
   bg-surface-2, borders border-border only. Wide tables scroll inside
   their own overflow-x-auto wrapper.
7. Recharts: series colors via hsl(var(--s-model)) / hsl(var(--s-market)),
   grid hsl(var(--border)), 2px lines, no area gradients, emphasized
   endpoint dot where a sparkline has a "now" value.
8. Copy: "calibrated forecast", units only (NEVER $), no ROI/edge claims,
   honest "unavailable" states (never fabricate). ASCII only in source.
9. Keep data-fetch logic untouched unless broken; this is a reskin, not a
   rewrite. <=300 LOC per file.
