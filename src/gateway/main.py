from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time
import asyncio
from contextlib import asynccontextmanager

import httpx
from src.core.config import config
from src.core.supervisor import supervisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    yield
    # Shutdown logic
    await supervisor.shutdown()


app = FastAPI(title="Vision Insight API Gateway", lifespan=lifespan)


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    stream: bool = False


class ImageGenerationRequest(BaseModel):
    """Text-to-image generation (OpenAI compatible)."""
    prompt: str
    n: int = 1
    size: str = "1024x1024"
    model: str = "schnell"  # schnell (fast) or dev (quality)
    steps: Optional[int] = None


class ImageEditRequest(BaseModel):
    """Image-to-image editing request."""
    prompt: str
    image: str  # Base64 encoded image
    strength: float = 0.7  # 0.0 = keep original, 1.0 = full regeneration
    size: Optional[str] = None
    model: str = "schnell"
    steps: Optional[int] = None


class VisionAnalyzeRequest(BaseModel):
    """Structured image analysis request."""
    image: str  # Base64 encoded image or URL
    task: str = "caption"  # caption, ocr, describe, analyze, objects, custom
    prompt: Optional[str] = None  # Custom prompt for 'custom' task
    max_tokens: int = 512


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }
            for name in config.models.keys()
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # 만약 요청된 모델이 없으면 기본값(vlm-fast) 사용
    model_name = request.model
    if model_name not in config.models:
        if "gpt" in model_name.lower() or "claude" in model_name.lower():
            model_name = "vlm-fast"  # 기본 모델로 리다이렉트
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_name}' not found. Available: {list(config.models.keys())}",
            )

    worker = await supervisor.get_worker(model_name)

    # Check if address is UDS or HTTP
    if worker.address.startswith("http"):
        transport = httpx.AsyncHTTPTransport()
        url = f"{worker.address}/chat"
    else:
        transport = httpx.AsyncHTTPTransport(uds=worker.address)
        url = "http://local/chat"

    async with httpx.AsyncClient(transport=transport) as client:
        try:
            resp = await client.post(
                url,
                json={"messages": request.messages, "stream": request.stream},
                timeout=60.0,
            )
            return resp.json()

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Worker error: {str(e)}")


@app.post("/v1/images/generations")
async def generate_images(request: ImageGenerationRequest):
    """
    Text-to-Image Generation (OpenAI compatible).

    Generate images from text prompts using FLUX models.

    Example:
    ```
    POST /v1/images/generations
    {
        "prompt": "a cat in space",
        "size": "1024x1024",
        "model": "schnell",
        "steps": 4
    }
    ```
    """
    model_alias = "image-gen"
    if model_alias not in config.models:
        raise HTTPException(status_code=404, detail="Diffusion model not configured")

    worker = await supervisor.get_worker(model_alias)

    if worker.address.startswith("http"):
        transport = httpx.AsyncHTTPTransport()
        url = f"{worker.address}/generate"
    else:
        transport = httpx.AsyncHTTPTransport(uds=worker.address)
        url = "http://local/generate"

    async with httpx.AsyncClient(transport=transport) as client:
        try:
            resp = await client.post(
                url,
                json={
                    "prompt": request.prompt,
                    "n": request.n,
                    "size": request.size,
                    "model": request.model,
                    "steps": request.steps,
                },
                timeout=300.0,  # 5 min timeout for image gen
            )
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Worker error: {str(e)}")


@app.post("/v1/images/edits")
async def edit_images(request: ImageEditRequest):
    """
    Image-to-Image Editing (img2img).

    Transform an existing image based on a text prompt.

    Example:
    ```
    POST /v1/images/edits
    {
        "prompt": "make it sunset",
        "image": "<base64 encoded image>",
        "strength": 0.7,
        "model": "schnell"
    }
    ```

    strength: 0.0 = keep original, 1.0 = full regeneration
    """
    model_alias = "image-gen"
    if model_alias not in config.models:
        raise HTTPException(status_code=404, detail="Diffusion model not configured")

    worker = await supervisor.get_worker(model_alias)

    if worker.address.startswith("http"):
        transport = httpx.AsyncHTTPTransport()
        url = f"{worker.address}/edit"
    else:
        transport = httpx.AsyncHTTPTransport(uds=worker.address)
        url = "http://local/edit"

    async with httpx.AsyncClient(transport=transport) as client:
        try:
            resp = await client.post(
                url,
                json={
                    "prompt": request.prompt,
                    "image": request.image,
                    "strength": request.strength,
                    "size": request.size,
                    "model": request.model,
                    "steps": request.steps,
                },
                timeout=300.0,
            )
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Worker error: {str(e)}")


@app.post("/v1/vision/analyze")
async def analyze_image(request: VisionAnalyzeRequest):
    """
    Structured Image Analysis.

    Analyze images with predefined tasks or custom prompts.

    Example:
    ```
    POST /v1/vision/analyze
    {
        "image": "<base64 encoded image>",
        "task": "caption"
    }
    ```

    Available tasks:
    - caption: Brief one-sentence description
    - ocr: Extract all visible text
    - describe: Detailed description
    - analyze: Comprehensive analysis
    - objects: List detected objects
    - custom: Use provided 'prompt' field
    """
    # Use vlm-fast for quick analysis, vlm-best for comprehensive
    model_alias = "vlm-best" if request.task in ["analyze", "describe"] else "vlm-fast"
    if model_alias not in config.models:
        model_alias = "vlm-fast" if "vlm-fast" in config.models else list(config.models.keys())[0]

    worker = await supervisor.get_worker(model_alias)

    if worker.address.startswith("http"):
        transport = httpx.AsyncHTTPTransport()
        url = f"{worker.address}/analyze"
    else:
        transport = httpx.AsyncHTTPTransport(uds=worker.address)
        url = "http://local/analyze"

    async with httpx.AsyncClient(transport=transport) as client:
        try:
            resp = await client.post(
                url,
                json={
                    "image": request.image,
                    "task": request.task,
                    "prompt": request.prompt,
                    "max_tokens": request.max_tokens,
                },
                timeout=120.0,
            )
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Worker error: {str(e)}")


@app.get("/v1/vision/tasks")
async def list_vision_tasks():
    """List available vision analysis tasks."""
    return {
        "tasks": [
            {"id": "caption", "description": "Brief one-sentence caption"},
            {"id": "ocr", "description": "Extract text from image (OCR)"},
            {"id": "describe", "description": "Detailed image description"},
            {"id": "analyze", "description": "Comprehensive analysis"},
            {"id": "objects", "description": "List detected objects"},
            {"id": "custom", "description": "Custom prompt (provide 'prompt' field)"},
        ]
    }


@app.get("/healthz")
async def health_check():
    return {"status": "ok", "timestamp": time.time()}


@app.get("/v1/system/status")
async def system_status():
    """
    Get system status including memory usage and loaded workers.

    Returns:
    - workers: Currently loaded workers with memory usage
    - memory: System memory status
    - config: Memory configuration
    """
    try:
        return await supervisor.get_status()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/v1/system/evict/{alias}")
async def evict_worker(alias: str):
    """Manually evict a specific worker to free memory."""
    try:
        await supervisor.stop_worker(alias)
        return {"status": "evicted", "alias": alias}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.gateway.host, port=config.gateway.port)
