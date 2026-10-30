import { api } from "./api.js";
import { $, h, icon, refreshIcons, money, fmtRange, utc, toast, setTheme, isDark, confirmDialog, pill, chip, progress, countdown, startTicker, busy } from "./ui.js";

const S = { orders: { pending: [], upcoming: [], past: [] }, near: null, radius: "10", live: null, vs: null, user: null, view: "find", chargers: [], bookings: [], mine: [], loading: true, f: { connector: "", power: "", price: "" }, on: null, target: null };
const CONNECTORS = ["TYPE2", "CCS2", "CHADEMO", "BHARAT_AC001", "BHARAT_DC001", "GBT"];
const where = () => new Promise((ok, no) => navigator.geolocation
  ? navigator.geolocation.getCurrentPosition((p) => ok(p.coords), () => no(new Error("We couldn't read your location. Allow location access in your browser, then try again.")), { enableHighAccuracy: true, timeout: 15000 })
  : no(new Error("This browser can't share your location.")));
const act = (label, fn) => (e) => busy(e.currentTarget, label, () => guard(fn)());  // spinner on the clicked button
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
const filtered = () => S.f.connector || S.f.power || S.f.price;
const windowText = (c) => (c.available_from && c.available_to ? `Open ${c.available_from.slice(0, 5)} to ${c.available_to.slice(0, 5)}` : "Open 24/7");

/* ---------- hub presence: Go live bar ---------- */
const isHub = () => !!S.user && S.user.role === "HUB" && S.user.verification_status === "APPROVED";
let beat = null;
async function syncLive() {
  if (!isHub()) S.live = null; else { try { S.live = await api.liveStatus(); } catch { S.live = null; } }
  const on = !!(S.live && S.live.is_live);
  if (on && !beat) beat = setInterval(heartbeat, 5 * 60 * 1000); else if (!on && beat) { clearInterval(beat); beat = null; }
  if (isHub() && !orderTimer) { orderTimer = setInterval(pollOrders, 20000); pollOrders(); } else if (!isHub() && orderTimer) { clearInterval(orderTimer); orderTimer = null; }
  renderLiveBar();
}
async function heartbeat() {  // re-checks the hub's location while the page is open; going out of range takes the hub offline
  try { const p = await where(); S.live = await api.goLive(p.latitude, p.longitude); renderLiveBar(); } catch (e) { toast(e.message, true); await syncLive(); }
}
function refreshView() { if (S.view === "find") guard(loadChargers)(); if (S.view === "chargers") guard(loadMine)(); }
function renderLiveBar() {
  const bar = $("#livebar"); document.body.classList.toggle("has-livebar", isHub()); bar.hidden = !isHub();
  if (!isHub()) return bar.replaceChildren();
  const L = S.live, live = !!(L && L.is_live);
  const btn = h("button", { className: "btn " + (live ? "" : "btn-primary"), textContent: live ? "Go offline" : "Go live", onclick: guard(async () => {
    btn.disabled = true; btn.textContent = live ? "Going offline…" : "Getting your location…";
    try {
      if (live) { await api.goOffline(); toast("You're offline. No new orders."); }
      else { const p = await where(); await api.goLive(p.latitude, p.longitude); toast("You're live. Drivers can now book your chargers."); }
    } finally { await syncLive(); refreshView(); } }) });
  const at = live ? utc(L.live_until).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  bar.replaceChildren(h("div", { className: "mx-auto max-w-7xl px-4 py-3 flex items-center justify-between gap-4 flex-wrap" },
    h("p", { className: "text-sm flex items-center gap-2" }, h("span", { className: "live-dot" + (live ? " on" : ""), "aria-hidden": "true" }),
      live ? `You're live. ${L.chargers_live} of ${L.chargers_total} chargers are taking orders. Keep this page open; you'll go offline at ${at} if it stops updating.`
           : "You're offline. Go live when you're at your charger to start receiving charging orders."), btn));
}

