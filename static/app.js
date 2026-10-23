"use strict";
/* EV Share front-end: vanilla JS + Leaflet. All dynamic text is inserted with textContent (no innerHTML). */

const $ = (sel, root = document) => root.querySelector(sel);
const state = { token: localStorage.getItem("evshare_token"), user: null, view: "find", chargers: [], markers: new Map(),
                maps: {}, pickMarker: null, authMode: "login", reviewBookingId: null, razorpayLoaded: false };

/* ---------- helpers ---------- */
function el(tag, props = {}, ...kids) {
  const { dataset, ...rest } = props;
  const n = Object.assign(document.createElement(tag), rest);
  if (dataset) Object.assign(n.dataset, dataset);
  for (const k of kids.flat()) if (k != null) n.append(k);
  return n;
}
const money = (n) => `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const utc = (s) => new Date(s.endsWith("Z") ? s : s + "Z");
const fmtRange = (a, b) => {
  const s = utc(a), e = utc(b);
  const day = s.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  const t = (d) => d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${day}, ${t(s)} – ${t(e)}`;
};
function stars(avg, count) {
  if (avg == null) return el("span", { className: "stars none", textContent: "No reviews yet" });
  const full = Math.round(avg);
  return el("span", { className: "stars", title: `${avg} out of 5`, textContent: "★".repeat(full) + "☆".repeat(5 - full) + ` ${avg.toFixed(1)} (${count})` });
}
function toast(msg, isErr = false) {
  const t = el("div", { className: "toast" + (isErr ? " err" : ""), textContent: msg });
  $("#toasts").append(t);
  setTimeout(() => t.remove(), isErr ? 6000 : 3500);
}
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload;
  if (form) payload = new URLSearchParams(form);
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && state.token && path !== "/auth/login") { logout(true); throw new Error("Session expired, please sign in again"); }
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ") : d || res.statusText);
  }
  return data;
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (err) { toast(err.message, true); } };
const needAuth = () => { if (!state.token) { openAuth("login"); return false; } return true; };
function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation is not available in this browser"));
    navigator.geolocation.getCurrentPosition((p) => resolve(p.coords), () => reject(new Error("Could not get your location (permission denied?)")), { timeout: 10000 });
  });
}
const onSubmit = (form, fn) => form.addEventListener("submit", (e) => { e.preventDefault(); guard(fn)(e); });
document.addEventListener("click", (e) => { if (e.target.matches("[data-close]")) e.target.closest("dialog").close(); });

