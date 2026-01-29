#!/bin/bash
# Initial setup script for Vision Insight API

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════╗"
echo "║   Vision Insight API - Initial Setup     ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

cd "$PROJECT_ROOT"

# Check prerequisites
echo -e "${GREEN}[1/5] Checking prerequisites...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[✗] Python 3 not found. Please install Python 3.11+${NC}"
    exit 1
fi
echo -e "${GREEN}[✓] Python: $(python3 --version)${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[✗] Docker not found. Please install Docker Desktop${NC}"
    exit 1
fi
echo -e "${GREEN}[✓] Docker: $(docker --version)${NC}"

# Check Apple Silicon
if [[ $(uname -m) != "arm64" ]]; then
    echo -e "${YELLOW}[!] Warning: MLX requires Apple Silicon (M1/M2/M3/M4)${NC}"
    echo -e "${YELLOW}    Workers will run in CPU-only mode${NC}"
fi

# Create virtual environment
echo -e "${GREEN}[2/5] Setting up Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}[✓] Created .venv${NC}"
else
    echo -e "${YELLOW}[!] .venv already exists${NC}"
fi

# Activate and install dependencies
echo -e "${GREEN}[3/5] Installing Python dependencies...${NC}"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-worker.txt

# Create directories
echo -e "${GREEN}[4/5] Creating directories...${NC}"
mkdir -p logs .pids

# Download models (optional)
echo -e "${GREEN}[5/5] Model setup...${NC}"
echo -e "${YELLOW}Models will be downloaded on first use.${NC}"
echo -e "${YELLOW}To pre-download models, run:${NC}"
echo ""
echo "  # VLM (fast)"
echo "  python -c \"from mlx_vlm import load; load('mlx-community/moondream2')\""
echo ""
echo "  # VLM (best quality)"
echo "  python -c \"from mlx_vlm import load; load('mlx-community/Qwen2.5-VL-7B-Instruct-4bit')\""
echo ""
echo "  # Image Generation"
echo "  python -c \"from mflux import Flux1; Flux1('schnell', quantize=4)\""
echo ""

echo -e "${GREEN}╔══════════════════════════════════════════╗"
echo "║        Setup Complete!                   ║"
echo "╚══════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Start the system:"
echo "     ${GREEN}make start${NC}"
echo ""
echo "  2. Or start manually:"
echo "     ${GREEN}./scripts/start-workers.sh start${NC}"
echo "     ${GREEN}docker compose up -d${NC}"
echo ""
echo "  3. Test the API:"
echo "     ${GREEN}curl http://localhost:8000/v1/models${NC}"
echo ""
echo "  4. Open API docs:"
echo "     ${GREEN}open http://localhost:8000/docs${NC}"
echo ""
