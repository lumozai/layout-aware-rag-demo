#!/bin/bash

echo "🚀 Starting Layout Aware RAG Demo..."

# Go to project root
cd "$(dirname "$0")/.."

# Clean up any existing processes first
echo "🧹 Cleaning up any existing processes..."
./scripts/stop-demo.sh > /dev/null 2>&1

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

# Check if Python 3.11 is available
if ! command -v python3.11 &> /dev/null; then
    echo "❌ Python 3.11 is not installed. Please install Python 3.11 and try again."
    echo "   You can install it from: https://www.python.org/downloads/"
    exit 1
fi

# Create necessary directories
mkdir -p uploads documents logs

# Check if Neo4j is running
if ! docker ps | grep -q neo4j-rag-demo; then
    echo "📦 Starting Neo4j database..."
    cd backend && docker-compose up -d neo4j && cd ..

    echo "⏳ Waiting for Neo4j to be ready..."
    sleep 15

    # Wait for Neo4j to be accessible
    while ! docker exec neo4j-rag-demo cypher-shell -u neo4j -p demo_password "RETURN 1" > /dev/null 2>&1; do
        echo "   Still waiting for Neo4j..."
        sleep 5
    done
    echo "✅ Neo4j is ready!"
fi

# Start backend
echo "🔧 Setting up backend virtual environment..."
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3.11 -m venv .venv
fi

# Activate virtual environment and install dependencies
source .venv/bin/activate
pip install -r requirements.txt

echo "🚀 Starting backend API..."

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i '' 's/your_secure_password/demo_password/g' .env
fi

# Start backend in background with hot reload
uvicorn main:app --host 0.0.0.0 --port 8001 --reload > ../logs/backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
sleep 5
while ! curl -s http://localhost:8001/health > /dev/null; do
    echo "   Still waiting for backend..."
    sleep 2
done
echo "✅ Backend is ready!"

# Start frontend
echo "🔧 Setting up frontend virtual environment..."
cd ../frontend

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3.11 -m venv .venv
fi

# Activate virtual environment and install dependencies
source .venv/bin/activate
pip install -r requirements.txt

echo "🚀 Starting Chainlit frontend..."

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
fi

# Start frontend in background with hot reload
chainlit run app.py --port 8000 --watch > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to be ready..."
sleep 8

echo ""
echo "🎉 Demo is ready!"
echo ""
echo "📱 Chainlit UI:     http://localhost:8000"
echo "🔗 Backend API:     http://localhost:8001"
echo "🗄️  Neo4j Browser:   http://localhost:7474 (neo4j/demo_password)"
echo ""
echo "📋 Process IDs:"
echo "   Backend PID: $BACKEND_PID"
echo "   Frontend PID: $FRONTEND_PID"
echo ""
echo "📝 Logs:"
echo "   Backend:  tail -f logs/backend.log"
echo "   Frontend: tail -f logs/frontend.log"
echo ""
echo "🛑 To stop all services:"
echo "   ./scripts/stop-demo.sh"
echo ""

# Save PIDs for stop script
echo "$BACKEND_PID" > .backend_pid
echo "$FRONTEND_PID" > .frontend_pid