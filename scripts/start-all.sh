#!/bin/bash
# Start entire Vision Insight API system
# 1. Workers on host (MLX acceleration)
# 2. Gateway in Docker

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
echo "║     Vision Insight API - Starting        ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

cd "$PROJECT_ROOT"

# Step 1: Start Workers on Host
echo -e "${GREEN}[1/3] Starting MLX Workers on Host...${NC}"
"$SCRIPT_DIR/start-workers.sh" start

# Wait for workers to be ready
echo -e "${YELLOW}[*] Waiting for workers to initialize...${NC}"
sleep 5

# Step 2: Build and Start Docker Gateway
echo -e "${GREEN}[2/3] Starting Gateway in Docker...${NC}"
docker compose up -d --build

# Step 3: Wait and verify
echo -e "${GREEN}[3/3] Verifying services...${NC}"
sleep 3

# Check gateway health
for i in {1..10}; do
    if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        echo -e "${GREEN}[✓] Gateway is healthy${NC}"
        break
    fi
    echo -e "${YELLOW}[*] Waiting for gateway... ($i/10)${NC}"
    sleep 2
done

# Show status
echo ""
echo -e "${BLUE}=== System Status ===${NC}"
"$SCRIPT_DIR/start-workers.sh" status
echo ""
docker compose ps

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗"
echo "║     Vision Insight API is Ready!         ║"
echo "╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  API:     http://localhost:8000"
echo "  Docs:    http://localhost:8000/docs"
echo "  Health:  http://localhost:8000/healthz"
echo ""
echo "Quick test:"
echo "  curl http://localhost:8000/v1/models"
echo ""