/* ---------- chrome ---------- */
const roleLabel = (u) => `${u.role === "HUB" ? "Hub" : "Driver"}, ${u.verification_status === "APPROVED" ? "verified" : u.verification_status === "PENDING" ? "under review" : "not verified"}`;
function renderChrome() {
  const nav = $("#nav"), user = $("#user");
  const tab = (id, label) => h("button", { className: "tab" + (S.view === id ? " is-active" : ""), textContent: label, onclick: () => go(id), "aria-current": S.view === id ? "page" : null });
  const u = S.user, ok = u && u.verification_status === "APPROVED", hub = u && u.role === "HUB", n = S.orders.pending.length;
  nav.replaceChildren(...[!hub ? tab("find", "Find chargers") : null,
    ok && !hub ? tab("bookings", "My bookings") : null,
    ok && hub ? tab("orders", n ? `Orders (${n})` : "Orders") : null, ok && hub ? tab("chargers", "My chargers") : null, ok && hub ? tab("share", "Share a charger") : null,
    u && !ok ? tab("verify", "Verify account") : null].filter(Boolean));
  const themeBtn = h("button", { className: "ibtn", dataset: { tip: isDark() ? "Switch to light mode" : "Switch to dark mode" }, "aria-label": isDark() ? "Switch to light mode" : "Switch to dark mode", onclick: () => { setTheme(!isDark()); renderChrome(); } }, icon(isDark() ? "sun" : "moon", "size-5"));
  user.replaceChildren(...(S.user ? [themeBtn, h("span", { className: "text-sm text-mute hidden sm:inline mr-1", textContent: `${S.user.name} · ${roleLabel(S.user)}` }),
      h("button", { className: "btn", textContent: "Sign out", onclick: async () => { await api.signOut(); S.user = null; S.bookings = []; S.mine = []; S.orders = { pending: [], upcoming: [], past: [] }; S.view = "find"; renderChrome(); await syncLive(); go("find"); toast("Signed out"); } })]
    : [themeBtn, h("button", { className: "btn", textContent: "Login", onclick: () => openAuth() }), h("button", { className: "btn btn-primary", textContent: "Register", onclick: () => go("register") })]));
  refreshIcons();
}
async function go(view) {  // eslint-disable-line
  if (view === "register" && S.user) view = "find";
  if (S.user && S.user.role === "HUB" && ["find", "bookings"].includes(view)) view = S.user.verification_status === "APPROVED" ? "orders" : "verify";
  if (S.user && S.user.role === "DRIVER" && ["orders", "chargers", "share"].includes(view)) view = S.user.verification_status === "APPROVED" ? "find" : "verify";
  if (view !== "find" && view !== "register" && !S.user) return openAuth();
  if (view === "share" && S.user.verification_status !== "APPROVED") { toast("Verify your account before sharing a charger.", true); view = "verify"; }
  S.view = view; renderChrome(); render();
  if (view === "verify") await guard(loadVerify)();
  if (view === "bookings") await guard(loadBookings)();
  if (view === "chargers") await guard(loadMine)();
  if (view === "orders") await guard(loadOrders)();
  if (view === "find") await guard(loadChargers)();  // always show fresh availability
}

/* ---------- find: list + map ---------- */
const activeBooking = () => S.bookings.find((b) => ["REQUESTED", "CONFIRMED"].includes(b.status) && utc(b.end_time) > new Date());
async function loadChargers() {
  if (S.user && S.user.role === "DRIVER" && S.user.verification_status === "APPROVED") { try { S.bookings = await api.bookings(); } catch { /* the banner is optional */ } }
  S.loading = true; render();
  try { S.chargers = await api.chargers({ ...S.f, near: S.near, radius: S.radius }); } finally { S.loading = false; render(); }
}
function filterBar() {
  const reload = () => guard(loadChargers)();
  const sel = h("select", { id: "f-conn", onchange: (e) => { S.f.connector = e.target.value; reload(); } }, h("option", { value: "", textContent: "Any" }), CONNECTORS.map((c) => h("option", { value: c, textContent: c.replace("_", " "), selected: S.f.connector === c })));
  const num = (id, key, min) => h("input", { id, type: "number", min, step: "any", value: S.f[key], placeholder: "No limit", onchange: (e) => { S.f[key] = e.target.value; reload(); } });
  const lab = (id, text, el) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: text }), el);
  const radius = h("select", { id: "f-radius", onchange: (e) => { S.radius = e.target.value; reload(); } }, ["2", "5", "10", "25", "50"].map((r) => h("option", { value: r, textContent: `${r} km`, selected: S.radius === r })));
  const nearRow = h("div", { className: "flex flex-wrap items-end gap-3" },
    h("button", { id: "btn-near", className: "btn " + (S.near ? "" : "btn-primary"), onclick: guard(async () => { const p = await where(); S.near = { lat: p.latitude, lon: p.longitude }; await loadChargers(); }) }, icon("locate-fixed", "size-4"), S.near ? "Update my location" : "Chargers near me"),
    S.near ? lab("f-radius", "Within", radius) : null,
    S.near ? h("button", { className: "btn", textContent: "Show all live chargers", onclick: () => { S.near = null; reload(); } }) : null,
    h("p", { className: "text-sm text-mute" }, S.near ? `Live chargers within ${S.radius} km of you, nearest first.` : "Showing every charger that is live right now."));
  return h("div", { className: "panel p-4 grid gap-4" }, nearRow, h("div", { className: "grid gap-4 sm:grid-cols-[1fr_1fr_1fr_auto] items-end" },
    lab("f-conn", "Connector", sel), lab("f-power", "Minimum power (kW)", num("f-power", "power", 1)), lab("f-price", "Maximum price (₹/kWh)", num("f-price", "price", 0)),
    h("button", { className: "btn", textContent: "Clear all filters", disabled: !filtered(), onclick: () => { S.f = { connector: "", power: "", price: "" }; reload(); } })));
}
const canReserve = () => !S.user || S.user.role === "DRIVER";
function chargerRow(c) {
  const meta = h("div", { className: "flex flex-wrap items-center gap-2" }, chip(c.connector_type.replace("_", " ")), chip(`${c.power_kw} kW`), chip(`${money(c.price_per_kwh)}/kWh`), chip(windowText(c)),
    c.is_live ? pill("Live now", "ok live") : pill("Offline"), c.busy_until ? pill(`In use until ${tm(c.busy_until)}`, "warn", "zap") : null);
  const rating = c.avg_rating == null ? "No reviews yet" : `${c.avg_rating.toFixed(1)} (${c.review_count})`;
  return h("li", { className: "row", dataset: { on: String(S.on === c.id), id: c.id }, onmouseenter: () => hl(c.id), onmouseleave: () => hl(null) },
    h("div", { className: "grid gap-1 min-w-0" }, h("h3", { className: "font-medium truncate", textContent: c.title }), h("p", { className: "text-sm text-mute truncate", textContent: c.address }), meta,
      h("p", { className: "text-sm flex items-center gap-1 text-mute" }, icon("star", "size-4"), h("span", { textContent: rating }))),
    h("div", { className: "flex gap-2 items-center flex-wrap self-center" }, c.review_count ? h("button", { className: "btn", textContent: "Read reviews", onclick: guard(() => openReviews(c)) }) : null,
      canReserve() ? (c.is_live ? h("button", { className: "btn btn-primary", onclick: () => openDrawer(c) }, icon("calendar-plus", "size-4"), "Request booking") : h("span", { className: "text-sm text-mute", textContent: "Hub offline" })) : null));
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
  const msg = filtered() ? ["No live chargers match your filters", "Try a lower power or a higher price limit, or clear the filters."]
    : S.near ? ["No live chargers near you right now", "Try a wider distance, or show every live charger."] : ["No charger is live right now", "Hubs appear here the moment they go live. Check back soon."];
  return h("section", { className: "panel p-8 grid gap-2 justify-items-start", "aria-labelledby": "e1" }, icon("plug-zap", "size-6 text-mute"),
    h("h2", { id: "e1", className: "font-semibold text-lg", textContent: msg[0] }), h("p", { className: "text-sm text-mute", textContent: msg[1] }),
    filtered() ? h("button", { className: "btn mt-2", textContent: "Clear all filters", onclick: () => { S.f = { connector: "", power: "", price: "" }; guard(loadChargers)(); } }) : null);
}
function findView() {
  const list = S.loading ? skeleton() : S.chargers.length ? h("ul", { className: "panel overflow-hidden" }, S.chargers.map(chargerRow)) : emptyFind();
  return h("div", { className: "grid gap-6" },
    h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Find a live charger" }),
      h("p", { className: "text-mute mt-1 max-w-[65ch]", textContent: "Only chargers whose hub is live right now are shown. Send a request, the hub accepts it, then you pay and head over." })),
    activeBooking() ? h("div", { className: "panel p-4 flex gap-3 items-center flex-wrap text-sm", role: "note" }, icon("info", "size-5 shrink-0 text-accent"),
      h("span", { className: "flex-1", textContent: `You have an open booking at ${activeBooking().charger_title}. Finish or cancel it before booking another charger.` }), h("button", { className: "btn", textContent: "View booking", onclick: () => go("bookings") })) : null,
    filterBar(), h("div", { className: "grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]" }, list, S.chargers.length && !S.loading ? mapPanel() : null));
}

