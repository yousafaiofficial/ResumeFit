const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[c]));

let authenticated = false;
let email = null;
let csrfToken = null;
let mode = "login";
let historyCursor = null;
let demoMode = false;
let resetToken = new URLSearchParams(window.location.hash.slice(1)).get("reset");
const authFailure = new URLSearchParams(window.location.search).get("auth_error");
if (resetToken || authFailure) {
  window.history.replaceState(null, "", window.location.pathname);
}

async function initCsrf() {
  try {
    const res = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
    if (res.ok) {
      const data = await res.json();
      csrfToken = data.csrf_token;
    }
  } catch (err) {
    console.error("Could not initialize authentication protection.", err);
  }
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const method = (opts.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const res = await fetch("/api/v1" + path, {
    ...opts,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });

  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));

  if (res.status === 401 && authenticated && path !== "/auth/logout") {
    void signOut();
  }

  if (!res.ok) {
    const msg = data.message || data.detail || "Something went wrong. Please check your inputs and try again.";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

async function signOut() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_) {
    // The session may already have expired; the server clears it when possible.
  }
  authenticated = false;
  email = null;
  csrfToken = null;
  demoMode = false;
  $("analyzeForm").reset();
  $("history").innerHTML = "";
  $("results").innerHTML = `
    <div class="empty">
      <h2>Your results appear here</h2>
      <p>Add a resume and a job description, then choose <strong>Analyze match</strong>.</p>
    </div>`;
  $("fileLabel").textContent = "Drop a PDF here or click to choose (Max 10 pages, 4MB)";
  render();
}

function render() {
  $("authView").classList.toggle("hidden", authenticated || demoMode);
  $("appView").classList.toggle("hidden", !authenticated || demoMode);
  $("demoView").classList.toggle("hidden", !demoMode);
  $("navRight").innerHTML = authenticated && !demoMode
    ? `<span>${esc(email || "")}</span><button class="btn link" id="out">Sign out</button>`
    : "";
  if (authenticated && !demoMode) {
    $("out").onclick = () => void signOut();
    loadHistory(true);
  }
}

/* ---------- Auth Handlers ---------- */
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    mode = t.dataset.mode;
    document.querySelectorAll(".tab").forEach((x) => {
      const isActive = x === t;
      x.classList.toggle("active", isActive);
      x.setAttribute("aria-selected", String(isActive));
    });
    $("authSubmit").textContent = mode === "login" ? "Sign in" : "Create account";
    $("password").autocomplete = mode === "login" ? "current-password" : "new-password";
    $("authError").textContent = "";
  };
});

$("authForm").onsubmit = async (e) => {
  e.preventDefault();
  $("authError").textContent = "";
  const submitBtn = $("authSubmit");
  submitBtn.disabled = true;

  try {
    const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
    const d = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: $("email").value,
        password: $("password").value,
      }),
    });
    authenticated = true;
    email = d.email;
    csrfToken = d.csrf_token;
    $("password").value = "";
    render();
  } catch (err) {
    $("authError").textContent = err.message;
  } finally {
    submitBtn.disabled = false;
  }
};

const SAMPLE_ANALYSIS = {
  score: 78,
  semantic_score: 74,
  skill_score: 84,
  job_title: "Sample Backend Engineer",
  word_count: 520,
  matched_skills: ["python", "fastapi", "postgresql", "docker"],
  missing_skills: ["kubernetes", "redis"],
  suggestions: [
    "Illustrative suggestion: add a concise summary tailored to the target role.",
    "Illustrative suggestion: describe measurable outcomes where you have evidence.",
  ],
  rewrites: [
    {
      original: "Responsible for maintaining fictional sample services.",
      suggested: "Maintained fictional sample services; add a verified impact metric.",
      source: "rules",
    },
  ],
  engine: "illustrative sample",
  cached: false,
};

function showDemo() {
  demoMode = true;
  render();
  showResult(SAMPLE_ANALYSIS, $("demoResults"), true);
}

$("trySampleBtn").addEventListener("click", showDemo);
$("demoBackBtn").addEventListener("click", () => {
  demoMode = false;
  render();
});

/* ---------- Analyze Handlers ---------- */
$("file").onchange = () => {
  $("fileLabel").textContent = $("file").files[0]?.name || "Drop a PDF here or click to choose (Max 10 pages, 4MB)";
};
["dragover", "dragenter"].forEach((ev) =>
  $("drop").addEventListener(ev, () => $("drop").classList.add("over"))
);
["dragleave", "drop"].forEach((ev) =>
  $("drop").addEventListener(ev, () => $("drop").classList.remove("over"))
);

