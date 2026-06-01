#!/usr/bin/env python3
"""
Startup script for AI Orchestrator on Hugging Face Spaces
Handles initialization and environment setup
"""

import os
import sys
import subprocess

def setup_environment():
    """Setup the environment for the AI Orchestrator"""
    
    # Create data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"✅ Created data directory: {data_dir}")
    
    # Set default environment variables if not set
    env_defaults = {
        'APP_NAME': 'AI Orchestrator',
        'ENVIRONMENT': 'production',
        'LOG_LEVEL': 'INFO',
        'DATABASE_URL': 'sqlite:///./data/ai_orchestrator.db',
        'LLM_PROVIDER': 'openai',
        'OPENAI_MODEL': 'gpt-4o-mini',
        'MAX_AGENT_ITERATIONS': '5',
        'DEFAULT_AGENT_TIMEOUT_SECONDS': '120',
        'CORS_ORIGINS': '*',
        'ENABLE_TELEGRAM_POLLING': 'false'
    }
    
    for key, default_value in env_defaults.items():
        if not os.getenv(key):
            os.environ[key] = default_value
            print(f"🔧 Set {key}={default_value}")
    
    print("✅ Environment setup complete")

def main():
    """Main startup function"""
    print("🚀 AI Orchestrator Startup")
    print("=" * 50)
    
    # Setup environment
    setup_environment()
    
    # Start the main application
    print("🎯 Starting main application...")
    try:
        # Import and run the main app
        from app import create_interface
        import threading
        import uvicorn
        import time
        
        # Start FastAPI server in background
        def start_fastapi():
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
                from backend.app.app import app
                uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
            except Exception as e:
                print(f"❌ FastAPI startup failed: {e}")
        
        print("📡 Starting FastAPI backend...")
        fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
        fastapi_thread.start()
        
        # Wait for backend to start
        time.sleep(3)
        
        # Start Gradio frontend
        print("🎨 Starting Gradio frontend...")
        demo = create_interface()
        demo.launch(
            server_name="0.0.0.0",
            server_port=7860,
            show_api=False,
            share=False
        )
        
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()