/* ---------- bookings ---------- */
async function loadBookings() { S.loading = true; render(); try { S.bookings = await api.bookings(); } finally { S.loading = false; render(); } }
const tm = (x) => utc(x).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
function bookingsView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "My bookings" }), h("p", { className: "text-mute mt-1", textContent: "Your requests and sessions, newest first." }));
  if (S.loading) return h("div", { className: "grid gap-6" }, head, skeleton());
  if (!S.bookings.length) return h("div", { className: "grid gap-6" }, head, h("section", { className: "panel p-8 grid gap-2 justify-items-start" }, icon("calendar-x", "size-6 text-mute"),
    h("h2", { className: "font-semibold text-lg", textContent: "No bookings yet" }), h("p", { className: "text-sm text-mute", textContent: "Find a live charger and send a request to see it here." }), h("button", { className: "btn btn-primary mt-2", textContent: "Find chargers", onclick: () => go("find") })));
  const now = new Date();
  return h("div", { className: "grid gap-6" }, head, h("ul", { className: "panel overflow-hidden" }, S.bookings.map((b) => {
    const st = b.status, upcoming = utc(b.end_time) > now, paid = b.payment_status === "PAID" || b.estimated_cost <= 0;
    let ic = "check-circle-2", cls = "text-accent", line = "Confirmed. You can go to the charger.";
    if (st === "REQUESTED") [ic, cls, line] = ["clock", "text-mute", "Waiting for the hub to accept."];
    else if (st === "CONFIRMED" && !paid) [ic, cls, line] = ["wallet", "text-accent", "Accepted by the hub. Pay to confirm your slot."];
    else if (st === "DECLINED") [ic, cls, line] = ["x-circle", "text-danger", `Declined by the hub${b.decline_reason ? `: ${b.decline_reason}` : ""}. You were not charged.`];
    else if (st === "CANCELLED") [ic, cls, line] = ["x-circle", "text-danger", `Cancelled${b.decline_reason ? `: ${b.decline_reason}` : ""}.`];
    else if (st === "COMPLETED") [ic, cls, line] = ["check-circle-2", "text-mute", "Completed. The charger is free for others."];
    const running = st === "CONFIRMED" && paid && utc(b.start_time) <= now && upcoming;
    if (running) [ic, cls, line] = ["zap", "text-accent", `Session in progress until ${tm(b.end_time)}.`];
    const go_ = st === "CONFIRMED" && paid && upcoming;
    const tone = running ? "ok live" : st === "REQUESTED" ? "" : st === "CONFIRMED" ? (paid ? "ok" : "warn") : st === "COMPLETED" ? "" : "danger";
    const label = running ? "In progress" : st === "REQUESTED" ? "Waiting" : st === "CONFIRMED" ? (paid ? "Confirmed" : "Pay now") : st[0] + st.slice(1).toLowerCase();
    return h("li", { className: "row" }, h("div", { className: "grid gap-1 min-w-0" }, h("div", { className: "flex items-center gap-2 flex-wrap" }, h("h3", { className: "font-medium", textContent: b.charger_title }), pill(label, tone)),
      h("p", { className: "text-sm text-mute", textContent: `${fmtRange(b.start_time, b.end_time)}, ${money(b.estimated_cost)}` }),
      h("p", { className: "text-sm flex items-start gap-1 " + cls }, icon(ic, "size-4 mt-0.5 shrink-0"), h("span", {}, line, b.hold_expires_at && (st === "REQUESTED" || (st === "CONFIRMED" && !paid)) ? [st === "REQUESTED" ? " Answer expected within " : " Pay within ", countdown(b.hold_expires_at), "."] : null)),
      running ? progress(b.start_time, b.end_time) : null,
      b.pickup_address ? h("p", { className: "text-sm", textContent: `Where: ${b.pickup_address}` }) : null),
      h("div", { className: "flex gap-2 items-center flex-wrap self-start" },
        go_ && b.pickup_latitude != null ? h("a", { className: "btn btn-primary", target: "_blank", rel: "noopener noreferrer", href: `https://www.google.com/maps/dir/?api=1&destination=${b.pickup_latitude},${b.pickup_longitude}` }, icon("navigation", "size-4"), "Directions") : null,
        st === "CONFIRMED" && !paid ? h("button", { className: "btn btn-primary", textContent: "Pay now", onclick: act("Opening payment…", async () => { await api.pay(b.id); toast("Payment complete. You can go to the charger."); await loadBookings(); }) }) : null,
        running ? h("button", { className: "btn", textContent: "End session", onclick: guard(async () => {
          if (!(await confirmDialog({ title: `End your session at '${b.charger_title}'?`, body: "Use this when you've finished charging. The charger becomes free for other drivers.", confirm: "End session", keep: "Keep charging" }))) return;
          await api.finish(b.id); toast("Session ended. Thanks for charging!"); await loadBookings(); }) }) : null,
        (st === "COMPLETED" || (st === "CONFIRMED" && !upcoming && paid)) && !b.reviewed ? h("button", { className: "btn", textContent: "Leave a review", onclick: () => openReviewForm(b) }) : null,
        (st === "REQUESTED" || st === "CONFIRMED") && upcoming && !running ? h("button", { className: "btn btn-danger", textContent: st === "REQUESTED" ? "Cancel request" : "Cancel booking", onclick: guard(async () => {
          if (!(await confirmDialog({ title: `Cancel ${st === "REQUESTED" ? "request" : "booking"} at '${b.charger_title}'?`, body: st === "REQUESTED" ? "The hub will be told. You haven't been charged." : "A paid booking is refunded in full. This frees the slot for other drivers.", confirm: st === "REQUESTED" ? "Cancel request" : "Cancel booking", keep: "Keep it" }))) return;
          await api.cancel(b.id); toast("Cancelled"); await loadBookings(); }) }) : null));
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

/* ---------- hub: orders ---------- */
let orderTimer = null;
async function loadOrders() {
  S.loading = true; render();
  try { const [pending, upcoming, past] = await Promise.all(["pending", "upcoming", "past"].map((x) => api.hubOrders(x))); S.orders = { pending, upcoming, past }; }
  finally { S.loading = false; render(); renderChrome(); }
}
async function pollOrders() {  // quietly checks for new requests while the hub is signed in
  try {
    const pending = await api.hubOrders("pending"), before = S.orders.pending.length; S.orders.pending = pending;
    if (pending.length > before) toast(pending.length - before > 1 ? "New charging requests" : "New charging request");
    if (S.view === "orders" && !S.loading) { S.orders.upcoming = await api.hubOrders("upcoming"); render(); }
    if (pending.length !== before) renderChrome();
  } catch { /* ignore a failed check; the next one will retry */ }
}
function ordersView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Orders" }),
    h("p", { className: "text-mute mt-1 max-w-[65ch]", textContent: "Drivers send requests while you're live. Accept one and the driver pays, then comes to you." }));
  if (S.loading) return h("div", { className: "grid gap-6" }, head, skeleton());
  const offline = S.live && !S.live.is_live ? h("div", { className: "panel p-4 flex gap-3 text-sm", role: "note" }, icon("radio-tower", "size-5 shrink-0 text-mute"), "You're offline, so drivers can't send new requests. Use Go live at the bottom of the page.") : null;
  const card = (o, extra, actions) => h("li", { className: "row" }, h("div", { className: "grid gap-1 min-w-0" },
    h("h3", { className: "font-medium", textContent: `${o.driver_name}${o.driver_vehicle ? `, ${o.driver_vehicle}` : ""}` }),
    h("p", { className: "text-sm text-mute", textContent: `${o.charger_title}, ${fmtRange(o.start_time, o.end_time)}, ${money(o.estimated_cost)}` }), extra),
    h("div", { className: "flex gap-2 items-center flex-wrap self-start" }, actions));
  const block = (title, items, empty, build) => h("section", { className: "grid gap-3" }, h("h2", { className: "font-semibold", textContent: items.length ? `${title} (${items.length})` : title }),
    items.length ? h("ul", { className: "panel overflow-hidden" }, items.map(build)) : h("p", { className: "text-sm text-mute panel p-4", textContent: empty }));
  const { pending, past } = S.orders, nowD = new Date();
  const isPaid = (o) => o.payment_status === "PAID" || o.estimated_cost <= 0;
  const running = S.orders.upcoming.filter((o) => isPaid(o) && utc(o.start_time) <= nowD), upcoming = S.orders.upcoming.filter((o) => !running.includes(o));
  return h("div", { className: "grid gap-6" }, head, offline,
    block("New requests", pending, "No requests waiting.", (o) => card(o, h("p", { className: "text-sm text-accent flex items-center gap-1" }, icon("clock", "size-4"), h("span", {}, "Please answer within ", o.hold_expires_at ? countdown(o.hold_expires_at) : "a few minutes", ".")), [
      h("button", { className: "btn btn-primary", textContent: "Accept", onclick: act("Accepting…", async () => { await api.acceptOrder(o.id); toast(o.estimated_cost > 0 ? "Accepted. The driver has been asked to pay." : "Accepted. The driver can come."); await loadOrders(); }) }),
      h("button", { className: "btn btn-danger", textContent: "Decline", onclick: () => askDecline(o) })])),
    running.length ? block("In progress", running, "", (o) => card(o, h("div", { className: "grid gap-2" }, h("p", { className: "text-sm flex items-center gap-1 text-accent" }, icon("zap", "size-4"), `Charging until ${tm(o.end_time)}.`), progress(o.start_time, o.end_time)),
      h("button", { className: "btn", textContent: "Mark session done", onclick: guard(async () => {
        if (!(await confirmDialog({ title: `Finish ${o.driver_name}'s session?`, body: "The charger becomes free for other drivers straight away.", confirm: "Mark done", keep: "Keep charging" }))) return;
        await api.finish(o.id); toast("Session finished. The charger is free."); await loadOrders(); }) }))) : null,
    block("Accepted", upcoming, "Nothing accepted yet.", (o) => card(o, h("p", { className: "text-sm flex items-center gap-1 " + (o.payment_status === "PAID" || o.estimated_cost <= 0 ? "text-accent" : "text-mute") },
        icon(o.payment_status === "PAID" || o.estimated_cost <= 0 ? "check-circle-2" : "wallet", "size-4"), o.payment_status === "PAID" || o.estimated_cost <= 0 ? "Confirmed. The driver is on the way." : h("span", {}, "Waiting for the driver to pay", o.hold_expires_at ? [" (", countdown(o.hold_expires_at), " left)"] : null, ".")),
      h("button", { className: "btn btn-danger", textContent: "Cancel order", onclick: guard(async () => {
        if (!(await confirmDialog({ title: `Cancel ${o.driver_name}'s booking?`, body: "A paid booking is refunded in full and the driver is told.", confirm: "Cancel order", keep: "Keep order" }))) return;
        await api.cancel(o.id); toast("Order cancelled"); await loadOrders(); }) }))),
    block("History", past, "Nothing here yet.", (o) => card(o, h("p", { className: "text-sm text-mute", textContent: `${o.status.charAt(0) + o.status.slice(1).toLowerCase()}${o.decline_reason ? `: ${o.decline_reason}` : ""}` }), null)));
}
function askDecline(o) {
  const d = $("#dlg"), opener = document.activeElement, why = h("textarea", { id: "dc-why", maxLength: 300, placeholder: "Optional. e.g. Closed for maintenance today." });
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => { e.preventDefault(); await api.declineOrder(o.id, why.value); d.close(); toast("Declined. The driver has been told."); await loadOrders(); }) },
    h("h2", { className: "font-semibold text-lg", textContent: `Decline ${o.driver_name}'s request?` }), h("p", { className: "text-sm text-mute", textContent: "The driver is told it was declined and isn't charged. The slot becomes free again." }),
    h("div", { className: "field" }, h("label", { htmlFor: "dc-why", textContent: "Reason for the driver (optional)" }), why),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Keep request", onclick: () => d.close() }), h("button", { className: "btn btn-danger", type: "submit", textContent: "Decline request" }))));
  d.showModal(); why.focus();
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
      h("p", { className: "text-sm flex items-center gap-1 " + (c.is_active ? "text-accent" : "text-mute") }, icon(c.is_active ? "check-circle-2" : "pause-circle", "size-4"), h("span", { textContent: `${c.is_active ? "Listed" : "Paused"}, ${c.is_live ? "live now" : "offline"}` }))),
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

