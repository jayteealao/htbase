#!/bin/bash
#
# HTBase curl examples - Basic operations
#
# Usage:
#   bash basic_examples.sh
#

# Configuration
BASE_URL="http://localhost:8000"

echo "=========================================="
echo "HTBase curl Examples - Basic Operations"
echo "=========================================="

# Example 1: Archive a single URL with readability
echo ""
echo "Example 1: Archive with readability"
echo "------------------------------------"
curl -X POST "$BASE_URL/api/save/readability" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "example-readability",
    "url": "https://example.com"
  }'
echo ""

# Example 2: Archive with monolith
echo ""
echo "Example 2: Archive with monolith"
echo "---------------------------------"
curl -X POST "$BASE_URL/api/save/monolith" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "example-monolith",
    "url": "https://example.com"
  }'
echo ""

# Example 3: Archive with all archivers
echo ""
echo "Example 3: Archive with all archivers"
echo "--------------------------------------"
curl -X POST "$BASE_URL/api/save/all" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "example-all",
    "url": "https://example.com"
  }'
echo ""

# Example 4: Retrieve archive
echo ""
echo "Example 4: Retrieve archive"
echo "----------------------------"
curl "$BASE_URL/api/retrieve?id=example-readability&archiver=readability" \
  --output example-readability.html
echo "Saved to: example-readability.html"
echo ""

# Example 5: Retrieve all archives as tarball
echo ""
echo "Example 5: Retrieve all archives"
echo "---------------------------------"
curl "$BASE_URL/api/retrieve?id=example-all&archiver=all" \
  --output example-all.tar.gz
echo "Saved to: example-all.tar.gz"
echo ""

echo "=========================================="
echo "Examples complete!"
echo "=========================================="
