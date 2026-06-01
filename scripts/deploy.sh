#!/bin/bash

# AI Orchestrator Deployment Script
# This script helps deploy the AI Orchestrator to Kubernetes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="ai-orchestrator"
IMAGE_NAME="ai-orchestrator"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    # Check docker
    if ! command -v docker &> /dev/null; then
        log_error "docker is not installed. Please install docker first."
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please configure kubectl."
        exit 1
    fi
    
    log_info "Prerequisites check passed!"
}

build_image() {
    log_info "Building Docker image..."
    
    if [ -n "$REGISTRY" ]; then
        FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    else
        FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    
    docker build -t "$FULL_IMAGE" .
    
    log_info "Image built: $FULL_IMAGE"
}

push_image() {
    if [ -z "$REGISTRY" ]; then
        log_warn "No registry specified. Skipping image push."
        log_warn "Set REGISTRY environment variable to push to a registry."
        return
    fi
    
    log_info "Pushing image to registry..."
    
    FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    docker push "$FULL_IMAGE"
    
    log_info "Image pushed: $FULL_IMAGE"
}

check_secrets() {
    log_info "Checking for required secrets..."
    
    if [ -z "$OPENAI_API_KEY" ]; then
        log_error "OPENAI_API_KEY environment variable is not set."
        log_error "Please set it before deploying: export OPENAI_API_KEY='your-key'"
        exit 1
    fi
    
    log_info "Secrets check passed!"
}

create_namespace() {
    log_info "Creating namespace..."
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_warn "Namespace $NAMESPACE already exists."
    else
        kubectl create namespace "$NAMESPACE"
        log_info "Namespace $NAMESPACE created."
    fi
}

create_secrets() {
    log_info "Creating Kubernetes secrets..."
    
    kubectl create secret generic ai-orchestrator-secrets \
        --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
        --from-literal=TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" \
        --from-literal=TELEGRAM_WEBHOOK_URL="${TELEGRAM_WEBHOOK_URL:-}" \
        --namespace="$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_info "Secrets created/updated."
}

update_deployment_image() {
    log_info "Updating deployment image reference..."
    
    if [ -n "$REGISTRY" ]; then
        FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    else
        FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    
    # Create temporary file with updated image
    sed "s|image: ai-orchestrator:latest|image: $FULL_IMAGE|g" k8s/deployment.yaml > /tmp/deployment-updated.yaml
    
    log_info "Image reference updated to: $FULL_IMAGE"
}

deploy_application() {
    log_info "Deploying application to Kubernetes..."
    
    if [ -f /tmp/deployment-updated.yaml ]; then
        kubectl apply -f /tmp/deployment-updated.yaml
        rm /tmp/deployment-updated.yaml
    else
        kubectl apply -f k8s/deployment.yaml
    fi
    
    log_info "Application deployed!"
}

deploy_ingress() {
    if [ -f k8s/ingress.yaml ]; then
        log_info "Deploying ingress..."
        kubectl apply -f k8s/ingress.yaml
        log_info "Ingress deployed!"
    else
        log_warn "Ingress file not found. Skipping ingress deployment."
    fi
}

wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    kubectl rollout status deployment/ai-orchestrator -n "$NAMESPACE" --timeout=300s
    
    log_info "Deployment is ready!"
}

show_status() {
    log_info "Deployment status:"
    echo ""
    
    echo "Pods:"
    kubectl get pods -n "$NAMESPACE"
    echo ""
    
    echo "Services:"
    kubectl get svc -n "$NAMESPACE"
    echo ""
    
    echo "Ingress:"
    kubectl get ingress -n "$NAMESPACE" 2>/dev/null || echo "No ingress found"
    echo ""
    
    echo "HPA:"
    kubectl get hpa -n "$NAMESPACE"
    echo ""
}

show_logs() {
    log_info "Recent logs:"
    kubectl logs -n "$NAMESPACE" -l app=ai-orchestrator --tail=50
}

show_help() {
    cat << EOF
AI Orchestrator Deployment Script

Usage: $0 [OPTIONS]

Options:
    --build-only        Only build the Docker image
    --push-only         Only push the Docker image (requires --build-only first)
    --deploy-only       Only deploy to Kubernetes (skip build/push)
    --skip-ingress      Skip ingress deployment
    --show-logs         Show application logs after deployment
    --help              Show this help message

Environment Variables:
    REGISTRY            Docker registry (e.g., docker.io/username)
    IMAGE_TAG           Image tag (default: latest)
    OPENAI_API_KEY      OpenAI API key (required)
    TELEGRAM_BOT_TOKEN  Telegram bot token (optional)
    TELEGRAM_WEBHOOK_URL Telegram webhook URL (optional)

Examples:
    # Full deployment
    export OPENAI_API_KEY='your-key'
    export REGISTRY='docker.io/username'
    $0

    # Build and push only
    export REGISTRY='docker.io/username'
    $0 --build-only

    # Deploy only (image already pushed)
    export OPENAI_API_KEY='your-key'
    $0 --deploy-only

    # Deploy with logs
    export OPENAI_API_KEY='your-key'
    $0 --show-logs

EOF
}

# Main script
main() {
    local BUILD_ONLY=false
    local PUSH_ONLY=false
    local DEPLOY_ONLY=false
    local SKIP_INGRESS=false
    local SHOW_LOGS=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build-only)
                BUILD_ONLY=true
                shift
                ;;
            --push-only)
                PUSH_ONLY=true
                shift
                ;;
            --deploy-only)
                DEPLOY_ONLY=true
                shift
                ;;
            --skip-ingress)
                SKIP_INGRESS=true
                shift
                ;;
            --show-logs)
                SHOW_LOGS=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    log_info "Starting AI Orchestrator deployment..."
    echo ""
    
    check_prerequisites
    
    if [ "$BUILD_ONLY" = true ]; then
        build_image
        log_info "Build complete! Use --push-only to push the image."
        exit 0
    fi
    
    if [ "$PUSH_ONLY" = true ]; then
        push_image
        log_info "Push complete!"
        exit 0
    fi
    
    if [ "$DEPLOY_ONLY" = false ]; then
        build_image
        push_image
    fi
    
    check_secrets
    create_namespace
    create_secrets
    update_deployment_image
    deploy_application
    
    if [ "$SKIP_INGRESS" = false ]; then
        deploy_ingress
    fi
    
    wait_for_deployment
    show_status
    
    if [ "$SHOW_LOGS" = true ]; then
        show_logs
    fi
    
    echo ""
    log_info "Deployment complete!"
    log_info "Access the application:"
    log_info "  - Health check: kubectl port-forward -n $NAMESPACE svc/ai-orchestrator 8000:8000"
    log_info "  - Then visit: http://localhost:8000/health"
    log_info "  - API docs: http://localhost:8000/docs"
}

# Run main function
main "$@"
