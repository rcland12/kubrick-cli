FROM python:3.11-slim

ARG UID=1000
ARG GID=1000

LABEL org.opencontainers.image.source="https://github.com/rcland12/kubrick-cli"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="kubrick-cli"
LABEL org.opencontainers.image.description="Kubrick CLI tool"

WORKDIR /app

COPY pyproject.toml ./
COPY kubrick_cli/ ./kubrick_cli/

RUN pip install --no-cache-dir -e . && \
    rm -rf /root/.cache

RUN groupadd -g ${GID} kubrick && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash kubrick

RUN mkdir -p /kubrick /workspace && \
    chown -R kubrick:kubrick /kubrick /workspace && \
    ln -s /kubrick /home/kubrick/.kubrick

USER kubrick

WORKDIR /workspace

ENV KUBRICK_IN_DOCKER=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["kubrick"]

CMD []
