/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html"],
  theme: {
    extend: {
      colors: {
        ink: "#14161A",
        bone: "#FAFAF7",
        primary: { DEFAULT: "#4F46E5", dark: "#3D34C4" },
        darkbg: "#15123A",
        darksurface: "#1D1A48",
        darkborder: "#2C2966",
        muted: "#6B7280",
        surfacegray: "#F7F7FB",
        bordergray: "#E5E7EB",
        success: "#2E9E6B",
        danger: "#D64545",
        warning: "#C98A2C",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        hud: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        count: ["'Bitcount Prop Single'", "ui-monospace", "monospace"],
        min: ["Abel", "sans-serif"],
        mod : [ "Exo", "sans-serif"],
        Tech : ["Sixtyfour", "sans-serif"]
      },
      boxShadow: {
        hard: "4px 4px 0 0 #14161A",
        "hard-sm": "2px 2px 0 0 #14161A",
      },
    },
  },
  plugins: [],
};