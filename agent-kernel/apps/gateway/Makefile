.PHONY: help build dev test lint tui tui-dev clean

# Default target
help:
	@echo "OpenClaw Gateway - Available targets:"
	@echo ""
	@echo "  make build      - Build the Gateway"
	@echo "  make dev        - Run Gateway in development mode"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linter"
	@echo "  make tui        - Start the TUI client"
	@echo "  make tui-dev    - Start TUI in debug mode"
	@echo "  make clean      - Clean build artifacts"
	@echo ""

# Build
build:
	npm run build

# Development
dev:
	npm run dev

# Tests
test:
	npm run test

# Linting
lint:
	npm run lint

# Type checking
typecheck:
	npm run typecheck

# TUI client
tui:
	@echo "Starting OpenClaw TUI..."
	@cd clients/tui && ./scripts/run.sh

tui-dev:
	@echo "Starting OpenClaw TUI (debug mode)..."
	@cd clients/tui && pip install -q -e . && python -m openclaw_tui.main --debug

tui-install:
	@echo "Installing TUI dependencies..."
	@cd clients/tui && pip install -e ".[dev]"

# Clean
clean:
	rm -rf dist node_modules
	@cd clients/tui && rm -rf __pycache__ .pytest_cache *.egg-info