/* ---------- maps ---------- */
function makeMap(id) {
  const map = L.map(id).setView([20.59, 78.96], 5);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
  return map;
}
const pinIcon = (sel) => L.divIcon({ className: "", html: `<div class="pin${sel ? " sel" : ""}">⚡</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });

/* ---------- navigation ---------- */
function showView(name) {
  if (name !== "find" && !needAuth()) return;
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "find") setTimeout(() => state.maps.find.invalidateSize(), 0);
  if (name === "bookings") loadBookings();
  if (name === "chargers") loadMyChargers();
  if (name === "share") {
    if (!state.maps.pick) {
      state.maps.pick = makeMap("map-pick");
      state.maps.pick.on("click", (e) => setPick(e.latlng.lat, e.latlng.lng));
    }
    setTimeout(() => state.maps.pick.invalidateSize(), 0);
  }
}
$("#nav").addEventListener("click", (e) => { const b = e.target.closest("button[data-view]"); if (b) showView(b.dataset.view); });

/* ---------- auth ---------- */
function renderAuth() {
  const box = $("#user-box"); box.replaceChildren();
  document.querySelectorAll("[data-auth]").forEach((b) => (b.hidden = !state.token));
  if (state.token && state.user) {
    box.append(el("span", { className: "muted", textContent: state.user.name }),
               el("button", { className: "btn ghost sm", textContent: "Sign out", onclick: () => logout() }));
  } else {
    box.append(el("button", { className: "btn sm", textContent: "Sign in", onclick: () => openAuth("login") }));
  }
}
function logout(expired = false) {
  state.token = null; state.user = null; localStorage.removeItem("evshare_token");
  renderAuth(); if (state.view !== "find") showView("find"); if (!expired) toast("Signed out");
  renderResults();
}
function openAuth(mode) {
  state.authMode = mode;
  document.querySelectorAll("#dlg-auth .tabs button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#name-wrap").hidden = mode !== "register";
  $("#a-submit").textContent = mode === "register" ? "Create account" : "Sign in";
  $("#a-pass").autocomplete = mode === "register" ? "new-password" : "current-password";
  $("#dlg-auth").showModal();
}
$("#dlg-auth .tabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-mode]"); if (b) openAuth(b.dataset.mode); });
onSubmit($("#auth-form"), async () => {
  const email = $("#a-email").value, password = $("#a-pass").value;
  if (state.authMode === "register") await api("/auth/register", { method: "POST", body: { email, name: $("#a-name").value || "Driver", password } });
  const t = await api("/auth/login", { method: "POST", form: { username: email, password } });
  state.token = t.access_token; localStorage.setItem("evshare_token", state.token);
  state.user = await api("/auth/me");
  $("#dlg-auth").close(); $("#a-pass").value = "";
  renderAuth(); renderResults(); toast(`Welcome, ${state.user.name}`);
});

/* ---------- find ---------- */
function searchParams({ center } = {}) {
  const q = new URLSearchParams();
  if (center) { q.set("lat", center.lat); q.set("lon", center.lng); q.set("radius_km", $("#f-radius").value); }
  if ($("#f-connector").value) q.set("connector_type", $("#f-connector").value);
  if ($("#f-power").value) q.set("min_power_kw", $("#f-power").value);
  if ($("#f-price").value) q.set("max_price_per_kwh", $("#f-price").value);
  if ($("#f-rating").value) q.set("min_rating", $("#f-rating").value);
  return q;
}
async function runSearch({ center, fit = true, userPos = null } = {}) {
  if (fit) { state.center = center || null; state.userPos = userPos; }
  const list = await api(`/chargers?${searchParams({ center })}`);
  state.chargers = list;
  renderResults(); drawMarkers(fit, userPos, center);
  $("#result-count").textContent = list.length ? `${list.length} charger${list.length === 1 ? "" : "s"} found` : "";
}
function drawMarkers(fit, userPos, center) {
  const map = state.maps.find;
  state.markers.forEach((m) => m.remove()); state.markers.clear();
  if (state.userMarker) { state.userMarker.remove(); state.userMarker = null; }
  const group = [];
  for (const c of state.chargers) {
    const m = L.marker([c.latitude, c.longitude], { icon: pinIcon(false), title: c.title }).addTo(map);
    m.on("click", () => highlight(c.id, false));
    state.markers.set(c.id, m); group.push(m.getLatLng());
  }
  if (userPos) {
    state.userMarker = L.circleMarker([userPos.latitude, userPos.longitude], { radius: 8, color: "#2563eb", fillColor: "#3b82f6", fillOpacity: .9 }).addTo(map).bindTooltip("You are here");
    group.push(state.userMarker.getLatLng());
  }
  if (fit && group.length) map.fitBounds(L.latLngBounds(group).pad(0.25), { maxZoom: 14 });
  else if (fit && center) map.setView(center, 12);
}
function highlight(id, pan = true) {
  document.querySelectorAll("#results .card").forEach((c) => c.classList.toggle("hl", Number(c.dataset.id) === id));
  state.markers.forEach((m, mid) => m.setIcon(pinIcon(mid === id)));
  const card = $(`#results .card[data-id="${id}"]`);
  if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const c = state.chargers.find((x) => x.id === id);
  if (pan && c) state.maps.find.flyTo([c.latitude, c.longitude], Math.max(state.maps.find.getZoom(), 14));
}
function windowText(c) {
  return c.available_from && c.available_to ? `Available ${c.available_from.slice(0, 5)}–${c.available_to.slice(0, 5)} (${c.timezone})` : "Available 24/7";
}
function chargerCard(c, { owner = false } = {}) {
  const badges = el("div", { className: "badges" },
    el("span", { className: "badge", textContent: c.connector_type }),
    el("span", { className: "badge", textContent: `${c.power_kw} kW` }),
    el("span", { className: "badge", textContent: `${money(c.price_per_kwh)}/kWh` }));
  if (c.distance_km != null) badges.append(el("span", { className: "badge", textContent: `${c.distance_km} km` }));
  if (!c.is_active) badges.append(el("span", { className: "badge warn", textContent: "Paused" }));
  const reviewsBtn = c.review_count ? el("button", { className: "btn ghost sm", textContent: "Reviews", onclick: guard(() => openReviews(c)) }) : null;
  const actions = el("div", { className: "actions" });
  if (!owner) actions.append(el("button", { className: "btn sm", textContent: "Book", onclick: () => openBook(c) }));
  if (reviewsBtn) actions.append(reviewsBtn);
  return el("div", { className: "card", dataset: { id: c.id }, onclick: owner ? null : () => highlight(c.id) },
    el("div", { className: "card-top" }, el("h4", { textContent: c.title }), stars(c.avg_rating, c.review_count)),
    el("div", { className: "muted small", textContent: c.address }),
    badges, el("div", { className: "muted small", textContent: windowText(c) }), actions);
}
function renderResults() {
  const box = $("#results"); box.replaceChildren();
  if (!state.chargers.length) return box.append(el("p", { className: "muted", textContent: "No chargers match. Try a larger radius or fewer filters." }));
  state.chargers.forEach((c) => box.append(chargerCard(c)));
}
$("#btn-locate").onclick = guard(async () => {
  const pos = await getPosition();
  const center = { lat: pos.latitude, lng: pos.longitude };
  state.maps.find.setView(center, 13);
  await runSearch({ center, fit: true, userPos: pos });
});
$("#btn-area").onclick = guard(async () => { const c = state.maps.find.getCenter(); state.center = c; state.userPos = null; await runSearch({ center: c, fit: false }); });
$("#btn-all").onclick = guard(() => runSearch({ fit: true }));
["f-connector", "f-power", "f-price", "f-rating", "f-radius"].forEach((id) => $(`#${id}`).addEventListener("change", guard(() => runSearch({ center: state.center, userPos: state.userPos, fit: false }))));

/* ---------- booking ---------- */
let bookingTarget = null;
const toLocalInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
function openBook(c) {
  if (!needAuth()) return;
  bookingTarget = c;
  $("#b-title").textContent = c.title;
  $("#b-info").textContent = `${c.address} · ${c.connector_type} · ${c.power_kw} kW · ${money(c.price_per_kwh)}/kWh · ${windowText(c)}`;
  const start = new Date(); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 2);
  $("#b-start").value = toLocalInput(start);
  $("#b-end").value = toLocalInput(new Date(start.getTime() + 3600000));
  updateEstimate(); $("#dlg-book").showModal();
}
function updateEstimate() {
  const s = new Date($("#b-start").value), e = new Date($("#b-end").value);
  const hrs = (e - s) / 3600000, box = $("#b-estimate");
  box.textContent = hrs > 0 && bookingTarget ? `Estimated max cost: ${money(bookingTarget.power_kw * hrs * bookingTarget.price_per_kwh)} for ${hrs.toFixed(hrs % 1 ? 1 : 0)} h` : "";
}
["b-start", "b-end"].forEach((id) => $(`#${id}`).addEventListener("input", updateEstimate));
onSubmit($("#book-form"), async () => {
  const b = await api("/bookings", { method: "POST", body: { charger_id: bookingTarget.id,
    start_time: new Date($("#b-start").value).toISOString(), end_time: new Date($("#b-end").value).toISOString() } });
  $("#dlg-book").close(); toast("Slot reserved. Complete payment to confirm with the host.");
  await startPayment(b.id);
});

