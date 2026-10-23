import { api } from "./api.js";
import { $, h, icon, refreshIcons, money, fmtRange, utc, toast, setTheme, isDark, confirmDialog } from "./ui.js";

const S = { user: null, view: "find", chargers: [], bookings: [], mine: [], loading: true, f: { connector: "", power: "", price: "" }, on: null, target: null };
const CONNECTORS = ["TYPE2", "CCS2", "CHADEMO", "BHARAT_AC001", "BHARAT_DC001", "GBT"];
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
const filtered = () => S.f.connector || S.f.power || S.f.price;
const windowText = (c) => (c.available_from && c.available_to ? `Open ${c.available_from.slice(0, 5)} to ${c.available_to.slice(0, 5)}` : "Open 24/7");

/* ---------- chrome ---------- */
function renderChrome() {
  const nav = $("#nav"), user = $("#user");
  const tab = (id, label) => h("button", { className: "btn border-transparent " + (S.view === id ? "text-accent" : "text-mute"), textContent: label, onclick: () => go(id), "aria-current": S.view === id ? "page" : null });
  nav.replaceChildren(tab("find", "Find chargers"), tab("bookings", "My bookings"), tab("chargers", "My chargers"), tab("share", "Share a charger"));
  const themeBtn = h("button", { className: "ibtn", dataset: { tip: isDark() ? "Switch to light mode" : "Switch to dark mode" }, "aria-label": isDark() ? "Switch to light mode" : "Switch to dark mode", onclick: () => { setTheme(!isDark()); renderChrome(); } }, icon(isDark() ? "sun" : "moon", "size-5"));
  user.replaceChildren(themeBtn, S.user
    ? h("span", { className: "text-sm text-mute hidden sm:inline mr-1", textContent: S.user.name })
    : null, S.user
    ? h("button", { className: "btn", textContent: "Sign out", onclick: () => { api.signOut(); S.user = null; S.bookings = []; S.mine = []; go("find"); toast("Signed out"); } })
    : h("button", { className: "btn btn-primary", textContent: "Sign in", onclick: openAuth }));
  refreshIcons();
}
async function go(view) {
  if (view !== "find" && !S.user) return openAuth();
  S.view = view; renderChrome(); render();
  if (view === "bookings") await guard(loadBookings)();
  if (view === "chargers") await guard(loadMine)();
}

