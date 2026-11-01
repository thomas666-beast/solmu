import { combineShares, sha256Hex } from "./shamir";
import { downloadShard } from "./api";
import type { Config, FileEntry } from "./api";

export interface DownloadResult {
  data: Uint8Array;
  hash: string;
}

export async function downloadFile(
  entry: FileEntry,
  cfg: Config
): Promise<DownloadResult> {
  const shareIds = Object.keys(entry.shards).sort((a, b) => Number(a) - Number(b));
  if (shareIds.length !== cfg.nodes.length) {
    throw new Error(
      `expected ${cfg.nodes.length} shares, entry lists ${shareIds.length}`
    );
  }

  const shares: Uint8Array[] = [];
  for (const nodeIdStr of shareIds) {
    const nodeId = Number(nodeIdStr);
    const node = cfg.nodes.find(n => n.id === nodeId);
    if (!node) throw new Error(`node ${nodeId} not in config`);
    const share = await downloadShard(node, entry.shards[nodeIdStr]);
    if (!share) throw new Error(`share missing on node ${nodeId}`);
    shares.push(share);
  }

  const data = await combineShares(shares);
  const hash = await sha256Hex(data);

  if (entry.hash && entry.hash !== hash) {
    throw new Error(
      `hash mismatch: expected ${entry.hash.slice(0, 12)}…, got ${hash.slice(0, 12)}…`
    );
  }

  return { data, hash }
}

export function saveToDisk(data: Uint8Array, filename: string): void {
  const blob = new Blob([data], { type: "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
