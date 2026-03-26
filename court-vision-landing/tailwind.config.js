/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0D0D12',
        surface: '#12121A',
        surfaceHover: '#1A1A24',
        primary: '#F0EFF4',
        accent: '#00E4FF',
        accentGlow: 'rgba(0, 228, 255, 0.15)',
        muted: '#5A5A66'
      },
      fontFamily: {
        sans: ['Space Grotesk', 'sans-serif'],
        drama: ['DM Serif Display', 'serif'],
        mono: ['Space Mono', 'monospace'],
        data: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
