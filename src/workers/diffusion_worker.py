"""
Diffusion Worker - FLUX-based image generation with MLX acceleration.

Supports:
- Text-to-Image: POST /generate
- Image-to-Image: POST /edit
"""

import sys
import time
import base64
import io
import os
from PIL import Image
from src.workers.base import BaseWorker, get_base_args

# Import mflux (0.15+ API)
try:
    from mflux.models.flux.variants.txt2img.flux import Flux1
    from mflux.models.common.config import ModelConfig

    MFLUX_AVAILABLE = True
    IMPORT_ERROR = None
except ImportError as e:
    Flux1 = None
    ModelConfig = None
    MFLUX_AVAILABLE = False
    IMPORT_ERROR = str(e)


class DiffusionWorker(BaseWorker):
    """
    FLUX-based image generation worker.
    Supports:
    - Text-to-Image: POST /generate
    - Image-to-Image: POST /edit
    """

    def __init__(self, alias, model_path, socket_path=None, port=None):
        super().__init__(alias, model_path, socket_path, port)
        self.flux = None
        self._model_type = None
        self._load_model()

    def _load_model(self):
        if not MFLUX_AVAILABLE:
            print(f"[!] mflux import failed: {IMPORT_ERROR}")
            return

        try:
            print(f"[*] Loading FLUX model: {self.model_path}...")

            # Determine model type and quantization
            model_type = "schnell" if "schnell" in self.model_path.lower() else "dev"
            num_bits = 4 if "4bit" in self.model_path.lower() else 8

            # Create model config
            model_config = ModelConfig.from_name(
                model_name=model_type,
                base_model=model_type,
            )

            # Initialize Flux1
            self.flux = Flux1(
                model_config=model_config,
                quantize=num_bits,
            )

            self._model_type = model_type
            print(f"[+] FLUX.1 {model_type} ({num_bits}-bit) loaded on Apple Silicon GPU")

        except Exception as e:
            print(f"[!] Model loading error: {e}")
            import traceback
            traceback.print_exc()

    def _base64_to_image(self, b64_string: str) -> Image.Image:
        """Convert base64 string to PIL Image."""
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]
        image_data = base64.b64decode(b64_string)
        return Image.open(io.BytesIO(image_data))

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def _setup_routes(self):
        super()._setup_routes()

        @self.app.post("/generate")
        async def generate(request: dict):
            """
            Text-to-Image generation.

            POST /generate
            {
                "prompt": "a cat in space",
                "size": "1024x1024",
                "steps": 4,
                "seed": 42
            }
            """
            prompt = request.get("prompt", "")
            size = request.get("size", "1024x1024")
            steps = request.get("steps") or 4  # default 4 steps for schnell
            seed = request.get("seed", int(time.time()))
            guidance = request.get("guidance", 3.5)

            # Parse size
            try:
                width, height = map(int, size.lower().split("x"))
            except Exception:
                width, height = 1024, 1024

            if self.flux is None:
                print("[!] FLUX model not loaded, returning mock image")
                return self._mock_gen(prompt)

            print(f"[*] Generating image: {prompt[:50]}... ({width}x{height}, steps={steps})")
            start_time = time.time()

            try:
                # Generate image using mflux API
                generated = self.flux.generate_image(
                    seed=seed,
                    prompt=prompt,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance=guidance,
                )

                # Get PIL image from GeneratedImage object
                img = generated.image if hasattr(generated, 'image') else generated
                img_str = self._image_to_base64(img)

                latency = time.time() - start_time
                print(f"[+] Generation complete ({latency:.2f}s)")

                return {
                    "created": int(time.time()),
                    "data": [{"b64_json": img_str, "revised_prompt": prompt}],
                    "usage": {"latency": latency, "seed": seed},
                }

            except Exception as e:
                print(f"[!] Generation error: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        @self.app.post("/edit")
        async def edit(request: dict):
            """
            Image-to-Image editing (img2img).

            POST /edit
            {
                "prompt": "make it sunset",
                "image": "<base64 encoded image>",
                "strength": 0.7,
                "steps": 4
            }
            """
            prompt = request.get("prompt", "")
            image_b64 = request.get("image", "")
            strength = request.get("strength", 0.7)
            steps = request.get("steps") or 4  # default 4 steps for schnell
            seed = request.get("seed", int(time.time()))
            guidance = request.get("guidance", 3.5)

            if self.flux is None:
                print("[!] FLUX model not loaded, returning mock image")
                return self._mock_gen(prompt)

            if not image_b64:
                return {"error": "image field is required for img2img"}

            print(f"[*] Editing image: {prompt[:50]}... (strength={strength})")
            start_time = time.time()

            try:
                # Decode and save input image temporarily
                input_image = self._base64_to_image(image_b64)
                width, height = input_image.size

                # Ensure dimensions are multiples of 16
                width = (width // 16) * 16
                height = (height // 16) * 16

                # Save temp image for mflux
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    input_image.save(tmp, format="PNG")
                    tmp_path = tmp.name

                try:
                    # Generate with image input
                    generated = self.flux.generate_image(
                        seed=seed,
                        prompt=prompt,
                        width=width,
                        height=height,
                        num_inference_steps=steps,
                        guidance=guidance,
                        image_path=tmp_path,
                        image_strength=strength,
                    )

                    img = generated.image if hasattr(generated, 'image') else generated
                    img_str = self._image_to_base64(img)
                finally:
                    # Clean up temp file
                    os.unlink(tmp_path)

                latency = time.time() - start_time
                print(f"[+] Edit complete ({latency:.2f}s)")

                return {
                    "created": int(time.time()),
                    "data": [{"b64_json": img_str, "revised_prompt": prompt}],
                    "usage": {"latency": latency, "strength": strength, "seed": seed},
                }

            except Exception as e:
                print(f"[!] Edit error: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

    def _mock_gen(self, prompt):
        """Return a mock purple image when model is not loaded."""
        img = Image.new("RGB", (512, 512), color=(200, 50, 200))
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return {
            "created": int(time.time()),
            "data": [{"b64_json": img_str}],
            "status": "mflux_load_failed",
        }


if __name__ == "__main__":
    args = get_base_args()
    worker = DiffusionWorker(args.alias, args.model_path, args.socket, args.port)
    worker.run()
