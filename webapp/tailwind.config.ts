import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        /* ---------------------------------------------------------------- */
        /* shadcn/ui structural tokens -- all driven by CSS variables        */
        /* ---------------------------------------------------------------- */
        border:      "hsl(var(--border))",
        input:       "hsl(var(--input))",
        ring:        "hsl(var(--ring))",
        background:  "hsl(var(--background))",
        foreground:  "hsl(var(--foreground))",

        primary: {
          DEFAULT:    "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:    "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT:    "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT:    "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:    "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT:    "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT:    "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },

        /* ---------------------------------------------------------------- */
        /* Semantic status tokens                                            */
        /* ---------------------------------------------------------------- */
        success: {
          DEFAULT:    "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT:    "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        danger: {
          DEFAULT:    "hsl(var(--danger))",
          foreground: "hsl(var(--danger-foreground))",
        },
        info: {
          DEFAULT:    "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },

        /* ---------------------------------------------------------------- */
        /* Tier tokens (S=gold, A=green, B=slate-mid, C=slate-dark)         */
        /* CSS-var-driven so they can be overridden in future themes.        */
        /* ---------------------------------------------------------------- */
        tier: {
          s: "hsl(var(--tier-s))",
          a: "hsl(var(--tier-a))",
          b: "hsl(var(--tier-b))",
          c: "hsl(var(--tier-c))",
        },

        /* ---------------------------------------------------------------- */
        /* Surface elevation steps (bg-surface-{0..3} classes)              */
        /* ---------------------------------------------------------------- */
        surface: {
          0: "hsl(var(--surface-0))",
          1: "hsl(var(--surface-1))",
          2: "hsl(var(--surface-2))",
          3: "hsl(var(--surface-3))",
        },

        /* ---------------------------------------------------------------- */
        /* Legacy aliases -- preserved for backward compat with existing     */
        /* components that reference bg.base / bg.panel / bg.subtle.         */
        /* ---------------------------------------------------------------- */
        bg: {
          base:   "hsl(var(--surface-0))",
          panel:  "hsl(var(--surface-1))",
          subtle: "hsl(var(--surface-2))",
        },
      },

      borderRadius: {
        lg:  "var(--radius)",
        md:  "calc(var(--radius) - 2px)",
        sm:  "calc(var(--radius) - 4px)",
        xl:  "calc(var(--radius) + 4px)",
        "2xl": "calc(var(--radius) + 8px)",
      },

      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },

      fontSize: {
        /* Minimum legible scale for data-dense dark dashboard */
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }], /* 10px -- reserve for non-essential meta only */
        xs:    ["0.75rem",  { lineHeight: "1rem"    }],  /* 12px -- caption / muted labels */
        sm:    ["0.875rem", { lineHeight: "1.25rem" }],  /* 14px -- body / table cells */
        base:  ["1rem",     { lineHeight: "1.5rem"  }],  /* 16px -- normal prose */
        lg:    ["1.125rem", { lineHeight: "1.75rem" }],  /* 18px */
        xl:    ["1.25rem",  { lineHeight: "1.75rem" }],  /* 20px */
        "2xl": ["1.5rem",   { lineHeight: "2rem"    }],  /* 24px */
      },

      spacing: {
        /* 4px grid -- Tailwind default covers this; explicit aliases for clarity */
        "0.5": "0.125rem",  /*  2px */
        "1":   "0.25rem",   /*  4px */
        "2":   "0.5rem",    /*  8px */
        "3":   "0.75rem",   /* 12px */
        "4":   "1rem",      /* 16px */
        "5":   "1.25rem",   /* 20px */
        "6":   "1.5rem",    /* 24px */
      },

      boxShadow: {
        /* Subtle elevation for dark cards -- separates surface from bg */
        "card":   "0 1px 3px 0 hsl(240 10% 2% / 0.6), 0 1px 2px -1px hsl(240 10% 2% / 0.4)",
        "card-md":"0 4px 6px -1px hsl(240 10% 2% / 0.7), 0 2px 4px -2px hsl(240 10% 2% / 0.5)",
        "ring":   "0 0 0 2px hsl(var(--ring))",
      },

      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to:   { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to:   { height: "0" },
        },
        /* Shimmer is defined in globals.css @keyframes skeleton-shimmer */
      },

      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up":   "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
