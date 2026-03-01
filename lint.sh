#!/bin/bash
# Lint script for faultcore
# Runs cargo fmt, cargo clippy, and ruff

set -e

uv run cargo fmt
uv run cargo clippy --all-targets --all-features -- -D warnings
uv run ruff check . --fix
uv run ruff format .
