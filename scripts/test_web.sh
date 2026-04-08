#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"

echo "=== GET /web/auctions ==="
curl -s "$BASE_URL/web/auctions" | head -c 500
echo
echo

echo "=== GET /web/auctions/cheapest ==="
curl -s "$BASE_URL/web/auctions/cheapest" | head -c 500
echo
echo

echo "=== GET /web/parser-runs ==="
curl -s "$BASE_URL/web/parser-runs" | head -c 500
echo
echo

echo "=== GET /web/auctions/1/view ==="
curl -s "$BASE_URL/web/auctions/1/view" | head -c 500
echo
