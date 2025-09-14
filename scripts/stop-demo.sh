#!/bin/bash

echo "🛑 Stopping Layout Aware RAG Demo..."

# Go to project root
cd "$(dirname "$0")/.."

# Kill backend process
if [ -f .backend_pid ]; then
    BACKEND_PID=$(cat .backend_pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "🔧 Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
        # Wait for backend to stop
        echo "⏳ Waiting for backend to stop..."
        while kill -0 $BACKEND_PID 2>/dev/null; do
            sleep 1
        done
        echo "✅ Backend stopped"
    else
        echo "⚠️  Backend process not found"
    fi
    rm -f .backend_pid
fi

# Kill frontend process
if [ -f .frontend_pid ]; then
    FRONTEND_PID=$(cat .frontend_pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "🎨 Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
        # Wait for frontend to stop
        echo "⏳ Waiting for frontend to stop..."
        while kill -0 $FRONTEND_PID 2>/dev/null; do
            sleep 1
        done
        echo "✅ Frontend stopped"
    else
        echo "⚠️  Frontend process not found"
    fi
    rm -f .frontend_pid
fi

# Kill any remaining processes on our ports (fallback)
echo "🧹 Cleaning up any remaining processes..."
lsof -ti:8001 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Stop Neo4j container
echo "📦 Stopping Neo4j database..."
cd backend && docker-compose down

echo "✅ Demo stopped!"