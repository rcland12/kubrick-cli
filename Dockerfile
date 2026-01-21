FROM python:3.14-slim AS builder
WORKDIR /app
SHELL ["/bin/sh", "-euxc"]
COPY . .
RUN pip install --no-cache-dir --upgrade pip build && \
    python -m build --wheel

FROM python:3.14-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/rcland12/kubrick-cli"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="kubrick-cli"
LABEL org.opencontainers.image.description="Kubrick CLI tool"

SHELL ["/bin/sh", "-euxc"]
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/kubrick

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /workspace ${HOME} && \
    chmod 1777 /workspace ${HOME}

WORKDIR /workspace
COPY --from=builder /app/dist/ /tmp/dist/
RUN pip install --no-cache-dir /tmp/dist/*.whl && \
    rm -rf /tmp/dist

ENTRYPOINT ["kubrick"]
CMD []
