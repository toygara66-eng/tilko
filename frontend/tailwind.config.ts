import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        note: ["var(--font-kalam)", "var(--font-caveat)", "cursive"],
        scribble: ["var(--font-caveat)", "cursive"],
      },
      colors: {
        neon: {
          DEFAULT: "#22d3ee",
          dim: "#0891b2",
          glow: "rgba(34, 211, 238, 0.35)",
        },
        gold: "#f5c542",
      },
      boxShadow: {
        neon: "0 0 24px rgba(34, 211, 238, 0.22)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.22s ease-out",
        "accordion-up": "accordion-up 0.22s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
