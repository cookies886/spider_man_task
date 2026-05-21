"""Sample local system metrics via psutil."""
from __future__ import annotations

import psutil


def sample(running_tasks: int = 0) -> dict:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    net = psutil.net_io_counters()
    return {
        "type": "heartbeat",
        "cpu": cpu,
        "mem": mem,
        "disk": disk,
        "net_in": net.bytes_recv,
        "net_out": net.bytes_sent,
        "running": running_tasks,
    }
