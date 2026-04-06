# Worker & Supervisor Design

## 1. Process Hierarchy
- **Parent (Gateway/Supervisor)**: 
  - Manages a pool of child processes.
  - Monitors resource usage (RAM/CPU).
  - Handles SIGTERM/SIGKILL for clean shutdown.
- **Child (Model Worker)**:
  - Runs a minimal HTTP/UDS server.
  - Loads a single MLX model.
  - Performs inference and returns structured JSON.

## 2. Communication Protocol
- **Transport**: UNIX Domain Sockets (UDS) - `/tmp/vision_worker_{model_alias}.sock`
- **Why UDS?**: 
  - Zero network overhead (faster than loopback).
  - No port conflicts.
  - Permissions-based security.
- **Payload**: JSON-RPC or Simple HTTP over UDS.

## 3. Hotset Manager Logic
1. Request arrives for model `A`.
2. Supervisor checks if `Worker(A)` is alive.
3. If alive, forward request.
4. If not alive:
   - Check current memory headroom.
   - If low, kill the LRU (Least Recently Used) worker.
   - Spawn `Worker(A)`, wait for health check.
   - Forward request.
5. Update `last_used_at` for `Worker(A)`.

## 4. Resource Guardrails
- **Timeout**: Each inference task has a hard timeout (e.g., 60s for VLM, 180s for Diffusion).
- **Graceful Shutdown**: Workers finish current request before exiting.
- **OOM Prevention**: If Unified Memory usage exceeds 90%, supervisor triggers immediate eviction of inactive workers.
