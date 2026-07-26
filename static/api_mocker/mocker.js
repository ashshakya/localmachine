const config = window.apiMockerConfig;
const byId = (id) => document.getElementById(id);

let collections = [];
let mocks = [];
let mocksById = new Map();
let selectedCollectionId = config.defaultCollectionId;
let historyEntries = [];
let selectedHistoryId = null;
let selectedHistoryDetail = null;

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2200);
}

function headersToText(headers) {
  return Object.entries(headers || {}).map(([key, value]) => `${key}: ${value}`).join("\n");
}

function textToHeaders(text) {
  const headers = {};
  text.split("\n").forEach((line) => {
    const separator = line.indexOf(":");
    if (separator < 1) return;
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (key) headers[key] = value;
  });
  return headers;
}

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = String(value);
  return element.innerHTML;
}

function collectionForId(collectionId) {
  return collections.find((collection) => collection.id === collectionId);
}

function mockUrl(mock) {
  const collection = collectionForId(mock.collection_id);
  return `/${collection?.slug || "collection"}${mock.path}`;
}

function absoluteMockUrl(mock) {
  return new URL(mockUrl(mock), window.location.origin).href;
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\"'\"'")}'`;
}

function curlCommand(mock) {
  return `curl -i -X ${mock.method} ${shellQuote(absoluteMockUrl(mock))}`;
}

async function copyText(value, successMessage) {
  try {
    await navigator.clipboard.writeText(value);
  } catch (_error) {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("Clipboard access is unavailable");
  }
  showToast(successMessage);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.error || "Request failed");
  }
  return data;
}

async function loadData() {
  try {
    [collections, mocks] = await Promise.all([
      requestJson(config.collectionsUrl),
      requestJson(config.collectionUrl),
    ]);
  } catch (error) {
    showToast(error.message || "Could not load API Mocker");
    return;
  }

  mocksById = new Map(mocks.map((mock) => [mock.id, mock]));
  if (!collections.some((collection) => collection.id === selectedCollectionId)) {
    selectedCollectionId = collections[0]?.id || config.defaultCollectionId;
  }
  renderCollectionOptions();
  renderCollections();
  renderMocks();
  updatePathPreview();
  await loadHistory();
}

function formatCapturedValue(value, emptyLabel = "(empty)") {
  if (value === null || value === undefined || value === "") return emptyLabel;
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  const text = String(value);
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch (_error) {
    return text;
  }
}

function historyTimestamp(value) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderHistory() {
  const query = byId("history-search").value.trim().toLowerCase();
  const filtered = historyEntries.filter((entry) =>
    entry.method.toLowerCase().includes(query)
    || entry.path.toLowerCase().includes(query)
    || String(entry.response_status).includes(query)
    || (entry.matched ? "matched" : "unmatched").includes(query)
  );

  byId("history-count").textContent = filtered.length;
  byId("history-empty").hidden = filtered.length > 0;
  byId("history-empty").textContent = historyEntries.length
    ? "No captured requests match your search."
    : "No requests captured for this collection yet.";
  byId("history-list").innerHTML = filtered.map((entry) => `
    <button class="history-item${entry.id === selectedHistoryId ? " active" : ""}${entry.matched ? "" : " unmatched"}" type="button" data-history-id="${escapeHtml(entry.id)}">
      <span class="method m-${escapeHtml(entry.method)}">${escapeHtml(entry.method)}</span>
      <span class="history-item-main">
        <strong>${escapeHtml(entry.path)}</strong>
        <small>${entry.matched ? "Matched mock" : "No mock matched"} · ${escapeHtml(historyTimestamp(entry.created_at))}</small>
      </span>
      <span class="history-item-meta">
        <strong>${escapeHtml(entry.response_status)}</strong>
        <small>${escapeHtml(entry.duration_ms)} ms</small>
      </span>
    </button>
  `).join("");
}

function clearInspector() {
  selectedHistoryDetail = null;
  byId("inspector-empty").hidden = false;
  byId("inspector-content").hidden = true;
}

