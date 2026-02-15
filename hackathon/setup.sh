#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 2020 AI Agent — One-click Setup Script
# ═══════════════════════════════════════════════════════════════
set -e

echo "🚑 2020 AI Agent — Setup"
echo "═══════════════════════════════"

# Check Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Install it: sudo apt install python3 python3-venv"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PY_VERSION found"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "✅ Virtual environment activated"

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"

# Install Playwright for PDF generation
echo "📦 Installing Playwright Chromium..."
playwright install chromium 2>/dev/null || echo "⚠️  Playwright Chromium install failed (PDFs won't work, but everything else will)"

# Set up .env if not present
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your API keys!"
    echo ""
    echo "   Required keys:"
    echo "   1. GROQ_API_KEY      — Free at https://console.groq.com"
    echo "   2. TELEGRAM_BOT_TOKEN — From @BotFather on Telegram"
    echo ""
    echo "   Optional keys:"
    echo "   3. ELEVENLABS_API_KEY — Free at https://elevenlabs.io (TTS)"
    echo "      (Edge-TTS works as free fallback, no key needed)"
    echo ""
    echo "   Open .env in your editor and add the keys, then run this script again."
    exit 0
else
    echo "✅ .env file exists"
fi

# Set up frontend
if [ -d "frontend" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend
    if command -v npm &> /dev/null; then
        npm install -q 2>/dev/null
        echo "✅ Frontend dependencies installed"
    else
        echo "⚠️  npm not found. Install Node.js: sudo apt install nodejs npm"
        echo "   Then run: cd frontend && npm install"
    fi
    cd ..
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Setup complete! To run the project:"
echo ""
echo "   # Terminal 1 — Backend (API + Telegram bot)"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "   # Terminal 2 — Frontend (React dashboard)"
echo "   cd frontend && npx vite --host 0.0.0.0 --port 8080"
echo ""
echo "   Then open: http://localhost:8080"
echo "   Login: admin / emergency2024"
echo ""
echo "   Telegram: Send /start to your bot"
echo "═══════════════════════════════════════════════════"
