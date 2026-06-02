# Stage 1: Build the frontend (React/Vite)
FROM node:20-slim as frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Set API URL to empty so it defaults to relative path in production
ENV VITE_API_BASE_URL=""
RUN npm run build

# Stage 2: Build the Python backend
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies for the app
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /usr/local /usr/local

# Make sure scripts from system site are usable
ENV PATH=/usr/local/bin:$PATH \
    PYTHONPATH=/usr/local/lib/python3.11/site-packages:$PYTHONPATH

# Copy application code
COPY . /app

# Copy built frontend assets to serve them via FastAPI
COPY --from=frontend-builder /frontend/dist /app/static

# Create data directory for SQLite
RUN mkdir -p /app/data

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose FastAPI backend port (Hugging Face default)
EXPOSE 7860

# Health check for FastAPI backend on port 7860
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_NAME="AI Orchestrator" \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    PORT=7860 \
    CORS_ORIGINS="*" \
    FRONTEND_URL="https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator"

# Run the backend application
CMD ["python", "app.py"]