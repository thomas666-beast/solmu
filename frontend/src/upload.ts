import { splitBytes, sha256Hex } from "./shamir";
import { uploadShard, broadcast } from "./api";
import type { Config, FileEntry } from "./api";

export interface UploadResult {
  fileId: string;
  size: number;
  hash: string;
  shareIds: string[];
}

export async function uploadFile(
  file: File,
  cfg: Config
): Promise<UploadResult> {
  const raw = new Uint8Array(await file.arrayBuffer());
  const n = cfg.nodes.length;
  if (n < 2) throw new Error("need at least 2 nodes");

  const fileId = `${Date.now()}-${file.name}`;
  const hash = await sha256Hex(raw);
  const shares = await splitBytes(raw, n);

  const shareIds: string[] = [];
  const shardMap: Record<string, string> = {};

  for (let i = 0; i < cfg.nodes.length; i++) {
    const node = cfg.nodes[i];
    const shareId = `${fileId}::${node.id}`;
    await uploadShard(node, shareId, shares[i]);
    shareIds.push(shareId);
    shardMap[String(node.id)] = shareId;
  }

  const entry: FileEntry = {
    file_id: fileId,
    sender: cfg.nodes[0].id,
    shards: shardMap,
    ts: Date.now(),
    hash,
  };
  await broadcast(cfg.nodes[0], entry);

  return { fileId, size: raw.length, hash, shareIds };
}
