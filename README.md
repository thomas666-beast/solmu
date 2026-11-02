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
7. [Run Locally (Development)](#run-locally-development)
8. [Run in LAN or WAN](#run-in-lan-or-wan)
9. [Testing](#testing)
10. [Security notes](#security-notes)
11. [License](#license)

---

## What it is

- A teaching and research project, written from scratch.
- A small distributed system: several nodes on localhost or on a LAN.
- A demonstration of **n-of-n secret sharing** for data in transit.
- A browser client in TypeScript and a Flask backend, with no database.

The flow:

1. You pick a file in the browser.
2. The browser streams it to a randomly chosen node.
3. That node hashes the file, encrypts it with a random 256-bit key (using SHAKE-256), and splits the *key* into `n` shares via Shamir's Secret Sharing.
4. The node writes one share file (containing the encrypted data and a piece of the key) to each node.
5. Every node broadcasts a catalogue entry so all nodes know the file exists.
6. To download, a node gathers all `n` shares, reconstructs the key, decrypts the data, verifies the SHA-256 hash, and streams it back to the browser.
7. The original temporary file is deleted from the receiving node immediately after distribution.

## What it is not

- **Not redundant.** If one node is down, the file cannot be reconstructed. This is a deliberate choice: "all shares required" means no partial recovery. It is the opposite of RAID or erasure-coded storage.
- **Not durable.** Shares live in `/tmp/run-shards/` by default. On many systems `/tmp` is cleared on reboot. Shares older than 24 hours are deleted on read and on startup cleanup.
- **Not fully production-hardened.** Uses simple session cookies.
- **Not built for massive files.** The server streams to disk and splits in 4 MiB blocks, so server memory usage is constant, but the browser holds the file.

## How it works

### Secret sharing and encryption

The receiving node generates a random 32-byte key. It uses this key to XOR the file with a SHAKE-256 keystream (acting as a fast stream cipher). It then uses Shamir's Secret Sharing over the RFC 3526 2048-bit prime to split the *key* into `n` shares.

Because the key is only 32 bytes, the Shamir math is fast. The bulk data is just encrypted and copied.

### Integrity

Before splitting, the node computes `SHA-256(data)`. The hash is stored in the catalogue entry. On download, the node recomputes the hash of the combined bytes and compares. A mismatch means at least one share was corrupted, and the download is rejected.

### Authentication

The system uses session cookies (HttpOnly, SameSite=Lax) backed by Argon2 password hashing.

- **Password in file -> We know the dangerous, because this is research project.**
  User credentials are stored as Argon2 hashes in `config/users.json`. The Flask session secret is stored in plain text in `config/nodes.json`. In a real production system, this would be moved to a secure database and environment variables. We accept this risk here to keep the architecture fully self-contained and understandable.

## Project layout

```text
solmu/
├── backend/
│   ├── app.py            Flask app: routes, auth, API
│   ├── auth.py           Argon2 hashing and user storage
│   ├── config.py         reads config/nodes.json
│   ├── distribute.py     encryption, splitting, distribution
│   ├── progress.py       in-memory SSE event queues
│   ├── storage.py        share files, catalogue, 24h cleanup
│   ├── sss.py            Pure-Python Shamir Secret Sharing
│   ├── upload.py         streaming file upload to disk
│   ├── requirements.txt
│   └── tests/
├── config/
│   ├── nodes.example.json
│   ├── nodes.json        (gitignored, contains secrets)
│   └── users.json        (gitignored, contains password hashes)
├── frontend/
│   ├── index.html        main tabbed UI
│   ├── login.html
│   ├── register.html
│   ├── style.css
│   ├── logo.svg
│   └── src/
│       ├── main.ts
│       ├── login.ts
│       ├── register.ts
│       ├── api.ts
│       ├── upload.ts
│       └── download.ts
├── package.json
├── run.py                local dev runner
└── README.md
```

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer and npm
- Linux or macOS recommended; Windows works with WSL or Git Bash

## Install

```bash
git clone https://github.com/thomas666-beast/solmu solmu
cd solmu

# Setup backend
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Setup frontend
npm install
npm run build

# Setup config
cp config/nodes.example.json config/nodes.json
# Edit config/nodes.json to set your "token" and "secret_key"
```

## Run Locally (Development)

We provide a Python script that starts all 5 nodes, builds the frontend if necessary, and pipes all logs to your terminal.

```bash
python3 run.py
```

Open `http://127.0.0.1:9001/`. You will be redirected to the login page.

1. Click **register** to create a local account.
2. Log in.
3. The interface has tabs for **SEND**, **CATALOGUE**, **NODES**, and **LOG**.

Press `Ctrl+C` in the terminal to stop all nodes.

## Run in LAN or WAN

**Run in LAN or WAN, it is possible just need configure every node.**
Because solmu is just HTTP nodes communicating with each other, it works across any network as long as they can reach each other's IPs and ports.

To deploy across multiple machines or Virtual Machines:

1. **Edit `config/nodes.json`**: Change the `"host"` for each node from `"127.0.0.1"` to the actual IP address of the machine (e.g., `"192.168.1.10"`). Keep the `"port"` the same on every machine.
2. **Copy the config**: Distribute the exact same `config/nodes.json` to every machine.
3. **Bind to network**: In `backend/app.py`, change the last line to bind to all interfaces:
   ```python
   app.run(host="0.0.0.0", port=me["port"])
   ```
4. **Start each node**: On machine 1, run `python app.py --node-id 1`. On machine 2, run `python app.py --node-id 2`.
5. **Firewall**: Ensure the port (e.g., 9001) is open on all machines.

For a production LAN, replace `app.run()` with Gunicorn:
`gunicorn -w 2 -b 0.0.0.0:9001 app:app`

## Testing

Backend:

```bash
cd backend
source ../venv/bin/activate
pytest -v
```

The suite covers health checks, auth, shard uploads, 24-hour expiry, catalogue persistence, broadcast fan-out, and cryptographic round-trips.

## Security notes

- **No transport encryption by default.** The browser talks HTTP to each node. Anyone on the same network can read the shares in flight. Use a reverse proxy (like Nginx) with TLS if running over the internet.
- **Password in file -> We know the dangerous, because this is research project.** See the Authentication section above.
- **CORS is wide open.** The backend allows `origins="*"`. Fine for local demos. Restrict it if exposing to the internet.
- **Shares are the secret.** In n-of-n Shamir, every share is a point on the polynomial. With all shares, the secret is recovered. If an attacker compromises all nodes, they get the key.

## License

MIT. See `LICENSE` for the full text.
