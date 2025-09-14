#!/bin/bash

echo "🧪 Testing Layout Aware RAG Demo..."

# Test backend health
echo "🔧 Testing backend health..."
if curl -s http://localhost:8001/health | grep -q "healthy"; then
    echo "✅ Backend is healthy"
else
    echo "❌ Backend health check failed"
    exit 1
fi

# Test frontend (just check if it's responding)
echo "🎨 Testing frontend..."
if curl -s http://localhost:8000 > /dev/null; then
    echo "✅ Frontend is responding"
else
    echo "❌ Frontend is not responding"
    exit 1
fi

# Test Neo4j connection
echo "🗄️  Testing Neo4j connection..."
if docker exec neo4j-rag-demo cypher-shell -u neo4j -p demo_password "RETURN 1" > /dev/null 2>&1; then
    echo "✅ Neo4j is accessible"
else
    echo "❌ Neo4j connection failed"
    exit 1
fi

echo ""
echo "🎉 All tests passed! Demo is ready to use."
echo ""
echo "Next steps:"
echo "1. Open http://localhost:8000 in your browser"
echo "2. Upload a PDF document"
echo "3. Ask questions and see evidence pins in action"