/* ---------- find: list + map ---------- */
async function loadChargers() {
  S.loading = true; render();
  try { S.chargers = await api.chargers(S.f); } finally { S.loading = false; render(); }
}
function filterBar() {
  const sel = h("select", { id: "f-conn", onchange: (e) => { S.f.connector = e.target.value; guard(loadChargers)(); } }, h("option", { value: "", textContent: "Any" }), CONNECTORS.map((c) => h("option", { value: c, textContent: c.replace("_", " "), selected: S.f.connector === c })));
  const num = (id, key, min) => h("input", { id, type: "number", min, step: "any", value: S.f[key], placeholder: "No limit", onchange: (e) => { S.f[key] = e.target.value; guard(loadChargers)(); } });
  const lab = (id, text, el) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: text }), el);
  return h("div", { className: "panel p-4 grid gap-4 sm:grid-cols-[1fr_1fr_1fr_auto] items-end" },
    lab("f-conn", "Connector", sel), lab("f-power", "Minimum power (kW)", num("f-power", "power", 1)), lab("f-price", "Maximum price (₹/kWh)", num("f-price", "price", 0)),
    h("button", { className: "btn", textContent: "Clear all filters", disabled: !filtered(), onclick: () => { S.f = { connector: "", power: "", price: "" }; guard(loadChargers)(); } }));
}
function chargerRow(c) {
  const meta = h("p", { className: "text-sm text-mute flex flex-wrap gap-x-4 gap-y-1" }, h("span", { textContent: c.connector_type.replace("_", " ") }), h("span", { textContent: `${c.power_kw} kW` }), h("span", { textContent: `${money(c.price_per_kwh)}/kWh` }), h("span", { textContent: windowText(c) }));
  const rating = c.avg_rating == null ? "No reviews yet" : `${c.avg_rating.toFixed(1)} (${c.review_count})`;
  return h("li", { className: "row", dataset: { on: String(S.on === c.id), id: c.id }, onmouseenter: () => hl(c.id), onmouseleave: () => hl(null) },
    h("div", { className: "grid gap-1 min-w-0" }, h("h3", { className: "font-medium truncate", textContent: c.title }), h("p", { className: "text-sm text-mute truncate", textContent: c.address }), meta,
      h("p", { className: "text-sm flex items-center gap-1 text-mute" }, icon("star", "size-4"), h("span", { textContent: rating }))),
    h("div", { className: "flex gap-2 items-center flex-wrap self-center" }, c.review_count ? h("button", { className: "btn", textContent: "Read reviews", onclick: guard(() => openReviews(c)) }) : null,
      h("button", { className: "btn btn-primary", onclick: () => openDrawer(c) }, icon("calendar-plus", "size-4"), "Reserve")));
}
function hl(id) {
  S.on = id;
  document.querySelectorAll("[data-id]").forEach((n) => (n.dataset.on = String(Number(n.dataset.id) === id)));
  document.querySelectorAll(".pin,.evpin").forEach((n) => (n.dataset.on = String(Number(n.dataset.id) === id)));
}
const tiles = () => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" });
const pinIcon = (id, on) => L.divIcon({ className: "", html: `<div class="evpin" data-id="${id ?? ""}" data-on="${!!on}"></div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
function mapPanel() { return window.L ? streetMap() : svgMap(); }
function streetMap() {
  const box = h("div", { className: "panel overflow-hidden isolate lg:sticky lg:top-24 h-[320px] lg:h-[calc(100vh-8rem)]", role: "region", "aria-label": "Map of chargers" });
  requestAnimationFrame(() => {
    if (!box.isConnected) return;
    const map = L.map(box); tiles().addTo(map); const pts = [];
    S.chargers.forEach((c) => {
      L.marker([c.latitude, c.longitude], { title: c.title, icon: pinIcon(c.id) }).addTo(map)
        .on("click", () => { hl(c.id); document.querySelector(`li[data-id="${c.id}"]`)?.scrollIntoView({ block: "nearest" }); });
      pts.push([c.latitude, c.longitude]);
    });
    pts.length === 1 ? map.setView(pts[0], 14) : map.fitBounds(pts, { padding: [32, 32], maxZoom: 14 });
  });
  return box;
}
function svgMap() {
  const cs = S.chargers, W = 100;
  const la = cs.map((c) => c.latitude), lo = cs.map((c) => c.longitude);
  const [a0, a1, o0, o1] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
  const x = (c) => 10 + ((c.longitude - o0) / (o1 - o0 || 1)) * 80, y = (c) => 90 - ((c.latitude - a0) / (a1 - a0 || 1)) * 80;
  const grid = [20, 40, 60, 80].map((v) => `<path d="M${v} 0V100M0 ${v}H100" stroke="rgb(var(--line))" stroke-width=".3"/>`).join("");
  const pins = cs.map((c) => `<g class="pin" data-id="${c.id}" tabindex="0" role="button" aria-label="Show ${String(c.id)}"><circle cx="${x(c).toFixed(1)}" cy="${y(c).toFixed(1)}" r="3.2" fill="rgb(var(--accent))" stroke="rgb(var(--panel))" stroke-width=".8"/></g>`).join("");
  const box = h("div", { className: "panel overflow-hidden lg:sticky lg:top-24 h-[320px] lg:h-[calc(100vh-8rem)]" });
  box.innerHTML = `<svg viewBox="0 0 ${W} ${W}" class="w-full h-full" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Relative positions of the chargers listed">${grid}${pins}</svg>`;
  box.querySelectorAll(".pin").forEach((g) => {
    const c = cs.find((k) => k.id === Number(g.dataset.id)); g.setAttribute("aria-label", c.title);
    g.onmouseenter = () => hl(c.id); g.onmouseleave = () => hl(null);
    const pick = () => { hl(c.id); document.querySelector(`li[data-id="${c.id}"]`)?.scrollIntoView({ block: "nearest" }); };
    g.onclick = pick; g.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), pick());
  });
  return box;
}
function skeleton() { return h("ul", { className: "panel overflow-hidden", "aria-busy": "true" }, [1, 2, 3, 4].map(() => h("li", { className: "row" }, h("div", { className: "grid gap-2" }, h("div", { className: "sk h-4 w-1/2" }), h("div", { className: "sk h-3 w-2/3" }), h("div", { className: "sk h-3 w-1/3" })), h("div", { className: "sk h-11 w-28" })))); }
function emptyFind() {
  return h("section", { className: "panel p-8 grid gap-2 justify-items-start", "aria-labelledby": "e1" }, icon("plug-zap", "size-6 text-mute"),
    h("h2", { id: "e1", className: "font-semibold text-lg", textContent: filtered() ? "No chargers match your filters" : "No chargers listed yet" }),
    h("p", { className: "text-sm text-mute", textContent: filtered() ? "Try a lower power or a higher price limit, or reset the filters." : "Chargers shared by hosts show up here as soon as they're listed." }),
    filtered() ? h("button", { className: "btn mt-2", textContent: "Clear all filters", onclick: () => { S.f = { connector: "", power: "", price: "" }; guard(loadChargers)(); } }) : null);
}
function findView() {
  const list = S.loading ? skeleton() : S.chargers.length ? h("ul", { className: "panel overflow-hidden" }, S.chargers.map(chargerRow)) : emptyFind();
  return h("div", { className: "grid gap-6" },
    h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Find a charger" }), h("p", { className: "text-mute mt-1 max-w-[65ch]", textContent: "Reserve a slot at a home or workplace charger near you, and pay when you book." })),
    filterBar(), h("div", { className: "grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]" }, list, S.chargers.length && !S.loading ? mapPanel() : null));
}

