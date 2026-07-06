# Task shortcuts (the Python equivalent of `npm run`).
# Usage: `make <target>`, e.g. `make agent`, `make backend`.
#
# Override the venv path if yours differs:
#   make agent VENV=.venv

VENV ?= path/to/venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# Load .env so the supabase CLI picks up SUPABASE_ACCESS_TOKEN / DB password / ref.
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: help venv install backend agent schema frontend frontend-install \
        supabase-link supabase-push db eval eval-behavioral eval-guardrail \
        eval-verify eval-groundedness eval-faithfulness eval-latency eval-stt \
        up down build

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv:  ## Create the virtualenv
	python3 -m venv $(VENV)

install:  ## Install Python deps into the venv
	$(PIP) install -r requirements.txt

backend:  ## Run the FastAPI backend (token + audit-log API)
	$(VENV)/bin/uvicorn backend.server:app --reload --port 8000

agent:  ## Run the LiveKit agent worker (dev / hot reload)
	$(PY) -m agent.main dev

schema:  ## Apply the DB schema (needs DATABASE_URL; see data/apply_schema.py)
	$(PY) data/apply_schema.py

supabase-link:  ## Link the local project to your remote Supabase project
	supabase link --project-ref $(SUPABASE_PROJECT_REF)

supabase-push:  ## Push migrations (supabase/migrations/*) to the remote DB
	supabase db push

db: supabase-link supabase-push  ## Link + push in one step

frontend-install:  ## Install frontend deps
	cd frontend && npm install

frontend:  ## Run the Next.js dev server
	cd frontend && npm run dev

eval:  ## Run all evals (behavioral + STT)
	$(PY) -m evals.run

eval-behavioral:  ## Run behavioral (compliance tag) evals only
	$(PY) -m evals.run --behavioral

eval-guardrail:  ## Run adversarial safety / emergency-recall evals only
	$(PY) -m evals.run --guardrail

eval-verify:  ## Run audit chain integrity (tamper/deletion detection) only
	$(PY) -m evals.run --verify

eval-groundedness:  ## Run numeric groundedness (no hallucinated doses) only
	$(PY) -m evals.run --groundedness

eval-faithfulness:  ## Run grounded faithfulness auditor (abstention + entailment)
	$(PY) -m evals.run --faithfulness

eval-latency:  ## Benchmark the planning path (p50/p95) + semantic-layer cost
	$(PY) -m evals.run --latency

eval-stt:  ## Run STT clinical-term WER evals only
	$(PY) -m evals.run --stt

build:  ## Build all Docker images
	docker compose build

up:  ## Start the full stack with Docker (agent + backend + frontend)
	docker compose up --build

down:  ## Stop and remove the Docker stack
	docker compose down
