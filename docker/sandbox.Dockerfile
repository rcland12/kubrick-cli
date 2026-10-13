# Disposable environment for trying Kubrick (Python 3.12, Node 24, git, ripgrep): the agent can only see the
# project mounted at /workspace, and anything it installs stays in the
# container (or the kubrick-sandbox-home volume). Built and run by `make sandbox`;
# Kubrick's source is mounted read-only at /opt/kubrick, so edits apply without
# a rebuild.
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git ripgrep && \
    rm -rf /var/lib/apt/lists/*

# Node.js + npm, so the agent can work on JavaScript/TypeScript projects too.
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Kubrick's dependencies (read from pyproject.toml), plus pytest for the agent.
COPY pyproject.toml /tmp/pyproject.toml
RUN python -c "import tomllib; p = tomllib.load(open('/tmp/pyproject.toml', 'rb'))['project']; \
open('/tmp/requirements.txt', 'w').write('\n'.join(p['dependencies'] + p['optional-dependencies']['bedrock'] + ['pytest']))" && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    printf '#!/bin/sh\nexec python -m kubrick_cli.main "$@"\n' > /usr/local/bin/kubrick && \
    chmod +x /usr/local/bin/kubrick && \
    mkdir -p /home/kubrick /workspace && chmod 1777 /home/kubrick /workspace

ENV HOME=/home/kubrick \
    PYTHONPATH=/opt/kubrick \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KUBRICK_CREDENTIAL_STORE=file

WORKDIR /workspace
ENTRYPOINT ["kubrick"]
