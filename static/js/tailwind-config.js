// Tailwind (CDN build) settings: colour names map to the CSS variables in /static/css/app.css, so dark mode is one switch.
tailwind.config = {
  darkMode: "class",
  theme: { extend: {
    fontFamily: { sans: ["Geist", "system-ui", "sans-serif"] },
    colors: Object.fromEntries(["canvas", "panel", "line", "ink", "mute", "accent", "onaccent", "danger", "warn"].map((n) => [n, `rgb(var(--${n}) / <alpha-value>)`])),
  } },
};
