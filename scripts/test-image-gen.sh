#!/bin/bash
# Test script for Vision Insight API image generation
# Output files are saved to ./output/ directory (not git tracked)

set -e

API_URL="${API_URL:-http://localhost:8000}"
OUTPUT_DIR="$(dirname "$0")/../output"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create output directory if not exists
mkdir -p "$OUTPUT_DIR"

# Benchmark prompt for quality comparison
# Using a fixed prompt allows comparing image quality across different runs
BENCHMARK_PROMPT="a majestic red fox sitting in an autumn forest, golden sunlight filtering through orange leaves, detailed fur texture, photorealistic style"

# Default prompt (use benchmark if no argument provided)
PROMPT="${1:-$BENCHMARK_PROMPT}"
SIZE="${2:-512x512}"

echo "=== Vision Insight API Test ==="
echo "Timestamp: $TIMESTAMP"
echo "Prompt: $PROMPT"
echo "Size: $SIZE"
echo ""

# Generate image
echo "Generating image..."
RESPONSE=$(curl -s -X POST "$API_URL/v1/images/generations" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"$PROMPT\",\"size\":\"$SIZE\"}")

# Check for errors
if echo "$RESPONSE" | grep -q '"error"'; then
  echo "Error: $(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error','Unknown error'))")"
  exit 1
fi

# Extract and save image
OUTPUT_FILE="$OUTPUT_DIR/gen_${TIMESTAMP}.png"
echo "$RESPONSE" | python3 -c "
import json, base64, sys
data = json.load(sys.stdin)
if 'data' in data and len(data['data']) > 0:
    img_data = base64.b64decode(data['data'][0]['b64_json'])
    with open('$OUTPUT_FILE', 'wb') as f:
        f.write(img_data)
    latency = data.get('usage', {}).get('latency', 0)
    seed = data.get('usage', {}).get('seed', 'N/A')
    print(f'Latency: {latency:.1f}s')
    print(f'Seed: {seed}')
    print(f'Size: {len(img_data)} bytes')
else:
    print('No image data in response')
    sys.exit(1)
"

echo ""
echo "Saved: $OUTPUT_FILE"

# Save metadata
META_FILE="$OUTPUT_DIR/gen_${TIMESTAMP}.json"
echo "{
  \"timestamp\": \"$TIMESTAMP\",
  \"prompt\": \"$PROMPT\",
  \"size\": \"$SIZE\",
  \"output\": \"$OUTPUT_FILE\"
}" > "$META_FILE"

echo "Metadata: $META_FILE"
echo ""
echo "=== Done ==="

# Open image on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
  open "$OUTPUT_FILE" 2>/dev/null || true
fi
