"""
Worker Manager - Lightweight daemon that manages MLX workers on host.

Runs on macOS host, controls worker lifecycle:
- Spawns workers on-demand via HTTP API
- Monitors idle workers
- Auto-offloads workers after idle timeout
- Memory-aware scheduling

This is the only process that needs to run persistently.
Workers are spawned/stopped dynamically.
"""

import asyncio
import subprocess
import os
import signal
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import config
from src.core.memory import (
    get_memory_status,
    get_model_memory_requirement,
    can_load_model,
)


# Configuration
IDLE_TIMEOUT_SECONDS = int(os.getenv("IDLE_TIMEOUT", "300"))  # 5 minutes default
HEALTH_CHECK_INTERVAL = 30  # seconds
MANAGER_PORT = int(os.getenv("MANAGER_PORT", "8100"))
# Restart worker after N requests to prevent semaphore leak accumulation
MAX_REQUESTS_BEFORE_RESTART = int(os.getenv("MAX_REQUESTS", "50"))


@dataclass
class WorkerProcess:
    """Tracks a running worker process."""
    alias: str
    process: subprocess.Popen
    port: int
    model_path: str
    model_type: str
    memory_gb: float
    started_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    request_count: int = 0


class WorkerManager:
    """Manages worker processes with auto-spawn and idle offload."""

    def __init__(self):
        self.workers: Dict[str, WorkerProcess] = {}
        self.lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # Port assignments
        self.port_map = {
            "vlm-fast": 8001,
            "vlm-best": 8002,
            "image-gen": 8003,
        }
        self._next_port = 8010

        # Paths
        self.project_root = PROJECT_ROOT
        self.log_dir = self.project_root / "logs"
        self.log_dir.mkdir(exist_ok=True)

    def _get_port(self, alias: str) -> int:
        """Get port for worker."""
        if alias in self.port_map:
            return self.port_map[alias]
        port = self._next_port
        self._next_port += 1
        return port

    async def _is_worker_healthy(self, port: int, timeout: float = 2.0) -> bool:
        """Check if worker is responding."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/health", timeout=timeout)
                return resp.status_code == 200
        except Exception:
            return False

    async def spawn_worker(self, alias: str) -> WorkerProcess:
        """Spawn a new worker process."""
        async with self.lock:
            # Already running?
            if alias in self.workers:
                worker = self.workers[alias]
                if worker.process.poll() is None:  # Still alive
                    if await self._is_worker_healthy(worker.port):
                        worker.last_used = time.time()
                        return worker
                # Dead, clean up
                del self.workers[alias]

            # Check model exists in config
            if alias not in config.models:
                raise ValueError(f"Unknown model: {alias}")

            model_cfg = config.models[alias]
            memory_gb = get_model_memory_requirement(model_cfg.path, model_cfg.type)

            # Check memory
            can_load, needed, available = can_load_model(
                model_cfg.path,
                model_cfg.type,
                config.memory.safety_margin_gb
            )

            if not can_load:
                # Try to free memory by stopping idle workers
                await self._evict_for_memory(needed)

                # Check again
                can_load, _, available = can_load_model(
                    model_cfg.path,
                    model_cfg.type,
                    config.memory.safety_margin_gb
                )
                if not can_load:
                    raise MemoryError(
                        f"Insufficient memory for {alias}: need {needed:.1f}GB, have {available:.1f}GB"
                    )

            port = self._get_port(alias)
            log_file = self.log_dir / f"{alias}.log"

            print(f"[*] Spawning {alias} on port {port} (memory: {memory_gb:.1f}GB)")

            # Start worker process
            cmd = [
                sys.executable, "-m", f"src.workers.{model_cfg.type}_worker",
                "--alias", alias,
                "--model_path", model_cfg.path,
                "--port", str(port),
            ]

            with open(log_file, "a") as log:
                log.write(f"\n=== Starting {alias} at {time.ctime()} ===\n")

            process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                env={**os.environ, "PYTHONPATH": str(self.project_root)},
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )

            worker = WorkerProcess(
                alias=alias,
                process=process,
                port=port,
                model_path=model_cfg.path,
                model_type=model_cfg.type,
                memory_gb=memory_gb,
            )
            self.workers[alias] = worker

            # Wait for worker to be ready
            print(f"[*] Waiting for {alias} to be ready...")
            for i in range(60):  # 60 seconds timeout
                if await self._is_worker_healthy(port):
                    print(f"[+] {alias} is ready (took {i+1}s)")
                    return worker
                await asyncio.sleep(1)

            # Failed to start
            print(f"[!] {alias} failed to start within timeout")
            self.stop_worker(alias)
            raise RuntimeError(f"Worker {alias} failed to start")

    async def _evict_for_memory(self, needed_gb: float):
        """Evict idle workers to free memory."""
        memory = get_memory_status()
        to_free = needed_gb - (memory.available - config.memory.safety_margin_gb)

        if to_free <= 0:
            return

        # Sort by last_used (oldest first)
        workers_by_idle = sorted(
            self.workers.items(),
            key=lambda x: x[1].last_used
        )

        freed = 0.0
        for alias, worker in workers_by_idle:
            if freed >= to_free:
                break
            print(f"[*] Evicting {alias} to free {worker.memory_gb:.1f}GB")
            self.stop_worker(alias)
            freed += worker.memory_gb
            await asyncio.sleep(0.5)  # Let memory be reclaimed

    def stop_worker(self, alias: str) -> bool:
        """Stop a worker process."""
        if alias not in self.workers:
            return False

        worker = self.workers[alias]
        print(f"[*] Stopping {alias}...")

        try:
            os.killpg(os.getpgid(worker.process.pid), signal.SIGTERM)
            worker.process.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(worker.process.pid), signal.SIGKILL)
            except Exception:
                pass

        del self.workers[alias]
        print(f"[+] {alias} stopped")
        return True

    def touch_worker(self, alias: str):
        """Update last_used time for a worker."""
        if alias in self.workers:
            self.workers[alias].last_used = time.time()
            self.workers[alias].request_count += 1

    async def _monitor_idle_workers(self):
        """Background task to offload idle workers."""
        print(f"[*] Idle monitor started (timeout: {IDLE_TIMEOUT_SECONDS}s, max_requests: {MAX_REQUESTS_BEFORE_RESTART})")

        while self._running:
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)

                now = time.time()
                to_stop = []

                for alias, worker in list(self.workers.items()):
                    # Check if process is still alive
                    if worker.process.poll() is not None:
                        print(f"[!] {alias} died unexpectedly")
                        to_stop.append(alias)
                        continue

                    # Check idle timeout
                    idle_time = now - worker.last_used
                    if idle_time > IDLE_TIMEOUT_SECONDS:
                        print(f"[*] {alias} idle for {idle_time:.0f}s, offloading...")
                        to_stop.append(alias)
                        continue

                    # Check request count (prevent semaphore leak accumulation)
                    if worker.request_count >= MAX_REQUESTS_BEFORE_RESTART:
                        print(f"[*] {alias} reached {worker.request_count} requests, recycling to prevent resource leaks...")
                        to_stop.append(alias)

                for alias in to_stop:
                    self.stop_worker(alias)

            except Exception as e:
                print(f"[!] Monitor error: {e}")

    def start_monitor(self):
        """Start the idle monitor background task."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_idle_workers())

    def stop_monitor(self):
        """Stop the idle monitor."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()

    def get_status(self) -> dict:
        """Get current status."""
        memory = get_memory_status()

        return {
            "workers": {
                alias: {
                    "port": w.port,
                    "model_path": w.model_path,
                    "model_type": w.model_type,
                    "memory_gb": w.memory_gb,
                    "uptime_seconds": time.time() - w.started_at,
                    "idle_seconds": time.time() - w.last_used,
                    "request_count": w.request_count,
                    "pid": w.process.pid,
                }
                for alias, w in self.workers.items()
            },
            "memory": {
                "total_gb": memory.total,
                "used_gb": memory.used,
                "available_gb": memory.available,
                "used_percent": memory.usage_percent,
                # Backward/forward compatibility: some clients use a different key.
                "usage_percent": memory.usage_percent,
                "models_loaded_gb": sum(w.memory_gb for w in self.workers.values()),
            },
            "config": {
                "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
                "max_requests_before_restart": MAX_REQUESTS_BEFORE_RESTART,
                "safety_margin_gb": config.memory.safety_margin_gb,
            }
        }

    def shutdown(self):
        """Stop all workers."""
        print("[*] Shutting down all workers...")
        for alias in list(self.workers.keys()):
            self.stop_worker(alias)


# Global manager instance
manager = WorkerManager()


# === FastAPI App ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.start_monitor()
    yield
    manager.stop_monitor()
    manager.shutdown()


app = FastAPI(title="Vision Worker Manager", lifespan=lifespan)


class SpawnResponse(BaseModel):
    alias: str
    port: int
    memory_gb: float
    status: str


@app.get("/health")
async def health():
    return {"status": "ok", "workers": len(manager.workers)}


@app.get("/status")
async def status():
    """Get full status including workers and memory."""
    return manager.get_status()


@app.post("/spawn/{alias}")
async def spawn(alias: str) -> SpawnResponse:
    """Spawn a worker (or return existing one)."""
    try:
        worker = await manager.spawn_worker(alias)
        return SpawnResponse(
            alias=alias,
            port=worker.port,
            memory_gb=worker.memory_gb,
            status="running"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MemoryError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stop/{alias}")
async def stop(alias: str):
    """Stop a worker."""
    if manager.stop_worker(alias):
        return {"status": "stopped", "alias": alias}
    raise HTTPException(status_code=404, detail=f"Worker {alias} not found")


@app.post("/touch/{alias}")
async def touch(alias: str):
    """Update last_used time (prevents idle offload)."""
    manager.touch_worker(alias)
    return {"status": "ok"}


@app.post("/stop-all")
async def stop_all():
    """Stop all workers."""
    count = len(manager.workers)
    manager.shutdown()
    return {"status": "stopped", "count": count}


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════╗
║         Vision Worker Manager                            ║
║                                                          ║
║  Port: {MANAGER_PORT}                                           ║
║  Idle Timeout: {IDLE_TIMEOUT_SECONDS}s                                     ║
║  Project: {PROJECT_ROOT}
╚══════════════════════════════════════════════════════════╝
""")
    uvicorn.run(app, host="0.0.0.0", port=MANAGER_PORT, log_level="info")
