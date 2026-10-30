import { api } from "./api.js";
import { $, h, icon, refreshIcons, toast, pill } from "./ui.js";

const S = { user: null, queue: [], loading: false, tab: "apps", users: { items: [], total: 0 }, f: { role: "", state: "all", q: "" } };
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

function render() {
  const user = $("#user");
  user.replaceChildren(...(S.user ? [h("span", { className: "text-sm text-mute", textContent: S.user.name }),
    h("button", { className: "btn", textContent: "Sign out", onclick: async () => { await api.signOut(); S.user = null; render(); } })] : []));
  $("#main").replaceChildren(S.user ? h("div", { className: "grid gap-6" }, tabs(), S.tab === "apps" ? queueView() : usersView()) : loginView()); refreshIcons();
}

function loginView() {
  const email = h("input", { id: "s-email", type: "email", required: true, autocomplete: "username" }), pass = h("input", { id: "s-pass", type: "password", required: true, autocomplete: "current-password" });
  const f = (id, t, el) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: t }), el);
  return h("form", { className: "panel p-6 grid gap-4 max-w-sm mx-auto mt-10", onsubmit: guard(async (e) => {
      e.preventDefault(); S.user = await api.staffSignIn(email.value, pass.value); toast(`Welcome, ${S.user.name}`); await load(); }) },
    h("h1", { className: "text-xl font-semibold", textContent: "Reviewer sign in" }), h("p", { className: "text-sm text-mute", textContent: "For EV Share staff who check driver and hub documents." }),
    f("s-email", "Email", email), f("s-pass", "Password", pass), h("button", { className: "btn btn-primary", type: "submit", textContent: "Sign in" }));
}

const tabs = () => h("div", { className: "flex gap-1 border-b border-line", role: "tablist" }, [["apps", "Applications"], ["users", "Users"]].map(([id, t]) =>
  h("button", { role: "tab", "aria-selected": String(S.tab === id), className: "tab" + (S.tab === id ? " is-active" : ""), textContent: t,
    onclick: async () => { S.tab = id; id === "users" ? await loadUsers() : await load(); } })));

async function load() { S.loading = true; render(); try { S.queue = await api.adminQueue(); } finally { S.loading = false; render(); } }

