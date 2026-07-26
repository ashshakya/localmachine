const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const toast = document.getElementById("toast");
let noteTimer;
let toastTimer;
let refreshController;

const byId = id => document.getElementById(id);
const requestedDays = Number(new URLSearchParams(window.location.search).get("days"));
let activeCommitDays = Number.isInteger(requestedDays) && requestedDays >= 0
  ? requestedDays
  : Number(byId("commit-range")?.value ?? 30);

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function slug(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function notify(message) {
  if (!toast) return;
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2400);
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

function serviceHTML(service) {
  const result = service.latency === null ? "offline" : `${service.latency}ms`;
  return `<article><i class="health ${escapeHTML(service.status)}"></i><div><strong>${escapeHTML(service.name)}</strong><span>${escapeHTML(service.url)}</span></div><small>${result}</small><a href="${escapeHTML(service.url)}" target="_blank" rel="noreferrer" aria-label="Open ${escapeHTML(service.name)}">↗</a></article>`;
}

function repoHTML(repo) {
    const statusLabel = repo.is_clean ? "Clean" : "Working";
  const openButton = `<button class="external repo-open" type="button" data-repo-path="${escapeHTML(repo.path)}" aria-label="Open ${escapeHTML(repo.name)} in Sublime Merge" title="Open in Sublime Merge">↗</button>`;
  const detailURL = `/repositories/${encodeURIComponent(repo.name)}/`;
  return `<article class="repo-row" id="repo-${slug(repo.name)}"><span class="repo-monogram">${escapeHTML(repo.name.slice(0, 2).toUpperCase())}</span><div class="repo-primary"><strong><a href="${detailURL}">${escapeHTML(repo.name)}</a></strong><span title="${escapeHTML(repo.path)}">${escapeHTML(repo.path)}</span></div><div class="branch"><small>BRANCH</small><strong>⑂ ${escapeHTML(repo.branch)}</strong></div><div class="changes"><small>CHANGES</small><strong class="${escapeHTML(repo.health)}">${repo.changes}</strong><span>${repo.modified} modified · ${repo.untracked} new</span></div><div class="commit"><small>LATEST COMMIT</small><strong>${escapeHTML(repo.last_commit.subject)}</strong><span>${escapeHTML(repo.last_commit.hash)} · ${escapeHTML(repo.last_commit.relative)}</span></div><span class="repo-status ${escapeHTML(repo.health)}"><i></i>${statusLabel}</span>${openButton}</article>`;
}

function activityHTML(event) {
  const initials = event.author.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase();
  return `<article><span class="avatar">${escapeHTML(initials)}</span><div><strong>${escapeHTML(event.subject)}</strong><span>${escapeHTML(event.author)} in <b>${escapeHTML(event.repository)}</b></span></div><code>${escapeHTML(event.hash)}</code><time datetime="${escapeHTML(event.iso)}">${escapeHTML(event.relative)}</time></article>`;
}

function sideRepoHTML(repo) {
  return `<a href="/repositories/${encodeURIComponent(repo.name)}/"><i class="repo-dot ${escapeHTML(repo.health)}"></i><span>${escapeHTML(repo.name)}</span><small>${escapeHTML(repo.branch)}</small></a>`;
}

function contributorHTML(contributor, total) {
  const initials = contributor.name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase();
  const width = Math.max(8, Math.round((contributor.commits / Math.max(1, total)) * 100));
  return `<article><span class="avatar">${escapeHTML(initials)}</span><strong>${escapeHTML(contributor.name)}</strong><div><i style="width:${width}%"></i></div><b>${contributor.commits}</b></article>`;
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function renderSnapshot(data) {
  setText("stat-repositories", data.stats.repositories);
  setText("stat-changes", data.stats.open_changes);
  setText("stat-commits", data.stats.commits_in_range);
  setText("commit-range-label", data.range_short_label);
  setText("stat-services", data.stats.healthy_services);
  setText("nav-repo-count", data.stats.repositories);
  setText("last-synced", new Date(data.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));

  if (byId("service-list")) byId("service-list").innerHTML = data.services.map(serviceHTML).join("");
  if (byId("repo-list")) byId("repo-list").innerHTML = data.repositories.length ? data.repositories.map(repoHTML).join("") : '<div class="empty">No Git repositories found in this workspace.</div>';
  if (byId("activity-list")) byId("activity-list").innerHTML = data.activity.length ? data.activity.slice(0, 8).map(activityHTML).join("") : '<div class="empty">No recent commits found.</div>';
  if (byId("side-repo-list")) byId("side-repo-list").innerHTML = data.repositories.length ? data.repositories.slice(0, 6).map(sideRepoHTML).join("") : '<p>No repositories found.</p>';
  if (byId("contributors-list")) byId("contributors-list").innerHTML = data.contributors.length ? data.contributors.map(item => contributorHTML(item, data.stats.commits_in_range)).join("") : '<div class="empty">No contributor data yet.</div>';
  activeCommitDays = Number(data.range_days);
  const rangeSelect = byId("commit-range");
  if (rangeSelect) {
    const rangeValue = String(data.range_days);
    const isPreset = Array.from(rangeSelect.options).some(option => option.value !== "custom" && option.value === rangeValue);
    rangeSelect.value = isPreset ? rangeValue : "custom";
    if (!isPreset && byId("custom-commit-days")) byId("custom-commit-days").value = rangeValue;
  }
  bindRepositoryButtons();
}

async function openRepository(button) {
  if (button.disabled) return;
  button.disabled = true;
  try {
    const data = await postJSON("/api/repositories/open/", { path: button.dataset.repoPath });
    notify(`${data.repository} opened in Sublime Merge`);
  } catch (error) {
    notify(error.message || "Could not open repository in Sublime Merge");
  } finally {
    button.disabled = false;
  }
}

function bindRepositoryButtons() {
  document.querySelectorAll(".repo-open:not([data-bound])").forEach(button => {
    button.dataset.bound = "true";
    button.addEventListener("click", () => openRepository(button));
  });
}

async function refreshSnapshot(showToast = false) {
  if (refreshController) return;
  const button = byId("refresh-all");
  refreshController = new AbortController();
  button?.classList.add("loading");
  if (button) button.textContent = "↻ Syncing…";
  const timeout = window.setTimeout(() => refreshController?.abort(), 12000);
  try {
    const response = await fetch(`/api/snapshot/?days=${encodeURIComponent(activeCommitDays)}`, { cache: "no-store", signal: refreshController.signal });
    if (!response.ok) throw new Error("Snapshot failed");
    const data = await response.json();
    renderSnapshot(data);
    const url = new URL(window.location.href);
    url.searchParams.set("days", String(data.range_days));
    window.history.replaceState({}, "", url);
    if (showToast) notify("Live workspace data refreshed");
  } catch (error) {
    notify(error.name === "AbortError" ? "Workspace refresh timed out" : "Could not refresh workspace data");
  } finally {
    window.clearTimeout(timeout);
    refreshController = null;
    button?.classList.remove("loading");
    if (button) button.textContent = "↻ Refresh data";
  }
}

byId("refresh-all")?.addEventListener("click", () => refreshSnapshot(true));
byId("refresh-services")?.addEventListener("click", () => refreshSnapshot(true));
byId("commit-range")?.addEventListener("change", event => {
  if (event.target.value === "custom") return;
  activeCommitDays = Number(event.target.value);
  refreshSnapshot(true);
});
byId("custom-range-form")?.addEventListener("submit", event => {
  event.preventDefault();
  const input = byId("custom-commit-days");
  const days = Number(input?.value);
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    notify("Enter a whole number from 1 to 3,650 days");
    input?.focus();
    return;
  }
  activeCommitDays = days;
  refreshSnapshot(true);
});
window.setInterval(() => { if (!document.hidden) refreshSnapshot(false); }, 30000);

const note = byId("daily-note");
note?.addEventListener("input", () => {
  window.clearTimeout(noteTimer);
  setText("note-status", "Saving…");
  noteTimer = window.setTimeout(async () => {
    try {
      await postJSON("/api/note/", { content: note.value });
      setText("note-status", "Saved in Django");
    } catch (error) { setText("note-status", "Save failed"); }
  }, 500);
});

byId("show-task-form")?.addEventListener("click", () => {
  const form = byId("task-form");
  if (!form) return;
  form.hidden = !form.hidden;
  if (!form.hidden) byId("task-title")?.focus();
});

byId("task-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  const titleInput = byId("task-title");
  const repositoryInput = byId("task-repository");
  if (!titleInput?.value.trim()) return;
  try {
    const data = await postJSON("/api/tasks/", { title: titleInput.value.trim(), repository: repositoryInput?.value || "" });
    byId("task-empty")?.remove();
    const row = document.createElement("article");
    row.dataset.taskId = data.task.id;
    row.innerHTML = `<button class="task-toggle" type="button" aria-label="Toggle ${escapeHTML(data.task.title)}"></button><div><strong>${escapeHTML(data.task.title)}</strong><span>${escapeHTML(data.task.repository || "General")} · added just now</span></div>`;
    byId("task-list")?.prepend(row);
    bindTask(row);
    titleInput.value = "";
    setText("nav-task-count", document.querySelectorAll("#task-list article[data-task-id]").length);
    notify("Task saved in MySQL");
  } catch (error) { notify("Could not save task"); }
});

function bindTask(row) {
  row.querySelector(".task-toggle")?.addEventListener("click", async () => {
    try {
      const data = await postJSON(`/api/tasks/${row.dataset.taskId}/toggle/`, {});
      row.classList.toggle("done", data.completed);
      const toggle = row.querySelector(".task-toggle");
      if (toggle) toggle.textContent = data.completed ? "✓" : "";
    } catch (error) { notify("Could not update task"); }
  });
}

document.querySelectorAll("#task-list article[data-task-id]").forEach(bindTask);
bindRepositoryButtons();
