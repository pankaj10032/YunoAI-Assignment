# Deployment Guide

This guide covers deploying the AI Orchestrator application using Docker and Kubernetes.

## Table of Contents

- [Docker Deployment](#docker-deployment)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [Production Considerations](#production-considerations)

## Docker Deployment

### Building the Image

```bash
# Build the Docker image
docker build -t ai-orchestrator:latest .

# Build with a specific tag
docker build -t ai-orchestrator:v1.0.0 .
```

### Running the Container

```bash
# Run with environment variables
docker run -d \
  --name ai-orchestrator \
  -p 8000:8000 \
  -e OPENAI_API_KEY=your-api-key \
  -e LLM_PROVIDER=openai \
  -e DATABASE_URL=sqlite:///./data/ai_orchestrator.db \
  -v $(pwd)/data:/app/data \
  ai-orchestrator:latest

# Check logs
docker logs -f ai-orchestrator

# Check health
curl http://localhost:8000/health
```

### Using Environment File

```bash
# Create .env file with your configuration
cp .env.example .env
# Edit .env with your values

# Run with env file
docker run -d \
  --name ai-orchestrator \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ai-orchestrator:latest
```

## Docker Compose Deployment

Docker Compose provides an easy way to run the application with all dependencies.

### Quick Start

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### Configuration

Edit `docker-compose.yaml` or create a `.env` file:

```env
OPENAI_API_KEY=your-api-key-here
TELEGRAM_BOT_TOKEN=your-telegram-token  # Optional
LLM_PROVIDER=openai  # or ollama
```

### Using Ollama (Local LLM)

The docker-compose file includes an optional Ollama service:

```bash
# Start with Ollama
docker-compose up -d

# Pull a model in Ollama
docker-compose exec ollama ollama pull llama3.1

# Set LLM_PROVIDER to ollama in your .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.1
```

## Kubernetes Deployment

For production deployments, Kubernetes provides scalability, high availability, and advanced orchestration.

### Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- Docker image pushed to a registry

### Step 1: Build and Push Image

```bash
# Tag for your registry
docker tag ai-orchestrator:latest your-registry/ai-orchestrator:v1.0.0

# Push to registry
docker push your-registry/ai-orchestrator:v1.0.0
```

### Step 2: Configure Secrets

Create a secrets file or edit `k8s/deployment.yaml`:

```bash
# Create secret from command line
kubectl create secret generic ai-orchestrator-secrets \
  --from-literal=OPENAI_API_KEY='your-key-here' \
  --namespace=ai-orchestrator \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 3: Deploy

```bash
# Apply deployment
kubectl apply -f k8s/deployment.yaml

# Check status
kubectl get pods -n ai-orchestrator

# Check logs
kubectl logs -n ai-orchestrator -l app=ai-orchestrator -f
```

### Step 4: Expose Service (Optional)

```bash
# Apply ingress
kubectl apply -f k8s/ingress.yaml

# Or use port-forward for testing
kubectl port-forward -n ai-orchestrator svc/ai-orchestrator 8000:8000
```

See [k8s/README.md](k8s/README.md) for detailed Kubernetes documentation.

## Configuration

### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required if using OpenAI) | - |
| `LLM_PROVIDER` | LLM provider: `openai` or `ollama` | `openai` |
| `DATABASE_URL` | Database connection string | `sqlite:///./data/ai_orchestrator.db` |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | `AI Orchestrator` |
| `ENVIRONMENT` | Environment: `development`, `production` | `development` |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o-mini` |
| `OLLAMA_BASE_URL` | Ollama API base URL | `http://ollama:11434` |
| `OLLAMA_MODEL` | Ollama model to use | `llama3.1` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for integration | - |
| `TELEGRAM_WEBHOOK_URL` | Telegram webhook URL | - |
| `ENABLE_TELEGRAM_POLLING` | Enable Telegram polling mode | `false` |
| `FRONTEND_URL` | Frontend application URL | `http://localhost:3000` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `http://localhost:3000` |
| `MAX_AGENT_ITERATIONS` | Maximum agent iterations | `5` |
| `DEFAULT_AGENT_TIMEOUT_SECONDS` | Default agent timeout | `120` |
| `SCHEDULER_MAX_CONCURRENT_JOBS` | Max concurrent scheduled jobs | `5` |

## Production Considerations

### 1. Database

**SQLite Limitations**: SQLite is suitable for development but has limitations in production:
- Single writer at a time
- No network access
- Limited concurrency

**Recommended for Production**: PostgreSQL or MySQL

```yaml
# Example PostgreSQL configuration
DATABASE_URL=postgresql://user:password@postgres:5432/ai_orchestrator
```

### 2. Security

**API Keys**:
- Never commit API keys to version control
- Use Kubernetes Secrets or external secret management
- Rotate keys regularly

**Container Security**:
- Run as non-root user (already configured)
- Scan images for vulnerabilities
- Keep base images updated

**Network Security**:
- Use NetworkPolicies in Kubernetes
- Enable TLS/SSL for external access
- Implement rate limiting

### 3. Scalability

**Horizontal Scaling**:
- Use HorizontalPodAutoscaler (configured in k8s/deployment.yaml)
- Configure based on CPU/memory metrics
- Consider custom metrics (request rate, queue depth)

**Resource Limits**:
- Set appropriate CPU/memory requests and limits
- Monitor actual usage and adjust
- Use PodDisruptionBudget for availability

### 4. Monitoring and Observability

**Logging**:
- Application logs are in JSON format
- Centralize logs (ELK, Loki, CloudWatch)
- Set appropriate log levels

**Metrics**:
- Expose Prometheus metrics
- Monitor key metrics: request rate, latency, errors
- Set up alerts for critical issues

**Tracing**:
- Implement distributed tracing
- Use correlation IDs (already implemented)
- Track request flows across services

### 5. High Availability

**Multiple Replicas**:
- Run at least 2 replicas (configured)
- Distribute across availability zones
- Use PodDisruptionBudget

**Health Checks**:
- Liveness, readiness, and startup probes configured
- Monitor health check failures
- Set appropriate timeouts

**Backup and Recovery**:
- Regular database backups
- Test restore procedures
- Document recovery processes

### 6. Performance Optimization

**Caching**:
- Implement response caching where appropriate
- Use Redis for distributed caching
- Cache LLM responses when possible

**Connection Pooling**:
- Configure database connection pools
- Tune pool sizes based on load
- Monitor connection usage

**Async Processing**:
- Use background tasks for long-running operations
- Implement job queues (already using background tasks)
- Monitor queue depths

### 7. Cost Optimization

**LLM Costs**:
- Monitor API usage
- Implement rate limiting
- Use appropriate model sizes
- Consider caching responses

**Infrastructure**:
- Right-size resource requests/limits
- Use spot instances where appropriate
- Implement auto-scaling policies

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs ai-orchestrator

# Common issues:
# - Missing environment variables
# - Invalid API keys
# - Port already in use
```

### Health Check Failing

```bash
# Check health endpoint
curl http://localhost:8000/health

# Check application logs
docker logs ai-orchestrator

# Verify environment variables
docker exec ai-orchestrator env | grep -E 'OPENAI|LLM'
```

### Database Issues

```bash
# Check database file permissions
docker exec ai-orchestrator ls -la /app/data/

# Verify database URL
docker exec ai-orchestrator env | grep DATABASE_URL

# Check SQLite database
docker exec -it ai-orchestrator sqlite3 /app/data/ai_orchestrator.db ".tables"
```

### Kubernetes Pod Issues

```bash
# Check pod status
kubectl get pods -n ai-orchestrator

# Describe pod
kubectl describe pod <pod-name> -n ai-orchestrator

# Check logs
kubectl logs <pod-name> -n ai-orchestrator

# Check events
kubectl get events -n ai-orchestrator --sort-by='.lastTimestamp'
```

## Support

For additional help:
- Check the [k8s/README.md](k8s/README.md) for Kubernetes-specific documentation
- Review application logs for error messages
- Consult the main project documentation
- Open an issue in the repository

## Next Steps

After deployment:
1. Verify health endpoint: `http://your-domain/health`
2. Access API documentation: `http://your-domain/docs`
3. Configure agents and workflows
4. Set up monitoring and alerts
5. Implement backup procedures
6. Document your deployment configuration