$("analyzeForm").onsubmit = async (e) => {
  e.preventDefault();
  $("analyzeError").textContent = "";

  if (!authenticated || demoMode) {
    $("analyzeError").textContent = "Sign in to analyze and save a resume.";
    return;
  }

  const fd = new FormData();
  fd.append("job_description", $("jd").value);
  fd.append("job_title", $("jobTitle").value);
  fd.append("resume_text", $("resumeText").value);
  if ($("file").files[0]) fd.append("resume_file", $("file").files[0]);

  const btn = $("analyzeBtn");
  btn.disabled = true;
  btn.textContent = "Analyzing Match…";

  try {
    const result = await api("/analyze", { method: "POST", body: fd });
    showResult(result);
    loadHistory(true);
  } catch (err) {
    $("analyzeError").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze match";
  }
};

function showResult(r, container = $("results"), illustrative = false) {
  const scoreClass = r.score >= 70 ? "score-strong" : r.score >= 45 ? "score-partial" : "score-weak";
  const ringOffset = 289 * (1 - r.score / 100);
  const verdict = r.score >= 70 ? "Strong Match" : r.score >= 45 ? "Partial Match" : "Weak Match";
  const chips = (list, cls) =>
    list.length
      ? `<div class="chips">${list.map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("")}</div>`
      : `<p class="note">None found.</p>`;

  container.innerHTML = `
    ${illustrative ? '<p class="note"><strong>Illustrative sample only:</strong> these scores and suggestions are fictional, not an assessment of your resume.</p>' : ""}
    <div class="result-head-row">
      <div class="scorehead">
        <div class="ring ${scoreClass}">
          <svg viewBox="0 0 100 100" role="img" aria-label="Match score ${Math.round(r.score)} percent">
            <circle class="ring-track" cx="50" cy="50" r="46"></circle>
            <circle class="ring-progress" cx="50" cy="50" r="46" stroke-dasharray="289" stroke-dashoffset="${ringOffset}"></circle>
          </svg>
          <span>${Math.round(r.score)}</span>
        </div>
        <div>
          <h2>${verdict}${r.job_title ? ": " + esc(r.job_title) : ""}</h2>
          <div class="subs">
            <div>Meaning match: <b>${r.semantic_score}%</b></div>
            <div>Skill coverage: <b>${r.skill_score !== null ? r.skill_score + "%" : "N/A"}</b></div>
            <div>Word count: <b>${r.word_count}</b></div>
            ${r.cached ? "<div class='cached-badge'>⚡ Cached analysis</div>" : ""}
          </div>
        </div>
      </div>
      <div>
        <button class="btn link export-report-btn" id="exportReportBtn">
          📄 Export / Print Report
        </button>
      </div>
    </div>

    <h3>Skills identified in job description that your resume proves</h3>
    ${chips(r.matched_skills, "ok")}

    <h3>Skills identified in job description your resume doesn't show</h3>
    ${chips(r.missing_skills, "miss")}

    <h3>Priority recommendations</h3>
    ${r.suggestions.length ? `<ul class="tips">${r.suggestions.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : "<p class='note'>No structural gaps detected.</p>"}

    <h3>Impact bullet rewrites</h3>
    ${r.rewrites.length ? r.rewrites.map((w, i) => `
      <div class="rw">
        <p class="old">${esc(w.original)}</p>
        <p class="new"><span>${esc(w.suggested)}</span></p>
        <div class="rewrite-actions">
          <button class="copy" data-i="${i}">Copy rewrite</button>
          <span class="src">${w.source === "ai" ? "AI Generated" : "Rule Engine"}</span>
        </div>
      </div>`).join("")
      : "<p class='note'>No weak or unquantified bullets detected.</p>"}

    <p class="note">Scored using engine: ${esc(r.engine)}. Always verify suggestions before incorporating into your resume.</p>
  `;

  // Attach copy listeners
  container.querySelectorAll(".copy").forEach((b) => {
    b.onclick = async () => {
      await navigator.clipboard.writeText(r.rewrites[b.dataset.i].suggested);
      b.textContent = "Copied ✓";
      setTimeout(() => (b.textContent = "Copy rewrite"), 2000);
    };
  });

  // Attach export listener (Item 61)
  const exportBtn = container.querySelector("#exportReportBtn");
  if (exportBtn) {
    exportBtn.onclick = () => window.print();
  }
}

/* ---------- History Pagination (Item 20) ---------- */
async function loadHistory(reset = false) {
  if (!authenticated || demoMode) return;

  if (reset) {
    historyCursor = null;
    $("history").innerHTML = "";
  }

  try {
    const url = `/history?limit=15${historyCursor ? "&cursor=" + historyCursor : ""}`;
    const data = await api(url);
    const rows = data.items || [];

    if (reset && !rows.length) {
      $("history").innerHTML = "<li><small>No past analyses saved yet.</small></li>";
      $("historyPagination").classList.add("hidden");
      return;
    }

    const html = rows.map((h) => `
      <li>
        <button class="open" data-id="${h.id}">
          ${esc(h.job_title)}<br>
          <small>${new Date(h.created_at).toLocaleDateString()}</small>
        </button>
        <span class="pill">${Math.round(h.score)}</span>
        <button class="x" data-del="${h.id}" aria-label="Delete analysis" title="Delete record">×</button>
      </li>`).join("");

    if (reset) {
      $("history").innerHTML = html;
    } else {
      $("history").insertAdjacentHTML("beforeend", html);
    }

    historyCursor = data.next_cursor;
    $("historyPagination").classList.toggle("hidden", !data.has_more);

    // Reattach listeners
    $("history").querySelectorAll(".open").forEach((b) => {
      b.onclick = async () => showResult(await api("/history/" + b.dataset.id));
    });
    $("history").querySelectorAll(".x").forEach((b) => {
      b.onclick = async () => {
        if (confirm("Delete this saved analysis?")) {
          await api("/history/" + b.dataset.del, { method: "DELETE" });
          loadHistory(true);
        }
      };
    });
  } catch (_) {}
}

const loadMoreBtn = $("loadMoreHistoryBtn");
if (loadMoreBtn) {
  loadMoreBtn.onclick = () => loadHistory(false);
}

async function restoreSession() {
  await initCsrf();
  try {
    const user = await api("/auth/me");
    const csrf = await api("/auth/csrf/session");
    email = user.email;
    csrfToken = csrf.csrf_token;
    authenticated = true;
  } catch (_) {
    authenticated = false;
    email = null;
    await initCsrf();
  }
  render();
}

async function initRecovery() {
  if (authFailure) {
    $("authError").textContent = authFailure === "existing_account"
      ? "An account already uses this email. Sign in with your password, or reset it."
      : "Google sign-in was canceled or could not be completed. Please try again.";
  }
  if (resetToken) {
    $("authForm").classList.add("hidden");
    $("resetForm").classList.remove("hidden");
    document.querySelectorAll(".tab").forEach((tab) => { tab.disabled = true; });
  }
  try {
    const options = await api("/auth/options");
    $("googleSignIn").classList.toggle("hidden", !options.google || Boolean(resetToken));
    $("forgotPassword").classList.toggle("hidden", !options.password_reset || Boolean(resetToken));
  } catch (_) {}
}

$("forgotPassword").onclick = async () => {
  $("forgotPassword").disabled = true;
  try {
    await initCsrf();
    const result = await api("/auth/password/forgot", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value }),
    });
    $("authError").textContent = result.message;
  } catch (err) {
    $("authError").textContent = err.message;
  } finally {
    $("forgotPassword").disabled = false;
  }
};

$("resetForm").onsubmit = async (event) => {
  event.preventDefault();
  const button = $("resetForm").querySelector("button");
  button.disabled = true;
  try {
    await initCsrf();
    const result = await api("/auth/password/reset", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: resetToken, password: $("resetPassword").value }),
    });
    resetToken = null;
    $("resetPassword").value = "";
    authenticated = false;
    csrfToken = null;
    email = null;
    $("resetForm").classList.add("hidden");
    $("authForm").classList.remove("hidden");
    document.querySelectorAll(".tab").forEach((tab) => { tab.disabled = false; });
    $("authError").textContent = result.message;
    await initCsrf();
    render();
    await initRecovery();
  } catch (err) {
    $("resetMessage").textContent = err.message;
  } finally {
    button.disabled = false;
  }
};

void (async () => {
  if (resetToken) {
    await initCsrf();
    render();
  } else {
    await restoreSession();
  }
  await initRecovery();
})();