/* ---------- payments ---------- */
function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((res, rej) => document.head.append(el("script", { src: "https://checkout.razorpay.com/v1/checkout.js", onload: res, onerror: () => rej(new Error("Could not load Razorpay checkout")) })));
}
async function startPayment(bookingId) {
  const co = await api("/payments/checkout", { method: "POST", body: { booking_id: bookingId } });
  if (co.status === "PAID") { toast("Nothing to pay. Booking confirmed."); return afterPay(); }
  if (co.provider === "mock") {
    await api("/payments/confirm", { method: "POST", body: { booking_id: bookingId } });
    toast("Paid (demo mode, no real money moved)"); return afterPay();
  }
  await loadRazorpay();
  new window.Razorpay({
    key: co.key_id, order_id: co.order_id, amount: Math.round(co.amount * 100), currency: co.currency,
    name: "EV Share", description: `Booking #${bookingId}`,
    handler: guard(async (r) => {
      await api("/payments/confirm", { method: "POST", body: { booking_id: bookingId, payment_id: r.razorpay_payment_id, signature: r.razorpay_signature } });
      toast("Payment successful"); afterPay();
    }),
  }).open();
}
function afterPay() { showView("bookings"); }

/* ---------- my bookings ---------- */
const payBadge = { PAID: "ok", REFUNDED: "warn", PENDING: "warn", UNPAID: "err" };
async function loadBookings() {
  const list = await guard(() => api("/bookings/mine"))(); if (!list) return;
  const box = $("#bookings"); box.replaceChildren();
  if (!list.length) return box.append(el("p", { className: "muted", textContent: "No bookings yet. Find a charger and reserve a slot." }));
  const now = new Date();
  list.forEach((b) => {
    const cancelled = b.status === "CANCELLED", ended = utc(b.end_time) < now;
    const actions = el("div", { className: "actions" });
    if (!cancelled && b.payment_status !== "PAID") actions.append(el("button", { className: "btn sm", textContent: "Pay now", onclick: guard(() => startPayment(b.id)) }));
    if (!cancelled && !ended) actions.append(el("button", { className: "btn danger sm", textContent: "Cancel", onclick: guard(() => cancelBooking(b.id)) }));
    if (!cancelled && ended && !b.reviewed) actions.append(el("button", { className: "btn ghost sm", textContent: "Leave a review", onclick: () => openReviewForm(b.id) }));
    box.append(el("div", { className: "card" },
      el("div", { className: "card-top" }, el("h4", { textContent: b.charger_title }),
        el("div", { className: "badges" }, el("span", { className: "badge " + (cancelled ? "err" : "ok"), textContent: b.status }),
          el("span", { className: "badge " + (payBadge[b.payment_status] || ""), textContent: b.payment_status }))),
      el("div", { className: "muted small", textContent: `${fmtRange(b.start_time, b.end_time)} · ${money(b.estimated_cost)}` }), actions));
  });
}
async function cancelBooking(id) {
  if (!confirm("Cancel this booking? A paid booking will be refunded.")) return;
  await api(`/bookings/${id}/cancel`, { method: "POST" }); toast("Booking cancelled"); loadBookings();
}

