#!/bin/bash
# Quick start script for Mahoun platform

set -e

echo "🚀 Starting Mahoun Platform..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo "✅ .env created. Please update with your settings."
    echo ""
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "📦 Building Docker images..."
docker-compose build

echo ""
echo "🎬 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
echo ""
echo "🏥 Health check:"
docker-compose ps

echo ""
echo "✅ Mahoun Platform is running!"
echo ""
echo "📊 Access points:"
echo "  - MCP Server:    http://localhost:8000"
echo "  - Neo4j Browser: http://localhost:7474"
echo "  - Prometheus:    http://localhost:9090"
echo "  - Grafana:       http://localhost:3000"
echo ""
echo "📖 View logs:"
echo "  docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "  docker-compose down"
echo ""
