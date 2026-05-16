# scripts/start_nodes.py
# Starts all signer nodes and the coordinator as separate processes
#
# Usage:
#   python scripts/start_nodes.py              — starts coordinator + 5 nodes
#   python scripts/start_nodes.py --nodes 3   — starts coordinator + 3 nodes
#   python scripts/start_nodes.py --stop       — stops all running nodes
#
# Each node runs independently, simulating separate machines.
# In production, each would run on a different host/container.

import subprocess
import sys
import os
import time
import signal
import argparse
import json
from pathlib import Path

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable  # fallback to system python

PID_FILE = PROJECT_ROOT / ".node_pids.json"


def start_nodes(num_nodes: int = 5):
    """
    Launches the coordinator and N signer nodes as background processes.

    Each node:
      - Runs as its own uvicorn server on a dedicated port
      - Has a unique NODE_ID environment variable
      - Simulates physical separation (in production: different hosts)

    Ports:
      8000 — Coordinator
      8001 — Node 1
      8002 — Node 2
      8003 — Node 3
      8004 — Node 4
      8005 — Node 5
    """
    print("=" * 55)
    print("  TSS WALLET NODE LAUNCHER")
    print("=" * 55)

    processes = {}
    env_base = os.environ.copy()
    # Set node URLs so coordinator can reach all nodes
    for i in range(1, num_nodes + 1):
        env_base[f"NODE_{i}_URL"] = f"http://localhost:{8000 + i}"

    # Start coordinator (port 8000)
    print("\n[*] Starting Coordinator (port 8000)...")
    coord_env = env_base.copy()
    coord_env["COORDINATOR_JWT_SECRET"] = "coordinator_master_secret_change_in_production"
    coord_proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "nodes.coordinator:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(PROJECT_ROOT),
        env=coord_env,
    )
    processes["coordinator"] = coord_proc.pid
    print(f"    Coordinator PID: {coord_proc.pid}")
    time.sleep(2)

    # Start each signer node
    for i in range(1, num_nodes + 1):
        port = 8000 + i
        print(f"\n[*] Starting Node {i} (port {port})...")
        node_env = env_base.copy()
        node_env["NODE_ID"] = str(i)
        node_env["NODE_PORT"] = str(port)
        node_env["JWT_SECRET"] = f"node{i}_jwt_secret_change_in_production"

        node_proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "nodes.node_app:app",
             "--host", "0.0.0.0", f"--port", str(port), "--reload"],
            cwd=str(PROJECT_ROOT),
            env=node_env,
        )
        processes[f"node_{i}"] = node_proc.pid
        print(f"    Node {i} PID: {node_proc.pid}")
        time.sleep(1)

    # Save PIDs for stop command
    PID_FILE.write_text(json.dumps(processes, indent=2))

    print("\n" + "=" * 55)
    print("  ALL NODES STARTED")
    print("=" * 55)
    print(f"\n  Coordinator : http://localhost:8000")
    print(f"  Coordinator API docs: http://localhost:8000/docs")
    for i in range(1, num_nodes + 1):
        print(f"  Node {i}       : http://localhost:{8000 + i}")
        print(f"  Node {i} docs  : http://localhost:{8000 + i}/docs")
    print(f"\n  PIDs saved to: {PID_FILE}")
    print("\n  Press Ctrl+C to stop all nodes")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        stop_nodes()


def stop_nodes():
    """Terminates all running node processes."""
    if not PID_FILE.exists():
        print("No PID file found. Nodes may not be running.")
        return

    pids = json.loads(PID_FILE.read_text())
    print("\n[*] Stopping all nodes...")
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Stopped {name} (PID {pid})")
        except ProcessLookupError:
            print(f"  {name} (PID {pid}) already stopped")
        except Exception as e:
            print(f"  Error stopping {name}: {e}")

    PID_FILE.unlink(missing_ok=True)
    print("  All nodes stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TSS Node Launcher")
    parser.add_argument("--nodes", type=int, default=5, help="Number of signer nodes to start")
    parser.add_argument("--stop", action="store_true", help="Stop all running nodes")
    args = parser.parse_args()

    if args.stop:
        stop_nodes()
    else:
        start_nodes(args.nodes)
