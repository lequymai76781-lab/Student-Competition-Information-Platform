import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#181D26",
        muted: "#5F6672",
        quiet: "#8A9099",
        line: "#E5E7EB",
        paper: "#F7F8FA",
        surface: "#FAFAF9",
        accent: "#315EF5",
        mint: "#12805C"
      },
      boxShadow: {
        soft: "0 8px 24px rgba(24, 29, 38, 0.06)",
        lift: "0 14px 34px rgba(24, 29, 38, 0.10)"
      },
      borderRadius: {
        lg: "10px",
        xl: "12px"
      }
    }
  },
  plugins: []
};

export default config;
