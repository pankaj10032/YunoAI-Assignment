/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--color-text)",
        muted: "var(--color-muted)",
        line: "var(--color-border)",
        surface: "var(--color-surface)",
        canvas: "var(--color-bg)",
      },
    },
  },
  plugins: [],
};
