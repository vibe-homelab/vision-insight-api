#!/bin/bash
# Uninstall Worker Manager launchd service

PLIST_NAME="com.vision-insight.worker-manager"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Uninstalling Worker Manager service..."

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "✓ Service uninstalled"
else
    echo "Service not installed"
fi
