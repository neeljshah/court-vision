/** Thin styled wrappers over @radix-ui/react-tabs primitives with forwardRef. */
import * as React from "react"
import * as RadixTabs from "@radix-ui/react-tabs"
import { cn } from "@/lib/utils"

const Tabs = RadixTabs.Root

const TabsList = React.forwardRef<
  React.ElementRef<typeof RadixTabs.List>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.List>
>(({ className, ...props }, ref) => (
  <RadixTabs.List
    ref={ref}
    className={cn(
      "inline-flex gap-1 rounded-lg bg-surface2 p-1",
      className
    )}
    {...props}
  />
))
TabsList.displayName = "TabsList"

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof RadixTabs.Trigger>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.Trigger>
>(({ className, ...props }, ref) => (
  <RadixTabs.Trigger
    ref={ref}
    className={cn(
      "rounded-md px-4 py-1.5 text-sm font-semibold text-muted transition",
      "data-[state=active]:bg-accent data-[state=active]:text-bg data-[state=active]:shadow",
      "hover:text-txt focus-visible:outline-none",
      className
    )}
    {...props}
  />
))
TabsTrigger.displayName = "TabsTrigger"

const TabsContent = React.forwardRef<
  React.ElementRef<typeof RadixTabs.Content>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.Content>
>(({ className, ...props }, ref) => (
  <RadixTabs.Content
    ref={ref}
    className={cn("focus-visible:outline-none", className)}
    {...props}
  />
))
TabsContent.displayName = "TabsContent"

export { Tabs, TabsList, TabsTrigger, TabsContent }
