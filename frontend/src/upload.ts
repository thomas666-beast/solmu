import { uploadFileRaw, type UploadResponse, type Config, type NodeInfo } from "./api";

export interface UploadResult {
  fileId: string;
  size: number;
  hash: string;
  shareIds: string[];
}


export function pickRandomNode(cfg: Config): NodeInfo {
  const i = Math.floor(Math.random() * cfg.nodes.length);
  return cfg.nodes[i];
}

export async function uploadFile(
  file: File,
  cfg: Config
): Promise<{ node: NodeInfo; response: UploadResponse }> {
  const node = pickRandomNode(cfg);
  const response = await uploadFileRaw(node, file);
  return { node, response };
}