function queueView() {
  const head = h("div", {}, h("h1", { className: "text-2xl font-semibold tracking-tight", textContent: "Review applications" }),
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

/* ---------- users: list, remove, restore ---------- */
async function loadUsers(more = false) {
  const p = { limit: 25, offset: more ? S.users.items.length : 0, state: S.f.state }; if (S.f.role) p.role = S.f.role; if (S.f.q.trim()) p.q = S.f.q.trim();
  if (!more) { S.loading = true; render(); }
  try { const r = await api.adminUsers(p); S.users = more ? { items: [...S.users.items, ...r.items], total: r.total } : r; } finally { S.loading = false; render(); }
}
const badge = (t, cls = "") => pill(t, cls.includes("accent") ? "ok" : cls.includes("danger") ? "danger" : "");
function usersView() {
  const sel = (id, label, opts, key) => h("div", { className: "field" }, h("label", { htmlFor: id, textContent: label }), h("select", { id, onchange: guard(async (e) => { S.f[key] = e.target.value; await loadUsers(); }) },
    opts.map(([v, t]) => h("option", { value: v, textContent: t, selected: S.f[key] === v }))));
  const q = h("input", { id: "u-q", type: "search", value: S.f.q, placeholder: "Name or email", onkeydown: (e) => { if (e.key === "Enter") { S.f.q = e.target.value; guard(loadUsers)(); } } });
  const filters = h("div", { className: "panel p-4 grid gap-4 sm:grid-cols-[1fr_1fr_2fr_auto] items-end" }, sel("u-role", "Type", [["", "Drivers and hubs"], ["DRIVER", "Drivers"], ["HUB", "Hubs"]], "role"),
    sel("u-state", "Status", [["all", "All"], ["active", "Active"], ["removed", "Removed"]], "state"), h("div", { className: "field" }, h("label", { htmlFor: "u-q", textContent: "Search" }), q),
    h("button", { className: "btn", textContent: "Search", onclick: guard(async () => { S.f.q = q.value; await loadUsers(); }) }));
  const head = h("h1", { className: "text-2xl font-semibold tracking-tight", textContent: "Users" });
  if (S.loading) return h("div", { className: "grid gap-4" }, head, filters, h("div", { className: "panel p-6" }, h("div", { className: "sk h-4 w-1/2" })));
  const { items, total } = S.users;
  const list = !items.length ? h("section", { className: "panel p-8 grid gap-2 justify-items-start" }, icon("users", "size-6 text-mute"), h("h2", { className: "font-semibold text-lg", textContent: "No users match" }),
      h("p", { className: "text-sm text-mute", textContent: "Try a different filter or search." }))
    : h("ul", { className: "panel overflow-hidden" }, items.map((u) => h("li", { className: "row" },
      h("div", { className: "grid gap-1 min-w-0" }, h("h3", { className: "font-medium", textContent: u.name }), h("p", { className: "text-sm text-mute break-all", textContent: u.email }),
        h("div", { className: "flex gap-2 flex-wrap" }, badge(u.role === "HUB" ? `Hub, ${u.hub_type.toLowerCase()}` : "Driver"), badge(u.verification_status.replace("_", " ").toLowerCase(), u.verification_status === "APPROVED" ? "border-accent text-accent" : ""),
          u.vehicle_number ? badge(u.vehicle_number) : null, !u.is_active ? badge("Removed", "border-danger text-danger") : null),
        !u.is_active && u.removal_reason ? h("p", { className: "text-sm", textContent: `Reason: ${u.removal_reason}` }) : null),
      h("div", { className: "flex gap-2 items-center self-start" }, u.is_active
        ? h("button", { className: "btn btn-danger", textContent: "Remove", onclick: () => askRemove(u) })
        : h("button", { className: "btn", textContent: "Restore", onclick: guard(async () => { await api.adminRestore(u.id); toast(`${u.name} restored`); await loadUsers(); }) })))));
  return h("div", { className: "grid gap-4" }, head, filters, h("p", { className: "text-sm text-mute", textContent: `${total} ${total === 1 ? "user" : "users"}` }), list,
    items.length < total ? h("div", {}, h("button", { className: "btn", textContent: "Show more", onclick: guard(() => loadUsers(true)) })) : null);
}
function askRemove(u) {
  const d = $("#dlg"), opener = document.activeElement, why = h("textarea", { id: "rm-why", maxLength: 500, required: true, minLength: 5, placeholder: "e.g. The documents you submitted did not match official records." });
  d.onclose = () => opener && opener.focus && opener.focus();
  d.replaceChildren(h("form", { className: "grid gap-4", onsubmit: guard(async (e) => {
      e.preventDefault(); const r = await api.adminRemove(u.id, why.value); d.close();
      toast(r.email_sent ? `${u.name} removed and emailed. ${r.cancelled_bookings} upcoming booking(s) cancelled.` : `${u.name} removed, but the email could not be sent. Tell them another way.`, !r.email_sent); await loadUsers(); }) },
    h("h2", { className: "font-semibold text-lg", textContent: `Remove ${u.name}?` }),
    h("p", { className: "text-sm text-mute", textContent: "They will get an email with your reason and their login will stop working. Upcoming bookings are cancelled and refunded. Their email address stays reserved, so they must register again with a different one." }),
    h("div", { className: "field" }, h("label", { htmlFor: "rm-why", textContent: "Reason (sent to the user)" }), why),
    h("div", { className: "flex justify-end gap-2" }, h("button", { className: "btn", type: "button", textContent: "Keep account", onclick: () => d.close() }), h("button", { className: "btn btn-danger", type: "submit", textContent: "Remove account" }))));
  d.showModal(); why.focus();
}

(async function init() {
  try { const me = await api.me(); if (me.is_admin) { S.user = me; await load(); return; } } catch { /* not signed in */ }
  render();
})();
