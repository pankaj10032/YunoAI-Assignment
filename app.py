"""
Gradio Interface for AI Orchestrator
This file serves as the entry point for the Hugging Face Space
"""

import gradio as gr
import os
import sys

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def create_interface():
    """Create the Gradio interface for the AI Orchestrator"""
    
    with gr.Blocks(title="AI Orchestrator", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # 🤖 AI Orchestrator
        
        A powerful system for creating, configuring, and orchestrating collaborative AI agents.
        
        ## Features
        - **Agent Management**: Create and configure AI agents
        - **Workflow Orchestration**: Design complex multi-agent workflows
        - **Real-time Monitoring**: Track agent execution and communication
        - **Telegram Integration**: Connect agents to Telegram
        
        ## API Documentation
        The FastAPI backend is available at `/api/docs` for full API documentation.
        """)
        
        with gr.Tab("Quick Start"):
            gr.Markdown("""
            ### Getting Started
            
            1. **Create an Agent**: Define your AI agent with specific capabilities
            2. **Design a Workflow**: Connect multiple agents in a workflow
            3. **Execute**: Run your workflow and monitor results
            4. **Integrate**: Connect to external channels like Telegram
            
            ### API Endpoints
            
            - `GET /health` - Health check
            - `POST /api/agents` - Create a new agent
            - `GET /api/agents` - List all agents
            - `POST /api/workflows` - Create a workflow
            - `POST /api/workflows/{id}/run` - Execute a workflow
            
            ### Environment Variables
            
            Configure the following environment variables:
            - `OPENAI_API_KEY` - Your OpenAI API key
            - `LLM_PROVIDER` - Choose between 'openai' or 'ollama'
            - `TELEGRAM_BOT_TOKEN` - Optional Telegram bot token
            """)
        
        with gr.Tab("API Explorer"):
            gr.Markdown("""
            ### Interactive API Documentation
            
            Visit the following endpoints for interactive API documentation:
            
            - **Swagger UI**: `/docs`
            - **ReDoc**: `/redoc`
            
            ### Example: Create an Agent
            
            ```bash
            curl -X POST "https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator/api/agents" \\
              -H "Content-Type: application/json" \\
              -d '{
                "name": "Research Assistant",
                "model": "gpt-4o-mini",
                "system_prompt": "You are a helpful research assistant.",
                "channels": ["api"]
              }'
            ```
            
            ### Example: Execute an Agent
            
            ```bash
            curl -X POST "https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator/api/agents/1/execute" \\
              -H "Content-Type: application/json" \\
              -d '{
                "task_description": "Research the latest AI trends"
              }'
            ```
            """)
        
        with gr.Tab("Configuration"):
            gr.Markdown("""
            ### Configuration Guide
            
            #### LLM Provider Setup
            
            **OpenAI**:
            ```bash
            export OPENAI_API_KEY="your-api-key"
            export LLM_PROVIDER="openai"
            export OPENAI_MODEL="gpt-4o-mini"
            ```
            
            **Ollama** (Local):
            ```bash
            export LLM_PROVIDER="ollama"
            export OLLAMA_BASE_URL="http://localhost:11434"
            export OLLAMA_MODEL="llama3.1"
            ```
            
            #### Telegram Integration
            
            1. Create a bot with [@BotFather](https://t.me/botfather)
            2. Get your bot token
            3. Set environment variable:
            ```bash
            export TELEGRAM_BOT_TOKEN="your-bot-token"
            ```
            
            #### Database Configuration
            
            ```bash
            export DATABASE_URL="sqlite:///./data/ai_orchestrator.db"
            ```
            """)
        
        with gr.Tab("About"):
            gr.Markdown("""
            ### About AI Orchestrator
            
            AI Orchestrator is a comprehensive platform for building and managing collaborative AI agent systems.
            
            **Key Capabilities**:
            - Multi-agent workflow orchestration
            - Real-time agent communication
            - Persistent memory and state management
            - Channel integrations (Telegram, API, WebSocket)
            - Audit trail and observability
            - Rate limiting and quota management
            
            **Technology Stack**:
            - **Backend**: FastAPI, Python 3.11+
            - **Database**: SQLAlchemy with SQLite/PostgreSQL
            - **LLM Integration**: OpenAI, Ollama
            - **Agent Framework**: CrewAI
            - **Frontend**: Gradio
            
            **Links**:
            - [GitHub Repository](https://github.com/yourusername/ai-orchestrator)
            - [Documentation](https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator)
            - [API Docs](/docs)
            
            **Version**: 0.1.0
            """)
    
    return demo

if __name__ == "__main__":
    # Create and launch the interface
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_api=False
    )