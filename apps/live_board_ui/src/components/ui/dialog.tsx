/**
 * Accessible Dialog wrapper over @radix-ui/react-dialog.
 * Radix handles focus trap, Escape key, and aria roles automatically.
 */
import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = RadixDialog.Root;
export const DialogTrigger = RadixDialog.Trigger;
export const DialogClose = RadixDialog.Close;

interface DialogContentProps {
  children: React.ReactNode;
  title: string;
  description?: string;
  className?: string;
}

export function DialogContent({
  children,
  title,
  description,
  className,
}: DialogContentProps) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 animate-fade-in" />
      <RadixDialog.Content
        className={cn(
          "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50",
          "w-[92vw] max-w-md max-h-[85vh] overflow-auto",
          "rounded-xl border border-line bg-surface p-5 shadow-xl animate-fade-in focus:outline-none",
          className
        )}
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <RadixDialog.Title className="text-base font-semibold text-txt">
            {title}
          </RadixDialog.Title>
          <RadixDialog.Close
            aria-label="Close"
            className="rounded-md p-1 text-muted hover:bg-surface2 hover:text-txt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X size={16} />
          </RadixDialog.Close>
        </div>

        {description ? (
          <RadixDialog.Description className="text-xs text-muted mb-4">
            {description}
          </RadixDialog.Description>
        ) : (
          <RadixDialog.Description className="sr-only">
            {title}
          </RadixDialog.Description>
        )}

        {children}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  );
}
