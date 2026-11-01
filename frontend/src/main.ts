import { LOCAL_CONFIG } from "./config";
import { uploadFile } from "./upload";
import { downloadFile, saveToDisk } from "./download";
import { fetchCatalogue } from "./api";
import type { FileEntry } from "./api";
import { health } from "./api";

const logEl = document.getElementById("log") as HTMLPreElement;
const fileInput = document.getElementById("file-input") as HTMLInputElement;
const uploadBtn = document.getElementById("upload-btn") as HTMLButtonElement;
const refreshBtn = document.getElementById("refresh-btn") as HTMLButtonElement;
const catEl = document.getElementById("catalogue") as HTMLUListElement;
const statusEl = document.getElementById("node-status") as HTMLUListElement;
const refreshStatusBtn = document.getElementById("refresh-status-btn") as HTMLButtonElement;

function log(msg: string) {
  const line = document.createElement("div");
  line.textContent = msg;
  if (msg.startsWith("error") || msg.includes("failed")) line.className = "line-err";
  else if (msg.includes("uploaded") || msg.includes("reconstructed") || msg.includes("ready")) line.className = "line-ok";
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
    } catch {
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
  const cat = await fetchCatalogue(LOCAL_CONFIG.nodes[0]);
  const entries = Object.values(cat);
  if (entries.length === 0) {
    const li = document.createElement("li");
    li.textContent = "(empty)";
    catEl.appendChild(li);
    return;
  }
  for (const entry of entries) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    const hashShort = entry.hash ? entry.hash.slice(0, 10) : "---------";
    label.innerHTML = `<span class="dim">${hashShort}</span> · ${entry.file_id}`;
    const btn = document.createElement("button");
    btn.textContent = "download";
    btn.addEventListener("click", () => handleDownload(entry));
    li.appendChild(label);
    li.appendChild(btn);
    catEl.appendChild(li);
  }
}

async function handleDownload(entry: FileEntry) {
  log(`downloading ${entry.file_id}`);
  try {
    const { data, hash } = await downloadFile(entry, LOCAL_CONFIG);
    log(`reconstructed ${data.length} bytes, hash=${hash.slice(0, 16)}…`);
    const name = entry.file_id.split("-").slice(1).join("-") || "download.bin";
    saveToDisk(data, name);
    log(`saved as ${name}`);
  } catch (e) {
    log(`download failed: ${(e as Error).message}`);
  }
}

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    log("no file selected");
    return;
  }
  log(`uploading ${file.name} (${file.size} bytes)`);
  try {
    const result = await uploadFile(file, LOCAL_CONFIG);
    log(`uploaded: ${result.fileId}, hash=${result.hash.slice(0, 16)}…`);
    fileInput.value = "";            // ← add this
    await refreshCatalogue();
  } catch (e) {
    log(`upload failed: ${(e as Error).message}`);
  }
});

refreshBtn.addEventListener("click", refreshCatalogue);
refreshStatusBtn.addEventListener("click", refreshStatus);

refreshCatalogue();
refreshStatus();
log("solmu ready");

