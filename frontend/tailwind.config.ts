// Tailwind v4: theme is configured via @theme in globals.css
// This file is kept for any v4-specific plugin configuration if needed in the future.
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
}
export default config
