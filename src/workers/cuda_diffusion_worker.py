"""
CUDA Diffusion Worker - Qwen-Image-2512 text-to-image generation via PyTorch/CUDA.

Supports:
- Text-to-Image: POST /generate
- Health check: GET /health

Requires: torch, diffusers, transformers, accelerate, Pillow
"""

import sys
import time
import base64
import io
import os
from typing import Optional

from PIL import Image
from pydantic import BaseModel, Field
from src.workers.base import BaseWorker, get_base_args

# Environment-driven configuration
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen-Image-2512")
TORCH_DTYPE = os.getenv("TORCH_DTYPE", "bfloat16")
GPU_MEMORY_FRACTION = float(os.getenv("GPU_MEMORY_FRACTION", "0.92"))
MAX_IMAGE_EDGE = int(os.getenv("MAX_IMAGE_EDGE", "2048"))
SAVE_OUTPUTS = os.getenv("SAVE_OUTPUTS", "0") == "1"
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
LOCAL_FILES_ONLY = os.getenv("LOCAL_FILES_ONLY", "0") == "1"


class GenerateRequest(BaseModel):
    """Image generation request."""
    prompt: str = Field(..., min_length=1, max_length=10000)
    negative_prompt: str = Field(default="", max_length=10000)
    width: int = Field(default=1024, ge=256, le=MAX_IMAGE_EDGE)
    height: int = Field(default=1024, ge=256, le=MAX_IMAGE_EDGE)
    num_inference_steps: int = Field(default=50, ge=1, le=100)
    true_cfg_scale: float = Field(default=4.0, ge=0.1, le=20.0)
    seed: Optional[int] = None
    output: str = Field(default="base64", pattern="^(base64|path)$")


class GenerateResponse(BaseModel):
    """Image generation response."""
    model: str
    seed: int
    width: int
    height: int
    elapsed_seconds: float
    image: str  # base64 or file path


class CUDADiffusionWorker(BaseWorker):
    """
    Qwen-Image-2512 text-to-image worker using PyTorch/CUDA.
    Compatible with the Gateway's /v1/images/generations proxy.
    """

    def __init__(self, alias, model_path, socket_path=None, port=None):
        super().__init__(alias, model_path, socket_path, port)
        self.pipe = None
        self._model_id = model_path or MODEL_ID
        self._load_model()

    def _load_model(self):
        try:
            import torch
            from diffusers import DiffusionPipeline

            dtype_map = {
                "bfloat16": torch.bfloat16,
                "float16": torch.float16,
                "fp16": torch.float16,
                "float32": torch.float32,
            }
            dtype = dtype_map.get(TORCH_DTYPE, torch.bfloat16)

            print(f"[*] Loading {self._model_id} (dtype={TORCH_DTYPE})...")

            # Detect available GPUs
            num_gpus = torch.cuda.device_count()
            print(f"[*] CUDA devices: {num_gpus}")

            if num_gpus == 0:
                print("[!] No CUDA devices found, loading on CPU")
                self.pipe = DiffusionPipeline.from_pretrained(
                    self._model_id,
                    torch_dtype=dtype,
                    local_files_only=LOCAL_FILES_ONLY,
                )
            elif num_gpus == 1:
                if GPU_MEMORY_FRACTION < 1.0:
                    torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)
                self.pipe = DiffusionPipeline.from_pretrained(
                    self._model_id,
                    torch_dtype=dtype,
                    local_files_only=LOCAL_FILES_ONLY,
                ).to("cuda:0")
            else:
                # Multi-GPU: balanced device map
                max_mem = {}
                for i in range(num_gpus):
                    total = torch.cuda.get_device_properties(i).total_mem
                    max_mem[i] = int(total * GPU_MEMORY_FRACTION)
                max_mem["cpu"] = "16GB"

                self.pipe = DiffusionPipeline.from_pretrained(
                    self._model_id,
                    torch_dtype=dtype,
                    device_map="balanced",
                    max_memory=max_mem,
                    local_files_only=LOCAL_FILES_ONLY,
                )

            # Disable progress bars for API mode
            if self.pipe is not None:
                self.pipe.set_progress_bar_config(disable=True)

            print(f"[+] {self._model_id} loaded successfully on CUDA")

        except Exception as e:
            print(f"[!] Model loading error: {e}")
            import traceback
            traceback.print_exc()

    def _setup_routes(self):
        super()._setup_routes()

        # Override health to include CUDA info
        @self.app.get("/health")
        async def health():
            import torch
            return {
                "status": "ok" if self.pipe else "model_not_loaded",
                "model": self._model_id,
                "backend": "cuda",
                "cuda_devices": torch.cuda.device_count(),
            }

        @self.app.post("/generate")
        async def generate(request: GenerateRequest):
            """Text-to-Image generation using Qwen-Image-2512."""
            if self.pipe is None:
                return {"error": "Model not loaded"}

            import torch

            seed = request.seed if request.seed is not None else int(time.time())
            generator = torch.Generator(device="cpu").manual_seed(seed)

            # Ensure dimensions are multiples of 16
            width = (request.width // 16) * 16
            height = (request.height // 16) * 16

            print(f"[*] Generating: {request.prompt[:60]}... ({width}x{height})")
            start = time.time()

            try:
                result = self.pipe(
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt or None,
                    width=width,
                    height=height,
                    num_inference_steps=request.num_inference_steps,
                    true_cfg_scale=request.true_cfg_scale,
                    generator=generator,
                )
                img = result.images[0]
                elapsed = time.time() - start
                print(f"[+] Generated in {elapsed:.2f}s")

                if request.output == "path" and SAVE_OUTPUTS:
                    os.makedirs(OUTPUT_DIR, exist_ok=True)
                    fname = f"{int(time.time())}_{seed}.png"
                    path = os.path.join(OUTPUT_DIR, fname)
                    img.save(path)
                    image_out = path
                else:
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    image_out = base64.b64encode(buf.getvalue()).decode()

                return GenerateResponse(
                    model=self._model_id,
                    seed=seed,
                    width=width,
                    height=height,
                    elapsed_seconds=round(elapsed, 3),
                    image=image_out,
                )

            except Exception as e:
                print(f"[!] Generation error: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        # OpenAI-compatible endpoint (proxied from gateway)
        @self.app.post("/openai_generate")
        async def openai_generate(request: dict):
            """
            OpenAI-compatible wrapper for gateway /v1/images/generations proxy.
            Converts between OpenAI format and internal format.
            """
            prompt = request.get("prompt", "")
            size = request.get("size", "1024x1024")
            steps = request.get("steps") or 50
            seed = request.get("seed", int(time.time()))
            guidance = request.get("guidance", 4.0)

            try:
                width, height = map(int, size.lower().split("x"))
            except Exception:
                width, height = 1024, 1024

            gen_req = GenerateRequest(
                prompt=prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                true_cfg_scale=guidance,
                seed=seed,
            )
            resp = await generate(gen_req)

            if isinstance(resp, dict) and "error" in resp:
                return resp

            # Convert to OpenAI-compatible format
            return {
                "created": int(time.time()),
                "data": [{"b64_json": resp.image, "revised_prompt": prompt}],
                "usage": {"latency": resp.elapsed_seconds, "seed": resp.seed},
            }


if __name__ == "__main__":
    args = get_base_args()
    worker = CUDADiffusionWorker(args.alias, args.model_path, args.socket, args.port)
    worker.run()
