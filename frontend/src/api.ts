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

export interface BroadcastResult {
  results: Record<string, number | string>;
}

const base = (n: NodeInfo) => `http://${n.host}:${n.port}`;

export async function health(n: NodeInfo): Promise<{ node_id: number; status: string }> {
  const r = await fetch(`${base(n)}/health`);
  if (!r.ok) throw new Error(`health ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function fetchConfig(n: NodeInfo): Promise<Config> {
  const r = await fetch(`${base(n)}/config`);
  if (!r.ok) throw new Error(`config ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function uploadShard(n: NodeInfo, shardId: string, data: Uint8Array): Promise<void> {
  const r = await fetch(`${base(n)}/shard/${shardId}`, {
    method: "POST",
    body: data,
    headers: { "Content-Type": "application/octet-stream" },
  });
  if (!r.ok) throw new Error(`upload shard to ${n.id} failed: ${r.status}`);
}

export async function downloadShard(n: NodeInfo, shardId: string): Promise<Uint8Array | null> {
  const r = await fetch(`${base(n)}/shard/${shardId}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`download shard from ${n.id} failed: ${r.status}`);
  return new Uint8Array(await r.arrayBuffer());
}

export async function broadcast(n: NodeInfo, entry: FileEntry): Promise<BroadcastResult> {
  const r = await fetch(`${base(n)}/broadcast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  if (!r.ok) throw new Error(`broadcast failed: ${r.status}`);
  return r.json();
}

export async function fetchCatalogue(n: NodeInfo): Promise<Record<string, FileEntry>> {
  const r = await fetch(`${base(n)}/catalogue`);
  if (!r.ok) throw new Error(`catalogue ${n.id} failed: ${r.status}`);
  return r.json();
}

export async function fetchRemoteConfig(n: NodeInfo): Promise<Config> {
  const r = await fetch(`${base(n)}/remote-config`);
  if (!r.ok) throw new Error(`remote-config ${n.id} failed: ${r.status}`);
  return r.json();
}

export interface ShardMap {
  [nodeId: string]: string;
}

export interface UploadResponse {
  size: number;
  file_id: string;
  hash: string;
  shards: ShardMap;
  distribution: Record<string, number | string>;
}

export async function uploadFileRaw(n: NodeInfo, file: File): Promise<UploadResponse> {
  const r = await fetch(`${base(n)}/upload`, {
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Filename": file.name,
    },
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`upload to node ${n.id} failed: ${r.status} ${text}`);
  }
  return r.json();
}

export async function reconstruct(n: NodeInfo, fileId: string): Promise<Blob> {
  const r = await fetch(`${base(n)}/reconstruct/${encodeURIComponent(fileId)}`);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`reconstruct failed: ${r.status} ${text}`);
  }
  return await r.blob();
}