function renderInspector(entry) {
  selectedHistoryDetail = entry;
  byId("inspector-empty").hidden = true;
  byId("inspector-content").hidden = false;
  byId("inspector-method").className = `method m-${entry.method}`;
  byId("inspector-method").textContent = entry.method;
  byId("inspector-path").textContent = entry.path;
  byId("inspector-status").textContent = entry.response_status;
  byId("inspector-duration").textContent = `${entry.duration_ms} ms`;
  byId("inspector-created").textContent = historyTimestamp(entry.created_at);
  byId("inspector-match").textContent = entry.matched
    ? `Matched${entry.mock_id ? ` · ${entry.mock_id.slice(0, 8)}` : ""}`
    : "No match";
  byId("inspector-client").textContent = entry.remote_addr || "Local";
  byId("inspector-query").textContent = formatCapturedValue(entry.query_params);
  byId("inspector-request-headers").textContent = formatCapturedValue(entry.request_headers);
  byId("inspector-request-body").textContent = formatCapturedValue(entry.request_body);
  byId("inspector-response-headers").textContent = formatCapturedValue(entry.response_headers);
  byId("inspector-response-body").textContent = formatCapturedValue(entry.response_body);
}

async function selectHistory(id) {
  selectedHistoryId = id;
  renderHistory();
  try {
    const entry = await requestJson(`${config.historyUrl}${id}/`);
    if (selectedHistoryId === id) renderInspector(entry);
  } catch (error) {
    showToast(error.message || "Could not load request details");
  }
}

async function loadHistory() {
  if (!selectedCollectionId) {
    historyEntries = [];
    selectedHistoryId = null;
    renderHistory();
    clearInspector();
    return;
  }
  const url = new URL(config.historyUrl, window.location.origin);
  url.searchParams.set("collection_id", selectedCollectionId);
  try {
    historyEntries = await requestJson(`${url.pathname}${url.search}`);
    if (!historyEntries.some((entry) => entry.id === selectedHistoryId)) {
      selectedHistoryId = historyEntries[0]?.id || null;
    }
    renderHistory();
    if (selectedHistoryId) await selectHistory(selectedHistoryId);
    else clearInspector();
  } catch (error) {
    historyEntries = [];
    selectedHistoryId = null;
    renderHistory();
    clearInspector();
    showToast(error.message || "Could not load request history");
  }
}

function renderCollectionOptions() {
  const select = byId("collection-id");
  select.innerHTML = collections.map((collection) =>
    `<option value="${escapeHtml(collection.id)}">${escapeHtml(collection.name)}</option>`
  ).join("");
  if (collections.some((collection) => collection.id === selectedCollectionId)) {
    select.value = selectedCollectionId;
  }
}

function renderCollections() {
  const query = byId("collection-search").value.trim().toLowerCase();
  const filtered = collections.filter((collection) =>
    collection.name.toLowerCase().includes(query)
    || collection.slug.toLowerCase().includes(query)
    || (collection.description || "").toLowerCase().includes(query)
  );
  byId("collection-empty").hidden = filtered.length > 0;
  byId("collection-list").innerHTML = filtered.map((collection) => {
    const isDefault = collection.id === config.defaultCollectionId;
    return `<article class="collection-item${collection.id === selectedCollectionId ? " active" : ""}" data-collection-id="${escapeHtml(collection.id)}">
      <button class="collection-select" type="button" data-action="select-collection" data-id="${escapeHtml(collection.id)}">
        <strong>${escapeHtml(collection.name)}</strong>
        <small>/${escapeHtml(collection.slug)} · ${escapeHtml(collection.mock_count)} mock${collection.mock_count === 1 ? "" : "s"}${collection.description ? ` · ${escapeHtml(collection.description)}` : ""}</small>
      </button>
      <div class="collection-actions">
        <button type="button" data-action="edit-collection" data-id="${escapeHtml(collection.id)}" aria-label="Edit ${escapeHtml(collection.name)}" title="Edit collection">✎</button>
        ${isDefault ? "" : `<button type="button" data-action="delete-collection" data-id="${escapeHtml(collection.id)}" aria-label="Delete ${escapeHtml(collection.name)}" title="Delete collection">×</button>`}
      </div>
    </article>`;
  }).join("");
}

