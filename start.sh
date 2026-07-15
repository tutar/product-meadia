#!/bin/bash
# Start backend + frontend for VidFlow
set -e
cd "$(dirname "$0")"

echo "=== VidFlow ==="
echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
echo ""

# Backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!

# Frontend  
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

cd ..
echo "Started (backend=$BACKEND_PID, frontend=$FRONTEND_PID)"
echo "Press Ctrl+C to stop both"
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
