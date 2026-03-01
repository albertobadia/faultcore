#!/bin/bash
# Build script for faultcore
# Builds the Rust extension and workspace

set -e

uv run maturin develop --release

uv run cargo build --workspace --release 