function renderMocks() {
  const selectedCollection = collections.find((collection) => collection.id === selectedCollectionId);
  const query = byId("mock-search").value.trim().toLowerCase();
  const collectionMocks = mocks.filter((mock) => mock.collection_id === selectedCollectionId);
  const filtered = collectionMocks.filter((mock) =>
    mock.method.toLowerCase().includes(query)
    || mock.path.toLowerCase().includes(query)
    || String(mock.status_code).includes(query)
  );

  byId("active-collection-name").textContent = selectedCollection
    ? `${selectedCollection.name} mocks`
    : "Configured mocks";
  byId("mock-count").textContent = filtered.length;
  byId("empty-state").hidden = filtered.length > 0;
  byId("empty-state").textContent = collectionMocks.length
    ? "No mocks match your search."
    : "No mocks in this collection yet. Create one to start testing.";
  byId("mocks-body").innerHTML = filtered.map((mock) => {
    const headerCount = Object.keys(mock.headers || {}).length;
    return `<tr>
      <td data-label="Method"><span class="method m-${escapeHtml(mock.method)}">${escapeHtml(mock.method)}</span></td>
      <td class="path" data-label="Path">${escapeHtml(mockUrl(mock))}</td>
      <td data-label="Status">${escapeHtml(mock.status_code)}</td>
      <td data-label="Latency">${escapeHtml(mock.latency_ms || 0)} ms</td>
      <td data-label="Headers">${headerCount ? `${headerCount} header${headerCount === 1 ? "" : "s"}` : "—"}</td>
      <td data-label="Requests"><strong class="request-count">${escapeHtml(mock.request_count || 0)}</strong></td>
      <td class="actions" data-label="Actions">
        <button class="test" type="button" data-action="test-mock" data-id="${escapeHtml(mock.id)}">Test</button>
        <button type="button" data-action="copy-url" data-id="${escapeHtml(mock.id)}">Copy URL</button>
        <button type="button" data-action="copy-curl" data-id="${escapeHtml(mock.id)}">Copy cURL</button>
        ${mock.method === "GET" ? `<button type="button" data-action="open-mock" data-id="${escapeHtml(mock.id)}">Open</button>` : ""}
        <button type="button" data-action="preview-mock" data-id="${escapeHtml(mock.id)}">Preview</button>
        <button type="button" data-action="edit-mock" data-id="${escapeHtml(mock.id)}">Edit</button>
        <button class="delete" type="button" data-action="delete-mock" data-id="${escapeHtml(mock.id)}">Delete</button>
      </td>
    </tr>`;
  }).join("");
}

function selectCollection(id) {
  if (selectedCollectionId === id) return;
  selectedCollectionId = id;
  selectedHistoryId = null;
  byId("mock-search").value = "";
  byId("history-search").value = "";
  resetForm();
  renderCollectionOptions();
  renderCollections();
  renderMocks();
  loadHistory();
}

function showCollectionForm(collection = null) {
  byId("collection-edit-id").value = collection?.id || "";
  byId("collection-name").value = collection?.name || "";
  byId("collection-description").value = collection?.description || "";
  byId("collection-form").hidden = false;
  byId("collection-name").focus();
}

function hideCollectionForm() {
  byId("collection-form").hidden = true;
  byId("collection-edit-id").value = "";
  byId("collection-name").value = "";
  byId("collection-description").value = "";
}

