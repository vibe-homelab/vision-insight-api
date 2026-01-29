#!/bin/bash
# Start MLX Workers on Host (macOS)
# Workers must run on host for Apple Silicon MLX acceleration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/.pids"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Activate virtual environment if exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo -e "${GREEN}[✓] Activated virtual environment${NC}"
fi

# Worker configurations
declare -A WORKERS=(
    ["vlm-fast"]="8001:mlx-community/moondream2:vlm"
    ["vlm-best"]="8002:mlx-community/Qwen2.5-VL-7B-Instruct-4bit:vlm"
    ["image-gen"]="8003:mlx-community/FLUX.1-schnell-4bit-mlx:diffusion"
)

start_worker() {
    local alias=$1
    local config=${WORKERS[$alias]}
    local port=$(echo $config | cut -d: -f1)
    local model_path=$(echo $config | cut -d: -f2)
    local worker_type=$(echo $config | cut -d: -f3)

    local pid_file="$PID_DIR/${alias}.pid"
    local log_file="$LOG_DIR/${alias}.log"

    # Check if already running
    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo -e "${YELLOW}[!] Worker $alias already running (PID: $(cat $pid_file))${NC}"
        return 0
    fi

    echo -e "${GREEN}[*] Starting $alias worker on port $port...${NC}"
    echo "    Model: $model_path"
    echo "    Type: $worker_type"

    # Start worker in background
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT" nohup python -m src.workers.${worker_type}_worker \
        --alias "$alias" \
        --model_path "$model_path" \
        --port "$port" \
        > "$log_file" 2>&1 &

    local pid=$!
    echo $pid > "$pid_file"

    # Wait for startup
    sleep 2

    if kill -0 $pid 2>/dev/null; then
        echo -e "${GREEN}[✓] $alias started (PID: $pid)${NC}"
    else
        echo -e "${RED}[✗] $alias failed to start. Check $log_file${NC}"
        return 1
    fi
}

stop_worker() {
    local alias=$1
    local pid_file="$PID_DIR/${alias}.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo -e "${YELLOW}[*] Stopping $alias (PID: $pid)...${NC}"
            kill $pid 2>/dev/null || true
            sleep 1
            kill -9 $pid 2>/dev/null || true
            echo -e "${GREEN}[✓] $alias stopped${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}[!] $alias not running${NC}"
    fi
}

status_worker() {
    local alias=$1
    local config=${WORKERS[$alias]}
    local port=$(echo $config | cut -d: -f1)
    local pid_file="$PID_DIR/${alias}.pid"

    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo -e "${GREEN}[✓] $alias: Running (PID: $(cat $pid_file), Port: $port)${NC}"

        # Check health
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "    ${GREEN}Health: OK${NC}"
        else
            echo -e "    ${YELLOW}Health: Starting...${NC}"
        fi
    else
        echo -e "${RED}[✗] $alias: Stopped${NC}"
    fi
}

show_logs() {
    local alias=$1
    local log_file="$LOG_DIR/${alias}.log"

    if [ -f "$log_file" ]; then
        tail -f "$log_file"
    else
        echo -e "${RED}[!] No log file for $alias${NC}"
    fi
}

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs} [worker]"
    echo ""
    echo "Commands:"
    echo "  start [worker]    Start all workers or specific worker"
    echo "  stop [worker]     Stop all workers or specific worker"
    echo "  restart [worker]  Restart all workers or specific worker"
    echo "  status            Show status of all workers"
    echo "  logs <worker>     Tail logs for specific worker"
    echo ""
    echo "Workers: ${!WORKERS[*]}"
    echo ""
    echo "Examples:"
    echo "  $0 start              # Start all workers"
    echo "  $0 start vlm-fast     # Start only vlm-fast worker"
    echo "  $0 stop               # Stop all workers"
    echo "  $0 status             # Show status"
    echo "  $0 logs image-gen     # Tail image-gen logs"
}

case "${1:-}" in
    start)
        if [ -n "${2:-}" ]; then
            if [ -n "${WORKERS[$2]:-}" ]; then
                start_worker "$2"
            else
                echo -e "${RED}Unknown worker: $2${NC}"
                exit 1
            fi
        else
            echo -e "${GREEN}Starting all workers...${NC}"
            for alias in "${!WORKERS[@]}"; do
                start_worker "$alias"
            done
        fi
        ;;
    stop)
        if [ -n "${2:-}" ]; then
            stop_worker "$2"
        else
            echo -e "${YELLOW}Stopping all workers...${NC}"
            for alias in "${!WORKERS[@]}"; do
                stop_worker "$alias"
            done
        fi
        ;;
    restart)
        if [ -n "${2:-}" ]; then
            stop_worker "$2"
            sleep 1
            start_worker "$2"
        else
            $0 stop
            sleep 2
            $0 start
        fi
        ;;
    status)
        echo -e "${GREEN}=== Worker Status ===${NC}"
        for alias in "${!WORKERS[@]}"; do
            status_worker "$alias"
        done
        ;;
    logs)
        if [ -z "${2:-}" ]; then
            echo -e "${RED}Please specify worker name${NC}"
            exit 1
        fi
        show_logs "$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac
