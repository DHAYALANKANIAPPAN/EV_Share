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
  const t = h("div", { className: "panel px-4 py-3 text-sm " + (err ? "border-danger text-danger" : ""), textContent: msg, role: err ? "alert" : "status" });
  $("#toasts").append(t); setTimeout(() => t.remove(), err ? 6000 : 3500);
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
