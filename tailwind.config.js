// Tailwind settings. Colour names map to the CSS variables in static/css/app.css, so dark mode is one switch.
// Rebuild the stylesheet after changing classes or these settings:  npm run build:css
module.exports = {
  content: ["./static/*.html", "./static/js/**/*.js"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["Geist", "system-ui", "sans-serif"] },
      colors: Object.fromEntries(
        ["canvas", "panel", "line", "ink", "mute", "accent", "onaccent", "danger", "warn"].map((n) => [n, `rgb(var(--${n}) / <alpha-value>)`])
      ),
    },
  },
  plugins: [],
};
