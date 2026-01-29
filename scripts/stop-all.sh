#!/bin/bash
# Stop entire Vision Insight API system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Stopping Vision Insight API...${NC}"

cd "$PROJECT_ROOT"

# Stop Docker containers
echo -e "${YELLOW}[1/2] Stopping Docker containers...${NC}"
docker compose down 2>/dev/null || true

# Stop workers
echo -e "${YELLOW}[2/2] Stopping MLX Workers...${NC}"
"$SCRIPT_DIR/start-workers.sh" stop

echo -e "${GREEN}[✓] All services stopped${NC}"