/* ---------- account verification ---------- */
const NOTICE = "EV Share will never call, text or email you to ask for an OTP, password or card details. Enter a code only inside this app, on the screen that asks for it. If anyone asks you to read one out, it is a scam.";
const noticeBox = () => h("div", { className: "panel p-4 flex gap-3 text-sm", role: "note" }, icon("shield-alert", "size-5 shrink-0 text-accent"), h("p", {}, h("strong", { textContent: "Staying safe. " }), NOTICE));
async function refreshUser() { S.user = await api.me(); renderChrome(); await syncLive(); }
async function loadVerify() { S.loading = true; render(); try { S.vs = await api.verification(); } finally { S.loading = false; render(); } }
const STATUS = { NOT_SUBMITTED: ["circle-dashed", "Not submitted yet", "text-mute"], PENDING: ["clock", "Under review. We'll approve or ask for changes soon.", "text-mute"], APPROVED: ["check-circle-2", "Verified. You're all set.", "text-accent"], REJECTED: ["x-circle", "Needs changes", "text-danger"] };
const STEPS = ["Create account", "Confirm email", "Upload documents", "Review"];
function stepper(cur) {
  return h("ol", { className: "flex gap-2 flex-wrap text-sm", "aria-label": "Registration progress" }, STEPS.map((t, i) => {
    const n = i + 1, done = n < cur, on = n === cur;
    return h("li", { className: "flex items-center gap-2 px-3 min-h-9 rounded-lg border " + (on ? "border-accent text-accent font-medium" : done ? "border-line text-accent" : "border-line text-mute"), "aria-current": on ? "step" : null },
      done ? icon("check", "size-4") : h("span", { textContent: String(n) }), t);
  }));
}
const NEEDS = { DRIVER: ["Email OTP (we email you a 6-digit code)", "Vehicle registration number", "Aadhaar card, masked (first 8 digits hidden)", "Vehicle registration certificate (RC)"],
  HOUSE: ["Email OTP (we email you a 6-digit code)", "House / property documents", "Property tax receipt"],
  SHOP: ["Email OTP (we email you a 6-digit code)", "House / property documents", "Property tax receipt", "Sanctioned building plan", "Occupancy certificate", "Shop & establishment licence"] };
