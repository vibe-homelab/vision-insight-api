# Project Plan: Vision Insight API Gateway

## 1. Project Overview
A self-hosted, high-performance API gateway optimized for Apple Silicon (M4), providing unified access to SOTA Vision-Language Models (VLM) and Image Generation models.

## 2. Core Architecture
The system consists of a centralized **Gateway** and multiple **Model Workers**.

### 2.1 Gateway (FastAPI)
- Acts as the primary entry point (OpenAI-compatible).
- Handles request routing, authentication, and load balancing.
- Manages worker lifecycles (Hotset Manager).
- Normalizes multimodal payloads (Base64/URL -> Tensor).

### 2.2 Model Workers (MLX-Inference)
- Isolated processes for each model (Qwen2-VL, Florence-2, FLUX).
- Communicates with Gateway via UNIX Domain Sockets (UDS) or Localhost HTTP.
- Specialized in MLX-optimized inference.

## 3. Technical Specification

### 3.1 Inference Stack
- **Framework**: MLX (Apple Silicon Native)
- **Library**: `mlx-vlm` (for VLM), `mlx-lm` (for text), `Diffusers/DiffusionKit` (for Image Gen).
- **Quantization**: 4-bit (Standard), 8-bit (High quality), 2-bit (Extreme speed).

### 3.2 API Endpoints
- `POST /v1/chat/completions`: Supports multi-modal messages (text + image).
- `POST /v1/images/generations`: Image generation via FLUX.1.
- `GET /v1/models`: List currently loaded and available models.
- `POST /v1/vision/insight`: Custom endpoint for structured insight extraction.

## 4. Resource Management (M4 Optimization)
- **Unified Memory Limit**: Set a hard cap (e.g., 75% of total RAM) for workers.
- **Lazy Loading**: Large models (FLUX) are loaded on-demand and evicted after a TTL (Time-To-Live).
- **Concurrency**: 
  - VLM: 2 concurrent requests.
  - Image Gen: 1 concurrent request.

## 5. Directory Structure
```text
vision-insight-api/
├── src/
│   ├── gateway/         # FastAPI Gateway logic
│   ├── workers/         # Model-specific worker implementations
│   │   ├── vlm_worker.py
│   │   ├── caption_worker.py
│   │   └── diffusion_worker.py
│   ├── core/            # Process management, Hotset Manager
│   └── utils/           # Image processing, logging
├── pyproject.toml       # Dependencies (uv/pip)
├── config.yaml          # Model paths, aliases, memory limits
└── README.md
```

## 6. Milestones
1. **Milestone 1**: Basic Gateway + Mock Workers (API verification).
2. **Milestone 2**: Integration of `mlx-vlm` (Qwen2-VL).
3. **Milestone 3**: Integration of `FLUX.1` worker.
4. **Milestone 4**: Final Hotset Manager logic & Memory optimization.
