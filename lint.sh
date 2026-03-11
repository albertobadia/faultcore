#!/bin/bash

set -e

cd faultcore_network
uv run cargo clippy --all-targets --all-features -- -D warnings

cd ../faultcore_interceptor
uv run cargo clippy --all-targets --all-features -- -D warnings

cd ..
uv run ruff check . --fix
uv run ruff format .
