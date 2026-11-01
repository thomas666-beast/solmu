# solmu

**Distributed ephemeral file transfer.** A file is split into `n` shares with
Shamir secret sharing and pushed to `n` nodes. It can only be reconstructed
when **all** `n` shares are present. Shares expire after 24 hours. Loss is
accepted: data is in transit, not stored.

*Finnish* **solmu** = "node, knot".

---

## Table of contents

1. [What it is](#what-it-is)
2. [What it is not](#what-it-is-not)
3. [How it works](#how-it-works)
4. [Project layout](#project-layout)
5. [Requirements](#requirements)
6. [Install](#install)
7. [Run](#run)
8. [Use](#use)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Design decisions](#design-decisions)
12. [Expiry and deletion](#expiry-and-deletion)
13. [Security notes](#security-notes)
14. [Roadmap](#roadmap)
15. [License](#license)

---

## What it is

- A teaching and research project, written from scratch.
- A small distributed system: several nodes on localhost or on a LAN.
- A demonstration of **n-of-n secret sharing** for data in transit.
- A browser client in TypeScript and a Flask backend, with no database.

The flow:

1. You pick a file in the browser.
2. The browser hashes it with SHA-256, then splits it into 5 shares
   (threshold = 5, so all shares are required).
3. Each share is POSTed to one node and stored as a temporary file.
4. Every node receives a catalogue entry: file id, sender, per-node share
   ids, timestamp, hash.
5. To download, the browser pulls all 5 shares, combines them, verifies the
   SHA-256, and saves the file.

## What it is not

- **Not redundant.** If one node is down, the file cannot be reconstructed.
  This is a deliberate choice: "all shares required" means no partial
  recovery. It is the opposite of RAID or erasure-coded storage.
- **Not durable.** Shares live in `/tmp/solmu-shards/` by default. On many
  systems `/tmp` is cleared on reboot. Shares older than 24 hours are
  deleted on read and on startup cleanup.
- **Not authenticated.** No users, no tokens, no TLS. Use on localhost or a
  trusted LAN only. Put it behind a reverse proxy with auth if you must
  expose it.
- **Not built for large files.** The browser holds the whole file and all
  shares in memory. A few megabytes are fine; hundreds are not.
- **Not a storage system.** It is a transfer mechanism that forgets.

## How it works

### Secret sharing

The browser splits the file with
[`shamir-secret-sharing`](https://www.npmjs.com/package/shamir-secret-sharing),
a zero-dependency TypeScript implementation of Shamir's Secret Sharing over
GF(2^8).

With `n` nodes we call `split(data, n, n)`: `n` shares are produced, and the
threshold is also `n`, so all `n` shares are required for `combine` to
return the original data. There is no partial recovery by design.

### Integrity

Before splitting, the browser computes `SHA-256(data)`. The hash is stored
in the catalogue entry. On download, the browser recomputes the hash of the
combined bytes and compares. A mismatch means at least one share was
corrupted, and the download is rejected.

### Distribution

Each share is uploaded with `POST /shard/<shard_id>` to a distinct node.
The node writes it atomically: write to `<id>.tmp`, `fsync`, `rename`.
A crash mid-write leaves either the previous version or no file, never a
truncated share.

After all uploads succeed, node 1 calls `POST /broadcast` with the
catalogue entry. Each node stores the entry in its own catalogue and in
`/tmp/solmu-shards/catalogue.json`.

### Configuration sync

`config/nodes.json` holds the node list and a version number. Node 1 polls
this file every 5 seconds. When the version changes, node 1 pushes the new
list to every other node with `POST /config-sync`. Each peer stores it in
memory and exposes it at `GET /remote-config`.

On startup, non-main nodes also pull the current list from node 1 with
`GET /config`, so a peer that boots after a version bump is not stale.

## Project layout

```
solmu/
├── backend/
│   ├── app.py            Flask app: routes and startup
│   ├── config.py         reads config/nodes.json
│   ├── storage.py        share files, catalogue, 24h cleanup
│   ├── requirements.txt
│   └── tests/
│       ├── conftest.py
│       ├── test_api.py
│       └── test_storage.py
├── config/
│   └── nodes.json        shared node list: id, host, port, version
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── logo.svg
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts       entry point, UI wiring
│       ├── api.ts        typed wrappers around backend routes
│       ├── shamir.ts     split / combine / sha256
│       ├── upload.ts     file -> shares -> nodes -> broadcast
│       ├── download.ts   shares -> combine -> verify -> save
│       └── config.ts     local copy of the node list
├── package.json
└── README.md
```

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer and npm
- Linux or macOS recommended; Windows works with WSL or Git Bash

## Install

```bash
git clone <repo-url> solmu
cd solmu

python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

npm install
```

## Run

Start all five nodes in separate terminals, or use one shell with `&`:

```bash
cd backend
source ../venv/bin/activate

python app.py --node-id 1 &
python app.py --node-id 2 &
python app.py --node-id 3 &
python app.py --node-id 4 &
python app.py --node-id 5 &
```

Build the frontend once:

```bash
cd ..
npm run build
```

Then open:

```
http://127.0.0.1:9001/
```

To rebuild the frontend after editing `frontend/src/*.ts`:

```bash
npm run build
```

For live rebuild while editing:

```bash
npm run watch
```

## Use

1. Open `http://127.0.0.1:9001/`.
2. The **nodes** panel shows each node's health.
3. Choose a file and click **upload**. The log shows the file id, hash, and
   the number of shares distributed.
4. The file appears in the **catalogue**.
5. Click **download** next to an entry. The browser fetches all shares,
   combines them, verifies the hash, and saves the file.
6. Stop one node and click **download** again. The download fails with
   `share missing on node N` — that is the n-of-n rule in action.

## Configuration

`config/nodes.json`:

```json
{
  "version": 1,
  "nodes": [
    { "id": 1, "host": "127.0.0.1", "port": 9001 },
    { "id": 2, "host": "127.0.0.1", "port": 9002 },
    { "id": 3, "host": "127.0.0.1", "port": 9003 },
    { "id": 4, "host": "127.0.0.1", "port": 9004 },
    { "id": 5, "host": "127.0.0.1", "port": 9005 }
  ]
}
```

For five real machines: set `host` to each machine's LAN address, keep
`port` identical on every machine (for example `9001`), copy the same file
to every node, and bump `version` after any change. Node 1 will push the
update to the others within 5 seconds.

`frontend/src/config.ts` contains a mirror of this list. The browser needs
to know where the nodes are before it can call any of them. If you change
the ports or hosts in `nodes.json`, update `config.ts` and rebuild.

## Testing

Backend:

```bash
cd backend
source ../venv/bin/activate
pytest -v
```

The suite covers:

- health and config routes
- shard POST/GET round-trip
- rejection of empty shard bodies
- 404 for missing or expired shards
- atomic write behavior (no `.tmp` files left behind)
- 24 hour expiry on read
- cleanup of old files
- catalogue persistence and notify
- broadcast fan-out (mocked HTTP)
- config sync and remote config storage
- pull from main on startup
- CORS header presence

Frontend: there is no test runner yet. The browser console plus the log
panel inside the page are the test surface. A future version may add
Vitest with a jsdom harness for the API wrappers.

## Design decisions

**No database.** The data is transient by definition. Shares are files,
the catalogue is one JSON file. A database would add migrations,
connection handling, and durability guarantees that contradict the
24 hour expiry.

**Threshold equals share count.** If we set threshold below `n`, a single
node failure would still allow recovery, but the security model changes:
fewer shares needed means weaker protection against a single compromised
node. The project explicitly chooses `n = threshold` to make the trade-off
visible.

**Atomic writes, not transactions.** A share is either fully present or
absent. `open -> write -> fsync -> rename` gives this on POSIX systems.
The catalogue file is written the same way, so a crash mid-update cannot
corrupt it.

**Broadcast over pull.** After upload, node 1 pushes the entry to every
peer with `/notify`. Pulling would require each peer to poll every other
peer, which scales poorly and is harder to reason about. The push model
keeps the "who knows what" logic in one place.

**Polling for config sync.** Node 1 checks `nodes.json` every 5 seconds.
For a teaching project this is simpler than a file watcher, portable
across systems, and easy to trace in the log.

**Plain TypeScript, no framework.** The frontend is a few files and one
build step (`esbuild`). React or Svelte would be justified if the UI grew
past a single page. It has not.

## Expiry and deletion

Shares are stored with a modification time. `load_shard` deletes a share
if `now - mtime > 24h` and returns `None`. `cleanup_old_shards` runs at
startup and deletes any file older than 24h.

The catalogue is pruned on read and on save by the same 24 hour rule,
using the `ts` field written by the browser (`Date.now()`, milliseconds).
A catalogue entry older than 24 hours is dropped, so the UI no longer
shows files whose shares are already gone.

Deletion is **best effort on read plus startup cleanup**, not a hard
guarantee at the second. If you need strict expiry, a background thread
or a `systemd` timer that calls `cleanup_old_shards` periodically is the
obvious next step.

## Security notes

- **No transport encryption.** The browser talks HTTP to each node.
  Anyone on the same network can read the shares in flight. The shares
  are pieces of a secret, but n-of-n secret sharing means that anyone who
  can collect all shares can reconstruct the file.
- **No access control.** Any client that can reach the node ports can
  upload, download, and broadcast.
- **Wide open CORS.** The backend allows `origins="*"`. Fine for local
  demos. Not fine for the internet.
- **Temporary directory.** Shares and catalogue are written to
  `/tmp/solmu-shards/` with the user's permissions. On a shared machine,
  another local user with root access can read them.
- **No rate limiting, no quotas.** A malicious client can fill the disk
  until the 24 hour cleanup catches up.
- **Shares are the secret.** In n-of-n Shamir, every share is a point on
  the polynomial. With all shares, the polynomial (and therefore the
  secret) is recovered. Do not treat a single share as harmless if an
  attacker could also compromise another node.

If you intend to run this beyond a demo, do at least:

- Bind Flask to `127.0.0.1` or a private interface, never `0.0.0.0` on a
  public host without a firewall.
- Put a reverse proxy with TLS and auth in front of node 1.
- Restrict the CORS origins to the exact host serving the page.
- Store shares under a directory owned by a dedicated user.

## Roadmap

Possible next steps, in rough order of value:

1. **Periodic cleanup.** A background thread that calls
   `cleanup_old_shards` every few minutes, so expiry does not depend on a
   read or a restart.
2. **Frontend tests.** Vitest with a mocked `fetch` for `api.ts`,
   `upload.ts`, `download.ts`.
3. **Per-node storage paths.** Let each node choose its share directory
   from the config file, so multi-machine deployments do not share
   `/tmp`.
4. **Share encryption at rest.** Encrypt each share with a key held only
   by that node, so a stolen disk does not leak shares.
5. **Authentication.** A shared token or mTLS between nodes, and a login
   for the browser client.
6. **Config reload on SIGHUP.** Instead of polling, react to a signal.
7. **Observability.** Structured logs and a `/metrics` route.
8. **Packaging.** A `Dockerfile` per node and a `docker-compose.yml` for
   the five-node demo.

None of these are required to demonstrate the core idea. They are listed
so future contributors know where the rough edges are.

## License

MIT. See `LICENSE` for the full text.

The project uses the following third-party libraries:

- [Flask](https://flask.palletsprojects.com/) — BSD-3-Clause
- [flask-cors](https://github.com/corydolphin/flask-cors) — MIT
- [requests](https://requests.readthedocs.io/) — Apache-2.0
- [esbuild](https://esbuild.github.io/) — MIT
- [shamir-secret-sharing](https://www.npmjs.com/package/shamir-secret-sharing) — MIT

Each library keeps its own license; the MIT license of this project
applies only to the code in this repository.
