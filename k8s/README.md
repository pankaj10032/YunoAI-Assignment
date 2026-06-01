# Kubernetes Deployment Guide

This directory contains Kubernetes manifests for deploying the AI Orchestrator application.

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured to access your cluster
- Docker image built and pushed to a registry
- Storage class available for PersistentVolumeClaim

## Files

- `deployment.yaml` - Main deployment configuration including:
  - Namespace
  - ConfigMap for environment variables
  - Secret for sensitive data
  - PersistentVolumeClaim for SQLite database
  - Deployment with 2 replicas
  - Service (ClusterIP)
  - HorizontalPodAutoscaler (2-10 replicas)
  - PodDisruptionBudget

- `ingress.yaml` - Ingress configuration for external access with:
  - WebSocket support
  - CORS configuration
  - Rate limiting
  - SSL/TLS support (optional)

## Quick Start

### 1. Build and Push Docker Image

```bash
# Build the Docker image
docker build -t your-registry/ai-orchestrator:latest .

# Push to your registry
docker push your-registry/ai-orchestrator:latest
```

### 2. Update Configuration

Edit `deployment.yaml` and update:

```yaml
# Update the image reference
image: your-registry/ai-orchestrator:latest

# Update storage class if needed
storageClassName: standard  # Change to your cluster's storage class
```

Edit `k8s/deployment.yaml` Secret section and add your API keys:

```yaml
stringData:
  OPENAI_API_KEY: "your-openai-api-key-here"
  TELEGRAM_BOT_TOKEN: "your-telegram-token-here"  # Optional
  TELEGRAM_WEBHOOK_URL: "https://your-domain.com/api/channels/telegram/webhook"  # Optional
```

### 3. Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f k8s/deployment.yaml

# Optional: Apply ingress if you need external access
kubectl apply -f k8s/ingress.yaml
```

### 4. Verify Deployment

```bash
# Check namespace
kubectl get namespace ai-orchestrator

# Check pods
kubectl get pods -n ai-orchestrator

# Check services
kubectl get svc -n ai-orchestrator

# Check logs
kubectl logs -n ai-orchestrator -l app=ai-orchestrator --tail=100 -f

# Check health
kubectl exec -n ai-orchestrator -it deployment/ai-orchestrator -- curl http://localhost:8000/health
```

## Configuration

### Environment Variables

All non-sensitive configuration is stored in the ConfigMap. To update:

```bash
kubectl edit configmap ai-orchestrator-config -n ai-orchestrator
```

After editing, restart pods:

```bash
kubectl rollout restart deployment/ai-orchestrator -n ai-orchestrator
```

### Secrets

Sensitive data is stored in Kubernetes Secrets. To update:

```bash
# Create/update secret from command line
kubectl create secret generic ai-orchestrator-secrets \
  --from-literal=OPENAI_API_KEY='your-key-here' \
  --from-literal=TELEGRAM_BOT_TOKEN='your-token-here' \
  --namespace=ai-orchestrator \
  --dry-run=client -o yaml | kubectl apply -f -