/* ---------- bookings ---------- */
async function loadBookings() { S.loading = true; render(); try { S.bookings = await api.bookings(); } finally { S.loading = false; render(); } }
function bookingsView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "My bookings" }), h("p", { className: "text-mute mt-1", textContent: "Slots you've reserved, newest first." }));
  if (S.loading) return h("div", { className: "grid gap-6" }, head, skeleton());
  if (!S.bookings.length) return h("div", { className: "grid gap-6" }, head, h("section", { className: "panel p-8 grid gap-2 justify-items-start" }, icon("calendar-x", "size-6 text-mute"),
    h("h2", { className: "font-semibold text-lg", textContent: "No bookings yet" }), h("p", { className: "text-sm text-mute", textContent: "Reserve a charger to see your upcoming and past sessions here." }), h("button", { className: "btn btn-primary mt-2", textContent: "Find chargers", onclick: () => go("find") })));
  const now = new Date();
  return h("div", { className: "grid gap-6" }, head, h("ul", { className: "panel overflow-hidden" }, S.bookings.map((b) => {
    const cancelled = b.status === "CANCELLED", live = !cancelled && utc(b.end_time) > now, unpaid = !cancelled && b.payment_status !== "PAID";
    return h("li", { className: "row" }, h("div", { className: "grid gap-1" }, h("h3", { className: "font-medium", textContent: b.charger_title }),
      h("p", { className: "text-sm text-mute", textContent: `${fmtRange(b.start_time, b.end_time)}, ${money(b.estimated_cost)}` }),
      h("p", { className: "text-sm flex items-center gap-1 " + (cancelled ? "text-danger" : unpaid ? "text-mute" : "text-accent") }, icon(cancelled ? "x-circle" : unpaid ? "clock" : "check-circle-2", "size-4"), h("span", { textContent: cancelled ? "Cancelled" : unpaid ? "Awaiting payment" : "Paid and confirmed" }))),
      h("div", { className: "flex gap-2 items-center flex-wrap" }, !cancelled && !live && !b.reviewed ? h("button", { className: "btn", textContent: "Leave a review", onclick: () => openReviewForm(b) }) : null,
        unpaid ? h("button", { className: "btn btn-primary", textContent: "Pay now", onclick: guard(async () => { await api.pay(b.id); toast("Payment complete"); await loadBookings(); }) }) : null,
        live ? h("button", { className: "btn btn-danger", textContent: "Cancel booking", onclick: guard(async () => {
          if (!(await confirmDialog({ title: `Cancel booking at '${b.charger_title}'?`, body: "A paid booking is refunded in full. This frees the slot for other drivers.", confirm: "Cancel booking", keep: "Keep booking" }))) return;
          await api.cancel(b.id); toast("Booking cancelled"); await loadBookings(); }) }) : null));
  })));
}

