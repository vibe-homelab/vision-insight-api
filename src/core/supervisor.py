"""
Supervisor - Connects to Worker Manager for dynamic worker control.

In Docker mode:
  Gateway → Supervisor → Worker Manager (host:8100) → Workers

The Worker Manager handles:
  - Worker process spawning
  - Memory management
  - Idle timeout & auto-offload
"""

import asyncio
import os
import time
import httpx
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.core.config import config


# Worker Manager address
WORKER_MANAGER_HOST = os.getenv("WORKER_MANAGER_HOST", "host.docker.internal")
WORKER_MANAGER_PORT = int(os.getenv("WORKER_MANAGER_PORT", "8100"))
WORKER_MANAGER_URL = f"http://{WORKER_MANAGER_HOST}:{WORKER_MANAGER_PORT}"


@dataclass
class WorkerInfo:
    """Information about a worker obtained from Worker Manager."""
    alias: str
    address: str
    port: int
    memory_gb: float
    last_used: float = field(default_factory=time.time)


class Supervisor:
    """
    Supervisor that delegates worker management to Worker Manager.

    This runs inside Docker and communicates with Worker Manager on host.
    """

    def __init__(self):
        self.workers: Dict[str, WorkerInfo] = {}
        self.lock = asyncio.Lock()

    def _get_worker_url(self, port: int) -> str:
        """Get URL to reach worker from Docker."""
        host = os.getenv("WORKER_HOST", "host.docker.internal")
        return f"http://{host}:{port}"

    async def _call_manager(self, method: str, path: str, **kwargs) -> dict:
        """Call Worker Manager API."""
        async with httpx.AsyncClient() as client:
            url = f"{WORKER_MANAGER_URL}{path}"
            try:
                if method == "GET":
                    resp = await client.get(url, timeout=10.0)
                else:
                    resp = await client.post(url, timeout=120.0, **kwargs)

                if resp.status_code >= 400:
                    error = resp.json().get("detail", resp.text)
                    raise RuntimeError(f"Worker Manager error: {error}")

                return resp.json()
            except httpx.ConnectError:
                raise RuntimeError(
                    f"Cannot connect to Worker Manager at {WORKER_MANAGER_URL}. "
                    "Make sure it's running on host."
                )

    async def get_worker(self, alias: str) -> WorkerInfo:
        """
        Get a worker, spawning if necessary.

        Calls Worker Manager to ensure worker is running.
        """
        async with self.lock:
            # Ask Worker Manager to spawn (idempotent - returns existing if running)
            result = await self._call_manager("POST", f"/spawn/{alias}")

            port = result["port"]
            worker = WorkerInfo(
                alias=alias,
                address=self._get_worker_url(port),
                port=port,
                memory_gb=result["memory_gb"],
            )

            self.workers[alias] = worker

            # Touch to reset idle timer
            await self._call_manager("POST", f"/touch/{alias}")

            return worker

    async def stop_worker(self, alias: str):
        """Stop a specific worker."""
        await self._call_manager("POST", f"/stop/{alias}")
        if alias in self.workers:
            del self.workers[alias]

    async def get_status(self) -> dict:
        """Get status from Worker Manager."""
        return await self._call_manager("GET", "/status")

    async def shutdown(self):
        """Stop all workers."""
        try:
            await self._call_manager("POST", "/stop-all")
        except Exception as e:
            print(f"[!] Shutdown error: {e}")
        self.workers.clear()


# Global supervisor instance
supervisor = Supervisor()
