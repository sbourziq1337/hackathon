"""
Configuration module — loads environment variables from .env file.
All API keys and settings are centralised here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Minimax AI ──────────────────────────────────────────────
MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID: str = os.getenv("MINIMAX_GROUP_ID", "")
MINIMAX_MODEL: str = "MiniMax-Text-01"
MINIMAX_API_URL: str = "https://api.minimax.chat/v1/text/chatcompletion_v2"

# ── ElevenLabs ──────────────────────────────────────────────
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_STT_URL: str = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_TTS_URL: str = (
    f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
)

# ── Twilio (Phone Calls) ───────────────────────────────────
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

# ── Groq AI (free alternative) ────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"

# ── Telegram Bot ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Dashboard Auth ──────────────────────────────────────────
DASHBOARD_USERNAME: str = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "emergency2024")
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# ── App Settings ────────────────────────────────────────────
APP_TITLE: str = "2020 AI Agent"
APP_VERSION: str = "1.0.0"
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
APP_ENV: str = os.getenv("APP_ENV", "development")
REPORTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
