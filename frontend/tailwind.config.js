/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: '#0B1D33', 900: '#0B1D33', 800: '#0F2540', 700: '#17395C', 600: '#1F4B77' },
        ink: '#0F2540',
        surface: '#F6F8FB',
        line: '#E3E8F0',
        brand: { DEFAULT: '#2563EB', dark: '#1D4ED8', 50: '#EFF5FF', 100: '#DBE8FE', 200: '#BFD7FE', 400: '#5B95F7', 500: '#2563EB', 600: '#1D4ED8', 700: '#1E40AF' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15,37,64,0.04), 0 1px 3px rgba(15,37,64,0.06)',
        raised: '0 8px 24px rgba(15,37,64,0.10)',
      },
    },
  },
  plugins: [],
}
