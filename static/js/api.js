let token = localStorage.getItem("evshare_token");
async function call(path, { method = "GET", body, form } = {}) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: form ? new URLSearchParams(form) : body && JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => e.msg).join(". ") : d || "Something went wrong. Try again.");
  }
  return data;
}
export const api = {
  hasSession: () => !!token,
  me: () => call("/auth/me"),
  async signIn(email, password) { token = (await call("/auth/login", { method: "POST", form: { username: email, password } })).access_token; localStorage.setItem("evshare_token", token); return call("/auth/me"); },
  async register(name, email, password) { await call("/auth/register", { method: "POST", body: { name, email, password } }); return this.signIn(email, password); },
  signOut() { token = null; localStorage.removeItem("evshare_token"); },
  chargers(f) { const q = new URLSearchParams(); if (f.connector) q.set("connector_type", f.connector); if (f.power) q.set("min_power_kw", f.power); if (f.price) q.set("max_price_per_kwh", f.price); return call(`/chargers?${q}`); },
  createCharger: (body) => call("/chargers", { method: "POST", body }),
  myChargers: () => call("/chargers/mine"),
  setActive: (id, is_active) => call(`/chargers/${id}`, { method: "PATCH", body: { is_active } }),
  chargerBookings: (id) => call(`/bookings/charger/${id}`),
  review: (booking_id, rating, comment) => call("/reviews", { method: "POST", body: { booking_id, rating, comment } }),
  reviews: (id) => call(`/reviews/charger/${id}`),
  book: (charger_id, start, end) => call("/bookings", { method: "POST", body: { charger_id, start_time: start, end_time: end } }),
  bookings: () => call("/bookings/mine"),
  cancel: (id) => call(`/bookings/${id}/cancel`, { method: "POST" }),
  async pay(id) {
    const co = await call("/payments/checkout", { method: "POST", body: { booking_id: id } });
    if (co.status === "PAID") return;
    if (co.provider !== "mock") throw new Error("Card payments open in the classic view at /classic. Pay there to finish.");
    await call("/payments/confirm", { method: "POST", body: { booking_id: id } });
  },
};
