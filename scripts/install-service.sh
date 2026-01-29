#!/bin/bash
# Install Worker Manager as macOS launchd service
# This ensures Worker Manager starts on boot and stays running

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.vision-insight.worker-manager"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Installing Vision Worker Manager as launchd service...${NC}"

# Find Python in venv
PYTHON_PATH="$PROJECT_ROOT/.venv/bin/python"
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}Virtual environment not found at $PROJECT_ROOT/.venv${NC}"
    echo "Run ./scripts/setup.sh first"
    exit 1
fi

# Create LaunchAgents directory if needed
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing service if running
if launchctl list | grep -q "$PLIST_NAME"; then
    echo -e "${YELLOW}Stopping existing service...${NC}"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Create plist file
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>src.worker_manager</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_ROOT}</string>
        <key>IDLE_TIMEOUT</key>
        <string>300</string>
        <key>MANAGER_PORT</key>
        <string>8100</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${PROJECT_ROOT}/logs/worker-manager.log</string>

    <key>StandardErrorPath</key>
    <string>${PROJECT_ROOT}/logs/worker-manager.error.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

echo -e "${GREEN}Created plist at: $PLIST_PATH${NC}"

# Create logs directory
mkdir -p "$PROJECT_ROOT/logs"

# Load the service
echo -e "${GREEN}Loading service...${NC}"
launchctl load "$PLIST_PATH"

# Verify it's running
sleep 2
if launchctl list | grep -q "$PLIST_NAME"; then
    echo -e "${GREEN}✓ Worker Manager service installed and running${NC}"
    echo ""
    echo "Service commands:"
    echo "  Start:   launchctl load $PLIST_PATH"
    echo "  Stop:    launchctl unload $PLIST_PATH"
    echo "  Status:  launchctl list | grep $PLIST_NAME"
    echo "  Logs:    tail -f $PROJECT_ROOT/logs/worker-manager.log"
    echo ""
    echo "Test:"
    echo "  curl http://localhost:8100/health"
else
    echo -e "${RED}✗ Failed to start service${NC}"
    echo "Check logs: $PROJECT_ROOT/logs/worker-manager.error.log"
    exit 1
fi