```

Or edit directly:

```bash
kubectl edit secret ai-orchestrator-secrets -n ai-orchestrator
```

### Database Persistence

The deployment uses a PersistentVolumeClaim for SQLite database storage:

- Default size: 5Gi
- Access mode: ReadWriteOnce
- Storage class: standard (adjust based on your cluster)

To check PVC status:

```bash
kubectl get pvc -n ai-orchestrator
```

## Scaling

### Manual Scaling

```bash
# Scale to 5 replicas
kubectl scale deployment ai-orchestrator --replicas=5 -n ai-orchestrator
```

### Auto-scaling

The HorizontalPodAutoscaler is configured to:
- Min replicas: 2
- Max replicas: 10
- Target CPU: 70%
- Target Memory: 80%

To check HPA status:

```bash
kubectl get hpa -n ai-orchestrator
kubectl describe hpa ai-orchestrator-hpa -n ai-orchestrator
```

## Ingress Configuration

If using the ingress for external access:

1. Update the host in `ingress.yaml`:
   ```yaml
   host: ai-orchestrator.example.com  # Your domain
   ```

2. Configure DNS to point to your ingress controller's external IP:
   ```bash
   kubectl get svc -n ingress-nginx  # Get ingress controller IP
   ```

3. For HTTPS, uncomment the TLS section and configure cert-manager or provide your own certificate.

## Monitoring

### Health Checks

The deployment includes three types of probes:

- **Liveness Probe**: Checks if the container is alive (restarts if failing)
- **Readiness Probe**: Checks if the container is ready to serve traffic
- **Startup Probe**: Gives the application time to start before other probes begin

All probes use the `/health` endpoint.

### Logs

```bash
# View logs from all pods
kubectl logs -n ai-orchestrator -l app=ai-orchestrator --tail=100 -f

# View logs from specific pod
kubectl logs -n ai-orchestrator <pod-name> -f

# View previous container logs (if crashed)
kubectl logs -n ai-orchestrator <pod-name> --previous
```

### Metrics

If Prometheus is configured, metrics are exposed on port 8000 at `/metrics`.

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl get pods -n ai-orchestrator

# Describe pod for events
kubectl describe pod <pod-name> -n ai-orchestrator

# Check logs
kubectl logs <pod-name> -n ai-orchestrator
```

### Database issues

```bash
# Check PVC
kubectl get pvc -n ai-orchestrator
kubectl describe pvc ai-orchestrator-data -n ai-orchestrator

# Access pod shell to check database
kubectl exec -it <pod-name> -n ai-orchestrator -- /bin/bash
ls -la /app/data/
```

### Service not accessible

```bash
# Check service
kubectl get svc -n ai-orchestrator
kubectl describe svc ai-orchestrator -n ai-orchestrator

# Check endpoints
kubectl get endpoints -n ai-orchestrator

# Port forward for testing
kubectl port-forward -n ai-orchestrator svc/ai-orchestrator 8000:8000
# Then access http://localhost:8000/health
```

### Configuration issues

```bash
# Check ConfigMap
kubectl get configmap ai-orchestrator-config -n ai-orchestrator -o yaml

# Check Secrets (values are base64 encoded)
kubectl get secret ai-orchestrator-secrets -n ai-orchestrator -o yaml
```

## Resource Management

### Resource Requests and Limits

Current configuration:
- Requests: 512Mi memory, 250m CPU
- Limits: 2Gi memory, 1000m CPU

Adjust based on your workload:

```bash
kubectl edit deployment ai-orchestrator -n ai-orchestrator
```

### Pod Disruption Budget

A PodDisruptionBudget ensures at least 1 pod is always available during voluntary disruptions (like node drains).

```bash
kubectl get pdb -n ai-orchestrator
```

## Cleanup

To remove all resources:

```bash
# Delete all resources in namespace
kubectl delete namespace ai-orchestrator

# Or delete specific resources
kubectl delete -f k8s/deployment.yaml
kubectl delete -f k8s/ingress.yaml
```

## Production Considerations

1. **Database**: Consider using PostgreSQL or MySQL instead of SQLite for production
2. **Secrets Management**: Use external secret management (e.g., HashiCorp Vault, AWS Secrets Manager)
3. **Monitoring**: Set up Prometheus and Grafana for metrics
4. **Logging**: Configure centralized logging (e.g., ELK stack, Loki)
5. **Backup**: Implement backup strategy for PersistentVolume
6. **Security**: 
   - Use NetworkPolicies to restrict traffic
   - Enable Pod Security Standards
   - Scan images for vulnerabilities
7. **High Availability**: Deploy across multiple availability zones
8. **Resource Limits**: Fine-tune based on actual usage patterns

## Support

For issues or questions, refer to the main project documentation or open an issue in the repository.
