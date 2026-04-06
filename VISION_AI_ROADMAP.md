# Implementation Roadmap: Self-hosted Vision AI on M4 Mac Mini

## Phase 1: Environment Setup & Gateway Prototype (Week 1)
*   **1.1. Python Environment**: Setup Python 3.12 with `uv` for high-performance dependency management.
*   **1.2. MLX Installation**: Install `mlx`, `mlx-lm`, and `mlx-vlm`.
*   **1.3. FastAPI Gateway Prototype**:
    *   Implement `/v1/chat/completions` (OpenAI-compatible).
    *   Implement basic routing logic based on model aliases.
    *   Setup local storage for image handling.

## Phase 2: Vision-to-Text & Insight Pipeline (Week 2)
*   **2.1. Light Captioning Worker**: Deploy `Moondream2` or `Florence-2` as a "fast" captioning worker.
*   **2.2. Heavy VLM Worker**: Deploy `Qwen2-VL-7B-Instruct` (Quantized) via `mlx-vlm`.
*   **2.3. Insight Extraction Engine**:
    *   Define specialized prompts for "insight extraction" (e.g., "Analyze this UI and list functional elements").
    *   Verify throughput and latency on M4.

## Phase 3: Text-to-Image & Creative Pipeline (Week 3)
*   **3.1. FLUX.1 Worker**: Integrate `FLUX.1-schnell` on MLX (4-bit quantization).
*   **3.2. Image Generation API**: Implement `POST /v1/images/generations`.
*   **3.3. Memory Orchestration**: Implement the "Hotset Manager" to manage VRAM between VLM and FLUX.

## Phase 4: Integration & Optimization (Week 4)
*   **4.1. Clawdbot/PageLM Integration**:
    *   Add the new local API endpoint as a provider in `Clawdbot` config.
    *   Create a "Vision Insight Skill" in Clawdbot that uses the local VLM for image reasoning.
*   **4.2. Performance Tuning**:
    *   Optimize quantization levels (2-bit vs 4-bit vs 8-bit).
    *   Setup `launchd` for automatic service management.
*   **4.3. Final Verification**: End-to-end testing of Agent -> Image Insight -> Text Result pipeline.