async function saveCollection(event) {
  event.preventDefault();
  const id = byId("collection-edit-id").value;
  const payload = {
    name: byId("collection-name").value.trim(),
    description: byId("collection-description").value.trim(),
  };
  if (!payload.name) {
    showToast("Collection name is required");
    return;
  }
  try {
    const collection = await requestJson(id ? `${config.collectionsUrl}${id}/` : config.collectionsUrl, {
      method: id ? "PUT" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    selectedCollectionId = collection.id;
    hideCollectionForm();
    showToast(id ? "Collection updated" : "Collection created");
    await loadData();
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteCollection(id) {
  const collection = collections.find((candidate) => candidate.id === id);
  if (!collection) return;
  const detail = collection.mock_count
    ? ` It also deletes ${collection.mock_count} mock${collection.mock_count === 1 ? "" : "s"}.`
    : "";
  if (!window.confirm(`Delete the "${collection.name}" collection?${detail}`)) return;
  try {
    await requestJson(`${config.collectionsUrl}${id}/`, {method: "DELETE"});
    if (selectedCollectionId === id) selectedCollectionId = config.defaultCollectionId;
    showToast("Collection deleted");
    await loadData();
  } catch (error) {
    showToast(error.message);
  }
}

function resetForm() {
  byId("mock-id").value = "";
  byId("method").value = "GET";
  byId("path").value = "";
  byId("status-code").value = 200;
  byId("latency-ms").value = 0;
  byId("response-body").value = "";
  byId("headers").value = "";
  byId("form-heading").textContent = "New mock";
  byId("submit-button").textContent = "Add mock";
  byId("cancel-edit").hidden = true;
  if (collections.some((collection) => collection.id === selectedCollectionId)) {
    byId("collection-id").value = selectedCollectionId;
  }
  updatePathPreview();
}

function prettifyResponseJson() {
  const responseEditor = byId("response-body");
  const source = responseEditor.value.trim();
  if (!source) {
    showToast("Enter a JSON response body first");
    responseEditor.focus();
    return;
  }

  try {
    responseEditor.value = JSON.stringify(JSON.parse(source), null, 2);
    showToast("Response JSON prettified");
  } catch (_error) {
    showToast("Response body is not valid JSON");
    responseEditor.focus();
  }
}

function editMock(id) {
  const mock = mocksById.get(id);
  if (!mock) return;
  byId("mock-id").value = mock.id;
  byId("collection-id").value = mock.collection_id;
  byId("method").value = mock.method;
  byId("path").value = mock.path;
  byId("status-code").value = mock.status_code;
  byId("latency-ms").value = mock.latency_ms || 0;
  byId("response-body").value = mock.response_body || "";
  byId("headers").value = headersToText(mock.headers);
  byId("form-heading").textContent = "Edit mock";
  byId("submit-button").textContent = "Save changes";
  byId("cancel-edit").hidden = false;
  updatePathPreview();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function statusLabel(statusCode) {
  const statusLabels = {
    200: "OK", 201: "Created", 202: "Accepted", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 304: "Not Modified",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    409: "Conflict", 422: "Unprocessable Content", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable",
  };
  return statusLabels[statusCode] || "";
}

function showResponse({mock, title, eyebrow, path, statusCode, statusText, latency, headers, responseBody}) {
  byId("preview-title").textContent = title;
  byId("preview-eyebrow").textContent = eyebrow;
  byId("preview-method").className = `method m-${mock.method}`;
  byId("preview-method").textContent = mock.method;
  byId("preview-path").textContent = path;
  byId("preview-status").textContent = `${statusCode}${statusText ? ` ${statusText}` : ""}`;
  byId("preview-latency").textContent = latency;
  byId("preview-headers").innerHTML = Object.entries(headers).map(([key, value]) =>
    `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`
  ).join("");

  let formattedBody = responseBody;
  if (responseBody) {
    try {
      formattedBody = JSON.stringify(JSON.parse(responseBody), null, 2);
    } catch (_error) {
      // Non-JSON response bodies are displayed as configured.
    }
  }
  byId("preview-body").textContent = formattedBody || "(empty response body)";
  byId("response-preview").showModal();
}

function previewMock(id) {
  const mock = mocksById.get(id);
  if (!mock) return;

  const responseBody = String(mock.response_body || "");
  const headers = Object.fromEntries(
    Object.entries(mock.headers || {}).map(([key, value]) => [String(key), String(value)])
  );
  if (!Object.keys(headers).some((key) => key.toLowerCase() === "content-type")) {
    headers["Content-Type"] = "application/json";
  }
  headers["Content-Length"] = String(new TextEncoder().encode(responseBody).length);

  showResponse({
    mock,
    title: "Response preview",
    eyebrow: "CONFIGURED RESPONSE",
    path: mockUrl(mock),
    statusCode: mock.status_code,
    statusText: statusLabel(mock.status_code),
    latency: `${mock.latency_ms || 0} ms configured latency`,
    headers,
    responseBody,
  });
}

async function testMock(id, button) {
  const mock = mocksById.get(id);
  if (!mock || button.disabled) return;
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Testing…";
  const startedAt = performance.now();

  try {
    const response = await fetch(mockUrl(mock), {
      method: mock.method,
      cache: "no-store",
      redirect: "manual",
    });
    const elapsedMs = Math.round(performance.now() - startedAt);
    const responseBody = mock.method === "HEAD" ? "" : await response.text();
    const headers = Object.fromEntries(response.headers.entries());
    showResponse({
      mock,
      title: "Live test result",
      eyebrow: "ACTUAL RESPONSE",
      path: absoluteMockUrl(mock),
      statusCode: response.status,
      statusText: response.statusText || statusLabel(response.status),
      latency: `${elapsedMs} ms actual response time`,
      headers,
      responseBody,
    });
    await loadData();
  } catch (error) {
    showToast(error.message || "The mock request failed");
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function copyMockUrl(id) {
  const mock = mocksById.get(id);
  if (!mock) return;
  try {
    await copyText(absoluteMockUrl(mock), "Mock URL copied");
  } catch (error) {
    showToast(error.message || "Could not copy the mock URL");
  }
}

async function copyMockCurl(id) {
  const mock = mocksById.get(id);
  if (!mock) return;
  try {
    await copyText(curlCommand(mock), "cURL command copied");
  } catch (error) {
    showToast(error.message || "Could not copy the cURL command");
  }
}

function openMock(id) {
  const mock = mocksById.get(id);
  if (mock?.method === "GET") window.open(absoluteMockUrl(mock), "_blank", "noopener,noreferrer");
}

async function clearRequestHistory() {
  const collection = collectionForId(selectedCollectionId);
  if (!collection || !historyEntries.length) return;
  if (!window.confirm(`Clear captured requests for "${collection.name}"?`)) return;

  const url = new URL(config.historyUrl, window.location.origin);
  url.searchParams.set("collection_id", selectedCollectionId);
  try {
    const result = await requestJson(`${url.pathname}${url.search}`, {method: "DELETE"});
    selectedHistoryId = null;
    showToast(`${result.deleted_count} request${result.deleted_count === 1 ? "" : "s"} cleared`);
    await loadData();
  } catch (error) {
    showToast(error.message || "Could not clear request history");
  }
}

async function replayRequest() {
  const entry = selectedHistoryDetail;
  if (!entry) return;

  const headers = {};
  Object.entries(entry.request_headers || {}).forEach(([key, value]) => {
    const normalizedKey = key.toLowerCase();
    if (value === "[redacted]") return;
    if (normalizedKey === "accept" || normalizedKey === "content-type") {
      headers[key] = value;
    }
  });
  const options = {
    method: entry.method,
    cache: "no-store",
    redirect: "manual",
    headers,
  };
  if (!["GET", "HEAD"].includes(entry.method) && entry.request_body) {
    options.body = entry.request_body;
  }

  const button = byId("replay-request");
  button.disabled = true;
  button.textContent = "Replaying…";
  try {
    const response = await fetch(entry.path, options);
    await response.text();
    showToast(`Request replayed · ${response.status}`);
    selectedHistoryId = null;
    await loadData();
  } catch (error) {
    showToast(error.message || "Could not replay the request");
  } finally {
    button.disabled = false;
    button.textContent = "Replay request";
  }
}

async function deleteMock(id) {
  if (!window.confirm("Delete this mock?")) return;
  try {
    await requestJson(`${config.collectionUrl}${id}/`, {method: "DELETE"});
    showToast("Mock deleted");
    if (byId("mock-id").value === id) resetForm();
    await loadData();
  } catch (error) {
    showToast(error.message);
  }
}

async function submitMock() {
  const id = byId("mock-id").value;
  let path = byId("path").value.trim();
  if (!path) {
    showToast("Path is required");
    return;
  }
  if (!path.startsWith("/")) path = `/${path}`;
  const payload = {
    collection_id: byId("collection-id").value,
    method: byId("method").value,
    path,
    status_code: Number.parseInt(byId("status-code").value || "200", 10),
    latency_ms: Number.parseInt(byId("latency-ms").value || "0", 10),
    response_body: byId("response-body").value,
    headers: textToHeaders(byId("headers").value),
  };
  try {
    await requestJson(id ? `${config.collectionUrl}${id}/` : config.collectionUrl, {
      method: id ? "PUT" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    selectedCollectionId = payload.collection_id;
    showToast(id ? "Mock updated" : "Mock created");
    resetForm();
    await loadData();
  } catch (error) {
    showToast(error.message);
  }
}

function updatePathPreview() {
  let path = byId("path").value.trim() || "/users/123";
  if (!path.startsWith("/")) path = `/${path}`;
  const selectedCollection = collectionForId(byId("collection-id").value || selectedCollectionId);
  byId("path-preview").textContent = `/${selectedCollection?.slug || "collection"}${path}`;
}

byId("submit-button").addEventListener("click", submitMock);
byId("prettify-response").addEventListener("click", prettifyResponseJson);
byId("cancel-edit").addEventListener("click", resetForm);
byId("close-preview").addEventListener("click", () => byId("response-preview").close());
byId("response-preview").addEventListener("click", (event) => {
  if (event.target === byId("response-preview")) byId("response-preview").close();
});
byId("path").addEventListener("input", updatePathPreview);
byId("collection-id").addEventListener("change", updatePathPreview);
byId("collection-search").addEventListener("input", renderCollections);
byId("mock-search").addEventListener("input", renderMocks);
byId("history-search").addEventListener("input", renderHistory);
byId("refresh-history").addEventListener("click", loadData);
byId("clear-history").addEventListener("click", clearRequestHistory);
byId("replay-request").addEventListener("click", replayRequest);
byId("show-collection-form").addEventListener("click", () => showCollectionForm());
byId("cancel-collection").addEventListener("click", hideCollectionForm);
byId("collection-form").addEventListener("submit", saveCollection);
byId("collection-list").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "select-collection") selectCollection(button.dataset.id);
  if (button.dataset.action === "edit-collection") {
    showCollectionForm(collections.find((collection) => collection.id === button.dataset.id));
  }
  if (button.dataset.action === "delete-collection") deleteCollection(button.dataset.id);
});
byId("mocks-body").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "test-mock") testMock(button.dataset.id, button);
  if (button.dataset.action === "copy-url") copyMockUrl(button.dataset.id);
  if (button.dataset.action === "copy-curl") copyMockCurl(button.dataset.id);
  if (button.dataset.action === "open-mock") openMock(button.dataset.id);
  if (button.dataset.action === "preview-mock") previewMock(button.dataset.id);
  if (button.dataset.action === "edit-mock") editMock(button.dataset.id);
  if (button.dataset.action === "delete-mock") deleteMock(button.dataset.id);
});
byId("history-list").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-history-id]");
  if (button) selectHistory(button.dataset.historyId);
});

loadData();
