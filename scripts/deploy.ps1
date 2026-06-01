# AI Orchestrator Deployment Script for Windows (PowerShell)
# This script helps deploy the AI Orchestrator to Kubernetes

param(
    [switch]$BuildOnly,
    [switch]$PushOnly,
    [switch]$DeployOnly,
    [switch]$SkipIngress,
    [switch]$ShowLogs,
    [switch]$Help
)

# Configuration
$NAMESPACE = "ai-orchestrator"
$IMAGE_NAME = "ai-orchestrator"
$IMAGE_TAG = if ($env:IMAGE_TAG) { $env:IMAGE_TAG } else { "latest" }
$REGISTRY = $env:REGISTRY

# Functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Show-Help {
    @"
AI Orchestrator Deployment Script

Usage: .\deploy.ps1 [OPTIONS]

Options:
    -BuildOnly        Only build the Docker image
    -PushOnly         Only push the Docker image (requires -BuildOnly first)
    -DeployOnly       Only deploy to Kubernetes (skip build/push)
    -SkipIngress      Skip ingress deployment
    -ShowLogs         Show application logs after deployment
    -Help             Show this help message

Environment Variables:
    REGISTRY            Docker registry (e.g., docker.io/username)
    IMAGE_TAG           Image tag (default: latest)
    OPENAI_API_KEY      OpenAI API key (required)
    TELEGRAM_BOT_TOKEN  Telegram bot token (optional)
    TELEGRAM_WEBHOOK_URL Telegram webhook URL (optional)

Examples:
    # Full deployment
    `$env:OPENAI_API_KEY = 'your-key'
    `$env:REGISTRY = 'docker.io/username'
    .\deploy.ps1

    # Build and push only
    `$env:REGISTRY = 'docker.io/username'
    .\deploy.ps1 -BuildOnly

    # Deploy only (image already pushed)
    `$env:OPENAI_API_KEY = 'your-key'
    .\deploy.ps1 -DeployOnly

    # Deploy with logs
    `$env:OPENAI_API_KEY = 'your-key'
    .\deploy.ps1 -ShowLogs

"@
}

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check kubectl
    if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "kubectl is not installed. Please install kubectl first."
        exit 1
    }
    
    # Check docker
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "docker is not installed. Please install docker first."
        exit 1
    }
    
    # Check cluster connection
    try {
        kubectl cluster-info | Out-Null
    }
    catch {
        Write-Error-Custom "Cannot connect to Kubernetes cluster. Please configure kubectl."
        exit 1
    }
    
    Write-Info "Prerequisites check passed!"
}

function Build-Image {
    Write-Info "Building Docker image..."
    
    if ($REGISTRY) {
        $FULL_IMAGE = "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    }
    else {
        $FULL_IMAGE = "${IMAGE_NAME}:${IMAGE_TAG}"
    }
    
    docker build -t $FULL_IMAGE .
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Docker build failed!"
        exit 1
    }
    
    Write-Info "Image built: $FULL_IMAGE"
}

function Push-Image {
    if (-not $REGISTRY) {
        Write-Warn "No registry specified. Skipping image push."
        Write-Warn "Set REGISTRY environment variable to push to a registry."
        return
    }
    
    Write-Info "Pushing image to registry..."
    
    $FULL_IMAGE = "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    docker push $FULL_IMAGE
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Docker push failed!"
        exit 1
    }
    
    Write-Info "Image pushed: $FULL_IMAGE"
}

function Test-Secrets {
    Write-Info "Checking for required secrets..."
    
    if (-not $env:OPENAI_API_KEY) {
        Write-Error-Custom "OPENAI_API_KEY environment variable is not set."
        Write-Error-Custom "Please set it before deploying: `$env:OPENAI_API_KEY = 'your-key'"
        exit 1
    }
    
    Write-Info "Secrets check passed!"
}

function New-Namespace {
    Write-Info "Creating namespace..."
    
    $namespaceExists = kubectl get namespace $NAMESPACE 2>$null
    if ($namespaceExists) {
        Write-Warn "Namespace $NAMESPACE already exists."
    }
    else {
        kubectl create namespace $NAMESPACE
        Write-Info "Namespace $NAMESPACE created."
    }
}