function registerView() {
  const R = (S.reg = S.reg || { name: "", email: "", pass: "", role: "DRIVER", hub: "HOUSE" });
  const f = (id, t, el, hint) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el, hint ? h("p", { className: "text-xs text-mute font-normal", textContent: hint }) : null);
  const text = (id, key, o = {}) => h("input", { id, value: R[key], required: true, oninput: (e) => (R[key] = e.target.value), ...o });
  const sel = (id, opts, key) => h("select", { id, onchange: (e) => { R[key] = e.target.value; render(); } }, opts.map(([v, t]) => h("option", { value: v, textContent: t, selected: v === R[key] })));
  const need = NEEDS[R.role === "DRIVER" ? "DRIVER" : R.hub];
  return h("div", { className: "grid gap-6 max-w-xl" },
    h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Register" }),
      h("p", { className: "text-mute mt-1", textContent: "Everyone is verified before they can book or list a charger. You'll upload your documents right after this step." })),
    stepper(1), noticeBox(),
    h("section", { className: "panel p-5 grid gap-3" }, h("h2", { className: "font-semibold", textContent: "I want to" }), f("r-role", "Account type", sel("r-role", [["DRIVER", "Charge my EV (driver)"], ["HUB", "Share a charger (hub)"]], "role")),
      R.role === "HUB" ? f("r-hub", "My property is a", sel("r-hub", [["HOUSE", "House"], ["SHOP", "Shop or business"]], "hub")) : null,
      h("p", { className: "text-sm text-mute", textContent: "You will need:" }), h("ul", { className: "text-sm grid gap-1 list-disc pl-5" }, need.map((n) => h("li", { textContent: n })))),
    h("form", { className: "panel p-5 grid gap-4", onsubmit: guard(async (e) => {
        e.preventDefault(); S.user = await api.register(R.name, R.email, R.pass, R.role, R.role === "HUB" ? R.hub : undefined); S.reg = null;
        renderChrome(); toast("Registered. Next, confirm your email."); await go("verify"); }) },
      h("h2", { className: "font-semibold", textContent: "Your details" }), f("r-name", "Full name", text("r-name", "name", { autocomplete: "name" })),
      f("r-email", "Email", text("r-email", "email", { type: "email", autocomplete: "email" }), "We'll send your verification code here."),
      f("r-pass", "Password", text("r-pass", "pass", { type: "password", minLength: 8, autocomplete: "new-password" }), "At least 8 characters."),
      h("button", { className: "btn btn-primary", type: "submit", textContent: "Register and continue" }),
      h("p", { className: "text-sm text-mute" }, "Already registered? ", h("button", { type: "button", className: "underline", textContent: "Login", onclick: () => openAuth() }))));
}
function verifyView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Finish your registration" }),
    h("p", { className: "text-mute mt-1 max-w-[65ch]", textContent: S.user.role === "DRIVER" ? "Drivers verify their identity and vehicle before reserving chargers." : "Hubs verify their property before listing chargers." }));
  if (S.loading || !S.vs) return h("div", { className: "grid gap-6 max-w-2xl" }, head, skeleton());
  const v = S.vs, locked = v.status === "PENDING" || v.status === "APPROVED", [ic, label, cls] = STATUS[v.status];
  const docsDone = v.required.every((r) => r.uploaded) && (v.role !== "DRIVER" || !!v.vehicle_number);
  const cur = v.status === "APPROVED" ? 5 : locked ? 4 : !v.email_verified ? 2 : !docsDone ? 3 : 4;
  const step = (title, lock, ...body) => h("section", { className: "panel p-5 grid gap-3 " + (lock ? "opacity-50" : ""), inert: !!lock, "aria-disabled": lock ? "true" : null }, h("h2", { className: "font-semibold", textContent: title }), ...body);
  const code = h("input", { id: "v-code", inputMode: "numeric", maxLength: 6, autocomplete: "one-time-code", placeholder: "6-digit code" });
  const emailStep = step("Step 2 of 4: Confirm your email", false, v.email_verified
    ? h("p", { className: "text-sm flex items-center gap-2 text-accent" }, icon("check-circle-2", "size-4"), `${S.user.email} is confirmed.`)
    : h("div", { className: "grid gap-3" }, h("p", { className: "text-sm text-mute", textContent: `We'll email a 6-digit code to ${S.user.email}. It expires in 10 minutes.` }),
        h("div", { className: "flex gap-2 flex-wrap items-end" }, h("button", { className: "btn", textContent: "Email me a code", onclick: act("Sending…", async () => { await api.sendCode(); toast("Code sent. Check your inbox."); $("#v-code").focus(); }) }),
          h("div", { className: "field" }, h("label", { htmlFor: "v-code", textContent: "Enter the code" }), code),
          h("button", { className: "btn btn-primary", textContent: "Confirm code", onclick: act("Checking…", async () => { await api.confirmCode(code.value.trim()); toast("Email confirmed"); await loadVerify(); await refreshUser(); }) }))));
  const car = h("input", { id: "v-car", value: (v.vehicle_number || "").toUpperCase(), disabled: locked, placeholder: "TN45AB1234", maxLength: 20, autocapitalize: "characters", spellcheck: false, className: "uppercase tracking-wide",
    oninput: (e) => { const at = e.target.selectionStart; e.target.value = e.target.value.toUpperCase(); e.target.setSelectionRange(at, at); } });
  const docRows = h("ul", { className: "panel overflow-hidden" }, v.required.map((r) => h("li", { className: "row" },
    h("div", { className: "grid gap-1 min-w-0" }, h("p", { className: "font-medium text-sm", textContent: r.label }),
      h("p", { className: "text-sm flex items-center gap-1 " + (r.uploaded ? "text-accent" : "text-mute") }, icon(r.uploaded ? "check-circle-2" : "circle-dashed", "size-4"), h("span", { className: "truncate", textContent: r.uploaded ? r.original_name : "Not uploaded" }))),
    h("label", { className: "btn cursor-pointer " + (locked ? "opacity-50 pointer-events-none" : ""), textContent: r.uploaded ? "Replace file" : "Choose file" },
      h("input", { type: "file", className: "sr-only", accept: ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png", disabled: locked,
        onchange: guard(async (e) => { const f = e.target.files[0]; if (!f) return; await api.uploadDoc(r.doc_type, f); toast("Uploaded"); await loadVerify(); }) })))));
  const docsStep = step("Step 3 of 4: Upload your documents", !v.email_verified && !locked,
    v.role === "DRIVER" ? h("div", { className: "flex gap-2 items-end flex-wrap" }, h("div", { className: "field flex-1 min-w-[200px]" }, h("label", { htmlFor: "v-car", textContent: "Vehicle registration number" }), car, h("p", { className: "text-xs text-mute font-normal", textContent: "Capital letters and digits only, for example TN45AB1234. Spaces and hyphens are ignored." })),
      h("button", { className: "btn", textContent: "Save number", disabled: locked, onclick: guard(async () => { await api.setVehicle(car.value); toast("Saved"); await loadVerify(); }) })) : null,
    h("p", { className: "text-sm text-mute", textContent: "PDF, JPG or PNG, up to 5 MB each. Files are encrypted and only our reviewers can open them." }), docRows);
  const consent = h("input", { id: "v-consent", type: "checkbox", className: "size-5", disabled: locked, checked: locked });
  const sendStep = step("Step 4 of 4: Send for review", !docsDone && !locked,
    h("label", { className: "flex items-start gap-3 text-sm min-h-11" }, consent, "I agree that EV Share may store these documents and have a reviewer check them against official records to verify my account."),
    h("div", {}, h("button", { className: "btn btn-primary", textContent: v.status === "REJECTED" ? "Resubmit for review" : v.status === "PENDING" ? "Submitted. Waiting for review" : v.status === "APPROVED" ? "Approved" : "Submit for review", disabled: !v.can_submit,
      onclick: guard(async () => { await api.submitVerification(consent.checked); toast("Submitted. A reviewer will check your documents."); await loadVerify(); await refreshUser(); window.scrollTo({ top: 0, behavior: "smooth" }); }) }),
      v.status === "PENDING" ? h("p", { className: "text-sm text-accent mt-2 flex items-center gap-2" }, icon("check-circle-2", "size-4"), "Your application is with a reviewer. There is nothing more to do right now.") : null));
  return h("div", { className: "grid gap-6 max-w-2xl" }, head, stepper(cur),
    h("div", { className: "panel p-4 grid gap-1" }, h("p", { className: "flex items-center gap-2 font-medium " + cls }, icon(ic, "size-5"), label),
      v.rejection_reason ? h("p", { className: "text-sm", textContent: `Reviewer's note: ${v.rejection_reason}` }) : null,
      v.status === "PENDING" ? h("p", { className: "text-sm text-mute", textContent: "A reviewer is checking each document against the official records. Sign in again later to see the result." }) : null),
    noticeBox(), emailStep, docsStep, sendStep);
}

