/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Trading-specific colors
        profit: {
          light: '#dcfce7',
          DEFAULT: '#22c55e',
          dark: '#15803d',
        },
        loss: {
          light: '#fee2e2',
          DEFAULT: '#ef4444',
          dark: '#b91c1c',
        },
        // Risk levels
        risk: {
          low: '#22c55e',
          medium: '#f59e0b',
          high: '#ef4444',
          critical: '#991b1b',
        },
        // Dashboard theme
        dashboard: {
          bg: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          text: '#f8fafc',
          muted: '#94a3b8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'flash-green': 'flash-green 0.5s ease-in-out',
        'flash-red': 'flash-red 0.5s ease-in-out',
        'pulse-border': 'pulse-border 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        'flash-green': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgba(34, 197, 94, 0.2)' },
        },
        'flash-red': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgba(239, 68, 68, 0.2)' },
        },
        'pulse-border': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.4)' },
          '50%': { boxShadow: '0 0 12px 4px rgba(239, 68, 68, 0.3)' },
        },
      },
    },
  },
  plugins: [],
};
