import {
  deleteFile,
  fetchCatalogue,
  health,
  logout,
  type FileEntry,
} from "./api";
import { LOCAL_CONFIG } from "./config";
import { downloadFile, saveToDisk } from "./download";
import { startUpload } from "./upload";

const logEl = document.getElementById("log") as HTMLPreElement;
const fileInput = document.getElementById("file-input") as HTMLInputElement;
const uploadBtn = document.getElementById("upload-btn") as HTMLButtonElement;
const refreshBtn = document.getElementById("refresh-btn") as HTMLButtonElement;
const refreshStatusBtn = document.getElementById("refresh-status-btn") as HTMLButtonElement;
const logoutBtn = document.getElementById("logout-btn") as HTMLButtonElement;
const catEl = document.getElementById("catalogue") as HTMLUListElement;
const statusEl = document.getElementById("node-status") as HTMLUListElement;
const sessionUserEl = document.getElementById("session-user") as HTMLSpanElement;
const uploadStatusEl = document.getElementById("upload-status") as HTMLDivElement;

function log(msg: string) {
  const line = document.createElement("div");
  line.textContent = msg;
  if (msg.startsWith("error") || msg.includes("failed")) line.className = "line-err";
  else if (
    msg.includes("ready") ||
    msg.includes("uploaded") ||
    msg.includes("reconstructed") ||
    msg.includes("deleted")
  )
    line.className = "line-ok";
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  console.log(msg);
}

async function refreshStatus() {
  statusEl.innerHTML = "";
  for (const n of LOCAL_CONFIG.nodes) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = `node ${n.id} · ${n.host}:${n.port}`;
    const state = document.createElement("span");
    try {
      await health(n);
      state.textContent = "ok";
      state.className = "ok";
    } catch (e) {
      const m = (e as Error).message;
      if (m.includes("401")) {
        window.location.href = "/login";
        return;
      }
      state.textContent = "unreachable";
      state.className = "down";
    }
    li.appendChild(name);
    li.appendChild(state);
    statusEl.appendChild(li);
  }
}

async function refreshCatalogue() {
  catEl.innerHTML = "";
  let cat: Record<string, FileEntry>;
  try {
    cat = await fetchCatalogue(LOCAL_CONFIG.nodes[0]);
  } catch (e) {
    const m = (e as Error).message;
    if (m.includes("401")) {
      window.location.href = "/login";
      return;
    }
    log(`catalogue failed: ${m}`);
    return;
  }
  const entries = Object.values(cat);
  if (entries.length === 0) {
    const li = document.createElement("li");
    li.textContent = "(empty)";
    catEl.appendChild(li);
    return;
  }
  for (const entry of entries) {
    const li = document.createElement("li");
    
    // Left side: file info
    const label = document.createElement("span");
    const hashShort = entry.hash ? entry.hash.slice(0, 10) : "----------";
    const when = new Date(entry.ts).toISOString().replace("T", " ").slice(0, 19);
    label.innerHTML = `<span class="dim">${hashShort}</span> · ${entry.name || entry.file_id} <span class="dim" style="font-size: 10px;">${when}</span>`;
    
    // Right side: action buttons grouped
    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.gap = "8px";
    
    const btn = document.createElement("button");
    btn.textContent = "download";
    btn.style.fontSize = "11px";
    btn.addEventListener("click", () => handleDownload(entry));
    
    const delBtn = document.createElement("button");
    delBtn.textContent = "delete";
    delBtn.style.fontSize = "11px";
    delBtn.addEventListener("click", () => handleDelete(entry));
    
    actions.appendChild(btn);
    actions.appendChild(delBtn);
    
    li.appendChild(label);
    li.appendChild(actions);
    catEl.appendChild(li);
  }
}

async function handleDownload(entry: FileEntry) {
  log(`reconstructing ${entry.file_id}`);
  try {
    const { blob, filename } = await downloadFile(entry, LOCAL_CONFIG);
    log(`reconstructed ${blob.size} bytes`);
    saveToDisk(blob, filename);
    log(`saved as ${filename}`);
  } catch (e) {
    log(`download failed: ${(e as Error).message}`);
  }
}

async function handleDelete(entry: FileEntry) {
  const label = entry.name || entry.file_id;
  if (!confirm(`delete ${label} from all nodes?`)) {
    log(`delete cancelled`);
    return;
  }
  log(`deleting ${label}`);
  try {
    await deleteFile(LOCAL_CONFIG.nodes[0], entry.file_id);
    log(`deleted ${label}`);
    await refreshCatalogue();
  } catch (e) {
    log(`delete failed: ${(e as Error).message}`);
  }
}

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    log("no file selected");
    return;
  }
  const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
  uploadStatusEl.textContent = `uploading ${file.name} (${sizeMb} MB)...`;
  log(`uploading ${file.name} (${sizeMb} MB)`);
  
  try {
    await startUpload(file, LOCAL_CONFIG, (event, data) => {
      const d = data as Record<string, unknown>;
      let msg = "";
      if (event === "received") msg = `node received file (${d.size} bytes)`;
      else if (event === "encrypting") msg = `encrypting…`;
      else if (event === "splitting") msg = `splitting…`;
      else if (event === "sending") msg = `sending share to node ${d.node_id}`;
      else if (event === "broadcasting") msg = `broadcasting catalogue…`;
      else if (event === "ready") msg = `ready · file_id=${d.file_id}`;
      else if (event === "error") msg = `error: ${d.message}`;
      
      if (msg) {
        log(msg);
        uploadStatusEl.textContent = msg;
      }
    });
    fileInput.value = "";
    uploadStatusEl.textContent = `ready · check catalogue`;
    await refreshCatalogue();
  } catch (e) {
    log(`upload failed: ${(e as Error).message}`);
    uploadStatusEl.textContent = `failed`;
  }
});

refreshBtn.addEventListener("click", refreshCatalogue);
refreshStatusBtn.addEventListener("click", refreshStatus);
logoutBtn.addEventListener("click", async () => {
  await logout();
  window.location.href = "/login";
});

// --- Tab Switching Logic ---
const tabBtns = document.querySelectorAll(".tab-btn");
const tabPanes = document.querySelectorAll(".tab-pane");

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    // Remove active class from all buttons and panes
    tabBtns.forEach((b) => b.classList.remove("active"));
    tabPanes.forEach((p) => p.classList.remove("active"));

    // Add active class to clicked button and its target pane
    btn.classList.add("active");
    const targetId = btn.getAttribute("data-target");
    if (targetId) {
      document.getElementById(targetId)?.classList.add("active");
    }
  });
});

(async () => {
  sessionUserEl.textContent = "session active";
  await refreshStatus();
  await refreshCatalogue();
  log("solmu ready");
})();

// Auto-refresh catalogue and node status every 5 minutes
setInterval(() => {
  // Only refresh if the tab is visible to save resources
  if (document.visibilityState === "visible") {
    refreshStatus();
    refreshCatalogue();
  }
}, 5 * 60 * 1000);
