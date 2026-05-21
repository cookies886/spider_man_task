"""Configuration loaded from environment variables."""
from __future__ import annotations

import os
import platform
import socket
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    master_url: str
    api_key: str
    node_id: str
    node_name: str
    listen_port: int
    heartbeat_interval: int
    work_dir: str

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        master_url = os.environ.get("MASTER_URL", "ws://localhost:8000")
        if master_url.startswith("http://"):
            master_url = "ws://" + master_url[len("http://"):]
        elif master_url.startswith("https://"):
            master_url = "wss://" + master_url[len("https://"):]
        return cls(
            master_url=master_url.rstrip("/"),
            api_key=os.environ["API_KEY"],
            node_id=os.environ["NODE_ID"],
            node_name=os.environ.get("NODE_NAME", socket.gethostname()),
            listen_port=int(os.environ.get("LISTEN_PORT", "8001")),
            heartbeat_interval=int(os.environ.get("HEARTBEAT_INTERVAL", "5")),
            work_dir=os.environ.get("WORK_DIR", "/tmp/spiderman_worker"),
        )


def system_info() -> dict:
    return {
        "os": sys.platform,
        "arch": platform.machine(),
        "python_version": platform.python_version(),
    }
