import { uploadFileRaw, watchProgress, type Config, type NodeInfo } from "./api";

export function pickRandomNode(cfg: Config): NodeInfo {
  const i = Math.floor(Math.random() * cfg.nodes.length);
  return cfg.nodes[i];
}

export async function startUpload(
  file: File,
  cfg: Config,
  onEvent: (event: string, data: unknown) => void
): Promise<void> {
  const node = pickRandomNode(cfg);
  const init = await uploadFileRaw(node, file);
  return new Promise((resolve, reject) => {
    const stop = watchProgress(node, init.upload_id, (event, data) => {
      onEvent(event, data);
      if (event === "ready") {
        stop();
        resolve();
      } else if (event === "error") {
        stop();
        reject(new Error((data as { message?: string }).message || "error"));
      }
    });
  });
}
