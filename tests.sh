#!/bin/bash
# Test script for faultcore
# Runs cargo tests and pytest

set -e

uv run cargo test

uv run pytest --ignore=benchmarks/ --ignore=tests/integration/ --ignore=integration_tests/ -v
