# PROJECT REPORT
# 2020 AI Agent — AI-Powered Emergency Triage for Natural Disaster Scenarios

---

## 1. PROJECT OVERVIEW

### 1.1 Purpose
The 2020 AI Agent is an AI-powered system designed to assist first responders and emergency dispatchers during natural disasters (earthquakes, floods, hurricanes, etc.). It rapidly classifies the severity of incoming emergency reports and generates actionable triage recommendations including first-aid instructions, responder actions, and transport priorities.

### 1.2 Problem Statement
During natural disasters, emergency services are overwhelmed with reports. Manual triage is slow and error-prone under stress. This system automates severity classification to ensure the most critical patients receive attention first, potentially saving lives through faster response.

### 1.3 Solution
A web-based application that accepts emergency reports via two channels:
- **Text messages** — typed descriptions from victims, bystanders, or field responders
- **Voice calls** — audio recordings transcribed to text using AI

Each report is analyzed by the triage engine, classified into a severity level, and returned as a structured report with medical reasoning, first-aid instructions, and recommended actions.

---

## 2. SYSTEM ARCHITECTURE

```
                    ┌──────────────────┐
                    │   Web Frontend   │
                    │  (HTML/CSS/JS)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   FastAPI Server  │
                    │   (async Python)  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
    │  ElevenLabs    │ │  Triage  │ │   Report    │
    │  STT / TTS     │ │  Engine  │ │   Store     │
    │  (Voice API)   │ │          │ │ (In-Memory) │
    └────────────────┘ └────┬─────┘ └──────┬──────┘
                            │              │
                  ┌─────────┼──────┐       │
                  │                │       │
          ┌───────▼──────┐ ┌──────▼───┐   │
          │  Minimax AI  │ │ Keyword  │   │
          │  (Primary)   │ │ Fallback │   │
          └──────────────┘ └──────────┘   │
                                          │
                               ┌──────────▼──────────┐
                               │   PDF Generator     │
                               │ (Playwright/Chrome)  │
                               └─────────────────────┘
```

### 2.1 Architecture Flow
1. Input arrives via the web frontend (text form or audio upload/recording)
2. If voice: audio is sent to ElevenLabs STT API for transcription
3. The text (typed or transcribed) is sent to the Triage Engine
4. Triage Engine attempts Minimax AI classification first; falls back to keyword engine if unavailable
5. AI returns a structured severity classification
6. The system enriches the report with metadata (timestamp, input source, location)
7. The report is stored in memory and returned to the frontend
8. Optionally: individual or summary PDF reports can be generated and downloaded

---

## 3. TECHNOLOGY STACK

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend Framework | FastAPI (Python, async) | High-performance API server |
| AI Engine (Primary) | Minimax AI (MiniMax-Text-01) | Intelligent triage classification |
| AI Engine (Fallback) | Keyword-based classifier | Offline/disaster-resilient triage |
| Voice-to-Text | ElevenLabs STT API (Scribe v1) | Audio transcription |
| Text-to-Speech | ElevenLabs TTS API | Audio readback of triage results |
| HTTP Client | httpx (async) | Non-blocking API calls |
| Data Validation | Pydantic v2 | Request/response validation |
| PDF Generation | Playwright (headless Chromium) | HTML-to-PDF rendering |
| Templating | Jinja2 | HTML templates for PDF reports |
| Frontend | HTML5, CSS3, Vanilla JavaScript | User interface |
| Configuration | python-dotenv | Environment variable management |

---

## 4. FEATURES IMPLEMENTED

### 4.1 Text Triage (POST /api/triage/text)
- Accepts JSON body with emergency report text, optional location, disaster type, and victim count
- Classifies severity using START triage protocol
- Returns full structured triage report
- Supports both English and Arabic input

### 4.2 Voice Triage (POST /api/triage/voice)
- Accepts audio file upload (WAV, MP3, WebM, OGG, M4A)
- Supports microphone recording directly from browser
- Transcribes audio via ElevenLabs STT
- Passes transcript to triage engine
- Returns triage report with input_source = "voice_call"

