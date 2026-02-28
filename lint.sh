#!/bin/bash
set -e

uv run cargo fmt
uv run cargo clippy --all-targets --all-features -- -D warnings
uv run ruff check . --fix
uv run ruff format .
