.PHONY: help build push deploy deploy-k8s clean test docker-run docker-stop logs

# Configuration
IMAGE_NAME ?= ai-orchestrator
IMAGE_TAG ?= latest
REGISTRY ?=
NAMESPACE ?= ai-orchestrator

# Conditional registry prefix
ifdef REGISTRY
	FULL_IMAGE = $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
else
	FULL_IMAGE = $(IMAGE_NAME):$(IMAGE_TAG)
endif

help: ## Show this help message
	@echo "AI Orchestrator - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Environment Variables:"
	@echo "  IMAGE_NAME    Docker image name (default: ai-orchestrator)"
	@echo "  IMAGE_TAG     Docker image tag (default: latest)"
	@echo "  REGISTRY      Docker registry (optional)"
	@echo "  NAMESPACE     Kubernetes namespace (default: ai-orchestrator)"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make REGISTRY=docker.io/username push"
	@echo "  make deploy-k8s"

build: ## Build Docker image
	@echo "Building Docker image: $(FULL_IMAGE)"
	docker build -t $(FULL_IMAGE) .
	@echo "Build complete!"

push: ## Push Docker image to registry
ifndef REGISTRY
	@echo "Error: REGISTRY is not set. Use: make REGISTRY=your-registry push"
	@exit 1
endif
	@echo "Pushing image: $(FULL_IMAGE)"
	docker push $(FULL_IMAGE)
	@echo "Push complete!"

build-push: build push ## Build and push Docker image

docker-run: ## Run container locally with docker-compose
	@echo "Starting AI Orchestrator with docker-compose..."
	docker-compose up -d
	@echo "Container started! Check logs with: make logs"

docker-stop: ## Stop local docker-compose containers
	@echo "Stopping containers..."
	docker-compose down
	@echo "Containers stopped!"

logs: ## Show docker-compose logs
	docker-compose logs -f

test: ## Run tests
	@echo "Running tests..."
	cd backend && pytest
	@echo "Tests complete!"

deploy-k8s: ## Deploy to Kubernetes
	@echo "Deploying to Kubernetes..."
	@if [ -z "$(OPENAI_API_KEY)" ]; then \
		echo "Error: OPENAI_API_KEY is not set"; \
		exit 1; \
	fi
	@kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@kubectl create secret generic ai-orchestrator-secrets \
		--from-literal=OPENAI_API_KEY="$(OPENAI_API_KEY)" \
		--from-literal=TELEGRAM_BOT_TOKEN="$(TELEGRAM_BOT_TOKEN)" \
		--from-literal=TELEGRAM_WEBHOOK_URL="$(TELEGRAM_WEBHOOK_URL)" \
		--namespace=$(NAMESPACE) \
		--dry-run=client -o yaml | kubectl apply -f -
	@if [ -n "$(REGISTRY)" ]; then \
		sed "s|image: ai-orchestrator:latest|image: $(FULL_IMAGE)|g" k8s/deployment.yaml | kubectl apply -f -; \
	else \
		kubectl apply -f k8s/deployment.yaml; \
	fi
	@echo "Deployment complete!"

deploy-ingress: ## Deploy ingress to Kubernetes
	@echo "Deploying ingress..."
	kubectl apply -f k8s/ingress.yaml
	@echo "Ingress deployed!"

undeploy-k8s: ## Remove Kubernetes deployment
	@echo "Removing Kubernetes deployment..."
	kubectl delete -f k8s/deployment.yaml --ignore-not-found=true
	kubectl delete -f k8s/ingress.yaml --ignore-not-found=true
	@echo "Deployment removed!"

k8s-status: ## Show Kubernetes deployment status
	@echo "Deployment Status:"
	@echo ""
	@echo "Pods:"
	@kubectl get pods -n $(NAMESPACE)
	@echo ""
	@echo "Services:"
	@kubectl get svc -n $(NAMESPACE)
	@echo ""
	@echo "Ingress:"
	@kubectl get ingress -n $(NAMESPACE) 2>/dev/null || echo "No ingress found"
	@echo ""
	@echo "HPA:"
	@kubectl get hpa -n $(NAMESPACE)

k8s-logs: ## Show Kubernetes pod logs
	kubectl logs -n $(NAMESPACE) -l app=ai-orchestrator --tail=100 -f

k8s-shell: ## Open shell in Kubernetes pod
	kubectl exec -it -n $(NAMESPACE) deployment/ai-orchestrator -- /bin/bash

k8s-port-forward: ## Port forward to Kubernetes service
	@echo "Port forwarding to http://localhost:8000"
	kubectl port-forward -n $(NAMESPACE) svc/ai-orchestrator 8000:8000

k8s-restart: ## Restart Kubernetes deployment
	kubectl rollout restart deployment/ai-orchestrator -n $(NAMESPACE)
	kubectl rollout status deployment/ai-orchestrator -n $(NAMESPACE)

clean: ## Clean up local Docker resources
	@echo "Cleaning up..."
	docker-compose down -v
	@echo "Cleanup complete!"

clean-all: clean ## Clean up all Docker images and containers
	@echo "Removing Docker images..."
	docker rmi $(FULL_IMAGE) 2>/dev/null || true
	@echo "All cleaned up!"

dev: ## Start development environment
	@echo "Starting development environment..."
	docker-compose up -d
	@echo "Development environment started!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"

health-check: ## Check application health
	@echo "Checking application health..."
	@curl -f http://localhost:8000/health || echo "Health check failed!"

# Full deployment workflow
deploy: build push deploy-k8s ## Full deployment: build, push, and deploy to Kubernetes
	@echo "Full deployment complete!"
	@echo "Waiting for deployment to be ready..."
	@kubectl rollout status deployment/ai-orchestrator -n $(NAMESPACE)
	@make k8s-status
