"""
Configuration loader for Vision Insight API.
"""

import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Optional


class ModelConfig(BaseModel):
    """Configuration for a single model."""
    type: str  # "vlm", "diffusion", "cuda_diffusion"
    path: str  # HuggingFace model path
    hot_reload: bool = False
    backend: str = "mlx"  # "mlx" or "cuda"
    params: Dict = Field(default_factory=dict)


class GatewayConfig(BaseModel):
    """API Gateway configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str = "default-key"


class MemoryConfig(BaseModel):
    """Memory management configuration."""
    max_unified_memory_gb: float = 24.0
    eviction_threshold_percent: int = 75
    safety_margin_gb: float = 4.0


class WorkersConfig(BaseModel):
    """Worker configuration."""
    ports: Dict[str, int] = Field(default_factory=lambda: {
        "vlm-fast": 8001,
        "vlm-best": 8002,
        "image-gen": 8003,
        "vlm-gemma": 8005,
        "image-gen-cuda": 8003,
    })
    health_check_interval: int = 30
    health_check_timeout: int = 5
    startup_timeout: int = 120


class AppConfig(BaseModel):
    """Main application configuration."""
    models: Dict[str, ModelConfig]
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    workers: WorkersConfig = Field(default_factory=WorkersConfig)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    cfg = AppConfig(**data)

    # Optional environment overrides (useful for container/runtime configs).
    if os.getenv("GATEWAY_PORT"):
        cfg.gateway.port = int(os.environ["GATEWAY_PORT"])
    if os.getenv("GATEWAY_API_KEY"):
        cfg.gateway.api_key = os.environ["GATEWAY_API_KEY"]

    return cfg


# Global config instance
config = load_config()
