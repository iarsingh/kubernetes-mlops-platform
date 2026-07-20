# =============================================================================
# Developer entrypoints. Run `make help` for the list.
# =============================================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

# Config (override on the CLI, e.g. `make train MLFLOW_TRACKING_URI=...`)
PY               ?= python
VENV             ?= .venv
NAMESPACE        ?= mlops
RELEASE          ?= ml-api
IMAGE_REPO       ?= ghcr.io/iarsingh/kubernetes-mlops-platform
TAG              ?= dev
MLFLOW_TRACKING_URI ?= sqlite:///mlflow.db

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- Python / local dev ---------------------------------------------------
.PHONY: venv
venv: ## Create a virtualenv and install deps
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

.PHONY: train
train: ## Train + register the model (uses MLFLOW_TRACKING_URI)
	MLFLOW_TRACKING_URI=$(MLFLOW_TRACKING_URI) $(PY) -m src.training.train

.PHONY: evaluate
evaluate: ## Evaluate the staging model and gate promotion to champion
	MLFLOW_TRACKING_URI=$(MLFLOW_TRACKING_URI) $(PY) -m src.training.evaluate

.PHONY: serve
serve: ## Run the inference API locally with uvicorn
	uvicorn src.inference.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: test
test: ## Run the pytest suite with coverage
	pytest --cov=src --cov-report=term-missing

.PHONY: lint
lint: ## Lint + format check with ruff
	ruff check src tests
	ruff format --check src tests

.PHONY: fmt
fmt: ## Auto-format with ruff
	ruff check --fix src tests
	ruff format src tests

# ---- Local stack ----------------------------------------------------------
.PHONY: compose-up
compose-up: ## Bring up the full local stack (postgres, minio, mlflow, api)
	docker compose up --build -d

.PHONY: compose-down
compose-down: ## Tear down the local stack (keeps volumes)
	docker compose down

.PHONY: compose-clean
compose-clean: ## Tear down the local stack and delete volumes
	docker compose down -v

# ---- Docker ---------------------------------------------------------------
.PHONY: docker-build
docker-build: ## Build both container images
	docker build -f docker/Dockerfile.inference -t $(IMAGE_REPO)/ml-api:$(TAG) .
	docker build -f docker/Dockerfile.training  -t $(IMAGE_REPO)/training:$(TAG) .

# ---- Helm / Kubernetes ----------------------------------------------------
.PHONY: helm-lint
helm-lint: ## Lint the Helm chart
	helm lint helm/ml-api

.PHONY: helm-template
helm-template: ## Render the chart to stdout
	helm template $(RELEASE) helm/ml-api

.PHONY: helm-install
helm-install: ## Install/upgrade the chart into the cluster
	helm upgrade --install $(RELEASE) helm/ml-api \
		--namespace $(NAMESPACE) --create-namespace \
		--set image.repository=$(IMAGE_REPO)/ml-api --set image.tag=$(TAG) \
		--wait --atomic

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall the release
	helm uninstall $(RELEASE) --namespace $(NAMESPACE)

.PHONY: port-forward
port-forward: ## Port-forward the service to localhost:8080
	kubectl port-forward svc/$(RELEASE) 8080:80 --namespace $(NAMESPACE)

# ---- Terraform ------------------------------------------------------------
.PHONY: tf-validate
tf-validate: ## terraform fmt check + init + validate
	terraform -chdir=terraform fmt -check -recursive
	terraform -chdir=terraform init -backend=false
	terraform -chdir=terraform validate
