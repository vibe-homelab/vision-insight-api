#!/bin/bash
# Full installation script for Vision Insight API
# Sets up everything needed for automatic operation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Vision Insight API - Full Installation             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

cd "$PROJECT_ROOT"

# Step 1: Check prerequisites
echo -e "${GREEN}[1/5] Checking prerequisites...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Python: $(python3 --version)"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker: $(docker --version | head -1)"

if [[ $(uname -m) != "arm64" ]]; then
    echo -e "${YELLOW}  ! Warning: Not Apple Silicon - MLX acceleration unavailable${NC}"
fi

# Step 2: Setup Python environment
echo -e "${GREEN}[2/5] Setting up Python environment...${NC}"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "  ${GREEN}✓${NC} Created virtual environment"
fi

source .venv/bin/activate
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements-worker.txt -q
echo -e "  ${GREEN}✓${NC} Installed dependencies"

# Step 3: Create directories
echo -e "${GREEN}[3/5] Creating directories...${NC}"
mkdir -p logs .pids
echo -e "  ${GREEN}✓${NC} Created logs/ and .pids/"

# Step 4: Install Worker Manager service
echo -e "${GREEN}[4/5] Installing Worker Manager service...${NC}"
"$SCRIPT_DIR/install-service.sh"

# Wait for service to be ready
sleep 2
if curl -sf http://localhost:8100/health > /dev/null; then
    echo -e "  ${GREEN}✓${NC} Worker Manager running on port 8100"
else
    echo -e "${RED}  ✗ Worker Manager failed to start${NC}"
    echo "  Check: tail -f $PROJECT_ROOT/logs/worker-manager.error.log"
    exit 1
fi

# Step 5: Start Docker Gateway
echo -e "${GREEN}[5/5] Starting Docker Gateway...${NC}"
docker compose up -d --build

# Wait for gateway
sleep 3
if curl -sf http://localhost:8000/healthz > /dev/null; then
    echo -e "  ${GREEN}✓${NC} Gateway running on port 8000"
else
    echo -e "${RED}  ✗ Gateway failed to start${NC}"
    echo "  Check: docker compose logs gateway"
    exit 1
fi

# Done!
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗"
echo "║       Installation Complete!                              ║"
echo "╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "The system is now running and fully automatic:"
echo ""
echo "  • Gateway:        http://localhost:8000"
echo "  • Swagger UI:     http://localhost:8000/docs"
echo "  • Worker Manager: http://localhost:8100"
echo ""
echo "How it works:"
echo "  1. You make an API call"
echo "  2. Worker Manager auto-spawns the needed worker"
echo "  3. Worker processes your request"
echo "  4. After 5 min idle, worker auto-offloads (frees memory)"
echo ""
echo "Quick test:"
echo "  ${BLUE}curl http://localhost:8000/v1/models${NC}"
echo ""
echo "Generate an image:"
echo "  ${BLUE}curl -X POST http://localhost:8000/v1/images/generations \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"prompt\": \"a cat in space\", \"size\": \"512x512\"}'${NC}"
echo ""
echo "Check system status:"
echo "  ${BLUE}curl http://localhost:8000/v1/system/status${NC}"
echo ""