### 4.3 Triage Classification Engine
**Primary: Minimax AI**
- Uses MiniMax-Text-01 model
- System prompt enforces START triage protocol
- Returns structured JSON with severity, reasoning, conditions, actions, first-aid

**Fallback: Keyword Classifier**
- Works offline without internet
- Pattern matches against 80+ medical keywords (English + Arabic)
- Supports vulnerability detection (children, elderly, pregnant)
- Automatic severity bumping for vulnerable populations

### 4.4 Severity Levels
| Level | Color | Description | Priority |
|-------|-------|-------------|----------|
| CRITICAL | Red | Life-threatening — immediate intervention needed | 1 |
| HIGH | Orange | Serious — urgent medical attention required | 3 |
| MODERATE | Yellow | Significant — medical evaluation needed | 5 |
| LOW | Green | Minor — self-care or minor treatment | 8 |

### 4.5 Classification Rules
1. Never underestimate severity — when in doubt, classify UP
2. Mechanism of injury considered (earthquake collapse, drowning, electrocution)
3. Children and elderly automatically receive a severity bump
4. Multiple injuries compound severity
5. Environmental context matters (trapped in rubble, flood water exposure)
6. Actionable first-aid instructions always provided

### 4.6 Report History & Filtering
- In-memory storage of all triage reports
- Filter by severity level (CRITICAL, HIGH, MODERATE, LOW)
- Filter by input source (text, voice_call)
- Newest-first ordering with pagination
- Individual report lookup by ID

### 4.7 Dashboard & Statistics
- Real-time severity distribution counts
- Visual bar chart of severity breakdown
- Recent reports list
- Total report counter

### 4.8 PDF Report Generation
- Individual report PDFs with full details, severity badge, and instructions
- Summary PDF with severity distribution chart and all reports table
- Professional styling with color-coded severity indicators
- Generated using Playwright headless Chromium

### 4.9 TTS Response (POST /api/triage/tts/{report_id})
- Generates spoken audio summary of a triage report
- Reads back severity, reasoning, ambulance requirement, and first-aid
- Uses ElevenLabs TTS API with multilingual v2 model

### 4.10 Web Frontend
- Modern dark-themed UI with responsive design
- Four main sections: New Triage, Voice Call, Report History, Dashboard
- Real-time server health status indicator
- Microphone recording with timer
- Audio file drag-and-drop upload
- Click-to-view report detail modal
- PDF download buttons
- JSON copy-to-clipboard

---

## 5. API ENDPOINTS

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | / | Frontend web application |
| GET | /health | System health check |
| GET | /docs | Swagger UI (interactive API docs) |
| POST | /api/triage/text | Text-based triage classification |
| POST | /api/triage/voice | Voice-based triage (audio upload) |
| POST | /api/triage/tts/{report_id} | Generate TTS audio for a report |
| GET | /api/reports | List reports (filterable by severity, source) |
| GET | /api/reports/stats | Severity distribution statistics |
| GET | /api/reports/{report_id} | Get single report by ID |
| GET | /api/reports/{report_id}/pdf | Download individual report PDF |
| GET | /api/reports/pdf/summary | Download summary PDF |

---

## 6. TRIAGE REPORT SCHEMA

Every triage operation produces a structured JSON report:

```json
{
    "report_id": "unique UUID",
    "input_source": "text | voice_call",
    "original_report": "the original text or transcript",
    "timestamp": "ISO 8601 timestamp",
    "severity": "CRITICAL | HIGH | MODERATE | LOW",
    "confidence": 0.0 - 1.0,
    "reasoning": "Medical reasoning for classification",
    "detected_conditions": ["list of detected conditions"],
    "recommended_actions": ["list of responder actions"],
    "first_aid_instructions": ["step-by-step first aid"],
    "needs_ambulance": true/false,
    "estimated_response_priority": 1-10,
    "vital_signs_concerns": ["vital sign issues"],
    "location": "location if provided",
    "disaster_type": "earthquake, flood, etc.",
    "num_victims": "number if known",
    "ai_model": "minimax | fallback_keyword"
}
```

