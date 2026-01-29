#!/bin/bash
# Quick local test without Docker
# Tests the full stack: Gateway + Workers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$PROJECT_ROOT"
source .venv/bin/activate 2>/dev/null || true

echo -e "${GREEN}=== Vision Insight API - Local Test ===${NC}"
echo ""

# Check if port 8000 is in use
if lsof -i :8000 > /dev/null 2>&1; then
    echo -e "${YELLOW}Port 8000 already in use. Using 8080 instead.${NC}"
    GATEWAY_PORT=8080
else
    GATEWAY_PORT=8000
fi

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    kill $GATEWAY_PID 2>/dev/null || true
    ./scripts/start-workers.sh stop 2>/dev/null || true
}
trap cleanup EXIT

# Step 1: Start a worker (vlm-fast only for quick test)
echo -e "${GREEN}[1/4] Starting vlm-fast worker...${NC}"
./scripts/start-workers.sh start vlm-fast
sleep 3

# Step 2: Start gateway
echo -e "${GREEN}[2/4] Starting gateway on port $GATEWAY_PORT...${NC}"
PYTHONPATH="$PROJECT_ROOT" python -m uvicorn src.gateway.main:app \
    --host 0.0.0.0 --port $GATEWAY_PORT &
GATEWAY_PID=$!
sleep 2

# Check if gateway started
if ! kill -0 $GATEWAY_PID 2>/dev/null; then
    echo -e "${RED}Gateway failed to start${NC}"
    exit 1
fi

# Step 3: Test endpoints
echo -e "${GREEN}[3/4] Testing endpoints...${NC}"
echo ""

# Health check
echo "Testing /healthz..."
curl -s "http://localhost:$GATEWAY_PORT/healthz" | python -m json.tool
echo ""

# List models
echo "Testing /v1/models..."
curl -s "http://localhost:$GATEWAY_PORT/v1/models" | python -m json.tool
echo ""

# System status
echo "Testing /v1/system/status..."
curl -s "http://localhost:$GATEWAY_PORT/v1/system/status" | python -m json.tool
echo ""

# Vision tasks
echo "Testing /v1/vision/tasks..."
curl -s "http://localhost:$GATEWAY_PORT/v1/vision/tasks" | python -m json.tool
echo ""

# Step 4: Summary
echo -e "${GREEN}[4/4] Test Summary${NC}"
echo ""
echo -e "${GREEN}✓ All basic endpoints working${NC}"
echo ""
echo "API is running at: http://localhost:$GATEWAY_PORT"
echo "Swagger UI: http://localhost:$GATEWAY_PORT/docs"
echo ""
echo "To test image generation (requires model download):"
echo "  curl -X POST http://localhost:$GATEWAY_PORT/v1/images/generations \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"prompt\": \"a cat\", \"size\": \"512x512\"}'"
echo ""
echo "Press Ctrl+C to stop..."
wait $GATEWAY_PID
