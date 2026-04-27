
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        dark: {
          950: "#06060a",
          900: "#0a0a12",
          850: "#0d0d1a",
          800: "#111122",
          700: "#1a1a2e",
          600: "#252540",
          500: "#33335a",
        },
        accent: {
          purple: "#7c6ee0",
          blue: "#4fc3f7",
          violet: "#8b5cf6",
          gold: "#f6c445",
          cyan: "#22d3ee",
        },
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 2s ease-in-out infinite",
        "fade-in": "fadeIn 0.3s ease-out",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
