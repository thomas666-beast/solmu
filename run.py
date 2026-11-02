#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
CONFIG_PATH = ROOT / "config" / "nodes.json"
VENV_PYTHON = ROOT / "venv" / "bin" / "python"
if os.name == "nt":
    VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"

# Handle Ctrl+C gracefully
processes = []

def cleanup(sig=None, frame=None):
    print("\n[run] shutting down all nodes...")
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
    print("[run] all nodes stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def check_setup():
    if not VENV_PYTHON.exists():
        print(f"[run] Error: Python venv not found at {VENV_PYTHON}")
        print("      Run: python3 -m venv venv && source venv/bin/activate && pip install -r backend/requirements.txt")
        sys.exit(1)

    if not CONFIG_PATH.exists():
        print(f"[run] Error: Config not found at {CONFIG_PATH}")
        print("      Copy config/nodes.example.json to config/nodes.json and edit it.")
        sys.exit(1)

    dist_dir = ROOT / "frontend" / "dist"
    if not (dist_dir / "main.js").exists():
        print("[run] Frontend build missing. Running 'npm run build'...")
        try:
            subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
        except FileNotFoundError:
            print("[run] Error: 'npm' not found. Please install Node.js.")
            sys.exit(1)
        except subprocess.CalledProcessError:
            print("[run] Error: Frontend build failed.")
            sys.exit(1)

def main():
    check_setup()

    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[run] Error reading config: {e}")
        sys.exit(1)

    nodes = cfg.get("nodes", [])
    if not nodes:
        print("[run] No nodes found in config.")
        sys.exit(1)

    print(f"[run] Starting {len(nodes)} nodes in development mode...")
    
    for node in nodes:
        node_id = node["id"]
        host = node["host"]
        port = node["port"]
        
        # Command: python app.py --node-id <id>
        # We do not pass --port because app.py reads it from config/nodes.json
        cmd = [str(VENV_PYTHON), "app.py", "--node-id", str(node_id)]
        
        print(f"  -> node {node_id} at {host}:{port}")
        
        # Start process, redirect output to stdout so we see logs
        p = subprocess.Popen(
            cmd,
            cwd=BACKEND_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        processes.append(p)
        time.sleep(0.2) # brief pause to avoid terminal output jumbling

    print("\n[run] All nodes started.")
    print(f"[run] Open http://127.0.0.1:{nodes[0]['port']}/ in your browser.")
    print("[run] Press Ctrl+C to stop.\n")

    # Keep the main thread alive until Ctrl+C
    try:
        while True:
            # Check if any node crashed unexpectedly
            for i, p in enumerate(processes):
                if p.poll() is not None:
                    print(f"[run] Warning: node {i+1} exited with code {p.returncode}")
                    # Remove dead process from list
                    processes.pop(i)
                    break
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