/* ---------- reserve slide-over ---------- */
const local = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
function openDrawer(c) {
  if (!S.user) return openAuth();
  if (S.user.role !== "DRIVER") return toast("Only driver accounts can reserve chargers.", true);
  if (S.user.verification_status !== "APPROVED") { toast("Verify your account to reserve chargers.", true); return go("verify"); }
  if (!c.is_live) return toast("This hub is offline right now. Try again when it's live.", true);
  const opener = document.activeElement, d = $("#drawer"), s = new Date(); s.setMinutes(0, 0, 0); s.setHours(s.getHours() + 2);
  const start = h("input", { id: "d-start", type: "datetime-local", required: true, value: local(s) }), end = h("input", { id: "d-end", type: "datetime-local", required: true, value: local(new Date(s.getTime() + 36e5)) });
  const busyBox = h("div", { className: "text-sm text-mute", "aria-live": "polite" });
  api.busy(c.id).then((slots) => { busyBox.replaceChildren(...(slots.length ? [h("p", { className: "font-medium text-ink", textContent: "Already taken" }), h("ul", { className: "grid gap-1" }, slots.map((x) => h("li", { textContent: `${fmtRange(x.start_time, x.end_time)}${x.in_progress ? " (in use now)" : ""}` })))] : [h("p", { textContent: "No other bookings in the next 7 days." })])); }).catch(() => {});
  const est = h("p", { className: "text-lg font-semibold" }), upd = () => { const hrs = (new Date(end.value) - new Date(start.value)) / 36e5; est.textContent = hrs > 0 ? `Up to ${money(c.power_kw * hrs * c.price_per_kwh)} for ${+hrs.toFixed(1)} h` : ""; };
  start.oninput = end.oninput = upd; upd();
  const close = () => { d.dataset.open = "false"; $("#scrim").dataset.open = "false"; document.removeEventListener("keydown", key); opener && opener.focus && opener.focus(); };
  const key = (e) => { if (e.key === "Escape") close(); if (e.key === "Tab") { const f = [...d.querySelectorAll("button,input")].filter((x) => !x.disabled); const i = f.indexOf(document.activeElement); if (e.shiftKey && i <= 0) { e.preventDefault(); f.at(-1).focus(); } else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); } } };
  const submit = h("button", { className: "btn btn-primary", type: "submit", textContent: "Send request" });
  const form = h("form", { className: "grid gap-4 p-6", onsubmit: guard(async (e) => {
    e.preventDefault(); submit.disabled = true; submit.textContent = "Sending…"; submit.setAttribute("aria-busy", "true");
    try { await api.book(c.id, new Date(start.value).toISOString(), new Date(end.value).toISOString()); close(); toast("Request sent. The hub will answer soon, and you pay once it accepts."); await go("bookings"); }
    finally { submit.disabled = false; submit.textContent = "Send request"; submit.removeAttribute("aria-busy"); } }) },
    h("div", {}, h("h2", { className: "text-xl font-semibold", textContent: c.title }), h("p", { className: "text-sm text-mute", textContent: `${c.address}. ${c.power_kw} kW, ${money(c.price_per_kwh)}/kWh. ${windowText(c)}.` })),
    h("div", { className: "field" }, h("label", { htmlFor: "d-start", textContent: "Start" }), start), h("div", { className: "field" }, h("label", { htmlFor: "d-end", textContent: "End" }), end), busyBox, est,
    h("p", { className: "text-xs text-mute", textContent: "The hub has to accept your request first, and you only pay after that. The price assumes the charger runs at full power for the whole slot. Times use your local timezone." }),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Discard", onclick: close }), submit));
  d.replaceChildren(h("div", { className: "flex justify-end p-2 border-b border-line" }, h("button", { className: "ibtn", type: "button", "aria-label": "Close panel", dataset: { tip: "Close panel" }, onclick: close }, icon("x", "size-5"))), form);
  refreshIcons(); d.dataset.open = "true"; $("#scrim").dataset.open = "true"; $("#scrim").onclick = close; document.addEventListener("keydown", key); setTimeout(() => start.focus(), 50);
}

