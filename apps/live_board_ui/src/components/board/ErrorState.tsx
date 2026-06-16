/** Centered error state with retry action for the live board. */
import { AlertTriangle } from "lucide-react"

interface ErrorStateProps {
  message: string
  onRetry: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-4 py-20 px-4 text-center"
    >
      <AlertTriangle className="text-live" size={36} aria-hidden="true" />
      <h2 className="text-base font-semibold text-txt">Could not load the board</h2>
      <p className="text-sm text-muted max-w-xs">{message}</p>
      <button
        onClick={onRetry}
        className="border border-line rounded-md px-3 py-1.5 text-sm text-txt hover:bg-surface2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        Retry
      </button>
    </div>
  )
}
