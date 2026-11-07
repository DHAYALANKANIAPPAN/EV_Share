// Applies the saved (or system) light/dark theme before the page paints. Kept out of the HTML for the Content-Security-Policy.
try{if(localStorage.getItem("ev_theme")==="dark"||(!localStorage.getItem("ev_theme")&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch{}
