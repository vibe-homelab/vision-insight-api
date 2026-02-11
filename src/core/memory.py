"""
Memory Manager for model allocation.
Supports Apple Silicon unified memory (macOS) and NVIDIA GPU memory (Linux).
"""

import platform
import subprocess
import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MemoryStatus:
    """Current memory status in GB."""
    total: float
    used: float
    available: float
    app_memory: float
    wired: float
    compressed: float

    @property
    def usage_percent(self) -> float:
        return (self.used / self.total) * 100 if self.total > 0 else 0


IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"

# Estimated memory usage per model (in GB)
MODEL_MEMORY_REQUIREMENTS: Dict[str, float] = {
    # MLX VLM models (macOS)
    "mlx-community/moondream2": 1.5,
    "mlx-community/Qwen2.5-VL-3B-Instruct-4bit": 2.5,
    "mlx-community/Qwen2.5-VL-7B-Instruct-4bit": 4.5,
    "mlx-community/Qwen2.5-VL-14B-Instruct-4bit": 8.0,

    # MLX Image generation models (macOS)
    "mlx-community/FLUX.1-schnell-4bit-mlx": 6.0,
    "mlx-community/FLUX.1-dev-4bit-mlx": 12.0,

    # CUDA Image generation models (Linux/NVIDIA)
    "Qwen/Qwen-Image-2512": 20.0,

    # Fallback estimates by type
    "_default_vlm": 3.0,
    "_default_diffusion": 8.0,
    "_default_cuda_diffusion": 20.0,
}


def get_model_memory_requirement(model_path: str, model_type: str = "vlm") -> float:
    """Get estimated memory requirement for a model."""
    if model_path in MODEL_MEMORY_REQUIREMENTS:
        return MODEL_MEMORY_REQUIREMENTS[model_path]

    # Estimate based on model name patterns
    path_lower = model_path.lower()

    if "14b" in path_lower:
        return 8.0
    elif "7b" in path_lower:
        return 4.5
    elif "3b" in path_lower:
        return 2.5
    elif "2b" in path_lower or "1b" in path_lower:
        return 1.5

    # Fallback by type
    if model_type == "diffusion":
        return MODEL_MEMORY_REQUIREMENTS["_default_diffusion"]
    return MODEL_MEMORY_REQUIREMENTS["_default_vlm"]


def _get_linux_memory_status() -> MemoryStatus:
    """Get memory status on Linux using /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]  # kB value
                    meminfo[key] = int(val) / (1024 * 1024)  # Convert to GB

        total = meminfo.get("MemTotal", 32.0)
        available = meminfo.get("MemAvailable", total * 0.5)
        used = total - available
        buffers = meminfo.get("Buffers", 0)
        cached = meminfo.get("Cached", 0)

        return MemoryStatus(
            total=round(total, 2),
            used=round(used, 2),
            available=round(available, 2),
            app_memory=round(used - buffers - cached, 2),
            wired=0.0,
            compressed=0.0,
        )
    except Exception:
        return _get_fallback_memory_status()


def _get_nvidia_gpu_memory() -> list[dict]:
    """Get NVIDIA GPU memory info via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split("\n"):
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 4:
                gpus.append({
                    "index": int(parts[0]),
                    "total_mb": float(parts[1]),
                    "used_mb": float(parts[2]),
                    "free_mb": float(parts[3]),
                })
        return gpus
    except Exception:
        return []


