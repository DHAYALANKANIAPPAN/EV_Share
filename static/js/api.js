function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = ok; s.onerror = () => no(new Error("Couldn't load the payment window. Check your connection and try again.")); document.head.append(s);
  });
}
async function call(path, { method = "GET", body, form, fd } = {}) {
  const headers = { "X-Requested-With": "evshare" };  // the session cookie is HttpOnly; this header blocks cross-site forms
  if (body && !fd) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: fd || (form ? new URLSearchParams(form) : body && JSON.stringify(body)) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => e.msg.replace(/^Value error, /, "")).join(". ") : d || "Something went wrong. Try again.");
  }
  return data;
}
export const api = {
  me: () => call("/auth/me"),
  async signIn(email, password) { await call("/auth/login", { method: "POST", form: { username: email, password } }); return call("/auth/me"); },
  async register(name, email, password, role, hub_type) { await call("/auth/register", { method: "POST", body: { name, email, password, role, hub_type } }); return this.signIn(email, password); },
  async staffSignIn(email, password) { await call("/auth/staff/login", { method: "POST", form: { username: email, password } }); return call("/auth/me"); },
  verification: () => call("/verification/status"),
  sendCode: () => call("/verification/otp/send", { method: "POST" }),
  confirmCode: (code) => call("/verification/otp/confirm", { method: "POST", body: { code } }),
  setVehicle: (vehicle_number) => call("/verification/vehicle", { method: "PUT", body: { vehicle_number } }),
  uploadDoc(doc_type, file) { const fd = new FormData(); fd.append("doc_type", doc_type); fd.append("file", file); return call("/verification/documents", { method: "POST", fd }); },
  submitVerification: (consent) => call("/verification/submit", { method: "POST", body: { consent } }),
  adminQueue: () => call("/admin/verifications"),
  adminDecide: (id, approve, reason) => call(`/admin/verifications/${id}/decision`, { method: "POST", body: { approve, reason } }),
  docUrl: (id) => `/admin/documents/${id}/file`,
  signOut: () => call("/auth/logout", { method: "POST" }).catch(() => {}),
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
    const confirm = (extra = {}) => call("/payments/confirm", { method: "POST", body: { booking_id: id, ...extra } });
    if (co.provider === "mock") return void (await confirm());
    await loadRazorpay();
    await new Promise((resolve, reject) => {
      const rz = new window.Razorpay({
        key: co.key_id, order_id: co.order_id, amount: Math.round(co.amount * 100), currency: co.currency,
        name: "EV Share", description: `Booking #${id}`, theme: { color: "#047857" },
        handler: (r) => confirm({ payment_id: r.razorpay_payment_id, signature: r.razorpay_signature }).then(resolve, reject),
        modal: { ondismiss: () => reject(new Error("Payment window closed. You can finish paying from My bookings before the hold ends.")) },
      });
      rz.on("payment.failed", (r) => reject(new Error((r.error && r.error.description) || "The payment didn't go through. Try again or use another method.")));
      rz.open();
    });
  },
};