---

## 7. PROJECT STRUCTURE

```
hackathon/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application + frontend serving
│   ├── config.py                # Environment configuration
│   ├── models/
│   │   ├── __init__.py
│   │   └── triage.py            # Pydantic data models & enums
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── triage.py            # Triage endpoints (text, voice, TTS)
│   │   └── reports.py           # Report history, stats & PDF endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── triage_engine.py     # Minimax AI + keyword fallback engine
│   │   ├── elevenlabs.py        # ElevenLabs STT & TTS integration
│   │   ├── report_store.py      # In-memory thread-safe report storage
│   │   └── pdf_generator.py     # Playwright PDF generation service
│   ├── static/
│   │   ├── index.html           # Frontend HTML
│   │   ├── style.css            # Frontend styles (dark theme)
│   │   └── app.js               # Frontend JavaScript logic
│   └── templates/
│       └── report.html           # Jinja2 HTML template for PDF reports
├── tests/
│   └── test_integration.py       # 54-assertion integration test suite
├── reports/                       # Generated PDF files
├── venv/                          # Python virtual environment
├── requirements.txt               # Python dependencies
├── .env                           # API keys (not committed)
├── .env.example                   # Template for .env
├── README.md                      # Quick-start documentation
└── PROJECT_REPORT.md              # This report
```

---

## 8. TESTING

### 8.1 Test Suite
The project includes a comprehensive integration test suite with **54 test assertions** across **18 test categories**.

### 8.2 Test Categories & Results

| # | Category | Tests | Result |
|---|----------|-------|--------|
| 1 | Health Check | 3 | PASS |
| 2 | Text Triage — CRITICAL | 13 | PASS |
| 3 | Text Triage — HIGH | 2 | PASS |
| 4 | Text Triage — MODERATE | 2 | PASS |
| 5 | Text Triage — LOW | 2 | PASS |
| 6 | Vulnerability Bump (child) | 1 | PASS |
| 7 | Arabic Language Input | 2 | PASS |
| 8 | Input Validation | 2 | PASS |
| 9 | Report History | 3 | PASS |
| 10 | Report Filtering | 3 | PASS |
| 11 | Single Report Lookup | 3 | PASS |
| 12 | Report Statistics | 3 | PASS |
| 13 | PDF — Single Report | 4 | PASS |
| 14 | PDF — Summary Report | 4 | PASS |
| 15 | Voice — Bad File Type | 1 | PASS |
| 16 | Voice — Empty File | 1 | PASS |
| 17 | TTS — Not Found | 1 | PASS |
| 18 | OpenAPI Documentation | 3 | PASS |
| | **TOTAL** | **54** | **ALL PASS** |

### 8.3 How to Run Tests
```bash
cd /home/ackera/hackathon
source venv/bin/activate
uvicorn app.main:app --port 8000 &
python tests/test_integration.py
```

---

## 9. STEP-BY-STEP BUILD LOG

### Step 1: Project Scaffolding
- Created directory structure (app/, services/, models/, routers/, templates/, tests/, reports/)
- Created requirements.txt with all dependencies
- Created .env.example template
- Installed dependencies in Python virtual environment
- Installed Playwright Chromium browser
- **Result: PASS** — All imports verified

### Step 2: Data Models (Pydantic)
- Created enums: SeverityLevel, InputSource, AIModel
- Created TextTriageRequest with validation (min_length=1)
- Created TriageReport with all 16 fields
- Created ReportHistoryQuery for filtering
- **Result: PASS** — All models validated

### Step 3: Triage Engine
- Built Minimax AI integration with START protocol system prompt
- Built keyword-based fallback with 80+ keywords (English + Arabic)
- Implemented vulnerability detection (child, elderly, pregnant) with severity bumping
- Implemented severity-specific first-aid instructions, actions, and vital sign concerns
- **Result: PASS** — Tested 5 scenarios (CRITICAL, LOW, child bump, Arabic, voice source)

