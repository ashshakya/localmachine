const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const toast = document.getElementById("toast");

function notify(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2400);
}

document.querySelector(".open-local-repo")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/api/repositories/open/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify({ path: button.dataset.repoPath }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Could not open repository in Sublime Merge");
    notify("Repository opened in Sublime Merge");
  } catch (error) {
    notify(error.message || "Could not open repository in Sublime Merge");
  } finally {
    button.disabled = false;
  }
});

document.querySelector(".repo-range-form")?.addEventListener("submit", event => {
  const form = event.currentTarget;
  const custom = form.querySelector('input[name="days"]');
  if (!custom?.value) custom.disabled = true;
  else form.querySelector('select[name="days"]')?.setAttribute("disabled", "disabled");
});
