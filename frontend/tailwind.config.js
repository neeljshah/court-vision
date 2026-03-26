/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          orange: '#f97316',
          blue: '#3b82f6',
          green: '#22c55e',
          red: '#ef4444',
        },
        surface: {
          900: '#0f1117',
          800: '#1a1d24',
          700: '#252932',
          600: '#2f3340',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
