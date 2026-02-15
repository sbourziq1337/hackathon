"""
2020 AI Agent — Entry Point.

Run with:  python main.py
Or:        uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import uvicorn
from app.config import APP_HOST, APP_PORT, APP_ENV

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=(APP_ENV == "development"),
        log_level="info",
    )
