import { api } from "./api.js";
import { $, h, icon, refreshIcons, toast } from "./ui.js";

const S = { user: null, queue: [], loading: false };
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

function render() {
  const user = $("#user");
  user.replaceChildren(...(S.user ? [h("span", { className: "text-sm text-mute", textContent: S.user.name }),
    h("button", { className: "btn", textContent: "Sign out", onclick: async () => { await api.signOut(); S.user = null; render(); } })] : []));
  $("#main").replaceChildren(S.user ? queueView() : loginView()); refreshIcons();
}

function loginView() {
  const email = h("input", { id: "s-email", type: "email", required: true, autocomplete: "username" }), pass = h("input", { id: "s-pass", type: "password", required: true, autocomplete: "current-password" });
  const f = (id, t, el) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el);
  return h("form", { className: "panel p-6 grid gap-4 max-w-sm mx-auto mt-10", onsubmit: guard(async (e) => {
      e.preventDefault(); S.user = await api.staffSignIn(email.value, pass.value); toast(`Welcome, ${S.user.name}`); await load(); }) },
    h("h1", { className: "text-xl font-semibold", textContent: "Reviewer sign in" }), h("p", { className: "text-sm text-mute", textContent: "For EV Share staff who check driver and hub documents." }),
    f("s-email", "Email", email), f("s-pass", "Password", pass), h("button", { className: "btn btn-primary", type: "submit", textContent: "Sign in" }));
}

async function load() { S.loading = true; render(); try { S.queue = await api.adminQueue(); } finally { S.loading = false; render(); } }

function queueView() {
  const head = h("div", {}, h("h1", { className: "text-3xl font-semibold tracking-tight", textContent: "Review applications" }),
    h("p", { className: "text-mute mt-1 max-w-[65ch]", textContent: "Open each document, check it against the official portal, then approve or ask the applicant to fix it." }));
  if (S.loading) return h("div", { className: "grid gap-6" }, head, h("div", { className: "panel p-6" }, h("div", { className: "sk h-4 w-1/2" })));
  if (!S.queue.length) return h("div", { className: "grid gap-6" }, head, h("section", { className: "panel p-8 grid gap-2 justify-items-start" }, icon("inbox", "size-6 text-mute"),
    h("h2", { className: "font-semibold text-lg", textContent: "No applications waiting" }), h("p", { className: "text-sm text-mute", textContent: "New submissions will show up here." })));
  return h("div", { className: "grid gap-6" }, head, h("ul", { className: "panel overflow-hidden" }, S.queue.map((a) => h("li", { className: "row" },
    h("div", { className: "grid gap-2 min-w-0" }, h("h3", { className: "font-medium", textContent: `${a.name} (${a.role === "HUB" ? `Hub, ${a.hub_type.toLowerCase()}` : "Driver"})` }),
      h("p", { className: "text-sm text-mute", textContent: `${a.email}${a.vehicle_number ? `, vehicle ${a.vehicle_number}` : ""}` }),
      h("ul", { className: "flex gap-2 flex-wrap" }, a.documents.map((d) => h("li", {}, h("a", { className: "btn", href: api.docUrl(d.id), target: "_blank", rel: "noopener noreferrer" }, icon("file-text", "size-4"), d.doc_type.replaceAll("_", " ").toLowerCase()))))),
    h("div", { className: "flex gap-2 items-center flex-wrap self-start" },
      h("button", { className: "btn btn-primary", textContent: "Approve", onclick: guard(async () => { await api.adminDecide(a.user_id, true); toast(`${a.name} approved`); await load(); }) }),
      h("button", { className: "btn btn-danger", textContent: "Ask for changes", onclick: () => askReason(a) }))))));
}

function askReason(a) {
  const d = $("#dlg"), opener = document.activeElement, why = h("textarea", { id: "why", maxLength: 500, required: true, minLength: 5, placeholder: "e.g. The RC photo is blurry. Please upload a clearer copy." });
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => { e.preventDefault(); await api.adminDecide(a.user_id, false, why.value); d.close(); toast("Applicant notified in the app"); await load(); }) },
    h("h2", { className: "font-semibold text-lg", textContent: `Ask ${a.name} for changes` }), h("div", { className: "field" }, h("label", { htmlFor: "why", textContent: "What should they fix?" }), why),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Cancel", onclick: () => d.close() }), h("button", { className: "btn btn-danger", type: "submit", textContent: "Send feedback" }))));
  d.showModal(); why.focus();
}

(async function init() {
  try { const me = await api.me(); if (me.is_admin) { S.user = me; await load(); return; } } catch { /* not signed in */ }
  render();
})();
