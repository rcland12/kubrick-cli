#!/bin/sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH" >&2
  echo "Install Docker first: https://docs.docker.com/get-docker/" >&2
  exit 1
fi

# Installs kubrick-docker into ~/.local/bin (default) without editing shell rc files.
#
# Usage:
#   sh install-kubrick-docker.sh
#
# Optional env vars:
#   INSTALL_DIR           (default: ~/.local/bin)
#   DOCKERHUB_IMAGE       (default: rcland12/kubrick-cli:latest)
#   GHCR_IMAGE            (default: ghcr.io/rcland12/kubrick-cli:latest)
#   NETWORK_MODE          (default: host)
#
# Local build fallback:
#   By default, local build fallback is OFF because the launcher is installed globally.
#   If you want local fallback, set:
#     KUBRICK_BUILD_CONTEXT=/path/to/kubrick-cli-repo
#   (the launcher will then build from that Dockerfile if pulls fail)

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
TARGET="${INSTALL_DIR}/kubrick-docker"

DOCKERHUB_IMAGE="${DOCKERHUB_IMAGE:-rcland12/kubrick-cli:latest}"
GHCR_IMAGE="${GHCR_IMAGE:-ghcr.io/rcland12/kubrick-cli:latest}"
NETWORK_MODE="${NETWORK_MODE:-host}"

mkdir -p "$INSTALL_DIR"

cat > "$TARGET" <<EOF
#!/bin/sh
set -eu

# kubrick-docker: run Kubrick CLI via Docker with correct host permissions.
#
# Fallback order:
#   1) Docker Hub image: ${DOCKERHUB_IMAGE}
#   2) GHCR image:      ${GHCR_IMAGE}
#   3) Local build (optional): if KUBRICK_BUILD_CONTEXT is set and pulls fail
#
# Usage:
#   kubrick-docker [kubrick args...]
#
# Optional env overrides:
#   KUBRICK_DOCKERHUB_IMAGE   (default: ${DOCKERHUB_IMAGE})
#   KUBRICK_GHCR_IMAGE        (default: ${GHCR_IMAGE})
#   KUBRICK_LOCAL_TAG         (default: kubrick-cli:local)
#   KUBRICK_BUILD_CONTEXT     (default: unset; when set enables local build fallback)
#   KUBRICK_DOCKERFILE        (default: Dockerfile)
#   KUBRICK_NETWORK_MODE      (default: ${NETWORK_MODE})

DOCKERHUB_IMAGE="\${KUBRICK_DOCKERHUB_IMAGE:-${DOCKERHUB_IMAGE}}"
GHCR_IMAGE="\${KUBRICK_GHCR_IMAGE:-${GHCR_IMAGE}}"
LOCAL_TAG="\${KUBRICK_LOCAL_TAG:-kubrick-cli:local}"
BUILD_CONTEXT="\${KUBRICK_BUILD_CONTEXT:-}"
DOCKERFILE="\${KUBRICK_DOCKERFILE:-Dockerfile}"
NETWORK_MODE="\${KUBRICK_NETWORK_MODE:-${NETWORK_MODE}}"

# Ensure host config dir exists BEFORE mounting (prevents root-owned host dir creation)
HOST_KUBRICK_DIR="\${HOME}/.kubrick"
mkdir -p "\$HOST_KUBRICK_DIR"

UID_VAL="\$(id -u)"
GID_VAL="\$(id -g)"

TTY_FLAGS=""
if [ -t 0 ] && [ -t 1 ]; then
  TTY_FLAGS="-it"
fi

choose_image() {
  if docker pull "\$DOCKERHUB_IMAGE" >/dev/null 2>&1; then
    echo "\$DOCKERHUB_IMAGE"
    return 0
  fi

  if docker pull "\$GHCR_IMAGE" >/dev/null 2>&1; then
    echo "\$GHCR_IMAGE"
    return 0
  fi

  if [ -n "\$BUILD_CONTEXT" ]; then
    if [ ! -f "\$BUILD_CONTEXT/\$DOCKERFILE" ]; then
      echo "Error: KUBRICK_BUILD_CONTEXT is set but \$BUILD_CONTEXT/\$DOCKERFILE not found." >&2
      exit 1
    fi
    echo "Docker Hub + GHCR pulls failed; building locally from \$BUILD_CONTEXT..." >&2
    docker build -t "\$LOCAL_TAG" -f "\$BUILD_CONTEXT/\$DOCKERFILE" "\$BUILD_CONTEXT" >&2
    echo "\$LOCAL_TAG"
    return 0
  fi

  echo "Error: failed to pull Docker images, and local build fallback is disabled." >&2
  echo "Fix: ensure you can access Docker Hub/GHCR, or set KUBRICK_BUILD_CONTEXT=/path/to/kubrick-cli-repo" >&2
  exit 1
}

IMAGE="\$(choose_image)"

# Run Kubrick in the caller's current directory as /workspace
exec docker run --rm \$TTY_FLAGS \\
  --network "\$NETWORK_MODE" \\
  --user "\$UID_VAL:\$GID_VAL" \\
  -e HOME=/home/kubrick \\
  -v "\$HOST_KUBRICK_DIR:/home/kubrick/.kubrick" \\
  -v "\$PWD:/workspace" \\
  -w /workspace \\
  "\$IMAGE" "\$@"
EOF

chmod +x "$TARGET"

echo ""
echo "✅ Successfully installed kubrick-docker"
echo "   Location: $TARGET"
echo ""

case ":${PATH}:" in
  *":${INSTALL_DIR}:"*)
    echo "✅ ${INSTALL_DIR} is already on your PATH."
    ;;
  *)
    echo ""
    echo "⚠️  ${INSTALL_DIR} is not on your PATH."
    echo "Run this AND add it to your shell config (~/.bashrc or ~/.zshrc):"
    echo "    export PATH=\"${INSTALL_DIR}:\$PATH\""
    ;;
esac

echo ""
echo "Try it:"
echo "  kubrick-docker --help"