/* ---------- reviews ---------- */
async function openReviews(c) {
  const list = await api(`/reviews/charger/${c.id}`);
  $("#r-title").textContent = `${c.title}: reviews`;
  const box = $("#r-list"); box.replaceChildren();
  list.forEach((r) => box.append(el("div", { className: "card" },
    el("div", { className: "card-top" }, el("strong", { textContent: r.user_name }), el("span", { className: "stars", textContent: "★".repeat(r.rating) + "☆".repeat(5 - r.rating) })),
    r.comment ? el("div", { textContent: r.comment }) : null,
    el("div", { className: "muted small", textContent: utc(r.created_at).toLocaleDateString() }))));
  $("#dlg-reviews").showModal();
}
let rating = 5;
function paintStars() { document.querySelectorAll("#star-input span").forEach((s) => s.classList.toggle("on", Number(s.dataset.v) <= rating)); }
for (let i = 1; i <= 5; i++) $("#star-input").append(el("span", { textContent: "★", dataset: { v: i }, onclick: () => { rating = i; paintStars(); } }));
function openReviewForm(bookingId) { state.reviewBookingId = bookingId; rating = 5; paintStars(); $("#rv-comment").value = ""; $("#dlg-review").showModal(); }
onSubmit($("#review-form"), async () => {
  await api("/reviews", { method: "POST", body: { booking_id: state.reviewBookingId, rating, comment: $("#rv-comment").value } });
  $("#dlg-review").close(); toast("Thanks for your review!"); loadBookings();
});

