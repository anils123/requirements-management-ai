#!/usr/bin/env bash
# start_dev.sh — Start FastAPI backend + Vite frontend
set -e

PYTHON="/c/Users/z0044e6b/AppData/Local/Programs/Python/Python313/python.exe"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}Starting Requirements Management AI...${NC}"

# Start FastAPI backend on port 8000
echo -e "${GREEN}[1/2]${NC} Starting FastAPI backend on http://localhost:8000"
cd "$ROOT/backend"
"$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 3

# Start Vite frontend on port 3000
echo -e "${GREEN}[2/2]${NC} Starting React frontend on http://localhost:3000"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}Both servers running:${NC}"
echo -e "  Frontend: ${CYAN}http://localhost:3000${NC}"
echo -e "  Backend:  ${CYAN}http://localhost:8000${NC}"
echo -e "  API docs: ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo "Press Ctrl+C to stop both servers"

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Servers stopped'" EXIT
wait
