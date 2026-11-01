import { reconstruct, type Config, type FileEntry } from "./api";

export async function downloadFile(
  entry: FileEntry,
  cfg: Config
): Promise<{ blob: Blob; filename: string }> {
  // Talk to the first node in the config; it will gather shares from peers.
  const node = cfg.nodes[0];
  const blob = await reconstruct(node, entry.file_id);
  const filename = entry.name || entry.file_id.split("-").slice(1).join("-") || "download.bin";
  return { blob, filename };
}

export function saveToDisk(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
