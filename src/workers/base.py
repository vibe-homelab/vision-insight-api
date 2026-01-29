import argparse
import uvicorn
import os
import signal
from fastapi import FastAPI


class BaseWorker:
    def __init__(
        self, alias: str, model_path: str, socket_path: str = None, port: int = None
    ):
        self.alias = alias
        self.model_path = model_path
        self.socket_path = socket_path
        self.port = port
        self.app = FastAPI(title=f"Worker {alias}")
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

    def run(self):
        print(f"[*] Worker {self.alias} starting...")
        if self.socket_path:
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            uvicorn.run(self.app, uds=self.socket_path, log_level="error")
        elif self.port:
            uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="error")
        else:
            raise ValueError("Either socket or port must be specified.")


def get_base_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alias", required=True)
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--socket", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args()
