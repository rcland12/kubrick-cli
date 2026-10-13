# Kubrick development tasks.
#
# Everything lives in this repo (.venv/, .dev/) or in Docker, never in your
# system or user site-packages, so `make reset` gets you back to a clean slate.
# Run `make` to list the targets.

PYTHON ?= 3.12
VENV   := .venv
BIN    := $(CURDIR)/$(VENV)/bin
# Kubrick's data dir for dev runs (config, encrypted API keys, history, saved
# conversations), kept apart from your real ~/.kubrick.
KUBRICK_HOME ?= $(CURDIR)/.dev/home
PLAYGROUND   := $(CURDIR)/.dev/playground
# Project the agent works in; defaults to a throwaway copy of examples/playground.
DIR  ?= $(PLAYGROUND)
ARGS ?=
IMAGE  := kubrick-sandbox
VOLUME := kubrick-sandbox-home

.DEFAULT_GOAL := help
.PHONY: help dev run setup test lint fmt playground sandbox sandbox-build \
	reset-home reset-sandbox reset

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "} {printf "  make %-14s %s\n", $$1, $$2}'

# --seed puts pip inside the venv, so a `pip install` run from Kubrick's shell
# (which inherits this venv) lands here instead of in ~/.local.
$(BIN)/kubrick: pyproject.toml
	uv venv --seed --allow-existing --python $(PYTHON) $(VENV)
	uv pip install --python $(BIN)/python -e ".[dev,all]"
	@touch $@

dev: $(BIN)/kubrick ## Create .venv with an editable Kubrick and the dev tools

$(PLAYGROUND):
	@rm -rf "$@" && mkdir -p "$(dir $@)" && cp -r examples/playground "$@"
	@cd "$@" && git init -q && git add -A && \
		git -c user.name=kubrick -c user.email=kubrick@localhost commit -qm "playground"
	@echo "Playground ready at $@"

playground: ## Reset the throwaway playground project to its original (buggy) state
	@rm -rf "$(PLAYGROUND)"
	@$(MAKE) --no-print-directory "$(PLAYGROUND)"

run: $(BIN)/kubrick $(PLAYGROUND) ## Run Kubrick from .venv with a separate home (DIR=path ARGS="...")
	@mkdir -p "$(KUBRICK_HOME)"
	@cd "$(DIR)" && env KUBRICK_HOME="$(KUBRICK_HOME)" KUBRICK_CREDENTIAL_STORE=file \
		VIRTUAL_ENV="$(CURDIR)/$(VENV)" PATH="$(BIN):$$PATH" "$(BIN)/kubrick" $(ARGS)

setup: $(BIN)/kubrick ## Rerun the setup wizard for `make run`
	@mkdir -p "$(KUBRICK_HOME)"
	@env KUBRICK_HOME="$(KUBRICK_HOME)" KUBRICK_CREDENTIAL_STORE=file "$(BIN)/kubrick" setup

test: $(BIN)/kubrick ## Run the test suite
	$(BIN)/pytest -q $(ARGS)

lint: $(BIN)/kubrick ## Check formatting and lint, as CI does
	$(BIN)/black --check kubrick_cli tests examples
	$(BIN)/flake8 kubrick_cli tests --max-line-length=100 --extend-ignore=E203,W503

fmt: $(BIN)/kubrick ## Format the code
	$(BIN)/black kubrick_cli tests examples

sandbox-build:
	docker build -q -f docker/sandbox.Dockerfile -t $(IMAGE) . >/dev/null

sandbox: sandbox-build $(PLAYGROUND) ## Run Kubrick in Docker: it sees only DIR; installs stay in the container
	docker run --rm -it --network host --user $$(id -u):$$(id -g) \
		-e TERM -e COLORTERM -e NO_COLOR -e KUBRICK_ASCII \
		-v "$(CURDIR)":/opt/kubrick:ro \
		-v "$(abspath $(DIR))":/workspace \
		-v $(VOLUME):/home/kubrick \
		$(IMAGE) $(ARGS)

reset-home: ## Forget the dev config and API keys (`make run` shows the wizard again)
	rm -rf "$(CURDIR)/.dev/home"

reset-sandbox: ## Delete the sandbox's home volume and image
	-docker volume rm $(VOLUME)
	-docker image rm $(IMAGE)

reset: ## Delete .venv and .dev (venv, dev home, playground)
	rm -rf $(VENV) .dev
