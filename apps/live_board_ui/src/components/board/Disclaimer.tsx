/** Honesty disclaimer: shown as a subtle banner or a fixed footer bar. */
import { Info } from "lucide-react"
import { cn } from "@/lib/utils"

interface DisclaimerProps {
  variant?: "banner" | "footer"
}

export function Disclaimer({ variant = "footer" }: DisclaimerProps) {
  const copy =
    'Decision support, not a money machine. Model where in-corpus, market-implied otherwise. No $ edge claimed.'

  if (variant === "banner") {
    return (
      <div
        role="note"
        aria-label="Disclaimer"
        className={cn(
          "flex items-center gap-2 rounded-md border border-line bg-surface2/60 px-3 py-2 text-[11px] text-muted"
        )}
      >
        <Info size={13} className="shrink-0 text-muted" aria-hidden="true" />
        <span>{copy}</span>
      </div>
    )
  }

  return (
    <footer
      role="contentinfo"
      aria-label="Disclaimer"
      className={cn(
        "fixed bottom-0 inset-x-0 bg-bg/90 backdrop-blur border-t border-line py-2 text-center text-[11px] text-muted z-20"
      )}
    >
      {copy}
    </footer>
  )
}
