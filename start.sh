#!/bin/bash
# Start API, frontend, and the local Celery worker for ProductMedia.
set -e
cd "$(dirname "$0")"

echo "=== ProductMedia ==="
echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
echo ""

# Backend
conda run --no-capture-output -n perfume-video uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!

# Frontend  
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

cd ..
./start-worker.sh &
WORKER_PID=$!

echo "Started (backend=$BACKEND_PID, frontend=$FRONTEND_PID, worker=$WORKER_PID)"
echo "Press Ctrl+C to stop both"
trap "kill $BACKEND_PID $FRONTEND_PID $WORKER_PID 2>/dev/null; exit" INT TERM
wait
