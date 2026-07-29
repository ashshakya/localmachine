const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const toast = document.querySelector("#portalToast");

function showToast(message, kind = "success") {
  if (!toast) return;
  toast.textContent = message;
  toast.dataset.kind = kind;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 3200);
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      "X-CSRFToken": csrfToken,
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({ error: "Unexpected server response." }));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

document.querySelector("#createTunnelForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.querySelector("#tunnelUsername");
  const username = input.value.trim().toLowerCase();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Reserving…";
  try {
    await apiRequest(`/api/tunnels/${encodeURIComponent(username)}`, { method: "PUT" });
    showToast(`${username} was reserved.`);
    window.location.reload();
  } catch (error) {
    showToast(error.message, "error");
    button.disabled = false;
    button.innerHTML = "Reserve subdomain <span>→</span>";
  }
});

document.addEventListener("click", async (event) => {
  const copyButton = event.target.closest("[data-copy]");
  if (copyButton) {
    const target = document.getElementById(copyButton.dataset.copy);
    const value = target?.value ?? target?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(value.trim());
      showToast("Copied to clipboard.");
    } catch {
      showToast("Clipboard access was blocked.", "error");
    }
    return;
  }

  const revealButton = event.target.closest("[data-reveal]");
  if (revealButton) {
    const input = document.getElementById(revealButton.dataset.reveal);
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    revealButton.textContent = showing ? "Show" : "Hide";
    return;
  }

  const card = event.target.closest(".tunnel-card");
  if (!card) return;
  const username = card.dataset.username;

  if (event.target.closest(".rotate-button")) {
    if (!confirm(`Rotate the token for ${username}? The current agent will disconnect.`)) return;
    try {
      await apiRequest(`/api/tunnels/${encodeURIComponent(username)}`, { method: "POST" });
      showToast(`Token rotated for ${username}.`);
      window.location.reload();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  if (event.target.closest(".delete-button")) {
    if (!confirm(`Delete ${username}? This subdomain will become available again.`)) return;
    try {
      await apiRequest(`/api/tunnels/${encodeURIComponent(username)}`, { method: "DELETE" });
      card.remove();
      showToast(`${username} was deleted.`);
      if (!document.querySelector(".tunnel-card")) window.location.reload();
    } catch (error) {
      showToast(error.message, "error");
    }
  }
});