function New-Secrets {
    Write-Info "Creating Kubernetes secrets..."
    
    $telegramToken = if ($env:TELEGRAM_BOT_TOKEN) { $env:TELEGRAM_BOT_TOKEN } else { "" }
    $telegramWebhook = if ($env:TELEGRAM_WEBHOOK_URL) { $env:TELEGRAM_WEBHOOK_URL } else { "" }
    
    kubectl create secret generic ai-orchestrator-secrets `
        --from-literal=OPENAI_API_KEY="$env:OPENAI_API_KEY" `
        --from-literal=TELEGRAM_BOT_TOKEN="$telegramToken" `
        --from-literal=TELEGRAM_WEBHOOK_URL="$telegramWebhook" `
        --namespace=$NAMESPACE `
        --dry-run=client -o yaml | kubectl apply -f -
    
    Write-Info "Secrets created/updated."
}

function Update-DeploymentImage {
    Write-Info "Updating deployment image reference..."
    
    if ($REGISTRY) {
        $FULL_IMAGE = "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    }
    else {
        $FULL_IMAGE = "${IMAGE_NAME}:${IMAGE_TAG}"
    }
    
    # Read deployment file and update image
    $deploymentContent = Get-Content k8s\deployment.yaml -Raw
    $updatedContent = $deploymentContent -replace 'image: ai-orchestrator:latest', "image: $FULL_IMAGE"
    $updatedContent | Set-Content $env:TEMP\deployment-updated.yaml
    
    Write-Info "Image reference updated to: $FULL_IMAGE"
}

function Deploy-Application {
    Write-Info "Deploying application to Kubernetes..."
    
    $tempDeployment = "$env:TEMP\deployment-updated.yaml"
    if (Test-Path $tempDeployment) {
        kubectl apply -f $tempDeployment
        Remove-Item $tempDeployment
    }
    else {
        kubectl apply -f k8s\deployment.yaml
    }
    
    Write-Info "Application deployed!"
}

function Deploy-Ingress {
    if (Test-Path k8s\ingress.yaml) {
        Write-Info "Deploying ingress..."
        kubectl apply -f k8s\ingress.yaml
        Write-Info "Ingress deployed!"
    }
    else {
        Write-Warn "Ingress file not found. Skipping ingress deployment."
    }
}

function Wait-ForDeployment {
    Write-Info "Waiting for deployment to be ready..."
    
    kubectl rollout status deployment/ai-orchestrator -n $NAMESPACE --timeout=300s
    
    Write-Info "Deployment is ready!"
}

function Show-Status {
    Write-Info "Deployment status:"
    Write-Host ""
    
    Write-Host "Pods:"
    kubectl get pods -n $NAMESPACE
    Write-Host ""
    
    Write-Host "Services:"
    kubectl get svc -n $NAMESPACE
    Write-Host ""
    
    Write-Host "Ingress:"
    kubectl get ingress -n $NAMESPACE 2>$null
    if (-not $?) {
        Write-Host "No ingress found"
    }
    Write-Host ""
    
    Write-Host "HPA:"
    kubectl get hpa -n $NAMESPACE
    Write-Host ""
}

function Show-Logs {
    Write-Info "Recent logs:"
    kubectl logs -n $NAMESPACE -l app=ai-orchestrator --tail=50
}

# Main script
function Main {
    if ($Help) {
        Show-Help
        exit 0
    }
    
    Write-Info "Starting AI Orchestrator deployment..."
    Write-Host ""
    
    Test-Prerequisites
    
    if ($BuildOnly) {
        Build-Image
        Write-Info "Build complete! Use -PushOnly to push the image."
        exit 0
    }
    
    if ($PushOnly) {
        Push-Image
        Write-Info "Push complete!"
        exit 0
    }
    
    if (-not $DeployOnly) {
        Build-Image
        Push-Image
    }
    
    Test-Secrets
    New-Namespace
    New-Secrets
    Update-DeploymentImage
    Deploy-Application
    
    if (-not $SkipIngress) {
        Deploy-Ingress
    }
    
    Wait-ForDeployment
    Show-Status
    
    if ($ShowLogs) {
        Show-Logs
    }
    
    Write-Host ""
    Write-Info "Deployment complete!"
    Write-Info "Access the application:"
    Write-Info "  - Health check: kubectl port-forward -n $NAMESPACE svc/ai-orchestrator 8000:8000"
    Write-Info "  - Then visit: http://localhost:8000/health"
    Write-Info "  - API docs: http://localhost:8000/docs"
}

# Run main function
Main
