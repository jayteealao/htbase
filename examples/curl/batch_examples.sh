#!/bin/bash
#
# HTBase curl examples - Batch operations
#
# Usage:
#   bash batch_examples.sh
#

# Configuration
BASE_URL="http://localhost:8000"

echo "=========================================="
echo "HTBase curl Examples - Batch Operations"
echo "=========================================="

# Example 1: Batch archive multiple URLs
echo ""
echo "Example 1: Batch archive"
echo "------------------------"
TASK_ID=$(curl -s -X POST "$BASE_URL/api/batch/readability" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"id": "article-1", "url": "https://example.com/1"},
      {"id": "article-2", "url": "https://example.com/2"},
      {"id": "article-3", "url": "https://example.com/3"}
    ]
  }' | jq -r '.task_id')

echo "Task ID: $TASK_ID"
echo ""

# Example 2: Check batch task status
echo ""
echo "Example 2: Check task status"
echo "-----------------------------"
echo "Waiting 5 seconds for task to process..."
sleep 5

curl -s "$BASE_URL/api/tasks/$TASK_ID" | jq '.'
echo ""

# Example 3: Poll task until completion
echo ""
echo "Example 3: Poll until completion"
echo "---------------------------------"

MAX_ATTEMPTS=60
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  STATUS=$(curl -s "$BASE_URL/api/tasks/$TASK_ID" | jq -r '.status')

  if [ "$STATUS" = "success" ] || [ "$STATUS" = "failed" ]; then
    echo "Task completed with status: $STATUS"
    curl -s "$BASE_URL/api/tasks/$TASK_ID" | jq '.'
    break
  fi

  echo "Status: $STATUS (attempt $((ATTEMPT + 1))/$MAX_ATTEMPTS)"
  sleep 5
  ATTEMPT=$((ATTEMPT + 1))
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
  echo "Timeout: Task did not complete in time"
fi

echo ""
echo "=========================================="
echo "Batch examples complete!"
echo "=========================================="
