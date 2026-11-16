/* HireBot PK – browser UI. Plain JavaScript, no build step.
   All dynamic text is inserted with textContent (never innerHTML) because GitHub profile
   fields are user-controlled. */
"use strict";

const state = {
  requirements: null,   // last parsed requirements (lets the recruiter refine: "make it Lahore")
  query: "",            // last search text, saved in the HR sheet
  busy: false,
};

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function safeHref(url) {
  if (typeof url !== "string") return null;
  if (/^https?:\/\//i.test(url) || url.startsWith("/cv/")) return url;
  return null;
}

const ICON = {
  pin: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  work: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>',
  edu: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10L12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/></svg>',
  clock: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  github: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.700 5.400-5.300 5.700.4.4.8 1.100.8 2.200v3.200c0 .3.2.7.8.6A11.500 11.500 0 0 0 12 .5z"/></svg>',
  linkedin: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M20.4 20.4h-3.6v-5.6c0-1.3 0-3-1.8-3s-2.100 1.400-2.100 2.900v5.700H9.300V9h3.400v1.600c.5-.9 1.600-1.800 3.400-1.800 3.600 0 4.300 2.400 4.300 5.500v6.100zM5.300 7.400a2.100 2.100 0 1 1 0-4.100 2.100 2.100 0 0 1 0 4.100zM7.100 20.400H3.500V9h3.600v11.400z"/></svg>',
  doc: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>',
  mail: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
};

function icon(name) {
  const span = document.createElement("span");
  span.innerHTML = ICON[name];            // static, trusted markup only
  span.style.display = "inline-flex";
  return span;
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error("Cannot reach the server. Is `python run.py` still running?");
  }
  if (!res.ok) {
    let detail = `Server error (${res.status})`;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

const postJSON = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let toastTimer;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3200);
}

const messages = $("#messages");
function scrollDown() { messages.scrollTop = messages.scrollHeight; }

// ----------------------------------------------------------------- messages
function userMessage(text) {
  messages.append(h("div", { class: "msg user" }, h("div", { class: "bubble", text })));
  scrollDown();
}

function botMessage(...content) {
  const stack = h("div", { class: "stack" });
  for (const c of content) if (c) stack.append(c);
  const row = h("div", { class: "msg bot" }, stack);
  messages.append(row);
  scrollDown();
  return stack;
}

const bubble = (text) => h("div", { class: "bubble", text });
const notice = (text, err = false) => h("div", { class: "notice" + (err ? " err" : ""), text });

function typing(labels) {
  const label = h("span", { text: labels[0] });
  const row = h("div", { class: "msg bot" },
    h("div", { class: "bubble typing" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")), label));
  messages.append(row);
  scrollDown();
  let i = 0;
  const timer = setInterval(() => { i = Math.min(i + 1, labels.length - 1); label.textContent = labels[i]; }, 3500);
  return () => { clearInterval(timer); row.remove(); };
}

// ---------------------------------------------------------- candidate cards
function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0] || "").join("").toUpperCase() || "?";
}

function metaItem(iconName, text) {
  return h("span", {}, icon(iconName), text);
}

function experienceText(c) {
  if (c.experience_years === null || c.experience_years === undefined) return "Experience unknown";
  return c.experience_source === "github_estimate"
    ? `~${c.experience_years} yrs on GitHub (estimate)`
    : `${c.experience_years} yrs experience`;
}

function educationText(c) {
  const e = c.education || {};
  if (e.text) return e.text.length > 60 ? e.text.slice(0, 57) + "…" : e.text;
  return "Education unknown";
}

function ringEl(score) {
  const cls = score >= 80 ? "" : score >= 60 ? "mid" : "low";
  const ring = h("div", { class: `ring ${cls}`, role: "img", "aria-label": `${score} percent match` }, h("span", { text: `${score}%` }));
  ring.style.setProperty("--p", score);
  return h("div", { class: "ring-wrap" }, ring, h("div", { class: "ring-label", text: "match" }));
}

