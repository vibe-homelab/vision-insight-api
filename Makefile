# Vision Insight API - Makefile

.PHONY: help install start stop restart status logs clean test

help:
	@echo "Vision Insight API"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Full installation (service + docker)"
	@echo "  make uninstall     Remove service and containers"
	@echo ""
	@echo "Control:"
	@echo "  make start         Start gateway (service must be installed)"
	@echo "  make stop          Stop gateway"
	@echo "  make restart       Restart gateway"
	@echo "  make status        Show system status"
	@echo ""
	@echo "Logs:"
	@echo "  make logs          Gateway logs"
	@echo "  make logs-manager  Worker Manager logs"
	@echo "  make logs-workers  All worker logs"
	@echo ""
	@echo "Other:"
	@echo "  make test          Run tests"
	@echo "  make test-api      Quick API test"
	@echo "  make clean         Clean up everything"

# === Setup ===

install:
	@chmod +x scripts/*.sh
	@./scripts/install.sh

uninstall:
	@echo "Stopping services..."
	@docker compose down 2>/dev/null || true
	@./scripts/uninstall-service.sh 2>/dev/null || true
	@echo "Done"

# === Control ===

start:
	@echo "Starting gateway..."
	@docker compose up -d

stop:
	@echo "Stopping gateway..."
	@docker compose down

restart:
	@docker compose restart gateway

status:
	@echo "=== Worker Manager ==="
	@curl -s http://localhost:8100/status 2>/dev/null | python3 -m json.tool || echo "Not running"
	@echo ""
	@echo "=== Gateway ==="
	@curl -s http://localhost:8000/healthz 2>/dev/null | python3 -m json.tool || echo "Not running"
	@echo ""
	@echo "=== Docker ==="
	@docker compose ps

# === Logs ===

logs:
	@docker compose logs -f gateway

logs-manager:
	@tail -f logs/worker-manager.log

logs-workers:
	@tail -f logs/*.log

# === Testing ===

test:
	@source .venv/bin/activate && PYTHONPATH=. pytest tests/ -v

test-api:
	@echo "=== Health Check ==="
	@curl -s http://localhost:8000/healthz | python3 -m json.tool
	@echo ""
	@echo "=== Models ==="
	@curl -s http://localhost:8000/v1/models | python3 -m json.tool
	@echo ""
	@echo "=== System Status ==="
	@curl -s http://localhost:8000/v1/system/status | python3 -m json.tool

# === Cleanup ===

clean:
	@docker compose down -v --rmi local 2>/dev/null || true
	@./scripts/uninstall-service.sh 2>/dev/null || true
	@rm -rf logs/ .pids/ __pycache__/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up"

# === Service Management ===

service-start:
	@launchctl load ~/Library/LaunchAgents/com.vision-insight.worker-manager.plist

service-stop:
	@launchctl unload ~/Library/LaunchAgents/com.vision-insight.worker-manager.plist

service-restart:
	@launchctl unload ~/Library/LaunchAgents/com.vision-insight.worker-manager.plist 2>/dev/null || true
	@launchctl load ~/Library/LaunchAgents/com.vision-insight.worker-manager.plist
