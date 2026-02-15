<p align="center">
  <h1 align="center">🚨 2020 AI Agent</h1>
  <p align="center">
    <strong>AI-Powered Emergency Triage System for Natural Disaster Scenarios</strong>
  </p>
  <p align="center">
    <em>Earthquakes · Floods · Hurricanes · Mass Casualty Events</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black" alt="React"/>
  <img src="https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white" alt="TypeScript"/>
  <img src="https://img.shields.io/badge/AI-GPT--5.2-412991?logo=openai&logoColor=white" alt="GPT-5.2"/>
  <img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white" alt="Telegram Bot"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
</p>

---

## 📋 Table of Contents

- [What Is This?](#-what-is-this)
- [Features](#-features)
- [How It Works](#-how-it-works)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Running with Docker](#-running-with-docker)
- [API Endpoints](#-api-endpoints)
- [Project Structure](#-project-structure)
- [Environment Variables](#-environment-variables)
- [Running Tests](#-running-tests)
- [Tech Stack](#-tech-stack)

---

## 🔍 What Is This?

During natural disasters, emergency services are overwhelmed with reports. **Manual triage is slow and error-prone under stress.** 

**2020 AI Agent** solves this by providing an AI-powered triage system that:

1. **Accepts emergency reports** from multiple channels (Telegram bot, voice calls, text API, web dashboard)
2. **Classifies severity** using GPT-5.2 AI + START triage protocol into 4 levels: 🔴 CRITICAL, 🟠 HIGH, 🟡 MODERATE, 🟢 LOW
3. **Broadcasts live updates** to a real-time dashboard where responders can prioritize and manage cases
4. **Enables responder ↔ victim communication** through a chat bridge (Telegram ↔ Dashboard)

> The AI is a **data collector only** — it never gives medical advice. All medical decisions are made by human responders on the dashboard.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **Multi-Turn AI Triage** | Conversational AI interviews victims, asking the most critical questions first (conscious? breathing? → location → name) |
| 📱 **Telegram Bot** | Full voice + text triage via Telegram — send a voice note or type your emergency |
| 🎙️ **Voice Interview Page** | Browser-based voice triage with microphone recording and AI voice responses |
| 📊 **Real-Time Dashboard** | Live SSE streaming of incoming cases with severity cards, stats, and operator tools |
| 🗺️ **Map View** | Interactive map with geocoded emergency markers (OpenStreetMap) |
| ⚡ **Instant Critical Detection** | Zero-latency keyword-based alerts BEFORE the AI responds (e.g. "not breathing", "cardiac arrest") |
| 🔊 **Voice Processing** | ElevenLabs STT/TTS (primary) + OpenAI Whisper STT / Edge-TTS (free fallbacks) |
| 📄 **PDF Reports** | Individual and summary PDF generation |
| 🌐 **Multilingual** | Supports English, French, and Arabic input |
| 🔒 **Dashboard Auth** | Login-protected dashboard for emergency responders |
| 🛡️ **Offline Fallback** | Keyword-based triage engine works without internet |

---

## ⚙️ How It Works

### Triage Flow

```
1. Victim sends emergency report (text, voice, or Telegram message)
          │
          ▼
2. INSTANT: Critical keyword detection (0ms latency)
   → If "not breathing", "cardiac arrest", etc. → immediate alert
          │
          ▼
3. AI Conversation Engine (GPT-5.2)
   → Asks follow-up questions to collect: what happened, vital signs,
     location, patient info, environmental dangers
          │
          ▼
4. Triage Classification (START protocol)
   → Severity: CRITICAL / HIGH / MODERATE / LOW
   → Confidence score, risk factors, priority rating
          │
          ▼
5. Real-Time Broadcast (SSE)
   → Dashboard receives live case card with all data
   → Map marker placed at geocoded location
          │
          ▼
6. Responder Action
   → View case details, chat with victim via Telegram bridge,
     update status, download PDF report
```

### Severity Levels (START Protocol)

| Level | Color | Examples | Priority |
|-------|-------|----------|----------|
| **CRITICAL** | 🔴 Red | Not breathing, no pulse, cardiac arrest, massive hemorrhage, trapped with crush injuries | 1-2 |
| **HIGH** | 🟠 Orange | Fractures, moderate burns, difficulty breathing, heavy bleeding, altered consciousness | 3-4 |
| **MODERATE** | 🟡 Yellow | Minor fractures, small cuts, mild burns, sprains, anxiety | 5-6 |
| **LOW** | 🟢 Green | Bruises, scratches, minor discomfort, emotional distress | 7-10 |

---

## 🏗️ Architecture

```
Input Channels:
  Telegram Bot (voice + text)  ──┐
  Voice Interview Page (mic)   ──┤
  Text Triage API              ──┘
                                 │
                                 ▼
              ┌──────────────────────────────────┐
              │   Instant Critical Detection     │ ← Zero-latency keyword alerts
              │   (runs BEFORE AI responds)      │
              └───────────┬──────────────────────┘
                          │
                          ▼
              ┌──────────────────────────────────┐
              │   AI Conversation Engine          │
              │   1. OpenAI GPT-5.2              │ ← Primary AI
              │   2. Smart keyword fallback      │ ← Offline mode
              └───────────┬──────────────────────┘
                          │
                ┌─────────┴──────────┐
                ▼                    ▼
        ┌─────────────┐    ┌──────────────────┐
        │ STT Chain   │    │ TTS Chain        │
        │ ElevenLabs  │    │ ElevenLabs       │
        │ → OpenAI    │    │ → Edge-TTS       │
        │   Whisper   │    │ → Browser Speech │
        └─────────────┘    └──────────────────┘
                          │
                          ▼
              ┌──────────────────────────────────┐
              │   Real-Time Dashboard (SSE)       │
              │   • Live case cards with severity │
              │   • Map with geocoded markers     │
              │   • Operator ↔ victim chat bridge │
              └──────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker + Docker Compose** (recommended — easiest way to run)
- **Python 3.10+** (tested on 3.13) — if running without Docker
- **Node.js 18+** — for the React frontend (without Docker)
- **ffmpeg** — for Telegram voice message processing

### 1. Clone the Repository

```bash
git clone https://github.com/sbourziq1337/hackathon.git
cd hackathon
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
nano .env   # Fill in your API keys (see Environment Variables section below)
```

---

### ⚡ Easiest Way: Use `make` (Docker)

Just one command to build and run everything:

```bash
make          # Build and start backend + frontend
```

That's it! The app is running:
- **Frontend:** http://localhost:8080
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

#### All `make` Commands

| Command | Description |
|---------|-------------|
| `make` or `make all` | Build and start everything (foreground) |
| `make up` | Build and start in background (detached) |
| `make down` | Stop and remove containers |
| `make logs` | Follow live logs |
| `make restart` | Restart everything |
| `make clean` | Full cleanup — remove containers, volumes, and images |

---

### 🛠️ Alternative: One-Click Setup Script (without Docker)

If you prefer to run locally without Docker:

```bash
chmod +x setup.sh
./setup.sh
```

The script will automatically:
1. ✅ Check Python version
2. ✅ Create a virtual environment
3. ✅ Install all Python dependencies
4. ✅ Install Playwright Chromium (for PDFs)
5. ✅ Set up `.env` from template
6. ✅ Install frontend npm packages

Then start the servers:

```bash
# Terminal 1 — Backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npx vite --host 0.0.0.0 --port 8080
```

---

### 📝 Manual Setup (step by step)

<details>
<summary>Click to expand manual setup instructions</summary>

#### Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\activate        # Windows

pip install -r requirements.txt
playwright install chromium
```

#### Install ffmpeg (for voice messages)

```bash
# Ubuntu / Debian / Kali
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows: download from https://ffmpeg.org/download.html
```

#### Start the Backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend API is now running at **http://localhost:8000**
- Swagger docs: **http://localhost:8000/docs**

#### Start the Frontend (in a new terminal)

```bash
cd frontend
npm install
npx vite --host 0.0.0.0 --port 8080
```

The frontend is now running at **http://localhost:8080**

</details>

---

### 🔐 Login to the Dashboard

- **Username:** `admin`
- **Password:** `emergency2024`

> ⚠️ Change these credentials in your `.env` file for production!

---

##  API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (status, version, report count) |
| `POST` | `/api/auth/login` | Dashboard login |
| `POST` | `/api/triage/text` | Submit a text emergency report |
| `POST` | `/api/triage/voice` | Submit an audio file for transcription + triage |
| `POST` | `/api/triage/chat` | Multi-turn conversational triage (start or continue) |
| `GET` | `/api/reports` | List all reports (filterable by severity, source, status) |
| `GET` | `/api/reports/stats` | Severity distribution statistics |
| `GET` | `/api/reports/{id}/pdf` | Download a single report as PDF |
| `POST` | `/api/interview/start` | Start a voice interview session |
| `POST` | `/api/interview/{sid}/message` | Send message in voice interview |
| `POST` | `/api/interview/stt` | Speech-to-text |
| `POST` | `/api/interview/tts` | Text-to-speech |
| `GET` | `/api/events` | SSE stream for real-time dashboard updates |
| `GET` | `/docs` | Swagger UI (interactive API documentation) |

### Example: Submit a text report

```bash
curl -X POST http://localhost:8000/api/triage/text \
  -H "Content-Type: application/json" \
  -d '{
    "message": "59-year-old female, heavy bleeding from leg, fractures, trapped under rubble",
    "location": "Casablanca, Morocco",
    "disaster_type": "earthquake"
  }'
```

### Example: Start a chat conversation

```bash
# Start a new conversation
curl -X POST http://localhost:8000/api/triage/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "There is an injured person here, please help"}'

# Continue the conversation (use the session_id from the response)
curl -X POST http://localhost:8000/api/triage/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc12345", "message": "She is conscious but not breathing well"}'
```

---

## 📂 Project Structure

```
hackathon/
├── app/                           # Backend (FastAPI + Python)
│   ├── main.py                    # App entry point, CORS, SSE, lifespan
│   ├── config.py                  # Environment configuration loader
│   ├── models/
│   │   └── triage.py              # Pydantic models (TriageReport, enums, requests)
│   ├── routers/
│   │   ├── auth.py                # Login/authentication endpoints
│   │   ├── triage.py              # Triage endpoints (text, voice, chat)
│   │   ├── reports.py             # Report history, stats & PDF endpoints
│   │   ├── voice_interview.py     # Voice interview REST API
│   │   └── phone.py               # Twilio phone call endpoints
│   ├── services/
│   │   ├── conversation_engine.py # Multi-turn AI conversations (GPT-5.2 → fallback)
│   │   ├── triage_engine.py       # Severity classifier (AI + keyword fallback)
│   │   ├── telegram_bot.py        # Telegram bot (voice + text + chat bridge)
│   │   ├── elevenlabs.py          # STT/TTS chains (ElevenLabs → Whisper → Edge-TTS)
│   │   ├── events.py              # SSE event broadcasting to dashboard
│   │   ├── geocoding.py           # Location → lat/lng (OpenStreetMap Nominatim)
│   │   ├── report_store.py        # In-memory thread-safe report storage
│   │   ├── pdf_generator.py       # PDF generation (Playwright + Jinja2)
│   │   └── call_sessions.py       # Phone call session manager
│   ├── static/                    # Legacy static files
│   └── templates/
│       └── report.html            # HTML template for PDF reports
│
├── frontend/                      # Frontend (React + TypeScript + Vite + Tailwind)
│   ├── src/
│   │   ├── App.tsx                # App root with auth & routing
│   │   ├── pages/
│   │   │   ├── Index.tsx          # Live dashboard (SSE real-time feed)
│   │   │   ├── Login.tsx          # Authentication page
│   │   │   ├── VoiceTriage.tsx    # Browser-based voice interview
│   │   │   ├── Hospitals.tsx      # Hospital/resource map
│   │   │   └── SeverityDistribution.tsx  # Severity charts
│   │   ├── components/
│   │   │   ├── MapView.tsx        # Interactive map with markers
│   │   │   ├── CaseCard.tsx       # Triage case severity card
│   │   │   ├── CaseDetailModal.tsx # Case detail + chat bridge
│   │   │   ├── CriticalCasesBox.tsx # Critical priority alerts
│   │   │   └── Layout.tsx         # App shell with sidebar nav
│   │   └── data/
│   │       └── api.ts             # API client functions
│   └── package.json
│
├── tests/
│   └── test_integration.py        # Integration test suite (54 assertions)
│
├── docker-compose.yml             # Docker multi-service config
├── Dockerfile.backend             # Backend container
├── Dockerfile.frontend            # Frontend container (nginx)
├── nginx.conf                     # Nginx reverse proxy config
├── requirements.txt               # Python dependencies
├── main.py                        # Alternative entry point (uvicorn)
├── setup.sh                       # One-click setup script
├── .env.example                   # Environment variables template
└── README.md                      # This file
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Required | Description | Where to Get |
|----------|----------|-------------|--------------|
| `OPENAI_API_KEY` | ✅ **Yes** | GPT-5.2 AI + Whisper STT | [platform.openai.com](https://platform.openai.com) |
| `TELEGRAM_BOT_TOKEN` | ✅ **Yes** | Telegram bot integration | [@BotFather](https://t.me/BotFather) on Telegram |
| `ELEVENLABS_API_KEY` | No | Premium STT/TTS (Edge-TTS is free fallback) | [elevenlabs.io](https://elevenlabs.io/) |
| `ELEVENLABS_VOICE_ID` | No | Voice for TTS | [elevenlabs.io/voices](https://elevenlabs.io/voices) |
| `TWILIO_ACCOUNT_SID` | No | Phone call support | [twilio.com](https://twilio.com) |
| `TWILIO_AUTH_TOKEN` | No | Phone call support | [twilio.com](https://twilio.com) |
| `TWILIO_PHONE_NUMBER` | No | Phone call support | [twilio.com](https://twilio.com) |
| `DASHBOARD_USERNAME` | No | Dashboard login (default: `admin`) | Set in `.env` |
| `DASHBOARD_PASSWORD` | No | Dashboard login (default: `emergency2024`) | Set in `.env` |
| `SECRET_KEY` | No | JWT signing key | Generate a random string |

> 💡 The system works fully **without optional API keys** — it uses the keyword-based fallback engine for triage and Edge-TTS (free) for text-to-speech.

---

## 🧪 Running Tests

```bash
# Make sure the backend is running first
source venv/bin/activate
uvicorn app.main:app --port 8000 &

# Run the integration test suite
python tests/test_integration.py
```

The test suite includes **54 assertions** across 18 categories covering health checks, triage classification (all severity levels), Arabic input, voice handling, PDF generation, report filtering, and more.

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | FastAPI (Python, async) | High-performance API server |
| **AI (Primary)** | OpenAI GPT-5.2 | Conversational triage + severity classification |
| **AI (Fallback)** | Keyword classifier | Offline triage with 80+ keywords (EN/AR/FR) |
| **STT** | ElevenLabs → OpenAI Whisper | Speech-to-text with automatic fallback |
| **TTS** | ElevenLabs → Edge-TTS | Text-to-speech with free fallback |
| **Frontend** | React + TypeScript + Vite | Modern SPA dashboard |
| **Styling** | Tailwind CSS + shadcn/ui | Component library & utility CSS |
| **Messaging** | python-telegram-bot | Telegram bot integration |
| **Maps** | Leaflet (via MapView) | Interactive emergency map |
| **Geocoding** | OpenStreetMap Nominatim | Free location → coordinates |
| **PDF** | Playwright + Jinja2 | HTML → PDF report generation |
| **Real-Time** | Server-Sent Events (SSE) | Live dashboard updates |
| **Validation** | Pydantic v2 | Request/response validation |
| **HTTP Client** | httpx (async) | Non-blocking external API calls |
| **Containerization** | Docker + Docker Compose | Production deployment |

---

<p align="center">
  <strong>Built for saving lives 🏥</strong><br/>
  <em>2020 AI Agent v1.0.0</em>
</p>