function whyPanel(c) {
  const wrap = h("div", { class: "why", hidden: true });
  const m = c.match;
  if (m) {
    for (const b of m.breakdown) {
      const mark = { match: "✓", partial: "~", miss: "✗", unknown: "?" }[b.status];
      const weight = b.weight ? ` (${b.weight}% of score)` : " (not counted)";
      const bar = b.score === null
        ? h("div", { class: "bar unknown" })
        : h("div", { class: "bar" }, h("i", { class: b.status, style: `width:${b.score}%` }));
      wrap.append(h("div", { class: "why-row" },
        h("div", { class: "why-label" }, h("span", { class: `mark ${b.status}`, text: mark }), b.label),
        bar,
        h("div", { class: "why-detail", text: `${b.detail}${weight}` })));
    }
    wrap.append(h("p", { class: "note", text: "The match % shows how closely the available profile data fits your requirements. It is not a hiring prediction. Unknown data is left out, not counted as zero." }));
  }
  if (c.top_repos && c.top_repos.length) {
    const box = h("div", { class: "repos" }, h("b", { text: "Top projects" }));
    for (const r of c.top_repos) {
      const href = safeHref(r.url);
      const name = href ? h("a", { href, target: "_blank", rel: "noopener noreferrer", text: r.name }) : r.name;
      box.append(h("div", { class: "repo-line" }, name,
        ` ${r.language ? "· " + r.language : ""} ${r.stars ? "· ★" + r.stars : ""} ${r.description ? "– " + r.description : ""}`));
    }
    wrap.append(box);
  }
  if (c.projects && c.projects.length) {
    const box = h("div", { class: "repos" }, h("b", { text: "Projects from CV" }));
    for (const p of c.projects) box.append(h("div", { class: "repo-line", text: p }));
    wrap.append(box);
  }
  return wrap;
}

function linkEl(kind, label, url, ic) {
  const href = safeHref(url);
  if (!href) return h("span", { class: "link off", title: `${label} not available` }, icon(ic), `${label}: not available`);
  return h("a", { class: "link", href, target: "_blank", rel: "noopener noreferrer" }, icon(ic), label);
}

