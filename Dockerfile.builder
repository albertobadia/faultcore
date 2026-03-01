FROM rust:latest

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    python3 \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /workspace

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /root/.local/bin/

ENV PATH="/root/.local/bin:$PATH"

COPY faultcore_interceptor/Cargo.toml /workspace/faultcore_interceptor/
COPY faultcore_interceptor/src /workspace/faultcore_interceptor/src

RUN cd /workspace/faultcore_interceptor && \
    cargo build --release

ENV LD_PRELOAD=/workspace/faultcore_interceptor/target/release/libfaultcore_interceptor.so

CMD ["/bin/bash"]
