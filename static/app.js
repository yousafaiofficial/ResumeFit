const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[c]));

let token = localStorage.getItem("rf_token");
let email = localStorage.getItem("rf_email");
let csrfToken = null;
let mode = "login";
let historyCursor = null;
let demoMode = false;

// Initialize CSRF protection on boot
async function initCsrf() {
  if (!token) return;

  try {
    const res = await fetch("/api/v1/auth/csrf", { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      csrfToken = data.csrf_token;
    }
  } catch (_) {}
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

  const res = await fetch("/api/v1" + path, {
    ...opts,
    headers,
    credentials: "include",
  });

  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));

  if (res.status === 401 && token) {
    signOut();
  }

  if (!res.ok) {
    const msg = data.message || data.detail || "Something went wrong. Please check your inputs and try again.";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function signOut() {
  api("/auth/logout", { method: "POST" }).catch(() => {});
  token = email = null;
  localStorage.removeItem("rf_token");
  localStorage.removeItem("rf_email");
  render();
}

function render() {
  $("authView").classList.toggle("hidden", !!token || demoMode);
  $("appView").classList.toggle("hidden", !token || demoMode);
  $("demoView").classList.toggle("hidden", !demoMode);
  $("navRight").innerHTML = token && !demoMode
    ? `<span>${esc(email || "")}</span><button class="btn link" id="out">Sign out</button>`
    : "";
  if (token && !demoMode) {
    $("out").onclick = signOut;
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
    token = d.token;
    email = d.email;
    if (d.csrf_token) csrfToken = d.csrf_token;

    localStorage.setItem("rf_token", token);
    localStorage.setItem("rf_email", email);
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
  $("fileLabel").textContent = $("file").files[0]?.name || "Drop a PDF here or click to choose (Max 10 pages, 5MB)";
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

  if (!token || demoMode) {
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
  const color = r.score >= 70 ? "var(--green)" : r.score >= 45 ? "#b58900" : "var(--red)";
  const verdict = r.score >= 70 ? "Strong Match" : r.score >= 45 ? "Partial Match" : "Weak Match";
  const chips = (list, cls) =>
    list.length
      ? `<div class="chips">${list.map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("")}</div>`
      : `<p class="note">None found.</p>`;

  container.innerHTML = `
    ${illustrative ? '<p class="note"><strong>Illustrative sample only:</strong> these scores and suggestions are fictional, not an assessment of your resume.</p>' : ""}
    <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
      <div class="scorehead">
        <div class="ring" style="--p:${r.score};--ringc:${color}"><span>${Math.round(r.score)}</span></div>
        <div>
          <h2>${verdict}${r.job_title ? ": " + esc(r.job_title) : ""}</h2>
          <div class="subs">
            <div>Meaning match: <b>${r.semantic_score}%</b></div>
            <div>Skill coverage: <b>${r.skill_score !== null ? r.skill_score + "%" : "N/A"}</b></div>
            <div>Word count: <b>${r.word_count}</b></div>
            ${r.cached ? "<div style='color:var(--green);font-size:12px;'>⚡ Cached analysis</div>" : ""}
          </div>
        </div>
      </div>
      <div>
        <button class="btn link" id="exportReportBtn" style="font-size:14px; border:1px solid var(--line); padding:6px 12px; border-radius:6px; background:var(--card);">
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
        <div style="display:flex; justify-content:space-between; align-items:center;">
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
  if (!token || demoMode) return;

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

// Initialize on page load
initCsrf();
render();
