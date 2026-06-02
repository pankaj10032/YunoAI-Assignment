"""
Custom AI Orchestrator Docker entrypoint.
This file starts the FastAPI backend directly and removes the Gradio frontend.
"""

import os
import sys
from pathlib import Path

# Add backend to Python path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

if __name__ == "__main__":
    import uvicorn

    try:
        from backend.app.app import app
    except Exception as exc:
        print(f"❌ Failed to import backend app: {exc}")
        raise

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info")

    print("🚀 Starting AI Orchestrator backend")
    print(f"📡 Listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level=log_level)
