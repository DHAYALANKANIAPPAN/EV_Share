const $ = (id) => document.getElementById(id);
let token = localStorage.getItem("evshare_token");

function say(text, isErr = false) { const m = $("msg"); m.textContent = text; m.className = isErr ? "err" : ""; }

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) { payload = new URLSearchParams(form); }
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => e.msg).join("; ") : d || res.statusText);
  }
  return data;
}

function el(tag, props = {}, ...kids) {
  const n = Object.assign(document.createElement(tag), props);
  kids.forEach((k) => n.append(k));
  return n;
}

function renderAuth() {
  const box = $("auth-box"); box.replaceChildren();
  $("login-sec").hidden = !!token;
  $("add-sec").hidden = $("book-sec").hidden = !token;
  if (token) {
    box.append(el("button", { className: "ghost", textContent: "Sign out", onclick: () => { token = null; localStorage.removeItem("evshare_token"); renderAuth(); $("bookings").replaceChildren(); } }));
    loadBookings();
  }
}

async function signIn(email, password) {
  const data = await api("/auth/login", { method: "POST", form: { username: email, password } });
  token = data.access_token; localStorage.setItem("evshare_token", token);
  renderAuth(); say("Signed in.");
}

$("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  try { await signIn($("email").value, $("password").value); } catch (err) { say(err.message, true); }
};
$("register").onclick = async () => {
  try {
    await api("/auth/register", { method: "POST", body: { email: $("email").value, name: $("name").value || "Driver", password: $("password").value } });
    await signIn($("email").value, $("password").value);
  } catch (err) { say(err.message, true); }
};

$("search-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = new URLSearchParams();
  if ($("lat").value && $("lon").value) { q.set("lat", $("lat").value); q.set("lon", $("lon").value); q.set("radius_km", $("radius").value); }
  if ($("connector").value) q.set("connector_type", $("connector").value);
  try { renderChargers(await api(`/chargers?${q}`)); say(""); } catch (err) { say(err.message, true); }
};

function renderChargers(list) {
  const box = $("results"); box.replaceChildren();
  if (!list.length) return box.append(el("p", { className: "meta", textContent: "No chargers found." }));
  list.forEach((c) => {
    const info = el("div", {}, el("strong", { textContent: c.title }),
      el("div", { className: "meta", textContent: `${c.address} · ${c.connector_type} · ${c.power_kw} kW · ₹${c.price_per_kwh}/kWh${c.distance_km != null ? ` · ${c.distance_km} km` : ""}` }));
    const start = el("input", { type: "datetime-local" }), end = el("input", { type: "datetime-local" });
    const btn = el("button", { textContent: "Book", onclick: () => book(c.id, start.value, end.value) });
    box.append(el("div", { className: "charger" }, info, token ? el("div", { className: "row" }, start, end, btn) : el("span", { className: "meta", textContent: "Sign in to book" })));
  });
}

async function book(chargerId, start, end) {
  if (!start || !end) return say("Pick a start and end time.", true);
  try {
    const b = await api("/bookings", { method: "POST", body: { charger_id: chargerId, start_time: new Date(start).toISOString(), end_time: new Date(end).toISOString() } });
    say(`Booked. Estimated max cost ₹${b.estimated_cost}.`); loadBookings();
  } catch (err) { say(err.message, true); }
}

async function loadBookings() {
  try {
    const list = await api("/bookings/mine"); const box = $("bookings"); box.replaceChildren();
    if (!list.length) return box.append(el("p", { className: "meta", textContent: "No bookings yet." }));
    list.forEach((b) => {
      const when = `${new Date(b.start_time + "Z").toLocaleString()} → ${new Date(b.end_time + "Z").toLocaleTimeString()}`;
      const row = el("div", { className: "charger" }, el("div", {}, el("strong", { textContent: `Charger #${b.charger_id}` }), el("div", { className: "meta", textContent: `${when} · ${b.status} · ₹${b.estimated_cost}` })));
      if (b.status === "CONFIRMED") row.append(el("button", { className: "ghost", textContent: "Cancel", onclick: async () => { try { await api(`/bookings/${b.id}/cancel`, { method: "POST" }); loadBookings(); } catch (err) { say(err.message, true); } } }));
      box.append(row);
    });
  } catch (err) { say(err.message, true); }
}

$("add-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  ["latitude", "longitude", "power_kw", "price_per_kwh"].forEach((k) => (f[k] = Number(f[k])));
  try { await api("/chargers", { method: "POST", body: f }); e.target.reset(); say("Charger added."); } catch (err) { say(err.message, true); }
};

renderAuth();
