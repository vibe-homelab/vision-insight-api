"""
VLM Worker - Vision Language Model for image understanding.
Uses mlx-vlm or Moondream for image-to-text tasks.

Endpoints:
- POST /chat - OpenAI-compatible chat completion with vision
- POST /analyze - Structured image analysis with predefined tasks
- GET /tasks - List available analysis tasks
"""

import sys
import base64
import io
import time
from PIL import Image
from src.workers.base import BaseWorker, get_base_args

# Conditionally import MLX related libs to avoid crashes if not installed during setup
try:
    import mlx.core as mx
    from mlx_vlm import load as load_vlm, generate as generate_vlm
    import moondream as md
except ImportError:
    mx = None
    load_vlm = None
    md = None


class VLMWorker(BaseWorker):
    """
    Vision Language Model worker for image understanding.
    Supports:
    - Image captioning
    - OCR (text extraction)
    - Detailed description
    - Comprehensive analysis
    - Object detection
    - Custom prompts
    """

    def __init__(self, alias, model_path, socket_path=None, port=None):
        super().__init__(alias, model_path, socket_path, port)
        self.model = None
        self.processor = None
        self.md_model = None  # For official moondream library
        self._load_model()

    def _load_model(self):
        if "moondream" in self.model_path.lower():
            if md is None:
                print("[!] moondream library not installed.")
                return
            print(
                f"[*] Loading Moondream model using official lib: {self.model_path}..."
            )

            try:
                self.md_model = md.vl(model=self.model_path)
            except TypeError:
                print("[*] Retrying Moondream load with positional argument...")
                self.md_model = md.vl(self.model_path)

            print(f"[+] Moondream {self.alias} loaded successfully.")

        else:
            if load_vlm is None:
                print("[!] MLX-VLM not installed.")
                return
            print(f"[*] Loading model using mlx-vlm: {self.model_path}...")
            self.model, self.processor = load_vlm(self.model_path)
            print(f"[+] Model {self.alias} loaded successfully.")

    def _setup_routes(self):
        super()._setup_routes()

        @self.app.post("/chat")
        async def chat(request: dict):
            """OpenAI-compatible chat completion with vision."""
            messages = request.get("messages", [])
            prompt = ""
            image_data = None

            for msg in messages:
                content = msg.get("content", [])
                if isinstance(content, str):
                    prompt += f"\n{msg['role']}: {content}"
                elif isinstance(content, list):
                    for part in content:
                        if part["type"] == "text":
                            prompt += f"\n{msg['role']}: {part['text']}"
                        elif part["type"] == "image_url":
                            img_url = part["image_url"]["url"]
                            if img_url.startswith("data:image"):
                                _, b64 = img_url.split(",", 1)
                                image_data = base64.b64decode(b64)

            # --- Case 1: Moondream Official Lib ---
            if self.md_model:
                pil_image = Image.open(io.BytesIO(image_data)) if image_data else None
                start_time = time.time()

                if pil_image:
                    encoded_img = self.md_model.encode_image(pil_image)
                    output = self.md_model.query(encoded_img, prompt)["answer"]
                else:
                    output = self.md_model.query(prompt)["answer"]

                latency = time.time() - start_time
                return self._format_response(output, latency)

            # --- Case 2: MLX-VLM ---
            if self.model:
                pil_image = Image.open(io.BytesIO(image_data)) if image_data else None
                start_time = time.time()
                output = generate_vlm(
                    self.model, self.processor, pil_image, prompt, max_tokens=512
                )
                latency = time.time() - start_time
                return self._format_response(output, latency)

            return self._mock_response(prompt)

        @self.app.post("/analyze")
        async def analyze(request: dict):
            """
            Structured image analysis with predefined tasks.

            POST /analyze
            {
                "image": "<base64 encoded image>",
                "task": "caption",  // caption, ocr, describe, analyze, objects, custom
                "prompt": "optional custom prompt for 'custom' task",
                "max_tokens": 512
            }
            """
            image_b64 = request.get("image", "")
            task = request.get("task", "caption")
            custom_prompt = request.get("prompt", "")
            max_tokens = request.get("max_tokens", 512)

            if not image_b64:
                return {"error": "image field is required"}

            # Task-specific prompts
            task_prompts = {
                "caption": "Provide a brief, one-sentence caption for this image.",
                "ocr": "Extract and return all text visible in this image. Return only the extracted text, nothing else.",
                "describe": "Describe this image in detail, including objects, colors, composition, and mood.",
                "analyze": """Analyze this image comprehensively. Include:
1) Main subject
2) Objects and their positions
3) Colors and lighting
4) Any text visible
5) Overall context or meaning""",
                "objects": "List all objects visible in this image, one per line.",
                "custom": custom_prompt or "Describe this image.",
            }

            prompt = task_prompts.get(task, task_prompts["caption"])

            try:
                # Decode image
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_data = base64.b64decode(image_b64)
                pil_image = Image.open(io.BytesIO(image_data))

                start_time = time.time()

                # Use Moondream if available
                if self.md_model:
                    encoded_img = self.md_model.encode_image(pil_image)
                    output = self.md_model.query(encoded_img, prompt)["answer"]
                # Use MLX-VLM
                elif self.model:
                    output = generate_vlm(
                        self.model, self.processor, pil_image, prompt, max_tokens=max_tokens
                    )
                else:
                    output = f"Mock analysis for task: {task}"

                latency = time.time() - start_time

                return {
                    "task": task,
                    "result": output,
                    "created": int(time.time()),
                    "model": self.model_path,
                    "usage": {
                        "latency": latency,
                        "prompt_used": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                    },
                }

            except Exception as e:
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        @self.app.get("/tasks")
        async def list_tasks():
            """List available analysis tasks."""
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

    def _format_response(self, content, latency):
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": len(content.split()), "latency": latency},
        }

    def _mock_response(self, prompt):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"Mock VLM response for prompt: {prompt[:50]}...",
                    },
                    "finish_reason": "stop",
                }
            ]
        }


if __name__ == "__main__":
    args = get_base_args()
    worker = VLMWorker(args.alias, args.model_path, args.socket, args.port)
    worker.run()