def get_memory_status() -> MemoryStatus:
    """
    Get current memory status.
    Uses /proc/meminfo on Linux, vm_stat on macOS.
    Returns memory values in GB.
    """
    if IS_LINUX:
        return _get_linux_memory_status()

    try:
        # Get vm_stat output
        result = subprocess.run(
            ["vm_stat"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return _get_fallback_memory_status()

        # Parse vm_stat output
        stats = {}
        for line in result.stdout.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                # Extract number, removing periods and converting
                match = re.search(r"(\d+)", value.strip())
                if match:
                    stats[key.strip()] = int(match.group(1))

        # vm_stat reports in pages (usually 16384 bytes = 16KB on Apple Silicon)
        page_size = 16384  # bytes

        # Get total physical memory using sysctl
        sysctl_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5
        )
        total_bytes = int(sysctl_result.stdout.strip())
        total_gb = total_bytes / (1024 ** 3)

        # Calculate memory components (convert pages to GB)
        def pages_to_gb(pages: int) -> float:
            return (pages * page_size) / (1024 ** 3)

        free_pages = stats.get("Pages free", 0)
        active_pages = stats.get("Pages active", 0)
        inactive_pages = stats.get("Pages inactive", 0)
        speculative_pages = stats.get("Pages speculative", 0)
        wired_pages = stats.get("Pages wired down", 0)
        compressed_pages = stats.get("Pages occupied by compressor", 0)
        purgeable_pages = stats.get("Pages purgeable", 0)

        # App memory = active + inactive (excluding wired/system)
        app_memory_gb = pages_to_gb(active_pages + inactive_pages)

        # Wired memory (kernel, system)
        wired_gb = pages_to_gb(wired_pages)

        # Compressed
        compressed_gb = pages_to_gb(compressed_pages)

        # Available = free + purgeable + speculative (can be reclaimed)
        available_gb = pages_to_gb(free_pages + purgeable_pages + speculative_pages + inactive_pages)

        # Used = total - available
        used_gb = total_gb - available_gb

        return MemoryStatus(
            total=round(total_gb, 2),
            used=round(used_gb, 2),
            available=round(available_gb, 2),
            app_memory=round(app_memory_gb, 2),
            wired=round(wired_gb, 2),
            compressed=round(compressed_gb, 2),
        )

    except Exception as e:
        print(f"[!] Error getting memory status: {e}")
        return _get_fallback_memory_status()


def _get_fallback_memory_status() -> MemoryStatus:
    """Fallback memory status when vm_stat fails."""
    # Try to at least get total memory
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5
        )
        total_gb = int(result.stdout.strip()) / (1024 ** 3)
    except Exception:
        total_gb = 32.0  # Assume 32GB as default

    # Conservative estimate: assume 50% available
    return MemoryStatus(
        total=total_gb,
        used=total_gb * 0.5,
        available=total_gb * 0.5,
        app_memory=total_gb * 0.3,
        wired=total_gb * 0.15,
        compressed=total_gb * 0.05,
    )


def can_load_model(model_path: str, model_type: str, safety_margin_gb: float = 4.0) -> tuple[bool, float, float]:
    """
    Check if a model can be loaded without memory overcommit.

    Args:
        model_path: Path/name of the model
        model_type: Type of model (vlm, diffusion)
        safety_margin_gb: Keep this much memory free for system

    Returns:
        (can_load, required_gb, available_gb)
    """
    memory = get_memory_status()
    required_gb = get_model_memory_requirement(model_path, model_type)
    effective_available = memory.available - safety_margin_gb

    can_load = effective_available >= required_gb

    return can_load, required_gb, memory.available


def calculate_eviction_needed(
    model_path: str,
    model_type: str,
    loaded_models: Dict[str, float],
    safety_margin_gb: float = 4.0
) -> list[str]:
    """
    Calculate which models need to be evicted to load a new model.

    Args:
        model_path: New model to load
        model_type: Type of new model
        loaded_models: Dict of {alias: memory_gb} for currently loaded models
        safety_margin_gb: Keep this much memory free

    Returns:
        List of model aliases to evict (in order), empty if no eviction needed
    """
    memory = get_memory_status()
    required_gb = get_model_memory_requirement(model_path, model_type)
    effective_available = memory.available - safety_margin_gb

    if effective_available >= required_gb:
        return []  # No eviction needed

    # Need to free memory
    memory_to_free = required_gb - effective_available
    evict_list = []
    freed_memory = 0.0

    # Sort by memory size descending (evict largest first to minimize evictions)
    # Could also sort by LRU here if we track usage time
    sorted_models = sorted(loaded_models.items(), key=lambda x: x[1], reverse=True)

    for alias, mem_gb in sorted_models:
        evict_list.append(alias)
        freed_memory += mem_gb

        if freed_memory >= memory_to_free:
            break

    return evict_list


if __name__ == "__main__":
    # Test memory monitoring
    status = get_memory_status()
    print(f"Memory Status:")
    print(f"  Total:      {status.total:.1f} GB")
    print(f"  Used:       {status.used:.1f} GB ({status.usage_percent:.1f}%)")
    print(f"  Available:  {status.available:.1f} GB")
    print(f"  App Memory: {status.app_memory:.1f} GB")
    print(f"  Wired:      {status.wired:.1f} GB")
    print(f"  Compressed: {status.compressed:.1f} GB")

    print(f"\nModel Memory Requirements:")
    for model, mem in MODEL_MEMORY_REQUIREMENTS.items():
        if not model.startswith("_"):
            print(f"  {model}: {mem:.1f} GB")