/* ---------- reviews ---------- */
const stars = (n) => "★".repeat(n) + "☆".repeat(5 - n);
function info(title, ...body) {
  const d = $("#dlg"), opener = document.activeElement, close = h("button", { className: "btn", type: "button", textContent: "Close", onclick: () => d.close() });
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("h2", { className: "font-semibold text-lg mb-4", textContent: title }), ...body, h("div", { className: "flex justify-end mt-6" }, close)); d.showModal(); close.focus();
}
async function openReviews(c) {
  const list = await api.reviews(c.id);
  info(`Reviews for '${c.title}'`, h("ul", { className: "panel overflow-hidden max-h-[50vh] overflow-y-auto" }, list.map((r) => h("li", { className: "row", style: "grid-template-columns:1fr" },
    h("p", { className: "text-sm flex justify-between gap-2" }, h("span", { className: "font-medium", textContent: r.user_name }), h("span", { className: "text-accent", textContent: stars(r.rating), "aria-label": `${r.rating} out of 5` })),
    r.comment ? h("p", { className: "text-sm", textContent: r.comment }) : null))));
}
function openReviewForm(b) {
  const d = $("#dlg"), opener = document.activeElement;
  const rate = h("select", { id: "rv-rate" }, [5, 4, 3, 2, 1].map((n) => h("option", { value: n, textContent: `${n} of 5` })));
  const note = h("textarea", { id: "rv-note", maxLength: 1000 });
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => { e.preventDefault(); await api.review(b.id, +rate.value, note.value); d.close(); toast("Review posted"); await loadBookings(); }) },
    h("h2", { className: "font-semibold text-lg", textContent: `Review '${b.charger_title}'` }),
    h("div", { className: "field" }, h("label", { htmlFor: "rv-rate", textContent: "Rating" }), rate), h("div", { className: "field" }, h("label", { htmlFor: "rv-note", textContent: "Comment (optional)" }), note),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Discard", onclick: () => d.close() }), h("button", { className: "btn btn-primary", type: "submit", textContent: "Post review" }))));
  d.showModal(); rate.focus();
}

