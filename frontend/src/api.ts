export interface NodeInfo {
  id: number;
  host: string;
  port: number;
}

export interface Config {
  version: number;
  nodes: NodeInfo[];
}

export interface FileEntry {
  file_id: string;
  sender: number;
  shards: Record<string, string>;
  ts: number;
  hash?: string;
  name?: string;
}

export interface UploadInit {
  upload_id: string;
  size: number;
}

const base = (n: NodeInfo) => `http://${n.host}:${n.port}`;

const opts = (extra: RequestInit = {}): RequestInit => ({
  credentials: "include",
  ...extra,
});

export async function register(username: string, password: string): Promise<void> {
  const r = await fetch(`/auth/register`, opts({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }));
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`register failed: ${r.status} ${text}`);
  }
}

export async function login(username: string, password: string): Promise<void> {
  const r = await fetch(`/auth/login`, opts({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }));
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`login failed: ${r.status} ${text}`);
  }
}

export async function logout(): Promise<void> {
  await fetch(`/auth/logout`, opts({ method: "POST" }));
}

export async function health(n: NodeInfo): Promise<{ node_id: number; status: string }> {
  const r = await fetch(`${base(n)}/health`, opts());
  if (!r.ok) throw new Error(`health ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function fetchConfig(n: NodeInfo): Promise<Config> {
  const r = await fetch(`${base(n)}/config`, opts());
  if (!r.ok) throw new Error(`config ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function uploadFileRaw(n: NodeInfo, file: File): Promise<UploadInit> {
  const r = await fetch(`${base(n)}/upload`, opts({
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Filename": file.name,
    },
  }));
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`upload to node ${n.id} failed: ${r.status} ${text}`);
  }
  return r.json();
}

export function watchProgress(
  n: NodeInfo,
  uploadId: string,
  onEvent: (event: string, data: unknown) => void
): () => void {
  const url = `${base(n)}/progress/${encodeURIComponent(uploadId)}`;
  const es = new EventSource(url, { withCredentials: true } as EventSourceInit);
  const names = [
    "received",
    "encrypting",
    "splitting",
    "sending",
    "broadcasting",
    "ready",
    "error",
  ];
  for (const name of names) {
    es.addEventListener(name, (e: MessageEvent) => {
      onEvent(name, JSON.parse(e.data || "{}"));
    });
  }
  es.onerror = () => {
    es.close();
    onEvent("error", { message: "progress stream disconnected" });
  };
  return () => es.close();
}

export async function reconstruct(n: NodeInfo, fileId: string): Promise<Blob> {
  const r = await fetch(`${base(n)}/reconstruct/${encodeURIComponent(fileId)}`, opts());
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`reconstruct failed: ${r.status} ${text}`);
  }
  return await r.blob();
}

export async function fetchCatalogue(n: NodeInfo): Promise<Record<string, FileEntry>> {
  const r = await fetch(`${base(n)}/catalogue`, opts());
  if (!r.ok) throw new Error(`catalogue ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function deleteFile(n: NodeInfo, fileId: string): Promise<unknown> {
  const r = await fetch(`${base(n)}/delete/${encodeURIComponent(fileId)}`, opts({
    method: "DELETE",
  }));
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`delete failed: ${r.status} ${text}`);
  }
  return r.json();
}
