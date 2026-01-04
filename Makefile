.PHONY: setup install login auth enable-api run clean revoke-app-default revoke-user clean-auth help

PYTHON_VERSION := 3.12.11
VENV := .venv
PROJECT_ID ?= $(GOOGLE_CLOUD_PROJECT)
BUCKET ?= $(GOOGLE_CLOUD_BUCKET)
GCLOUD_SDK_ROOT := $(CURDIR)/google-cloud-sdk
GCLOUD := $(GCLOUD_SDK_ROOT)/bin/gcloud

help:
	@echo "Google Cloud Speech-to-Text - Available Commands"
	@echo ""
	@echo "  make setup       - Create venv and install dependencies"
	@echo "  make install     - Install dependencies only"
	@echo "  make login       - Login to Google Cloud"
	@echo "  make auth        - Set application default credentials"
	@echo "  make enable-api  - Enable Speech-to-Text API"
	@echo "  make run         - Run the transcription script"
	@echo "  make clean       - Remove virtual environment"
	@echo "  make clean-auth  - Revoke all stored credentials"
	@echo ""
	@echo "First time setup:"
	@echo "  make setup && make login && make auth && make enable-api"

setup:
	@echo "Creating Python $(PYTHON_VERSION) virtual environment..."
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python $(PYTHON_VERSION) $(VENV); \
		. $(VENV)/bin/activate && uv pip install -r requirements.txt; \
	else \
		python3.12 -m venv $(VENV); \
		. $(VENV)/bin/activate && pip install -r requirements.txt; \
	fi
	@echo ""
	@echo "Setup complete! Activate with: source $(VENV)/bin/activate"

install:
	@. $(VENV)/bin/activate && pip install -r requirements.txt

login:
	@echo "Logging into Google Cloud..."
	$(GCLOUD) auth login

auth:
	@echo "Setting application default credentials..."
	$(GCLOUD) auth application-default login

enable-api:
	@echo "Enabling Speech-to-Text API..."
	$(GCLOUD) services enable speech.googleapis.com

run:
	@if [ -z "$(PROJECT_ID)" ]; then \
		echo "Error: GOOGLE_CLOUD_PROJECT not set"; \
		echo "Run: export GOOGLE_CLOUD_PROJECT=your-project-id"; \
		exit 1; \
	fi
	@if [ -z "$(BUCKET)" ]; then \
		echo "Error: GOOGLE_CLOUD_BUCKET not set"; \
		echo "Run: export GOOGLE_CLOUD_BUCKET=your-bucket-name"; \
		exit 1; \
	fi
	@source "$(GCLOUD_SDK_ROOT)/path.zsh.inc" && \
		. $(VENV)/bin/activate && \
		GOOGLE_CLOUD_PROJECT=$(PROJECT_ID) \
		GOOGLE_CLOUD_BUCKET=$(BUCKET) \
		python gc_stt.py --bucket $(BUCKET)

clean:
	rm -rf $(VENV)
	@echo "Virtual environment removed"

revoke-app-default:
	@echo "Revoking application default credentials..."
	$(GCLOUD) auth application-default revoke

revoke-user:
	@echo "Revoking gcloud user credentials..."
	$(GCLOUD) auth revoke

clean-auth: revoke-app-default revoke-user
	@echo "All gcloud credentials revoked"