function candidateCard(c, rank) {
  const card = h("article", { class: "card" + (c.status === "shortlisted" ? " shortlisted" : ""), "data-id": c.id });
  const score = c.match ? c.match.score : null;

  const avatarHref = safeHref(c.avatar_url);
  const avatar = h("div", { class: "avatar" }, avatarHref
    ? h("img", { src: avatarHref, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
    : initials(c.name));

  const meta = h("div", { class: "meta" },
    metaItem("pin", c.location_raw || "Location unknown"),
    metaItem("work", experienceText(c)),
    metaItem("edu", educationText(c)));
  if (c.last_active) meta.append(metaItem("clock", `Last GitHub activity ${c.last_active}`));

  card.append(h("div", { class: "card-head" },
    rank ? h("div", { class: "rank", text: `#${rank}` }) : null,
    avatar,
    h("div", { class: "who" },
      h("h3", {}, c.name, h("span", { class: "tag" + (c.source === "cv" ? " cv" : ""), text: c.source === "cv" ? "Uploaded CV" : "GitHub" })),
      c.headline ? h("p", { class: "headline", text: c.headline }) : null,
      meta),
    score !== null ? ringEl(score) : null));

  // skill chips: required skills first (with match status), then other skills
  const chips = h("div", { class: "chips" });
  const seen = new Set();
  const mark = { match: "✓", partial: "~", miss: "✗" };
  if (c.match && c.match.skills_detail) {
    for (const s of c.match.skills_detail) {
      seen.add(s.skill.toLowerCase());
      chips.append(h("span", { class: `chip ${s.status}`, title: s.note || "", text: `${mark[s.status]} ${s.skill}` }));
    }
  }
  let extra = 0;
  for (const s of c.skills_display || []) {
    if (seen.has(s.toLowerCase()) || extra >= 6) continue;
    chips.append(h("span", { class: "chip", text: s })); extra++;
  }
  if (chips.children.length) card.append(chips);

  const why = whyPanel(c);
  if (why.children.length) {
    const toggle = h("button", { class: "why-toggle", type: "button", "aria-expanded": "false",
      text: score !== null ? `Why ${score}%?` : "More details" });
    toggle.addEventListener("click", () => {
      why.hidden = !why.hidden;
      toggle.setAttribute("aria-expanded", String(!why.hidden));
    });
    card.append(toggle, why);
  }

  const emailBtn = c.email
    ? h("a", { class: "link", href: "#", onclick: (e) => { e.preventDefault(); openContact(c); } }, icon("mail"), c.email)
    : h("span", { class: "link off" }, icon("mail"), "Email: not public");
  card.append(h("div", { class: "links" },
    linkEl("github", "GitHub", c.github_url, "github"),
    linkEl("linkedin", "LinkedIn", c.linkedin_url, "linkedin"),
    linkEl("cv", "View CV", c.cv_url, "doc"),
    emailBtn));

  const shortBtn = h("button", { class: "btn shortlist", type: "button" });
  const paintShort = () => {
    const on = c.status === "shortlisted";
    shortBtn.textContent = on ? "✓ Shortlisted" : "Shortlist";
    shortBtn.classList.toggle("on", on);
    card.classList.toggle("shortlisted", on);
  };
  paintShort();
  shortBtn.addEventListener("click", () => toggleShortlist(c, shortBtn, paintShort));

  const rejectBtn = h("button", { class: "btn reject", type: "button", text: "Reject" });
  rejectBtn.addEventListener("click", () => rejectCandidate(c, card));
  const contactBtn = h("button", { class: "btn contact", type: "button", text: "Contact" });
  contactBtn.addEventListener("click", () => openContact(c));

  card.append(h("div", { class: "actions" }, shortBtn, rejectBtn, contactBtn));
  return card;
}

// ------------------------------------------------------------------ actions
async function toggleShortlist(c, btn, repaint) {
  btn.disabled = true;
  try {
    if (c.status === "shortlisted") {
      await postJSON("/api/unshortlist", { candidate_id: c.id });
      c.status = null;
      toast(`${c.name} removed from the shortlist`);
    } else {
      const r = await postJSON("/api/shortlist", {
        candidate_id: c.id, match_score: c.match ? c.match.score : null, query: state.query,
      });
      c.status = "shortlisted";
      const sheet = h("a", { href: "/api/hr-sheet", download: "", text: "Download the HR sheet" });
      const parts = [`Saved ${c.name} to the HR sheet (${r.count} shortlisted). `, sheet, ". "];
      if (r.email) {
        parts.push(h("a", { href: "#", text: `Email ${r.email}`, onclick: (e) => { e.preventDefault(); openContact(c); } }), ".");
      } else {
        parts.push("No public email is available, so use their GitHub or LinkedIn link to reach out.");
      }
      botMessage(h("div", { class: "bubble" }, ...parts));
    }
    repaint();
    refreshSidebar();
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
  }
}

async function rejectCandidate(c, card) {
  try {
    await postJSON("/api/reject", { candidate_id: c.id, match_score: c.match ? c.match.score : null, query: state.query });
    card.classList.add("leaving");
    setTimeout(() => card.remove(), 200);
    toast(`${c.name} rejected and hidden from future searches`);
    if (c.status === "shortlisted") refreshSidebar();
  } catch (e) {
    toast(e.message);
  }
}

// ------------------------------------------------------------- contact modal
function openContact(c) {
  const saved = (k) => localStorage.getItem(k) || "";
  const role = (state.requirements && state.requirements.job_role) || "Software Engineer";

  const nameIn = h("input", { type: "text", value: saved("hb_name"), placeholder: "Your name" });
  const companyIn = h("input", { type: "text", value: saved("hb_company"), placeholder: "Company" });
  const roleIn = h("input", { type: "text", value: role });
  const kindSel = h("select", {}, h("option", { value: "job", text: "Job offer" }), h("option", { value: "internship", text: "Internship offer" }));
  const subjectIn = h("input", { type: "text" });
  const bodyIn = h("textarea");
  const status = h("p", { class: "hint", text: "Writing a draft…" });

  const close = () => bg.remove();
  const mailLinks = () => {
    const s = encodeURIComponent(subjectIn.value), b = encodeURIComponent(bodyIn.value);
    return {
      mailto: `mailto:${c.email}?subject=${s}&body=${b}`,
      gmail: `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(c.email)}&su=${s}&body=${b}`,
    };
  };

  const mailBtn = h("button", { class: "btn primary", type: "button", text: "Open in email app", disabled: !c.email });
  mailBtn.addEventListener("click", () => { window.location.href = mailLinks().mailto; });
  const gmailBtn = h("button", { class: "btn ghost", type: "button", text: "Open in Gmail", disabled: !c.email });
  gmailBtn.addEventListener("click", () => window.open(mailLinks().gmail, "_blank", "noopener"));
  const copyBtn = h("button", { class: "btn ghost", type: "button", text: "Copy text" });
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(`Subject: ${subjectIn.value}\n\n${bodyIn.value}`); toast("Copied"); }
    catch (_) { bodyIn.select(); toast("Press Ctrl+C to copy"); }
  });
  const regenBtn = h("button", { class: "btn ghost", type: "button", text: "Write again" });

  async function generate() {
    localStorage.setItem("hb_name", nameIn.value); localStorage.setItem("hb_company", companyIn.value);
    $("#setName").value = nameIn.value; $("#setCompany").value = companyIn.value;
    status.textContent = "Writing a draft…";
    regenBtn.disabled = true;
    try {
      const d = await postJSON("/api/email-draft", {
        candidate_id: c.id, job_role: roleIn.value, recruiter_name: nameIn.value,
        company: companyIn.value, kind: kindSel.value,
      });
      subjectIn.value = d.subject; bodyIn.value = d.body;
      status.textContent = c.email ? `To: ${c.email}. Edit the text if you like, then send it.`
        : "This candidate has no public email. Copy the text and message them on GitHub or LinkedIn.";
    } catch (e) { status.textContent = e.message; }
    regenBtn.disabled = false;
  }
  regenBtn.addEventListener("click", generate);

  const bg = h("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) close(); } },
    h("div", { class: "modal-card", role: "dialog", "aria-modal": "true", "aria-label": "Contact candidate" },
      h("h2", { text: `Contact ${c.name}` }),
      h("div", { class: "row" }, h("label", {}, "Your name", nameIn), h("label", {}, "Company", companyIn)),
      h("div", { class: "row" }, h("label", {}, "Position", roleIn), h("label", {}, "Offer type", kindSel)),
      status,
      h("label", {}, "Subject", subjectIn),
      h("label", {}, "Message", bodyIn),
      h("div", { class: "modal-actions" }, regenBtn, copyBtn, gmailBtn, mailBtn,
        h("button", { class: "btn ghost", type: "button", text: "Close", onclick: close }))));
  document.body.append(bg);
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });
  generate();
}