/* ---------- owner: my chargers ---------- */
async function loadMine() { S.loading = true; render(); try { S.mine = await api.myChargers(); } finally { S.loading = false; render(); } }
function mineView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "My chargers" }), h("p", { className: "text-mute mt-1", textContent: "Pause a listing to stop new bookings, or see who has reserved it." }));
  if (S.loading) return h("div", { className: "grid gap-6" }, head, skeleton());
  if (!S.mine.length) return h("div", { className: "grid gap-6" }, head, h("section", { className: "panel p-8 grid gap-2 justify-items-start" }, icon("plug", "size-6 text-mute"),
    h("h2", { className: "font-semibold text-lg", textContent: "You haven't shared a charger yet" }), h("p", { className: "text-sm text-mute", textContent: "List your home or workplace charger so nearby drivers can reserve it." }), h("button", { className: "btn btn-primary mt-2", textContent: "Share a charger", onclick: () => go("share") })));
  return h("div", { className: "grid gap-6" }, head, h("ul", { className: "panel overflow-hidden" }, S.mine.map((c) => h("li", { className: "row" },
    h("div", { className: "grid gap-1 min-w-0" }, h("h3", { className: "font-medium truncate", textContent: c.title }), h("p", { className: "text-sm text-mute", textContent: `${c.connector_type.replace("_", " ")}, ${c.power_kw} kW, ${money(c.price_per_kwh)}/kWh. ${windowText(c)}` }),
      h("p", { className: "text-sm flex items-center gap-1 " + (c.is_active ? "text-accent" : "text-mute") }, icon(c.is_active ? "check-circle-2" : "pause-circle", "size-4"), h("span", { textContent: c.is_active ? "Listed" : "Paused" }))),
    h("div", { className: "flex gap-2 items-center flex-wrap" }, h("button", { className: "btn", textContent: "View bookings", onclick: guard(() => openOwnerBookings(c)) }),
      h("button", { className: "btn", textContent: c.is_active ? "Pause listing" : "Resume listing", onclick: guard(async () => { await api.setActive(c.id, !c.is_active); toast(c.is_active ? "Listing paused" : "Listing resumed"); await loadMine(); }) }))))));
}
async function openOwnerBookings(c) {
  const list = await api.chargerBookings(c.id);
  info(`Bookings for '${c.title}'`, list.length ? h("ul", { className: "panel overflow-hidden max-h-[50vh] overflow-y-auto" }, list.map((b) => h("li", { className: "row", style: "grid-template-columns:1fr" },
    h("p", { className: "text-sm font-medium", textContent: fmtRange(b.start_time, b.end_time) }), h("p", { className: "text-sm text-mute", textContent: `${b.status === "CANCELLED" ? "Cancelled" : b.payment_status === "PAID" ? "Paid" : "Awaiting payment"}, ${money(b.estimated_cost)}` }))))
    : h("p", { className: "text-sm text-mute", textContent: "No one has reserved this charger yet." }));
}

