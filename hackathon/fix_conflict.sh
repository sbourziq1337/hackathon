#!/bin/bash
# Fix '409 Conflict' by ensuring only ONE instance of the bot runs

echo "🛑 Stopping local Python processes..."
pkill -f "python main.py" || true
pkill -f "uvicorn" || true

echo "🐳 Stopping Docker containers..."
docker compose down

echo "🧹 Cleaning up..."
docker system prune -f 2>/dev/null || true

echo "🚀 Starting fresh..."
docker compose up --build
