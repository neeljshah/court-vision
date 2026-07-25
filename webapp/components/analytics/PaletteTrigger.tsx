"use client";
// Tiny nav-chrome button that opens the global CommandPalette. Kept separate
// from CommandPalette.tsx so the server layout only needs one small client
// island in the nav row; talks to the palette via a CustomEvent (no shared
// store needed for a single button -> single listener pair).
export function PaletteTrigger() {
  return (
    <button
      type="button"
      className="a-theme"
      aria-label="Search (Cmd K)"
      onClick={() => window.dispatchEvent(new CustomEvent("cv-open-palette"))}
      style={{ fontSize: 13, gap: 6, display: "inline-flex", alignItems: "center", width: "auto", padding: "0 12px" }}
    >
      Search <span className="mono" style={{ color: "var(--ink-3)" }}>/</span>
    </button>
  );
}

export default PaletteTrigger;
