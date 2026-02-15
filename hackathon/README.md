# 2020 AI Agent

AI-powered emergency triage system for natural disaster scenarios (earthquakes, floods, hurricanes). Helps first responders and dispatchers classify severity of incoming emergency reports and generate actionable triage recommendations.

## Features

- **Multi-Channel Input** — Telegram bot (text + voice), voice interview page, text triage API
- **AI-Powered Triage** — Minimax AI (MiniMax-Text-01) primary, Groq Llama-3 fallback, with START protocol
- **Real-Time Dashboard** — Live SSE streaming of incoming reports, map view with geocoded locations
- **Voice Processing** — ElevenLabs STT/TTS (primary), Groq Whisper STT + Edge-TTS fallback
- **Telegram Bot** — Full voice + text triage via @BotFather bot with operator chat bridge
- **Instant Critical Detection** — Zero-latency keyword-based alerts before AI responds
- **4-Level Severity** — CRITICAL (Red), HIGH (Orange), MODERATE (Yellow), LOW (Green)
- **Geocoding** — Automatic location → map coordinates via Nominatim
- **PDF Reports** — Individual and summary PDF generation via Playwright
- **Offline Fallback** — Keyword-based triage engine works without internet

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/hackathon.git
cd hackathon

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\activate        # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright browser (needed for PDF generation)
playwright install chromium

# 5. Install ffmpeg (needed for voice messages)
# Ubuntu/Debian/Kali:
sudo apt install ffmpeg
# Mac:
# brew install ffmpeg
# Windows: download from https://ffmpeg.org/download.html

# 6. Set up environment variables
cp .env.example .env
nano .env   # Fill in your API keys (see table below)

# 7. Start the backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 8. (Optional) Start the React frontend in a second terminal
cd frontend
npm install
npx vite --host 0.0.0.0 --port 8080

# 9. Open in browser
#    Backend API:  http://localhost:8000/docs
#    Frontend:     http://localhost:8080
#    Login:        admin / emergency2024
```

## System Requirements

- **Python 3.10+** (tested on 3.13)
- **ffmpeg** — required for Telegram voice message processing
- **Node.js 18+** — only if you want to run the React frontend
- **Internet** — for AI (Groq) and speech services

## API Keys Required

| Variable | Where to Get | Required? |
|----------|-------------|-----------|
| `GROQ_API_KEY` | https://console.groq.com (FREE) | **YES** — main AI + STT |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | **YES** — for Telegram bot |
| `ELEVENLABS_API_KEY` | https://elevenlabs.io/ | No — Edge-TTS is free fallback |
| `MINIMAX_API_KEY` | https://www.minimaxi.com/ | No — Groq is free fallback |
| `TWILIO_*` | https://twilio.com | No — only for phone calls |

## Architecture

```
Input Channels:
  Telegram Bot (voice + text)  ──┐
  Voice Interview Page (mic)   ──┤
  Text Triage API              ──┘
                                 │
                                 v
              ┌──────────────────────────────────┐
              │   Instant Critical Detection     │ ← Zero-latency keyword alerts
              │   (runs BEFORE AI responds)      │
              └───────────┬──────────────────────┘
                          │
                          v
              ┌──────────────────────────────────┐
              │   AI Conversation Engine          │
              │   1. Minimax (MiniMax-Text-01)   │ ← Primary (event requirement)
              │   2. Groq (Llama-3.3-70b)        │ ← Free fallback
              │   3. Smart keyword fallback      │ ← Offline mode
              └───────────┬──────────────────────┘
                          │
                ┌─────────┴──────────┐
                v                    v
        ┌─────────────┐    ┌──────────────────┐
        │ STT Chain   │    │ TTS Chain        │
        │ ElevenLabs  │    │ ElevenLabs       │
        │ → Groq      │    │ → Edge-TTS       │
        │   Whisper   │    │ → Browser Speech │
        └─────────────┘    └──────────────────┘
                          │
                          v
              ┌──────────────────────────────────┐
              │   Real-Time Dashboard (SSE)       │
              │   • Live case cards with severity │
              │   • Map with geocoded markers     │
              │   • Operator ↔ victim chat bridge │
              └──────────────────────────────────┘
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/triage/text` | Text-based triage |
| `POST` | `/api/triage/voice` | Voice-based triage (audio upload) |
| `POST` | `/api/triage/chat` | Chat-based multi-turn triage |
| `GET` | `/api/reports` | List reports (filterable) |
| `GET` | `/api/reports/stats` | Severity distribution stats |
| `GET` | `/api/reports/{report_id}/pdf` | Download report PDF |
| `POST` | `/api/interview/start` | Start voice interview session |
| `POST` | `/api/interview/{sid}/message` | Send message to interview |
| `POST` | `/api/interview/stt` | Speech-to-text |
| `POST` | `/api/interview/tts` | Text-to-speech |
| `GET` | `/api/events` | SSE stream for live updates |
| `GET` | `/docs` | Swagger UI |

## Project Structure

```
hackathon/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Environment configuration
│   ├── models/
│   │   └── triage.py              # Pydantic models (TriageReport)
│   ├── routers/
│   │   ├── auth.py                # Login/auth endpoints
│   │   ├── triage.py              # Triage endpoints (text, voice, chat)
│   │   ├── reports.py             # Report history & PDF endpoints
│   │   ├── voice_interview.py     # Voice interview REST API
│   │   └── phone.py               # Twilio phone endpoints
│   ├── services/
│   │   ├── conversation_engine.py # Multi-turn AI (Minimax → Groq → fallback)
│   │   ├── elevenlabs.py          # STT/TTS (ElevenLabs → Groq Whisper → Edge-TTS)
│   │   ├── telegram_bot.py        # Telegram bot (text + voice + chat bridge)
│   │   ├── geocoding.py           # Location → coordinates (Nominatim)
│   │   ├── triage_engine.py       # Single-shot triage (AI + keyword fallback)
│   │   ├── events.py              # SSE event broadcasting
│   │   ├── call_sessions.py       # Phone call session manager
│   │   ├── report_store.py        # In-memory report storage
│   │   └── pdf_generator.py       # Playwright PDF generation
│   ├── static/                    # Legacy static files
│   └── templates/
│       └── report.html            # Jinja2 HTML template for PDFs
├── frontend/                      # React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/                 # Index, VoiceInterview, Hospitals, etc.
│   │   ├── components/            # MapView, Layout, CaseCard, etc.
│   │   └── data/api.ts            # API client
│   └── package.json
├── tests/
│   └── test_integration.py
├── setup.sh                       # One-click setup script
├── requirements.txt
├── .env.example
└── README.md
```

## Running Tests

```bash
source venv/bin/activate
uvicorn app.main:app --port 8000 &
python tests/test_integration.py
```
