# Multi-stage development and runtime image for Hebog.
ARG UV_VERSION=0.9.16
ARG PYTHON_VERSION=3.14
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin

FROM python:${PYTHON_VERSION}-slim AS base

WORKDIR /app
RUN apt-get update \
    && apt-get --no-install-recommends install -y ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv-bin /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
ENTRYPOINT ["tini", "-g", "--"]

FROM base AS dev

RUN apt-get update \
    && apt-get --no-install-recommends install -y curl \
    && curl -fsSL https://just.systems/install.sh \
        -o /tmp/install-just.sh \
    && bash /tmp/install-just.sh --to /usr/local/bin \
    && rm /tmp/install-just.sh \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --all-groups
CMD ["bash"]

FROM base AS runtime

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src/ ./src/
RUN uv sync --frozen --no-dev
CMD ["hebog", "--version"]
