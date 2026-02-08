#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_URL="http://localhost:8000"
WEBAPP_URL="http://localhost:3000"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Agent Readiness Lab - Demo${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check if services are running
echo -e "${YELLOW}Checking services...${NC}"
if ! curl -s "$API_URL/health" > /dev/null 2>&1; then
    echo "Starting services..."
    docker compose up -d --build
    echo "Waiting for services to be healthy..."
    sleep 15
fi

# Check API health
if ! curl -s "$API_URL/health" > /dev/null 2>&1; then
    echo "API not ready. Waiting..."
    sleep 10
fi

echo -e "${GREEN}✓ Services are running${NC}"
echo "  - API: $API_URL"
echo "  - Webapp: $WEBAPP_URL"
echo

# Ingest traces
echo -e "${YELLOW}Ingesting example traces...${NC}"

for trace in examples/traces/*.jsonl; do
    filename=$(basename "$trace")
    result=$(curl -s -X POST "$API_URL/ingest_trace" \
        -F "file=@$trace" | jq -r '.status // .detail')
    echo "  - $filename: $result"
done
echo

# List traces
echo -e "${YELLOW}Available traces:${NC}"
curl -s "$API_URL/traces" | jq -r '.traces[] | "  - \(.session_id): \(.goal)"'
echo

# Run replay evaluation
echo -e "${YELLOW}Running replay evaluation...${NC}"
RUN_RESPONSE=$(curl -s -X POST "$API_URL/run_eval" \
    -H "Content-Type: application/json" \
    -d '{"mode": "replay", "runs": 1}')

RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.run_id')
echo "  Run ID: $RUN_ID"
echo "  $(echo "$RUN_RESPONSE" | jq -r '.message')"
echo

# Wait for completion
echo -e "${YELLOW}Waiting for completion...${NC}"
while true; do
    STATUS_RESPONSE=$(curl -s "$API_URL/runs/$RUN_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
    COMPLETED=$(echo "$STATUS_RESPONSE" | jq -r '.completed_sessions')
    TOTAL=$(echo "$STATUS_RESPONSE" | jq -r '.total_sessions')

    echo -ne "\r  Progress: $COMPLETED/$TOTAL sessions ($STATUS)    "

    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        echo
        break
    fi

    sleep 2
done
echo

# Show results
echo -e "${YELLOW}Results:${NC}"
METRICS=$(curl -s "$API_URL/runs/$RUN_ID")

STATUS=$(echo "$METRICS" | jq -r '.status')
if [ "$STATUS" = "completed" ]; then
    echo -e "  ${GREEN}✓ Evaluation completed!${NC}"
    echo
    echo "  Metrics:"
    echo "$METRICS" | jq -r '.metrics |
        "    - Success Rate: \((.success_rate // 0) * 100 | floor)%",
        "    - Median Time: \((.median_time_to_complete_ms // 0) / 1000 | floor)s",
        "    - Error Recovery: \((.error_recovery_rate // 0) * 100 | floor)%",
        "    - Blocked Actions: \(.harmful_action_blocks // 0)",
        "    - Tool Calls: \(.tool_call_count // 0)"'
else
    echo -e "  ${RED}✗ Evaluation failed${NC}"
    echo "$METRICS" | jq -r '.error_message // "Unknown error"'
fi

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}View HTML Report:${NC}"
echo "  $API_URL/runs/$RUN_ID/report"
echo
echo -e "${GREEN}View JSON Report:${NC}"
echo "  $API_URL/runs/$RUN_ID/json"
echo -e "${BLUE}========================================${NC}"
