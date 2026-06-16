/** Small pill badge for source provenance and status labels. Uses cva for variant-driven styling. */
import { cva, type VariantProps } from "class-variance-authority";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-wide whitespace-nowrap",
  {
    variants: {
      variant: {
        model:   "bg-model/15 text-model border border-model/40",
        market:  "bg-market/15 text-market border border-market/40",
        live:    "bg-live/15 text-live border border-live/40",
        neutral: "bg-surface2 text-txt border border-line",
        muted:   "bg-surface2 text-muted border border-line",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

interface BadgeProps extends VariantProps<typeof badgeVariants> {
  children: ReactNode;
  className?: string;
  title?: string;
  "aria-label"?: string;
}

export function Badge({
  variant,
  children,
  className,
  title,
  "aria-label": ariaLabel,
}: BadgeProps) {
  return (
    <span
      className={cn(badgeVariants({ variant }), className)}
      title={title}
      aria-label={ariaLabel}
    >
      {children}
    </span>
  );
}