/* ---------- my chargers (owner) ---------- */
async function loadMyChargers() {
  const list = await guard(() => api("/chargers/mine"))(); if (!list) return;
  const box = $("#my-chargers"); box.replaceChildren();
  if (!list.length) return box.append(el("p", { className: "muted", textContent: "You haven't shared a charger yet." }));
  list.forEach((c) => {
    const card = chargerCard(c, { owner: true });
    card.querySelector(".actions").append(
      el("button", { className: "btn ghost sm", textContent: c.is_active ? "Pause listing" : "Resume listing",
        onclick: guard(async () => { await api(`/chargers/${c.id}`, { method: "PATCH", body: { is_active: !c.is_active } }); loadMyChargers(); }) }),
      el("button", { className: "btn ghost sm", textContent: "Bookings", onclick: guard(() => openOwnerBookings(c)) }));
    box.append(card);
  });
}
async function openOwnerBookings(c) {
  const list = await api(`/bookings/charger/${c.id}`);
  $("#o-title").textContent = `${c.title}: bookings`;
  const box = $("#o-list"); box.replaceChildren();
  if (!list.length) box.append(el("p", { className: "muted", textContent: "No bookings yet." }));
  list.forEach((b) => {
    const row = el("div", { className: "card" }, el("div", { className: "card-top" },
      el("strong", { textContent: fmtRange(b.start_time, b.end_time) }),
      el("div", { className: "badges" }, el("span", { className: "badge", textContent: b.status }), el("span", { className: "badge " + (payBadge[b.payment_status] || ""), textContent: b.payment_status }))),
      el("div", { className: "muted small", textContent: money(b.estimated_cost) }));
    if (b.status === "CONFIRMED" && utc(b.end_time) > new Date())
      row.append(el("div", { className: "actions" }, el("button", { className: "btn danger sm", textContent: "Cancel booking",
        onclick: guard(async () => { if (confirm("Cancel this booking? The driver will be refunded if they paid.")) { await api(`/bookings/${b.id}/cancel`, { method: "POST" }); $("#dlg-owner").close(); toast("Booking cancelled"); } }) })));
    box.append(row);
  });
  $("#dlg-owner").showModal();
}

/* ---------- share a charger ---------- */
function setPick(lat, lng) {
  const f = $("#add-form").elements;
  f.latitude.value = lat.toFixed(6); f.longitude.value = lng.toFixed(6);
  if (state.pickMarker) state.pickMarker.setLatLng([lat, lng]); else state.pickMarker = L.marker([lat, lng], { icon: pinIcon(true) }).addTo(state.maps.pick);
}
$("#btn-pick-locate").onclick = guard(async () => { const p = await getPosition(); state.maps.pick.setView([p.latitude, p.longitude], 16); setPick(p.latitude, p.longitude); });
$("#limit-hours").addEventListener("change", (e) => { $("#hours-box").hidden = $("#hours-hint").hidden = !e.target.checked; });
["latitude", "longitude"].forEach((n) => $("#add-form").elements[n].addEventListener("change", () => {
  const f = $("#add-form").elements, lat = parseFloat(f.latitude.value), lng = parseFloat(f.longitude.value);
  if (!isNaN(lat) && !isNaN(lng)) { setPick(lat, lng); state.maps.pick.setView([lat, lng], 15); }
}));
onSubmit($("#add-form"), async (e) => {
  const f = e.target.elements, body = {
    title: f.title.value, address: f.address.value, connector_type: f.connector_type.value,
    latitude: Number(f.latitude.value), longitude: Number(f.longitude.value),
    power_kw: Number(f.power_kw.value), price_per_kwh: Number(f.price_per_kwh.value),
  };
  if ($("#limit-hours").checked) Object.assign(body, { available_from: f.available_from.value, available_to: f.available_to.value, timezone: f.timezone.value });
  await api("/chargers", { method: "POST", body });
  e.target.reset(); $("#hours-box").hidden = $("#hours-hint").hidden = true;
  if (state.pickMarker) { state.pickMarker.remove(); state.pickMarker = null; }
  toast("Charger listed. Drivers can now find it."); showView("chargers");
});

/* ---------- boot ---------- */
(async function init() {
  state.maps.find = makeMap("map-find");
  if (state.token) { try { state.user = await api("/auth/me"); } catch { state.token = null; } }
  renderAuth();
  await guard(() => runSearch({ fit: true }))();
})();
