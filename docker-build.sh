#!/bin/bash

# Build and start the Docker container for ROS 2 Humble

set -e

echo "================================"
echo "LeRobot ROS 2 Humble Docker Setup"
echo "================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   https://docs.docker.com/engine/install/"
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "⚠️  docker-compose not found. Installing via pip..."
    pip install docker-compose
fi

echo "📦 Building Docker image..."
docker-compose build --no-cache

echo ""
echo "✅ Docker image built successfully!"
echo ""
echo "To start the container, run:"
echo "  docker-compose up -d"
echo ""
echo "To attach to the running container:"
echo "  docker-compose exec lerobot-ros2 bash"
echo ""
echo "To stop the container:"
echo "  docker-compose down"
echo ""
