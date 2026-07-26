const config = window.documentViewerConfig;
const elements = {
  welcome: document.querySelector("#welcome"),
  workspace: document.querySelector("#workspace"),
  openForm: document.querySelector("#openForm"),
  filePath: document.querySelector("#filePath"),
  openError: document.querySelector("#openError"),
  uploadError: document.querySelector("#uploadError"),
  fileUpload: document.querySelector("#fileUpload"),
  dropZone: document.querySelector("#dropZone"),
  editor: document.querySelector("#editor"),
  preview: document.querySelector("#preview"),
  saveButton: document.querySelector("#saveButton"),
  saveState: document.querySelector("#saveState"),
  autosave: document.querySelector("#autosave"),
  fileName: document.querySelector("#fileName"),
  fileLocation: document.querySelector("#fileLocation"),
  fileType: document.querySelector("#fileType"),
  cursorPosition: document.querySelector("#cursorPosition"),
  externalChange: document.querySelector("#externalChange"),
  divider: document.querySelector("#divider"),
  panes: document.querySelector("#panes"),
  toast: document.querySelector("#toast"),
};
const state = {path:"",name:"",source:"path",kind:"markdown",mtimeNs:null,dirty:false,renderTimer:null,saveTimer:null,pollTimer:null};
const allowedFilePattern = /\.(md|markdown|html|htm)$/i;
const maxFileSize = 5 * 1024 * 1024;

function csrfToken() {
  const pageToken = document.querySelector('meta[name="csrf-token"]')?.content;
  if (pageToken && pageToken !== "NOTPROVIDED") return pageToken;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="))
    ?.slice("csrftoken=".length) || "";
}

async function api(url, body) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type":"application/json","X-CSRFToken":csrfToken()},
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({error:"Something went wrong."}));
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong.");
    error.data = data;
    throw error;
  }
  return data;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => elements.toast.classList.remove("show"), 2600);
}

function setDirty(dirty) {
  state.dirty = dirty;
  elements.saveButton.disabled = state.source === "upload" ? false : (!state.path || !dirty);
  elements.saveState.classList.toggle("dirty", dirty);
  if (state.source === "upload") {
    elements.saveState.lastChild.textContent = dirty ? " Edited locally" : " Ready to download";
  } else {
    elements.saveState.lastChild.textContent = dirty ? " Unsaved changes" : " Saved";
  }
}

