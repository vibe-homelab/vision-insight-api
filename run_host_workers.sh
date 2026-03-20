#!/bin/bash
# run_host_workers.sh

# 프로젝트 루트 경로 확보
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 가상 환경의 Python 경로 설정
PYTHON_BIN="./.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "[!] 가상 환경을 찾을 수 없습니다. 'uv venv && uv pip install -e .'을 먼저 실행하세요."
    exit 1
fi

# 기존 워커 정리
echo "[*] Cleaning up old workers..."
pkill -f src.workers || true
sleep 2

export PYTHONPATH=$PYTHONPATH:.

# M4 Mac Mini 32GB 안전 로딩 가이드:
# 여러 모델을 동시에 띄울 경우 메모리 사용량에 주의하세요.

if [ "$1" == "gen" ]; then
    echo "[*] [생성 모드] Starting Diffusion Worker (FLUX.2-Klein-4B 4-bit) on Port 8003..."
    $PYTHON_BIN -m src.workers.diffusion_worker --alias image-gen --model_path themindstudio/flux2-klein-4b-mlx-4bit --port 8003 > diffusion_worker.log 2>&1 &
    echo "[+] FLUX.2 Worker is starting. Check diffusion_worker.log for status."
else
    echo "[*] [분석 모드] Starting VLM Worker (Qwen3.5-4B) on Port 8001..."
    $PYTHON_BIN -m src.workers.vlm_worker --alias vlm-fast --model_path mlx-community/Qwen3.5-4B-MLX-4bit --port 8001 > vlm_worker.log 2>&1 &
    echo "[+] VLM Worker is starting. Check vlm_worker.log for status."
fi

echo "[!] Use 'pkill -f src.workers' to stop."
wait
