FROM python:3.11-slim AS builder

WORKDIR /app
SHELL ["/bin/sh", "-euxc"]

COPY . .
RUN pip install --no-cache-dir --upgrade pip build && \
    python -m build --wheel


FROM python:3.11-slim AS runtime

ARG UID=1000
ARG GID=1000

LABEL org.opencontainers.image.source="https://github.com/rcland12/kubrick-cli"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="kubrick-cli"
LABEL org.opencontainers.image.description="Kubrick CLI tool"

SHELL ["/bin/sh", "-euxc"]

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV USER=kubrick
ENV HOME=/home/${USER}

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g ${GID} ${USER} && \
    useradd -m -u ${UID} -g ${GID} -s /bin/sh ${USER} && \
    mkdir -p /workspace && \
    chown -R ${USER}:${USER} ${HOME} /workspace

WORKDIR /workspace
COPY --from=builder /app/dist/ /tmp/dist/
RUN pip install --no-cache-dir /tmp/dist/*.whl && \
    rm -rf /tmp/dist

USER ${USER}
ENTRYPOINT ["kubrick"]
CMD []