function previewDocument(html) {
  elements.preview.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
  :root{color:#243027;background:#fff}*{box-sizing:border-box}body{max-width:900px;margin:0 auto;padding:42px 48px 80px;font:16px/1.7 ui-sans-serif,system-ui,-apple-system,sans-serif}h1,h2,h3,h4{line-height:1.2;margin:1.6em 0 .6em}h1{font:700 2.8rem/1.05 Georgia,serif;letter-spacing:-.04em;border-bottom:2px solid #f05a28;padding-bottom:.3em}h2{font-size:1.7rem;border-bottom:1px solid #ddd;padding-bottom:.3em}a{color:#bf421c}img{max-width:100%}blockquote{margin:1.4em 0;padding:.2em 1.2em;border-left:4px solid #f05a28;color:#687069}code{padding:.15em .35em;background:#f2eee6;font:90% SFMono-Regular,Consolas,monospace}pre{padding:18px;overflow:auto;color:#dce6de;background:#17211b}pre code{padding:0;background:none}table{width:100%;border-collapse:collapse}th,td{padding:9px 12px;border:1px solid #d9d4ca;text-align:left}th{background:#f2eee6}@media(max-width:600px){body{padding:28px 22px}h1{font-size:2.1rem}}
  </style></head><body>${html}</body></html>`;
}

async function renderPreview() {
  try {
    const data = await api(config.renderUrl, {content:elements.editor.value,kind:state.kind});
    previewDocument(data.html);
  } catch (error) {
    previewDocument(`<p style="color:#a22">${escapeHtml(error.message)}</p>`);
  }
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = String(value);
  return span.innerHTML;
}

function scheduleRender() {
  clearTimeout(state.renderTimer);
  state.renderTimer = setTimeout(renderPreview, 140);
}

function scheduleAutosave() {
  clearTimeout(state.saveTimer);
  if (elements.autosave.checked) state.saveTimer = setTimeout(() => saveDocument(), 900);
}

async function openDocument(path = elements.filePath.value) {
  elements.openError.hidden = true;
  try {
    const data = await api(config.loadUrl, {path});
    Object.assign(state, {path:data.path,name:data.name,source:"path",kind:data.kind,mtimeNs:data.mtime_ns});
    elements.filePath.value = data.path;
    elements.editor.value = data.content;
    elements.fileName.textContent = data.name;
    elements.fileLocation.textContent = data.path;
    elements.fileType.textContent = data.kind === "markdown" ? "MD" : "HTML";
    elements.saveButton.firstChild.textContent = "Save ";
    elements.autosave.disabled = false;
    elements.welcome.hidden = true;
    elements.workspace.hidden = false;
    elements.externalChange.hidden = true;
    setDirty(false);
    updateCursor();
    await renderPreview();
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(checkExternalChange, 1800);
    history.replaceState(null, "", `?file=${encodeURIComponent(data.path)}`);
    elements.editor.focus();
  } catch (error) {
    elements.openError.textContent = error.message;
    elements.openError.hidden = false;
  }
}

async function openUpload(file) {
  elements.uploadError.hidden = true;
  if (!file) return;
  if (!allowedFilePattern.test(file.name)) {
    elements.uploadError.textContent = "Only Markdown (.md, .markdown) and HTML (.html, .htm) files are supported.";
    elements.uploadError.hidden = false;
    return;
  }
  if (file.size > maxFileSize) {
    elements.uploadError.textContent = "The file is larger than the 5 MB limit.";
    elements.uploadError.hidden = false;
    return;
  }
  try {
    const content = await file.text();
    clearInterval(state.pollTimer);
    Object.assign(state, {path:"",name:file.name,source:"upload",kind:/\.(md|markdown)$/i.test(file.name)?"markdown":"html",mtimeNs:null});
    elements.editor.value = content;
    elements.fileName.textContent = file.name;
    elements.fileLocation.textContent = "Uploaded from this browser";
    elements.fileType.textContent = state.kind === "markdown" ? "MD" : "HTML";
    elements.saveButton.firstChild.textContent = "Download ";
    elements.autosave.checked = false;
    elements.autosave.disabled = true;
    elements.welcome.hidden = true;
    elements.workspace.hidden = false;
    elements.externalChange.hidden = true;
    setDirty(false);
    updateCursor();
    await renderPreview();
    history.replaceState(null, "", location.pathname);
    elements.editor.focus();
  } catch (_error) {
    elements.uploadError.textContent = "Could not read this file. Make sure it is a UTF-8 text document.";
    elements.uploadError.hidden = false;
  } finally {
    elements.fileUpload.value = "";
  }
}

async function openPasteEditor() {
  clearInterval(state.pollTimer);
  Object.assign(state, {
    path: "",
    name: "pasted-markdown.md",
    source: "upload",
    kind: "markdown",
    mtimeNs: null,
  });
  elements.editor.value = "";
  elements.fileName.textContent = state.name;
  elements.fileLocation.textContent = "Pasted Markdown · stored only in this browser";
  elements.fileType.textContent = "MD";
  elements.saveButton.firstChild.textContent = "Download ";
  elements.autosave.checked = false;
  elements.autosave.disabled = true;
  elements.welcome.hidden = true;
  elements.workspace.hidden = false;
  elements.externalChange.hidden = true;
  setDirty(false);
  updateCursor();
  await renderPreview();
  history.replaceState(null, "", location.pathname);
  elements.editor.focus();
}

function downloadUpload() {
  const blob = new Blob([elements.editor.value], {type:state.kind==="markdown"?"text/markdown;charset=utf-8":"text/html;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = state.name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  setDirty(false);
  showToast("Edited document downloaded");
}

async function saveDocument(force = false) {
  if (state.source === "upload") {
    downloadUpload();
    return;
  }
  if (!state.path || !state.dirty) return;
  elements.saveState.lastChild.textContent = " Saving…";
  try {
    const data = await api(config.saveUrl, {path:state.path,content:elements.editor.value,mtime_ns:state.mtimeNs,force});
    state.mtimeNs = data.mtime_ns;
    elements.externalChange.hidden = true;
    setDirty(false);
    showToast("Document saved");
  } catch (error) {
    if (error.data?.conflict) {
      elements.externalChange.hidden = false;
      elements.saveState.lastChild.textContent = " Save blocked";
    } else {
      elements.saveState.lastChild.textContent = " Save failed";
      showToast(error.message);
    }
  }
}

async function checkExternalChange() {
  if (!state.path || document.hidden) return;
  try {
    const data = await api(config.statusUrl, {path:state.path});
    if (data.mtime_ns !== state.mtimeNs) {
      if (state.dirty) elements.externalChange.hidden = false;
      else await openDocument(state.path);
    }
  } catch (_error) {}
}

function updateCursor() {
  const before = elements.editor.value.slice(0, elements.editor.selectionStart);
  const lines = before.split("\n");
  elements.cursorPosition.textContent = `Ln ${lines.length}, Col ${lines.at(-1).length + 1}`;
}

elements.openForm.addEventListener("submit", (event) => {event.preventDefault();openDocument();});
document.querySelector("#pasteMarkdown").addEventListener("click", openPasteEditor);
document.querySelector("#chooseFile").addEventListener("click", (event) => {event.stopPropagation();elements.fileUpload.click();});
elements.fileUpload.addEventListener("change", () => openUpload(elements.fileUpload.files[0]));
elements.dropZone.addEventListener("click", (event) => {if (event.target !== elements.fileUpload) elements.fileUpload.click();});
elements.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {event.preventDefault();elements.fileUpload.click();}
});
for (const eventName of ["dragenter","dragover"]) elements.dropZone.addEventListener(eventName, (event) => {event.preventDefault();elements.dropZone.classList.add("dragging");});
for (const eventName of ["dragleave","drop"]) elements.dropZone.addEventListener(eventName, (event) => {event.preventDefault();elements.dropZone.classList.remove("dragging");});
elements.dropZone.addEventListener("drop", (event) => openUpload(event.dataTransfer.files[0]));
elements.editor.addEventListener("input", () => {setDirty(true);scheduleRender();scheduleAutosave();updateCursor();});
elements.editor.addEventListener("click", updateCursor);
elements.editor.addEventListener("keyup", updateCursor);
elements.editor.addEventListener("keydown", (event) => {
  if (event.key === "Tab") {
    event.preventDefault();
    elements.editor.setRangeText("  ", elements.editor.selectionStart, elements.editor.selectionEnd, "end");
    elements.editor.dispatchEvent(new Event("input"));
  }
});
elements.saveButton.addEventListener("click", () => saveDocument());
document.querySelector("#refreshPreview").addEventListener("click", renderPreview);
document.querySelector("#changeFile").addEventListener("click", () => {
  if (state.dirty && !confirm("Discard your unsaved changes and open another file?")) return;
  clearInterval(state.pollTimer);
  elements.autosave.disabled = false;
  elements.workspace.hidden = true;
  elements.welcome.hidden = false;
  elements.filePath.focus();
});
document.querySelector("#reloadFile").addEventListener("click", () => openDocument(state.path));
document.querySelector("#dismissChange").addEventListener("click", () => {elements.externalChange.hidden=true;saveDocument(true);});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {event.preventDefault();saveDocument();}
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {event.preventDefault();event.returnValue="";}
});

let dragging = false;
elements.divider.addEventListener("pointerdown", (event) => {dragging=true;elements.divider.setPointerCapture(event.pointerId);});
elements.divider.addEventListener("pointermove", (event) => {
  if (!dragging || window.innerWidth <= 900) return;
  const box = elements.panes.getBoundingClientRect();
  const percent = Math.max(25, Math.min(75, ((event.clientX - box.left) / box.width) * 100));
  document.documentElement.style.setProperty("--editor-width", `${percent}%`);
});
elements.divider.addEventListener("pointerup", () => {dragging=false;});
elements.divider.addEventListener("keydown", (event) => {
  if (!["ArrowLeft","ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--editor-width"));
  const next = Math.max(25, Math.min(75, current + (event.key==="ArrowRight"?5:-5)));
  document.documentElement.style.setProperty("--editor-width", `${next}%`);
});

const requestedFile = new URLSearchParams(location.search).get("file");
if (requestedFile) {
  elements.filePath.value = requestedFile;
  openDocument(requestedFile);
}
