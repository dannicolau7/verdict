import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Verdict design tokens
        ink:     '#1A1A2E',
        slate:   '#64748B',
        cloud:   '#F8FAFC',
        line:    '#E2E8F0',
        brand:   '#6366F1',
        pass:    '#10B981',
        fail:    '#EF4444',
        caution: '#F59E0B',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        'spin-slow': { to: { transform: 'rotate(360deg)' } },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'spin-slow': 'spin-slow 1.4s linear infinite',
        'fade-up':   'fade-up 0.25s ease-out both',
      },
    },
  },
  plugins: [],
} satisfies Config
