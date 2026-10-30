export const h = (tag, a = {}, ...kids) => {
  const { dataset, ...rest } = a, n = Object.assign(document.createElement(tag), rest);
  if (dataset) Object.assign(n.dataset, dataset);
  kids.flat().forEach((k) => k != null && n.append(k));
  return n;
};
export const $ = (s, r = document) => r.querySelector(s);
export const icon = (name, cls = "size-4") => h("i", { className: cls, dataset: { lucide: name } });
export const refreshIcons = () => window.lucide && window.lucide.createIcons();
export const money = (n) => `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
export const utc = (s) => new Date(s.endsWith("Z") ? s : s + "Z");
export const fmtRange = (a, b) => {
  const s = utc(a), e = utc(b), t = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${s.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}, ${t(s)} to ${t(e)}`;
};
export function toast(msg, err = false) {
  const t = h("div", { className: "toast" + (err ? " toast-err" : ""), role: err ? "alert" : "status" }, icon(err ? "alert-circle" : "check-circle-2", "size-5"), h("span", { textContent: msg }),
    h("button", { type: "button", "aria-label": "Dismiss", onclick: () => t.remove() }, icon("x", "size-4")));
  $("#toasts").append(t); refreshIcons(); setTimeout(() => t.remove(), err ? 7000 : 4000);
}

/* small display helpers shared by both pages */
export const pill = (text, tone = "", ic) => h("span", { className: ["pill", ...tone.split(" ").filter(Boolean).map((t) => "pill-" + t)].join(" ") }, ic ? icon(ic, "size-3.5") : null, text);
export const chip = (text) => h("span", { className: "chip", textContent: text });
export const progress = (start, end) => h("div", { className: "progress", role: "progressbar", "aria-label": "Session progress", dataset: { start, end } }, h("span", { style: "width:0%" }));

/* live countdown to a deadline (ISO string, naive UTC like the API). `onExpire` runs once when it reaches zero. */
export const countdown = (iso, label = "") => h("span", { className: "countdown", dataset: { deadline: iso.endsWith("Z") ? iso : iso + "Z", label } }, "…");
let tickerStarted = false;
export function startTicker(onExpire) {
  if (tickerStarted) return; tickerStarted = true;
  const fmt = (ms) => { const t = Math.max(0, Math.floor(ms / 1000)), h_ = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60; return (h_ ? `${h_}:${String(m).padStart(2, "0")}` : String(m)) + `:${String(sec).padStart(2, "0")}`; };
  setInterval(() => {
    const now = Date.now(); let expired = false;
    document.querySelectorAll("[data-deadline]").forEach((n) => {
      const left = new Date(n.dataset.deadline) - now;
      if (left <= 0) { if (n.dataset.done !== "1") { n.dataset.done = "1"; expired = true; } n.textContent = "now"; }
      else { n.textContent = fmt(left); n.dataset.urgent = String(left < 120000); }
    });
    document.querySelectorAll(".progress[data-start]").forEach((n) => {
      const s0 = new Date(n.dataset.start.endsWith("Z") ? n.dataset.start : n.dataset.start + "Z"), e0 = new Date(n.dataset.end.endsWith("Z") ? n.dataset.end : n.dataset.end + "Z");
      n.firstChild.style.width = `${Math.min(100, Math.max(0, ((now - s0) / (e0 - s0)) * 100)).toFixed(1)}%`;
    });
    if (expired && onExpire) onExpire();
  }, 1000);
}

/* run an async action with a spinner on the button that triggered it */
export async function busy(btn, label, fn) {
  const text = btn.textContent; btn.setAttribute("aria-busy", "true"); btn.disabled = true; btn.textContent = label;
  try { return await fn(); } finally { btn.removeAttribute("aria-busy"); btn.disabled = false; if (btn.isConnected) btn.textContent = text; }
}

export function setTheme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  try { localStorage.setItem("ev_theme", dark ? "dark" : "light"); } catch {}
}
export const isDark = () => document.documentElement.classList.contains("dark");
export function confirmDialog({ title, body, confirm, keep = "Keep it" }) {
  return new Promise((res) => {
    const d = $("#dlg"), opener = document.activeElement;
    const no = h("button", { className: "btn", textContent: keep, type: "button", onclick: () => d.close("no") });
    const yes = h("button", { className: "btn btn-danger", textContent: confirm, type: "button", onclick: () => d.close("yes") });
    d.replaceChildren(h("h2", { className: "font-semibold text-lg", textContent: title }), h("p", { className: "text-mute text-sm mt-2", textContent: body }),
      h("div", { className: "flex justify-end gap-2 mt-6" }, no, yes));
    d.onclose = () => { res(d.returnValue === "yes"); opener && opener.focus && opener.focus(); };
    d.showModal(); no.focus();
  });
}
