#!/bin/bash
cd src-tauri
echo "Starting test server..."
RUST_LOG=info cargo run --bin test_server &
SERVER_PID=$!
sleep 2

echo ""
echo "Testing endpoints..."
echo ""

echo "1. Health check:"
curl -s http://127.0.0.1:8787/api/health | jq . || echo "Failed"
echo ""

echo "2. Root endpoint:"
curl -s http://127.0.0.1:8787/ | jq . || echo "Failed"
echo ""

echo "3. Config endpoint:"
curl -s http://127.0.0.1:8787/api/config | jq . || echo "Failed"
echo ""

echo "4. Tags endpoint (this might fail if not logged in):"
curl -s http://127.0.0.1:8787/api/tags 2>&1 | head -20
echo ""

echo "5. Similar tags endpoint (this might fail if not logged in):"
curl -s "http://127.0.0.1:8787/api/similar-tags?threshold=98" 2>&1 | head -20
echo ""

echo "Stopping server..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