### Step 4: ElevenLabs Integration
- Built async STT function with multi-format support (WAV, MP3, WebM, OGG, M4A)
- Built async TTS function with multilingual v2 model
- Both functions handle missing API keys gracefully (return None)
- **Result: PASS** — Graceful failure tests passed

### Step 5: Report Store
- Built thread-safe in-memory store with asyncio.Lock
- Implemented add, get_all (with filters), get_by_id, count, severity_counts
- Supports filtering by severity and input_source
- Newest-first ordering with pagination (limit/offset)
- **Result: PASS** — All CRUD operations verified

### Step 6: FastAPI Application & Routers
- Built triage router: POST /api/triage/text, POST /api/triage/voice, POST /api/triage/tts/{id}
- Built reports router: GET /api/reports, GET /api/reports/stats, GET /api/reports/{id}
- Added input validation for audio files (type checking, empty file detection)
- Added CORS middleware, health check endpoint
- **Result: PASS** — All 10 endpoints tested

### Step 7: PDF Generation
- Created Jinja2 HTML template with professional styling
- Single-report PDF with severity badge, conditions, instructions, vital signs
- Summary PDF with bar chart and tabular report list
- Playwright headless Chromium rendering
- **Result: PASS** — Both PDFs generated (45KB single, 33KB summary), valid PDF headers

### Step 8: API Key Configuration
- Added Minimax and ElevenLabs API keys to .env
- Fixed Minimax API error detection (HTTP 200 with error in body: status_code 1008)
- System properly falls back to keyword engine when API has insufficient balance
- **Result: PASS** — Error detection and fallback verified

### Step 9: Frontend
- Built responsive dark-themed UI with sidebar navigation
- Four main pages: New Triage, Voice Call, Report History, Dashboard
- Microphone recording with timer, audio file drag-and-drop
- Real-time triage result display with color-coded severity
- Report history with filtering and click-to-view detail modals
- Dashboard with stats cards, bar chart, and recent reports
- PDF download and JSON copy buttons
- **Result: PASS** — Frontend served, all assets load, API integration working

### Step 10: Full Integration Test Suite
- 54 assertions across 18 categories
- **Result: 54/54 PASS — 3 consecutive clean runs**

---

## 10. HOW TO RUN

```bash
# Navigate to project
cd /home/ackera/hackathon

# Activate virtual environment
source venv/bin/activate

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Open in browser
# http://localhost:8000          — Frontend UI
# http://localhost:8000/docs     — Swagger API docs
```

---

## 11. ENVIRONMENT VARIABLES

| Variable | Required | Current Status |
|----------|----------|---------------|
| MINIMAX_API_KEY | For AI triage | Set (insufficient balance — uses fallback) |
| MINIMAX_GROUP_ID | For AI triage | Not required for current API |
| ELEVENLABS_API_KEY | For voice features | Set (free tier restricted) |
| ELEVENLABS_VOICE_ID | For TTS | Set (Rachel voice) |

> The system works fully without API keys using the keyword-based fallback engine.

---

## 12. KNOWN LIMITATIONS

1. **Minimax AI**: Account has insufficient balance — system uses keyword fallback
2. **ElevenLabs**: Free tier blocked due to unusual activity — voice endpoints return clear error messages
3. **Storage**: In-memory only — reports are lost on server restart (production would use a database)
4. **Authentication**: No user authentication (would be needed for production)
5. **Rate Limiting**: Not implemented (would be needed for production)

---

## 13. FUTURE IMPROVEMENTS

1. Add database persistence (PostgreSQL/SQLite)
2. Add WebSocket for real-time triage updates to dispatcher dashboard
3. Add user authentication and role-based access
4. Add geolocation mapping of incidents
5. Add integration with emergency dispatch systems (CAD)
6. Add multi-language support beyond English and Arabic
7. Add automated re-triage based on updated information
8. Mobile application for field responders

---

*Report generated on: February 14, 2026*
*2020 AI Agent v1.0.0*