/* ---------- login (drivers and hubs) ---------- */
function openAuth() {
  const d = $("#dlg"), opener = document.activeElement;
  const email = h("input", { id: "a-email", type: "email", required: true, autocomplete: "email", placeholder: "name@example.com" }), pass = h("input", { id: "a-pass", type: "password", required: true, autocomplete: "current-password" });
  const f = (id, t, el) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el);
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => {
      e.preventDefault(); S.user = await api.signIn(email.value, pass.value); d.close(); toast(`Welcome back, ${S.user.name}`); renderChrome(); await syncLive();
      if (S.user.verification_status !== "APPROVED") return go("verify");
      go(["verify", "register"].includes(S.view) ? "find" : S.view); }) },
    h("h2", { className: "text-xl font-semibold", textContent: "Login" }), f("a-email", "Email", email), f("a-pass", "Password", pass),
    h("button", { className: "btn btn-primary", type: "submit", textContent: "Login" }),
    h("button", { className: "btn border-transparent text-mute", type: "button", textContent: "New here? Register", onclick: () => { d.close(); go("register"); } }),
    h("button", { className: "btn border-transparent text-mute", type: "button", textContent: "Cancel", onclick: () => d.close() })));
  d.showModal(); email.focus();
}

/* ---------- boot ---------- */
function render() { const m = $("#main"); m.classList.remove("view-enter"); void m.offsetWidth; m.classList.add("view-enter"); m.replaceChildren({ find: findView, bookings: bookingsView, chargers: mineView, share: shareView, verify: verifyView, register: registerView, orders: ordersView }[S.view]()); refreshIcons(); }
startTicker(() => setTimeout(() => { if (S.view === "bookings") guard(loadBookings)(); else if (S.view === "orders") guard(loadOrders)(); else if (S.view === "find") guard(loadChargers)(); }, 1200));
(async function init() {
  try { const me = await api.me(); S.user = me.is_admin ? null : me; } catch { /* not signed in */ }
  renderChrome(); await syncLive();
  if (S.user && S.user.role === "HUB") await go("find"); else await guard(loadChargers)();
})();
