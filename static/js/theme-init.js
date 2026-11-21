// Applies the theme before the page paints. Deep sage (dark) is the default; a visitor can switch to warm ivory (light).
// Kept out of the HTML for the Content-Security-Policy.
try { if (localStorage.getItem("ev_theme") !== "light") document.documentElement.classList.add("dark"); } catch { document.documentElement.classList.add("dark"); }
