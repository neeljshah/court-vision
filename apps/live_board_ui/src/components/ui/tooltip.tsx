/** InfoTooltip: accessible radix-ui tooltip wrapper with design-token styling. */
import * as Tooltip from "@radix-ui/react-tooltip";
import React from "react";

interface InfoTooltipProps {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}

export function InfoTooltip({ label, children, side = "top" }: InfoTooltipProps) {
  return (
    <Tooltip.Provider delayDuration={150}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side={side}
            sideOffset={6}
            className="rounded-md bg-surface2 text-txt border border-line px-2.5 py-1.5 text-xs shadow-lg max-w-[240px] z-50 animate-fade-in"
          >
            {label}
            <Tooltip.Arrow className="fill-surface2" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
