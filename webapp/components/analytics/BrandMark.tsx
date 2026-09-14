type BrandMarkProps = { className?: string };

/** Compact CourtVision aperture mark for product chrome. */
export function BrandMark({ className }: BrandMarkProps) {
  return <svg className={className} viewBox="0 0 36 36" fill="none" aria-hidden="true">
    <circle cx="18" cy="18" r="16" fill="#A8ADB0" />
    <circle cx="18" cy="18" r="12.7" stroke="#EEF0EF" strokeWidth="1.1" opacity=".9" />
    <path d="M7 20.5C10 12.5 15.7 8.5 23.5 9.4C27.1 9.8 29.4 11.4 31 13.1" stroke="#666D70" strokeWidth="1.2" strokeLinecap="round" />
    <path d="M8.4 24.2C12.2 26.6 16.2 27.7 20.2 27.1C25.2 26.4 28.2 23.4 29.8 20.6" stroke="#D9DDDC" strokeWidth="1.1" strokeLinecap="round" />
    <circle cx="18" cy="18" r="6.2" fill="#11191B" />
    <circle cx="18" cy="18" r="3.4" fill="#E86E21" />
    <path d="M10 25.5L15.4 20.1L19 21.2L26.8 12.7" stroke="#F08A42" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
