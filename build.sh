#!/bin/bash

set -e

uv run maturin develop --release

uv run cargo build --release --bin faultcore-run 