// -------------------------------------------------------------------- chat
function renderResults(data) {
  const parts = [];
  parts.push(bubble(data.reply));
  for (const w of data.warnings || []) parts.push(notice(w));
  if (data.stats && data.searched) {
    parts.push(h("p", { class: "hint", text: `Analysed ${data.stats.github_analyzed} GitHub profiles from Pakistan and ${data.stats.cvs} uploaded CVs.` }));
  }
  const stack = botMessage(...parts);
  if (data.candidates && data.candidates.length) {
    const list = h("div", { class: "cards" });
    data.candidates.forEach((c, i) => list.append(candidateCard(c, i + 1)));
    stack.append(list);
    scrollDown();
  }
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.busy) return;
  state.busy = true;
  $("#sendBtn").disabled = true;
  userMessage(text);
  const stop = typing(["Understanding your requirements…", "Searching GitHub…", "Reading profiles…", "Ranking the best matches…"]);
  try {
    const data = await postJSON("/api/chat", { message: text, previous_requirements: state.requirements });
    stop();
    if (data.searched) { state.requirements = data.requirements; state.query = text; }
    renderResults(data);
  } catch (e) {
    stop();
    botMessage(notice(e.message, true));
  } finally {
    state.busy = false;
    $("#sendBtn").disabled = false;
    $("#msg").focus();
  }
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length || state.busy) return;
  state.busy = true;
  userMessage(`Uploaded ${files.length} CV${files.length > 1 ? "s" : ""}: ${files.map((f) => f.name).join(", ")}`);
  const stop = typing(["Reading the document…", "Cleaning the image and running OCR…", "Extracting skills, experience and education…"]);
  try {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (state.requirements) form.append("requirements", JSON.stringify(state.requirements));
    const data = await api("/api/cv/upload", { method: "POST", body: form });
    stop();
    const n = data.candidates.length;
    const parts = [];
    if (n) {
      parts.push(bubble(state.requirements
        ? `I read ${n} CV${n > 1 ? "s" : ""} and scored ${n > 1 ? "them" : "it"} against your last search. They will also appear in future searches.`
        : `I read ${n} CV${n > 1 ? "s" : ""}. Now tell me who you are looking for and I'll rank them together with GitHub candidates.`));
    }
    for (const err of data.errors) parts.push(notice(err, true));
    const stack = botMessage(...parts);
    if (n) {
      const list = h("div", { class: "cards" });
      data.candidates.forEach((c, i) => list.append(candidateCard(c, state.requirements ? i + 1 : null)));
      stack.append(list);
      scrollDown();
    }
  } catch (e) {
    stop();
    botMessage(notice(e.message, true));
  } finally {
    state.busy = false;
    $("#cvInput").value = "";
  }
}

