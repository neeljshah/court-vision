// PaperOnlyBanner.tsx -- the one upper-case PAPER ONLY banner every paper surface shows:
// /paper-trading (the record) and each /paper/<fill>/ detail page. Server-safe (no hooks,
// no node:fs), so a server page and a client page can both mount it. ASCII only.

export function PaperOnlyBanner() {
  return (
    <div
      role="alert"
      data-testid="real-money-deny-banner"
      aria-label="Real money is DENIED -- paper mode only"
      className="mb-5 rounded-lg border border-warning/50 bg-warning/10 px-4 py-2.5 text-[12px] text-warning"
    >
      <span className="font-semibold">Real-money: DENY.</span>{" "}
      PAPER ONLY (paper mode). No real money placed. No order path exists. Calibration record only.
    </div>
  );
}

export default PaperOnlyBanner;
