PY    ?= python3.13
EX    ?= examples/orphan-hunter
TF    := terraform -chdir=$(EX)
export GUARDRAILS_DIR := $(abspath $(EX))

.PHONY: help setup lint test check fmt bootstrap init init-migrate lock validate plan apply destroy preflight \
        smoke act1 act2 act3 truth truth-all reset reseed reply status ladder ladder-approve level sync \
        ledger-reset steps rehearse rehearse-auto

help:           ## lista de comandos
	@grep -E '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup:          ## venv + dependencias de desarrollo
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

lint:           ## ruff + lint de Cedar
	ruff check . && python scripts/lint_cedar.py

test:           ## pytest con moto (sin AWS)
	pytest

check: lint test ## todo lo que corre sin AWS

fmt:            ## terraform fmt
	terraform fmt -recursive

bootstrap:      ## OIDC + roles de GitHub Actions + bucket de estado (una vez, local)
	./scripts/bootstrap.sh

init:           ## init con el backend S3 (backend.hcl lo crea el bootstrap)
	@test -f $(EX)/backend.hcl || { echo "Falta $(EX)/backend.hcl: corre make bootstrap"; exit 1; }
	$(TF) init -backend-config=backend.hcl

init-migrate:   ## mueve un estado local existente al bucket S3
	$(TF) init -backend-config=backend.hcl -migrate-state

lock:           ## .terraform.lock.hcl para Linux (CI) y macOS
	$(TF) providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=darwin_amd64
	terraform -chdir=bootstrap providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=darwin_amd64

validate:
	$(TF) validate

plan:
	$(TF) plan

apply:
	$(TF) apply

destroy:
	$(TF) destroy

preflight:      ## credenciales, terraform, AgentCore, CloudTrail, cuotas y modelo
	python scripts/preflight.py

smoke:          ## plumbing sin LLM (envia 1 correo de prueba)
	python scripts/smoke_test.py

act1:           ## sin gobierno
	python scripts/run_agent.py --act 1

act2:           ## gobernado por Cedar
	python scripts/run_agent.py --act 2

act3:           ## escalera de confianza
	python scripts/run_agent.py --act 3

truth:          ## tags reales del lote activo
	python scripts/show_inventory.py

truth-all:
	python scripts/show_inventory.py --all

reset:          ## siguiente lote (a -> b -> c)
	python scripts/reset_batch.py

reseed:         ## recrea lo borrado y revierte tags (terraform apply)
	python scripts/reset_batch.py --reseed

reply:          ## make reply NAME=old-build-cache ANSWER=release|claim
	python scripts/owner_reply.py $(NAME) $(ANSWER)

status:         ## nivel y evidencia
	python scripts/ladder.py status

ladder:         ## baja sola; propone subir
	python scripts/ladder.py evaluate

ladder-approve: ## aplica el ascenso propuesto
	python scripts/ladder.py evaluate --approve

level:          ## make level L=2
	python scripts/ladder.py set $(L)

sync:           ## registra en el ledger el nivel de terraform.tfvars
	python scripts/ladder.py sync

ledger-reset:   ## borra el ledger
	python scripts/ladder.py reset

steps:          ## pasos del ensayo, sin ejecutar
	python scripts/rehearse.py --list

rehearse:       ## ensayo guiado de los 3 actos
	python scripts/rehearse.py

rehearse-auto:  ## ensayo cronometrado sin pausas
	python scripts/rehearse.py --auto
