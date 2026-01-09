#!/bin/bash
#
# HTBase curl examples - Advanced operations
#
# Usage:
#   bash advanced_examples.sh
#

# Configuration
BASE_URL="http://localhost:8000"

echo "=========================================="
echo "HTBase curl Examples - Advanced"
echo "=========================================="

# Example 1: Archive with all formats
echo ""
echo "Example 1: Archive with all formats"
echo "------------------------------------"
curl -X POST "$BASE_URL/api/save/all" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "complete-archive",
    "url": "https://example.com"
  }'
echo ""

# Example 2: Generate summary
echo ""
echo "Example 2: Generate AI summary"
echo "-------------------------------"
echo "First, archive with readability..."
curl -s -X POST "$BASE_URL/api/save/readability" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "summary-example",
    "url": "https://example.com"
  }' > /dev/null

echo "Now generating summary..."
curl -X POST "$BASE_URL/api/admin/summarize" \
  -H 'Content-Type: application/json' \
  -d '{
    "item_id": "summary-example"
  }'
echo ""

# Example 3: Check service health
echo ""
echo "Example 3: Health check"
echo "-----------------------"
curl -s "$BASE_URL/api/health" | jq '.'
echo ""

# Example 4: Archive PDF
echo ""
echo "Example 4: Archive as PDF"
echo "-------------------------"
curl -X POST "$BASE_URL/api/save/pdf" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "pdf-example",
    "url": "https://example.com"
  }'
echo ""

# Example 5: Take screenshot
echo ""
echo "Example 5: Take screenshot"
echo "--------------------------"
curl -X POST "$BASE_URL/api/save/screenshot" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "screenshot-example",
    "url": "https://example.com"
  }'
echo ""

# Example 6: Retrieve with query parameters
echo ""
echo "Example 6: Retrieve by URL"
echo "--------------------------"
curl "$BASE_URL/api/retrieve?url=https://example.com&archiver=readability" \
  --output by-url.html
echo "Saved to: by-url.html"
echo ""

# Example 7: Download all formats as tarball
echo ""
echo "Example 7: Download all formats"
echo "--------------------------------"
curl "$BASE_URL/api/retrieve?id=complete-archive&archiver=all" \
  --output complete-archive.tar.gz
echo "Saved to: complete-archive.tar.gz"
echo ""

# Example 8: Error handling - Invalid URL
echo ""
echo "Example 8: Error handling"
echo "-------------------------"
echo "Attempting to archive invalid URL..."
curl -X POST "$BASE_URL/api/save/readability" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "invalid-test",
    "url": "not-a-url"
  }'
echo ""

# Example 9: Error handling - Missing required field
echo ""
echo "Example 9: Missing required field"
echo "----------------------------------"
curl -X POST "$BASE_URL/api/save/readability" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://example.com"
  }'
echo ""

echo "=========================================="
echo "Advanced examples complete!"
echo "=========================================="
