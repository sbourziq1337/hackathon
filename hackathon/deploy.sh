#!/bin/bash

# Deployment script for 2020 AI Agent
# Usage: ./deploy.sh <server-ip> <ssh-key-path>

SERVER_IP="${1:-91.98.143.225}"
SSH_KEY="${2:--}"  # use default if not provided
REMOTE_USER="root"
REMOTE_PATH="/opt/2020-ai-agent"

echo "🚀 Deploying to $SERVER_IP..."

# 1. Copy project to server
echo "📦 Copying project files..."
rsync -avz \
  --delete \
  -e "ssh -i $SSH_KEY" \
  --exclude '.git' \
  --exclude '.env' \
  --exclude '__pycache__' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'reports' \
  --exclude '.DS_Store' \
  ./ "$REMOTE_USER@$SERVER_IP:$REMOTE_PATH/"

# 2. SSH into server and deploy
echo "⚙️  Setting up on server..."
ssh -i "$SSH_KEY" "$REMOTE_USER@$SERVER_IP" << 'DEPLOY_SCRIPT'
set -e

REMOTE_PATH="/opt/2020-ai-agent"
cd "$REMOTE_PATH"

# Create .env from template if it doesn't exist
if [ ! -f .env ]; then
  echo "⚠️  .env not found. Creating template..."
  cat > .env << 'EOF'
# AI APIs
GROQ_API_KEY=your_groq_key_here
MINIMAX_API_KEY=optional
MINIMAX_GROUP_ID=optional

# Speech APIs
ELEVENLABS_API_KEY=optional
ELEVENLABS_VOICE_ID=optional

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_token_here

# Twilio (optional)
TWILIO_ACCOUNT_SID=optional
TWILIO_AUTH_TOKEN=optional
TWILIO_PHONE_NUMBER=optional

# Server
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=production
BASE_URL=http://91.98.143.225:8000

# Dashboard Auth
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=emergency2024
SECRET_KEY=change-this-in-production
EOF
  echo "✅ Created .env template. Please fill in your API keys."
fi

# Start with Docker Compose
echo "🐳 Starting Docker containers..."
docker compose up -d --build

echo "✅ Deployment complete!"
echo "📝 Frontend:  http://91.98.143.225:8080"
echo "📝 Backend:   http://91.98.143.225:8000/docs"
echo "🔑 Default login: admin / emergency2024"
DEPLOY_SCRIPT

echo "✅ Done!"