/* ---------- owner: share a charger (form page) ---------- */
function shareView() {
  const f = (id, t, el, hint) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el, hint ? h("p", { className: "text-xs text-mute font-normal", textContent: hint }) : null);
  const inp = (id, o = {}) => h("input", { id, required: true, ...o });
  const title = inp("s-title", { maxLength: 120 }), addr = inp("s-addr", { maxLength: 255 }), lat = inp("s-lat", { type: "number", step: "any", min: -90, max: 90 }), lon = inp("s-lon", { type: "number", step: "any", min: -180, max: 180 });
  const conn = h("select", { id: "s-conn" }, CONNECTORS.map((c) => h("option", { value: c, textContent: c.replace("_", " ") })));
  const kw = inp("s-kw", { type: "number", step: "any", min: 0.1, max: 350 }), price = inp("s-price", { type: "number", step: "any", min: 0 });
  const limit = h("input", { id: "s-limit", type: "checkbox", className: "size-5", onchange: () => (hours.hidden = !limit.checked) });
  const from = inp("s-from", { type: "time", value: "18:00" }), to = inp("s-to", { type: "time", value: "08:00" }), tz = inp("s-tz", { value: "Asia/Kolkata" });
  const hours = h("div", { className: "grid gap-4 sm:grid-cols-3", hidden: true }, f("s-from", "Open from", from), f("s-to", "Open until", to), f("s-tz", "Timezone", tz, "If 'from' is later than 'until', the window runs overnight."));
  const locate = h("button", { className: "btn", type: "button", textContent: "Use my location", onclick: guard(async () => { const p = await new Promise((ok, no) => navigator.geolocation ? navigator.geolocation.getCurrentPosition(ok, () => no(new Error("We couldn't read your location. Allow location access or enter coordinates."))) : no(new Error("This browser can't share your location. Enter coordinates instead."))); lat.value = p.coords.latitude.toFixed(6); lon.value = p.coords.longitude.toFixed(6); }) });
  const submit = h("button", { className: "btn btn-primary", type: "submit", textContent: "List charger" });
  const mapBox = h("div", { className: "panel overflow-hidden isolate h-64", hidden: !window.L, role: "region", "aria-label": "Map. Click to place your charger." });
  let map, mk;
  const setPt = (pan) => {
    const a = parseFloat(lat.value), o = parseFloat(lon.value); if (!map || isNaN(a) || isNaN(o)) return;
    mk ? mk.setLatLng([a, o]) : (mk = L.marker([a, o], { icon: pinIcon(null, true) }).addTo(map));
    if (pan) map.setView([a, o], Math.max(map.getZoom(), 15));
  };
  lat.onchange = lon.onchange = () => setPt(true);
  locate.addEventListener("click", () => setTimeout(() => setPt(true), 1500));
  requestAnimationFrame(() => {
    if (!window.L || !mapBox.isConnected) return;
    map = L.map(mapBox).setView([20.59, 78.96], 5); tiles().addTo(map);
    map.on("click", (e) => { lat.value = e.latlng.lat.toFixed(6); lon.value = e.latlng.lng.toFixed(6); setPt(false); });
  });
  return h("div", { className: "grid gap-6 max-w-2xl" }, h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Share a charger" }), h("p", { className: "text-mute mt-1", textContent: "Add the details drivers need to find and reserve your charger." })),
    h("form", { className: "panel p-6 grid gap-4", onsubmit: guard(async (e) => {
      e.preventDefault(); submit.disabled = true;
      const body = { title: title.value, address: addr.value, latitude: +lat.value, longitude: +lon.value, connector_type: conn.value, power_kw: +kw.value, price_per_kwh: +price.value };
      if (limit.checked) Object.assign(body, { available_from: from.value, available_to: to.value, timezone: tz.value });
      try { await api.createCharger(body); toast("Charger listed"); go("chargers"); } finally { submit.disabled = false; } }) },
      f("s-title", "Title", title), f("s-addr", "Address", addr),
      h("div", { className: "grid gap-4 sm:grid-cols-[1fr_1fr_auto] items-end" }, f("s-lat", "Latitude", lat), f("s-lon", "Longitude", lon), locate),
      mapBox, window.L ? h("p", { className: "text-xs text-mute -mt-2", textContent: "Click the map to place your charger, or use your location." }) : null,
      h("div", { className: "grid gap-4 sm:grid-cols-3" }, f("s-conn", "Connector", conn), f("s-kw", "Power (kW)", kw), f("s-price", "Price per kWh (₹)", price)),
      h("label", { className: "flex items-center gap-3 text-sm font-medium min-h-11" }, limit, "Only available during certain hours"), hours,
      h("div", { className: "flex justify-end" }, submit)));
}

