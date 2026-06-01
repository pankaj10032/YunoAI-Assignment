# Multi-stage build for production-ready AI Orchestrator
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY requirements.txt .
COPY backend/requirements.txt backend_requirements.txt

# Install Python dependencies for both frontend and backend
RUN pip install --no-cache-dir --user \
    -r requirements.txt \
    -r backend_requirements.txt

# Production stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . /app

# Create data directory for SQLite
RUN mkdir -p /app/data

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose ports (Gradio on 7860, FastAPI on 8000)
EXPOSE 7860 8000

# Health check for FastAPI backend
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_NAME="AI Orchestrator" \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Run the application (Gradio will start FastAPI in background)
CMD ["python", "app.py"]