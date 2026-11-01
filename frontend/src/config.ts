import type { Config } from "./api";

export const LOCAL_CONFIG: Config = {
  version: 1,
  nodes: [
    { id: 1, host: "127.0.0.1", port: 9001 },
    { id: 2, host: "127.0.0.1", port: 9002 },
    { id: 3, host: "127.0.0.1", port: 9003 },
    { id: 4, host: "127.0.0.1", port: 9004 },
    { id: 5, host: "127.0.0.1", port: 9005 },
  ],
};
