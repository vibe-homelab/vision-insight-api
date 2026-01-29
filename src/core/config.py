"""
Configuration loader for Vision Insight API.
"""

import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Optional


class ModelConfig(BaseModel):
    """Configuration for a single model."""
    type: str  # "vlm" or "diffusion"
    path: str  # HuggingFace model path
    hot_reload: bool = False
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


class WorkerPortsConfig(BaseModel):
    """Worker port assignments."""
    vlm_fast: int = Field(default=8001, alias="vlm-fast")
    vlm_best: int = Field(default=8002, alias="vlm-best")
    image_gen: int = Field(default=8003, alias="image-gen")

    class Config:
        populate_by_name = True


class WorkersConfig(BaseModel):
    """Worker configuration."""
    ports: Dict[str, int] = Field(default_factory=lambda: {
        "vlm-fast": 8001,
        "vlm-best": 8002,
        "image-gen": 8003,
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

    return AppConfig(**data)


# Global config instance
config = load_config()
