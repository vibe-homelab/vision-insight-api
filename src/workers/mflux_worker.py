"""
MFLUX Worker - MLX-native image generation using FLUX models.
Supports both text-to-image and image-to-image generation.
"""

import base64
import io
import os
import time
from typing import Optional
from PIL import Image
from pydantic import BaseModel, Field

from src.workers.base import BaseWorker, get_base_args


class GenerateRequest(BaseModel):
    """Text-to-image generation request."""
    prompt: str
    n: int = 1
    size: str = "1024x1024"
    model: str = "schnell"  # schnell (fast) or dev (quality)
    steps: Optional[int] = None  # None = auto (4 for schnell, 20 for dev)
    seed: Optional[int] = None
    guidance: float = 3.5


class EditRequest(BaseModel):
    """Image-to-image editing request."""
    prompt: str
    image: str  # Base64 encoded image
    strength: float = Field(default=0.7, ge=0.0, le=1.0)
    size: Optional[str] = None  # None = keep original size
    model: str = "schnell"
    steps: Optional[int] = None
    seed: Optional[int] = None
    guidance: float = 3.5


class MfluxWorker(BaseWorker):
    """Worker for MFLUX-based image generation."""

    def __init__(self, alias: str, model_path: str, socket_path: str = None, port: int = None):
        self.flux = None
        self._model_loaded = None
        super().__init__(alias, model_path, socket_path, port)

    def _load_model(self, model_name: str = "schnell"):
        """Lazy load the FLUX model."""
        if self._model_loaded == model_name:
            return

        from mflux import Flux1, Config

        print(f"[*] Loading FLUX model: {model_name}")
        start = time.time()

        # Use 4-bit quantization for memory efficiency
        self.flux = Flux1(
            model_name=model_name,
            quantize=4,  # 4-bit quantization
        )

        self._model_loaded = model_name
        print(f"[*] Model loaded in {time.time() - start:.2f}s")

    def _parse_size(self, size_str: str) -> tuple[int, int]:
        """Parse size string like '1024x1024' to (width, height)."""
        parts = size_str.lower().split("x")
        if len(parts) != 2:
            return 1024, 1024
        return int(parts[0]), int(parts[1])

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _base64_to_image(self, b64_string: str) -> Image.Image:
        """Convert base64 string to PIL Image."""
        # Handle data URL format
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]
        image_data = base64.b64decode(b64_string)
        return Image.open(io.BytesIO(image_data))

    def _setup_routes(self):
        super()._setup_routes()

        @self.app.post("/generate")
        async def generate(request: GenerateRequest):
            """
            Text-to-image generation.

            POST /generate
            {
                "prompt": "a cat in space",
                "n": 1,
                "size": "1024x1024",
                "model": "schnell",
                "steps": 4,
                "seed": 42
            }
            """
            try:
                self._load_model(request.model)

                width, height = self._parse_size(request.size)
                steps = request.steps or (4 if request.model == "schnell" else 20)

                results = []
                for i in range(request.n):
                    seed = (request.seed + i) if request.seed else None

                    start = time.time()
                    image = self.flux.generate_image(
                        prompt=request.prompt,
                        width=width,
                        height=height,
                        num_steps=steps,
                        seed=seed,
                        guidance=request.guidance,
                    )
                    elapsed = time.time() - start

                    results.append({
                        "b64_json": self._image_to_base64(image),
                        "revised_prompt": request.prompt,
                    })
                    print(f"[*] Generated image {i+1}/{request.n} in {elapsed:.2f}s")

                return {
                    "created": int(time.time()),
                    "data": results,
                }

            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.post("/edit")
        async def edit(request: EditRequest):
            """
            Image-to-image editing (img2img).

            POST /edit
            {
                "prompt": "make it sunset",
                "image": "<base64 encoded image>",
                "strength": 0.7,
                "model": "schnell",
                "steps": 4
            }
            """
            try:
                self._load_model(request.model)

                # Decode input image
                input_image = self._base64_to_image(request.image)

                # Determine output size
                if request.size:
                    width, height = self._parse_size(request.size)
                else:
                    width, height = input_image.size

                # Ensure dimensions are multiples of 16 (required by FLUX)
                width = (width // 16) * 16
                height = (height // 16) * 16

                steps = request.steps or (4 if request.model == "schnell" else 20)

                start = time.time()

                # img2img uses init_image and strength
                output_image = self.flux.generate_image(
                    prompt=request.prompt,
                    width=width,
                    height=height,
                    num_steps=steps,
                    seed=request.seed,
                    guidance=request.guidance,
                    init_image=input_image,
                    init_image_strength=request.strength,
                )

                elapsed = time.time() - start
                print(f"[*] Edited image in {elapsed:.2f}s (strength={request.strength})")

                return {
                    "created": int(time.time()),
                    "data": [{
                        "b64_json": self._image_to_base64(output_image),
                        "revised_prompt": request.prompt,
                    }],
                }

            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.get("/models")
        async def list_models():
            """List available FLUX models."""
            return {
                "models": [
                    {
                        "id": "schnell",
                        "name": "FLUX.1-schnell",
                        "description": "Fast generation (4 steps), good for iteration",
                        "default_steps": 4,
                    },
                    {
                        "id": "dev",
                        "name": "FLUX.1-dev",
                        "description": "High quality generation (20 steps)",
                        "default_steps": 20,
                    },
                ]
            }


if __name__ == "__main__":
    args = get_base_args()
    worker = MfluxWorker(args.alias, args.model_path, args.socket, args.port)
    worker.run()
