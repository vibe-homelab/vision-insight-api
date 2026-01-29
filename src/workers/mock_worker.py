import sys
import asyncio
import httpx
import time
import os
import signal
from src.workers.base import BaseWorker, get_base_args


class MockVLMWorker(BaseWorker):
    def __init__(self, alias, model_path, socket_path=None, port=None):
        super().__init__(alias, model_path, socket_path, port)

    def _setup_routes(self):
        super()._setup_routes()

        @self.app.post("/chat")
        async def chat(request: dict):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "This is a MOCK response from the UDS worker.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 10, "latency": 0.1},
            }


if __name__ == "__main__":
    args = get_base_args()
    worker = MockVLMWorker(args.alias, args.model_path, args.socket, args.port)
    worker.run()
