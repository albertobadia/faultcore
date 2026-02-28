#!/bin/bash
set -e

uv run cargo test

uv run pytest --ignore=benchmarks/ --ignore=tests/integration/ -v
