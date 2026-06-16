/** Controlled tab strip for selecting the active sport (MLB / Soccer / Tennis). */
import type { Sport } from "@/types/board"
import { SPORTS } from "@/types/board"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface SportTabsProps {
  sport: Sport
  onChange: (s: Sport) => void
}

export function SportTabs({ sport, onChange }: SportTabsProps) {
  return (
    <Tabs
      value={sport}
      onValueChange={(v) => onChange(v as Sport)}
    >
      <TabsList aria-label="Sport">
        {SPORTS.map(({ value, label }) => (
          <TabsTrigger key={value} value={value}>
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
