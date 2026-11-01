import { split, combine } from "shamir-secret-sharing";

export async function splitBytes(data: Uint8Array, n: number): Promise<Uint8Array[]> {
  if (n < 2) throw new Error("n must be >= 2");
  return await split(data, n, n); // threshold = n → all shares required
}

export async function combineShares(shares: Uint8Array[]): Promise<Uint8Array> {
  if (shares.length === 0) throw new Error("no shares");
  return await combine(shares);
}

export function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}