/* ---------- reserve slide-over ---------- */
const local = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
function openDrawer(c) {
  if (!S.user) return openAuth();
  const opener = document.activeElement, d = $("#drawer"), s = new Date(); s.setMinutes(0, 0, 0); s.setHours(s.getHours() + 2);
  const start = h("input", { id: "d-start", type: "datetime-local", required: true, value: local(s) }), end = h("input", { id: "d-end", type: "datetime-local", required: true, value: local(new Date(s.getTime() + 36e5)) });
  const est = h("p", { className: "text-lg font-semibold" }), upd = () => { const hrs = (new Date(end.value) - new Date(start.value)) / 36e5; est.textContent = hrs > 0 ? `Up to ${money(c.power_kw * hrs * c.price_per_kwh)} for ${+hrs.toFixed(1)} h` : ""; };
  start.oninput = end.oninput = upd; upd();
  const close = () => { d.dataset.open = "false"; $("#scrim").dataset.open = "false"; document.removeEventListener("keydown", key); opener && opener.focus && opener.focus(); };
  const key = (e) => { if (e.key === "Escape") close(); if (e.key === "Tab") { const f = [...d.querySelectorAll("button,input")].filter((x) => !x.disabled); const i = f.indexOf(document.activeElement); if (e.shiftKey && i <= 0) { e.preventDefault(); f.at(-1).focus(); } else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); } } };
  const submit = h("button", { className: "btn btn-primary", type: "submit", textContent: "Reserve and pay" });
  const form = h("form", { className: "grid gap-4 p-6", onsubmit: guard(async (e) => {
    e.preventDefault(); submit.disabled = true; submit.textContent = "Reserving…"; submit.setAttribute("aria-busy", "true");
    try { const b = await api.book(c.id, new Date(start.value).toISOString(), new Date(end.value).toISOString()); await api.pay(b.id).catch((er) => toast(er.message, true)); close(); toast("Booked. See it under My bookings."); }
    finally { submit.disabled = false; submit.textContent = "Reserve and pay"; submit.removeAttribute("aria-busy"); } }) },
    h("div", {}, h("h2", { className: "text-xl font-semibold", textContent: c.title }), h("p", { className: "text-sm text-mute", textContent: `${c.address}. ${c.power_kw} kW, ${money(c.price_per_kwh)}/kWh. ${windowText(c)}.` })),
    h("div", { className: "field" }, h("label", { htmlFor: "d-start", textContent: "Start" }), start), h("div", { className: "field" }, h("label", { htmlFor: "d-end", textContent: "End" }), end), est,
    h("p", { className: "text-xs text-mute", textContent: "The price assumes the charger runs at full power for the whole slot. Times use your local timezone." }),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Discard", onclick: close }), submit));
  d.replaceChildren(h("div", { className: "flex justify-end p-2 border-b border-line" }, h("button", { className: "ibtn", type: "button", "aria-label": "Close panel", dataset: { tip: "Close panel" }, onclick: close }, icon("x", "size-5"))), form);
  refreshIcons(); d.dataset.open = "true"; $("#scrim").dataset.open = "true"; $("#scrim").onclick = close; document.addEventListener("keydown", key); setTimeout(() => start.focus(), 50);
}

/* ---------- auth dialog ---------- */
function openAuth() {
  let register = false; const d = $("#dlg"), opener = document.activeElement;
  const draw = () => {
    const name = h("input", { id: "a-name", autocomplete: "name", required: true }), email = h("input", { id: "a-email", type: "email", required: true, autocomplete: "email", placeholder: "name@example.com" }), pass = h("input", { id: "a-pass", type: "password", minLength: 8, required: true, autocomplete: register ? "new-password" : "current-password" });
    const f = (id, t, el, hint) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el, hint ? h("p", { className: "text-xs text-mute font-normal", textContent: hint }) : null);
    d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => { e.preventDefault(); S.user = register ? await api.register(name.value, email.value, pass.value) : await api.signIn(email.value, pass.value); d.close(); toast(`Welcome, ${S.user.name}`); renderChrome(); if (S.view === "bookings") await loadBookings(); }) },
      h("h2", { className: "text-xl font-semibold", textContent: register ? "Create your account" : "Sign in to EV Share" }),
      register ? f("a-name", "Name", name) : null, f("a-email", "Email", email), f("a-pass", "Password", pass, register ? "At least 8 characters." : null),
      h("button", { className: "btn btn-primary", type: "submit", textContent: register ? "Create account" : "Sign in" }),
      h("button", { className: "btn border-transparent text-mute", type: "button", textContent: register ? "I have an account. Sign in" : "Create an account", onclick: () => { register = !register; draw(); } }),
      h("button", { className: "btn border-transparent text-mute", type: "button", textContent: "Cancel", onclick: () => d.close() })));
    $("#a-email").focus();
  };
  d.onclose = () => opener && opener.focus && opener.focus(); draw(); d.showModal(); $("#a-email").focus();
}

/* ---------- boot ---------- */
function render() { const m = $("#main"); m.replaceChildren({ find: findView, bookings: bookingsView, chargers: mineView, share: shareView }[S.view]()); refreshIcons(); }
(async function init() {
  if (api.hasSession()) { try { S.user = await api.me(); } catch { api.signOut(); } }
  renderChrome(); await guard(loadChargers)();
})();
