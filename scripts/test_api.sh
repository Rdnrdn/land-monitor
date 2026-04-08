#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"

echo "=== GET /health ==="
curl -s "$BASE_URL/health"
echo
echo

echo "=== GET /auctions ==="
curl -s "$BASE_URL/auctions"
echo
echo

echo "=== GET /auctions/recent ==="
curl -s "$BASE_URL/auctions/recent"
echo
echo

echo "=== GET /auctions/cheapest ==="
curl -s "$BASE_URL/auctions/cheapest"
echo
echo

echo "=== GET /auctions/1 ==="
curl -s "$BASE_URL/auctions/1"
echo
echo

echo "=== GET /parser-runs ==="
curl -s "$BASE_URL/parser-runs"
echo
