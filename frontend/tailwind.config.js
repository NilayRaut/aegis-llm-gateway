/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        heading: ['Syne', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        canvas: '#F8F7F4',
        surface: '#FFFFFF',
        muted: '#F1EFE9',
        border: '#E5E2DC',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