// ------------------------------------------------------------------ sidebar
async function refreshSidebar() {
  try {
    const { items } = await api("/api/shortlist");
    $("#shortCount").textContent = items.length;
    const box = $("#shortList");
    box.replaceChildren();
    if (!items.length) {
      box.append(h("p", { class: "empty", text: "No one yet. Press Shortlist on a candidate and they appear here and in the HR sheet." }));
      return;
    }
    for (const it of items) {
      const links = [];
      for (const [label, url] of [["GitHub", it.github_url], ["LinkedIn", it.linkedin_url], ["CV", it.cv_url]]) {
        const href = safeHref(url);
        if (href) links.push(h("a", { href, target: "_blank", rel: "noopener noreferrer", text: label }), " ");
      }
      box.append(h("div", { class: "short-item" },
        h("div", { class: "nm" }, h("b", { text: it.name }), h("small", {}, ...(links.length ? links : [it.location || ""]))),
        it.match_score !== null && it.match_score !== undefined ? h("span", { class: "score-badge", text: `${Math.round(it.match_score)}%` }) : null,
        h("button", { class: "x", type: "button", title: "Remove from shortlist", "aria-label": `Remove ${it.name}`,
          onclick: async () => {
            await postJSON("/api/unshortlist", { candidate_id: it.id });
            document.querySelectorAll(`.card[data-id="${CSS.escape(it.id)}"]`).forEach((el) => {
              el.classList.remove("shortlisted");
              const b = el.querySelector(".btn.shortlist");
              if (b) { b.textContent = "Shortlist"; b.classList.remove("on"); }
            });
            refreshSidebar();
          } }, "×")));
    }
  } catch (e) { /* sidebar is non-critical */ }
}

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const pills = $("#statusPills");
    pills.replaceChildren(
      h("span", { class: "pill " + (s.groq ? "ok" : "warn"), text: s.groq ? "Groq AI connected" : "Groq key missing (basic mode)" }),
      h("span", { class: "pill " + (s.github_token ? "ok" : "warn"), text: s.github_token ? "GitHub token set" : "GitHub token missing" }));
  } catch (_) { /* ignore */ }
}

// -------------------------------------------------------------------- setup
const EXAMPLES = [
  "I want a Python developer in Islamabad with 3 years experience, FastAPI and Machine Learning",
  "ML engineer in Lahore",
  "Django developer from Karachi",
  "React developer in Rawalpindi with 2 years experience",
];

function init() {
  const sug = $("#suggestions");
  EXAMPLES.forEach((t) => sug.append(h("button", { type: "button", text: t.length > 48 ? t.slice(0, 46) + "…" : t, title: t, onclick: () => sendMessage(t) })));

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#msg");
    const text = input.value;
    input.value = "";
    sendMessage(text);
  });
  $("#cvInput").addEventListener("change", (e) => uploadFiles(e.target.files));

  const chat = $("#chatPane");
  ["dragenter", "dragover"].forEach((ev) => chat.addEventListener(ev, (e) => { e.preventDefault(); chat.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((ev) => chat.addEventListener(ev, (e) => { e.preventDefault(); if (ev === "drop" || e.target === $("#dropVeil")) chat.classList.remove("dragging"); }));
  chat.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));

  $("#setName").value = localStorage.getItem("hb_name") || "";
  $("#setCompany").value = localStorage.getItem("hb_company") || "";
  $("#setName").addEventListener("input", (e) => localStorage.setItem("hb_name", e.target.value));
  $("#setCompany").addEventListener("input", (e) => localStorage.setItem("hb_company", e.target.value));

  $("#sideToggle").addEventListener("click", () => $("#side").classList.add("open"));
  $("#sideClose").addEventListener("click", () => $("#side").classList.remove("open"));
  $("#resetRejected").addEventListener("click", async () => {
    const r = await postJSON("/api/reset-rejected", {});
    toast(r.restored ? `${r.restored} rejected candidate(s) will show up again` : "No rejected candidates");
  });

  botMessage(h("div", { class: "bubble", text:
    "Hi! I'm HireBot. Tell me who you need in plain English, like \"I want a 3 year experienced Python developer in Islamabad\".\n\n" +
    "I search GitHub live for Pakistani developers, read any CVs you upload (PDF, scan or photo), and rank everyone by how well they fit. " +
    "Then you can shortlist, reject or email them." }));
  loadStatus();
  refreshSidebar();
  $("#msg").focus();
}

init();
