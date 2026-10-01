/* Umeed frontend — a small vanilla-JS single-page app.
   State lives in localStorage so a member stays signed in on their device. */

(() => {
  "use strict";

  const LS_KEY = "umeed.member";
  let member = loadMember();        // { id, name, phone, is_manager }
  let currentTab = "upcoming";

  // ---------- tiny DOM helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, props = {}, ...kids) => {
    const n = Object.assign(document.createElement(tag), props);
    for (const k of kids) n.append(k?.nodeType ? k : document.createTextNode(k ?? ""));
    return n;
  };

  function loadMember() {
    try { return JSON.parse(localStorage.getItem(LS_KEY)) || null; }
    catch { return null; }
  }
  function saveMember(m) {
    member = m;
    try { localStorage.setItem(LS_KEY, JSON.stringify(m)); } catch { /* private mode */ }
  }
  function clearMember() {
    member = null;
    try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ }
  }

  // ---------- API ----------
  async function api(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (member) {
      headers["X-Member-Id"] = String(member.id);
      headers["X-Member-Phone"] = member.phone;
    }
    const res = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = {};
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) throw new Error(data.error || "Request failed. Please try again.");
    return data;
  }

  // ---------- formatting ----------
  function fmtDate(iso) {
    const d = new Date(iso);
    return {
      day: d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }),
      time: d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
      full: d.toLocaleString(undefined, {
        weekday: "long", day: "numeric", month: "long",
        hour: "numeric", minute: "2-digit",
      }),
    };
  }
  const esc = (s) => String(s ?? "");

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, 2600);
  }

  // ---------- screen switching ----------
  function render() {
    const joined = !!member;
    $("#join-screen").hidden = joined;
    $("#app").hidden = !joined;
    if (!joined) return;

    $("#manager-badge").hidden = !member.is_manager;
    $("#fab").hidden = !member.is_manager;
    $("#who-btn").textContent = initials(member.name);
    loadDrives();
    loadReminders();
  }

  function initials(name) {
    return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("") || "?";
  }

  // ---------- join ----------
  $("#join-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("#join-name").value.trim();
    const phone = $("#join-phone").value.trim();
    const errEl = $("#join-error");
    errEl.textContent = "";
    try {
      const { member: m, returning } = await api("POST", "/api/join", { name, phone });
      saveMember(m);
      render();
      toast(returning ? `Welcome back, ${m.name.split(" ")[0]}!` : `Welcome to Umeed, ${m.name.split(" ")[0]}!`);
    } catch (err) {
      errEl.textContent = err.message;
    }
  });

  // ---------- drives list ----------
  async function loadDrives() {
    const list = $("#drive-list");
    list.innerHTML = "";
    let drives = [];
    try {
      ({ drives } = await api("GET", `/api/drives?scope=${currentTab}`));
    } catch (err) {
      list.append(el("p", { className: "empty" }, err.message));
      return;
    }
    if (!drives.length) {
      list.append(emptyState());
      return;
    }
    for (const d of drives) list.append(driveCard(d));
  }

  function emptyState() {
    const wrap = el("div", { className: "empty" });
    wrap.append(el("span", { className: "big" }, currentTab === "past" ? "🗂️" : "🌤️"));
    wrap.append(el("p", {},
      currentTab === "past"
        ? "No past drives yet."
        : (member.is_manager
            ? "No upcoming drives. Tap + to announce one."
            : "No upcoming drives yet. You'll see them here as soon as they're announced.")));
    return wrap;
  }

  function driveCard(d) {
    const { day, time } = fmtDate(d.start_time);
    const card = el("div", { className: "card" + (d.cancelled ? " cancelled" : "") });

    card.append(el("div", { className: "card-date" }, `${day} · ${time}`));

    const title = el("h3", {}, d.title);
    if (d.cancelled) title.append(el("span", { className: "chip-cancelled" }, "Cancelled"));
    title.addEventListener("click", () => openDetail(d.id));
    card.append(title);

    if (d.location) card.append(el("p", { className: "where" }, d.location));

    const counts = el("div", { className: "counts" });
    counts.append(mk(`${d.counts.going}`, "going"));
    counts.append(mk(`${d.counts.maybe}`, "maybe"));
    card.append(counts);
    function mk(n, label) {
      const s = el("span", {});
      s.append(el("b", {}, n), ` ${label}`);
      return s;
    }

    if (!d.is_past && !d.cancelled) card.append(rsvpRow(d));

    const more = el("button", {
      className: "btn btn-ghost", style: "margin-top:.6rem;padding:.45rem;font-size:.85rem;",
    }, "View details & who's joining");
    more.addEventListener("click", () => openDetail(d.id));
    card.append(more);
    return card;
  }

  function rsvpRow(d) {
    const row = el("div", { className: "rsvp" });
    const opts = [["going", "✅ Going"], ["maybe", "🤔 Maybe"], ["no", "❌ Can't"]];
    for (const [val, label] of opts) {
      const b = el("button", {}, label);
      if (d.my_status === val) b.classList.add(`sel-${val}`);
      b.addEventListener("click", async () => {
        try {
          const { drive } = await api("POST", `/api/drives/${d.id}/rsvp`, { status: val });
          // Refresh just this card in place.
          const fresh = driveCard(drive);
          d = drive;
          row.closest(".card").replaceWith(fresh);
          toast(val === "going" ? "You're in! 🎉" : val === "maybe" ? "Marked as maybe." : "Marked as can't make it.");
          loadReminders();
        } catch (err) { toast(err.message); }
      });
      row.append(b);
    }
    return row;
  }

  // ---------- drive detail ----------
  async function openDetail(id) {
    const overlay = $("#detail-overlay");
    const body = $("#detail-body");
    body.innerHTML = "<p class='muted'>Loading…</p>";
    overlay.hidden = false;
    let d;
    try { ({ drive: d } = await api("GET", `/api/drives/${id}`)); }
    catch (err) { body.innerHTML = ""; body.append(el("p", { className: "muted" }, err.message)); return; }

    const { full } = fmtDate(d.start_time);
    body.innerHTML = "";
    const h = el("h2", { id: "detail-title" }, d.title);
    if (d.cancelled) h.append(el("span", { className: "chip-cancelled" }, "Cancelled"));
    body.append(h);
    body.append(el("p", { className: "detail-when" }, "🗓️ " + full));
    if (d.location) body.append(el("p", { className: "detail-where" }, "📍 " + d.location));
    if (d.description) body.append(el("p", { className: "detail-desc" }, d.description));

    if (!d.is_past && !d.cancelled) body.append(rsvpRow(d));

    body.append(attendGroup("Going", d.attendees.going, ""));
    body.append(attendGroup("Maybe", d.attendees.maybe, "maybe"));

    if (member.is_manager) {
      const actions = el("div", { className: "manager-actions" });
      const edit = el("button", { className: "btn btn-secondary" }, "Edit drive");
      edit.addEventListener("click", () => { overlay.hidden = true; openDriveForm(d); });
      actions.append(edit);
      body.append(actions);
    }
  }

  function attendGroup(label, names, cls) {
    const g = el("div", { className: "attend-group" });
    g.append(el("h4", {}, `${label} (${names.length})`));
    if (!names.length) {
      g.append(el("p", { className: "muted small" }, "No one yet."));
    } else {
      const pills = el("div", { className: "name-pills" });
      for (const n of names) pills.append(el("span", { className: "name-pill " + cls }, n));
      g.append(pills);
    }
    return g;
  }

  // ---------- announce / edit drive ----------
  function openDriveForm(d) {
    const overlay = $("#drive-form-overlay");
    $("#drive-form-title").textContent = d ? "Edit drive" : "Announce a drive";
    $("#drive-id").value = d ? d.id : "";
    $("#d-title").value = d ? d.title : "";
    $("#d-start").value = d ? toLocalInput(d.start_time) : "";
    $("#d-end").value = d && d.end_time ? toLocalInput(d.end_time) : "";
    $("#d-location").value = d ? d.location : "";
    $("#d-desc").value = d ? d.description : "";
    $("#cancel-row").hidden = !d;
    $("#d-cancel").checked = d ? d.cancelled : false;
    $("#drive-form-error").textContent = "";
    overlay.hidden = false;
  }

  function toLocalInput(iso) {
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fromLocalInput(val) {
    return val ? new Date(val).toISOString() : "";
  }

  $("#drive-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("#drive-form-error");
    errEl.textContent = "";
    const id = $("#drive-id").value;
    const payload = {
      title: $("#d-title").value.trim(),
      start_time: fromLocalInput($("#d-start").value),
      end_time: fromLocalInput($("#d-end").value),
      location: $("#d-location").value.trim(),
      description: $("#d-desc").value.trim(),
    };
    try {
      if (id) {
        payload.cancelled = $("#d-cancel").checked;
        await api("PATCH", `/api/drives/${id}`, payload);
        toast("Drive updated.");
      } else {
        await api("POST", "/api/drives", payload);
        toast("Drive announced! 📣");
      }
      $("#drive-form-overlay").hidden = true;
      currentTab = "upcoming";
      syncTabs();
      loadDrives();
      loadReminders();
    } catch (err) {
      errEl.textContent = err.message;
    }
  });

  // ---------- reminders ----------
  async function loadReminders() {
    const box = $("#reminders");
    box.innerHTML = "";
    let reminders = [];
    try { ({ reminders } = await api("GET", "/api/reminders")); }
    catch { box.hidden = true; return; }

    if (!reminders.length) { box.hidden = true; return; }
    box.hidden = false;
    for (const r of reminders) {
      const { day, time } = fmtDate(r.start_time);
      const line = el("div", { className: "reminder" });
      line.append(el("span", { className: "bell" }, "🔔"));
      const text = el("div", {});
      if (r.needs_rsvp) {
        text.append(el("strong", {}, `${r.title} — ${day}, ${time}. `), "Are you joining? ");
      } else if (r.my_status === "going") {
        text.append(el("strong", {}, `Coming up: ${r.title}`), ` — ${day}, ${time}. See you there!`);
      } else {
        text.append(el("strong", {}, `${r.title} — ${day}, ${time}.`));
      }
      const link = el("a", { href: "#", style: "color:inherit;font-weight:700;" }, " Open");
      link.addEventListener("click", (e) => { e.preventDefault(); openDetail(r.drive_id); });
      text.append(link);
      line.append(text);
      box.append(line);
    }
  }

  // ---------- account / manager ----------
  $("#who-btn").addEventListener("click", async () => {
    $("#account-name").textContent = member.name;
    $("#account-phone").textContent = member.phone;
    $("#unlock-block").hidden = member.is_manager;
    const membersBlock = $("#members-block");
    membersBlock.hidden = !member.is_manager;
    if (member.is_manager) await loadMembers();
    $("#account-overlay").hidden = false;
  });

  async function loadMembers() {
    try {
      const { members } = await api("GET", "/api/members");
      $("#members-count").textContent = members.length;
      const ul = $("#members-list");
      ul.innerHTML = "";
      for (const m of members) {
        const li = el("li", {});
        li.append(el("span", {}, m.name));
        li.append(m.is_manager
          ? el("span", { className: "tag" }, "Manager")
          : el("span", { className: "muted small" }, m.phone));
        ul.append(li);
      }
    } catch (err) { toast(err.message); }
  }

  $("#unlock-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("#unlock-error");
    errEl.textContent = "";
    try {
      const { member: m } = await api("POST", "/api/manager/unlock", { passcode: $("#unlock-code").value });
      saveMember(m);
      $("#account-overlay").hidden = true;
      render();
      toast("Manager tools unlocked. 🛠️");
    } catch (err) {
      errEl.textContent = err.message;
    }
  });

  $("#logout-btn").addEventListener("click", () => {
    clearMember();
    $("#account-overlay").hidden = true;
    render();
  });

  // ---------- tabs ----------
  function syncTabs() {
    $$(".tab").forEach((t) => t.classList.toggle("is-active", t.dataset.tab === currentTab));
  }
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    currentTab = t.dataset.tab;
    syncTabs();
    loadDrives();
  }));

  // ---------- overlay wiring ----------
  $("#fab").addEventListener("click", () => openDriveForm(null));
  document.addEventListener("click", (e) => {
    if (e.target.matches("[data-close-detail]") || e.target.id === "detail-overlay")
      $("#detail-overlay").hidden = true;
    if (e.target.matches("[data-close-form]") || e.target.id === "drive-form-overlay")
      $("#drive-form-overlay").hidden = true;
    if (e.target.matches("[data-close-account]") || e.target.id === "account-overlay")
      $("#account-overlay").hidden = true;
  });

  // ---------- go ----------
  render();
})();
