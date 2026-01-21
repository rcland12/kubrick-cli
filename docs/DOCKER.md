# Running Kubrick CLI with Docker

Guide to running Kubrick CLI in a Docker container.

## Container Registries

Kubrick CLI Docker images are available from two registries:

- **Docker Hub**: `rcland12/kubrick-cli`
- **GitHub Container Registry**: `ghcr.io/rcland12/kubrick-cli`

Both registries have identical images. Choose whichever you prefer!

## Understanding File Permissions

**IMPORTANT:** Kubrick needs to create and modify files in your project directory. To avoid permission issues, the container must run with your user ID and group ID (UID/GID).

### Why UID/GID Matters

When Docker creates files, they're owned by the user running inside the container. If the container runs as root (UID 0), all created files will be owned by root on your host system, making them difficult to edit or delete without `sudo`.

**The Solution:** Run the container with your host UID/GID using the `--user` flag. This ensures:
- Files created by Kubrick are owned by you
- No permission errors when editing files
- Compatibility between pip and Docker installations
- No need for `sudo` to clean up files

### Automatic vs Manual UID/GID

**Option 1: Use `kubrick-docker` wrapper (Automatic)**
The wrapper automatically detects and uses your UID/GID. No manual configuration needed.

```bash
kubrick-docker  # Handles UID/GID automatically
```

**Option 2: Docker Compose (Semi-Automatic)**
Export `UID` and `GID` environment variables once (add to `~/.bashrc` or `~/.zshrc`):

```bash
export UID=$(id -u)
export GID=$(id -g)
```

Then Docker Compose uses them automatically.

**Option 3: Manual Docker Commands (Manual)**
You must pass `--user $(id -u):$(id -g)` with every command.

### Technical Details

The Kubrick Docker image is designed to work with any UID/GID:
- `/workspace` and `/home/kubrick` have `chmod 1777` (world-writable with sticky bit)
- The container runs as the specified user at runtime
- This is the same approach used by VS Code Dev Containers and GitLab CI

## Installation Methods

### Option 1: Install Wrapper Script (Recommended)

The easiest way to use Kubrick with Docker is to install the `kubrick-docker` wrapper script. This creates a convenient command that handles all Docker flags automatically.

#### Quick Install

```bash
# Install from GitHub
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh

# Or download and run locally
wget https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh
sh install-kubrick-docker.sh
```

#### What It Does

- Installs `kubrick-docker` wrapper to `~/.local/bin/`
- Creates a smart launcher with automatic image fallback:
  1. Tries Docker Hub: `rcland12/kubrick-cli:latest`
  2. Falls back to GHCR: `ghcr.io/rcland12/kubrick-cli:latest`
  3. Optionally builds locally if configured
- Handles all volume mounts and permissions automatically
- Uses your UID/GID to avoid permission issues
- Works from any directory

#### Add to PATH

If `~/.local/bin` is not on your PATH:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Reload shell
source ~/.bashrc  # or source ~/.zshrc
```

#### Usage

```bash
# Run from any project directory
cd /path/to/your/project
kubrick-docker

# With arguments
kubrick-docker --triton-url my-server:8000
kubrick-docker --load 20240118_143022
```

#### Configuration

The wrapper script respects environment variables:

```bash
# Use a custom Docker image
export KUBRICK_DOCKERHUB_IMAGE=myrepo/kubrick-cli:custom
kubrick-docker

# Use a different network mode
export KUBRICK_NETWORK_MODE=bridge
kubrick-docker

# Enable local build fallback
export KUBRICK_BUILD_CONTEXT=/path/to/kubrick-cli-repo
kubrick-docker  # Will build locally if pulls fail
```

#### Uninstall

```bash
# Quick uninstall
curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/uninstall-kubrick-docker.sh | sh

# Or manually
rm ~/.local/bin/kubrick-docker
```

### Option 2: Use Docker Compose

Docker Compose provides a convenient way to run Kubrick without typing long docker commands. The kubrick-cli repository includes a `docker-compose.yaml` file that you can reference from any project directory.

See [Using Docker Compose](#using-docker-compose) section below for details.

### Option 3: Manual Docker Commands

If you prefer full control, use Docker commands directly. See [Quick Start](#quick-start) section below.

## Quick Start

### With standard Docker:

**IMPORTANT:** Always include `--user $(id -u):$(id -g)` to avoid permission issues!

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick (from Docker Hub)
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# Or from GitHub Container Registry
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  ghcr.io/rcland12/kubrick-cli
```

### With Docker Compose:

**IMPORTANT:** Set UID/GID environment variables first (add to `~/.bashrc` or `~/.zshrc`):

```bash
export UID=$(id -u)
export GID=$(id -g)
```

Then run:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick (replace with your kubrick-cli path)
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick
```

**Note:** The docker-compose.yaml file is in the kubrick-cli repository and uses `${UID}:${GID}` from your environment. See [Using Docker Compose](#using-docker-compose) for details.

## Basic Usage

### Run in Current Directory

```bash
cd /path/to/your/project
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli
```

### With Custom Triton Server

```bash
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli \
  --triton-url my-server:8000
```

### Load Previous Conversation

```bash
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli \
  --load 20240118_143022
```

### With Custom Model Name

```bash
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli \
  --model-name my-llm-model
```

## Understanding the Command

### Required Flags

```bash
--rm                        # Remove container after exit
-it                         # Interactive terminal
--network host              # Access localhost (for Triton)
--user $(id -u):$(id -g)    # Run as your user (CRITICAL for file permissions!)
```

### Volume Mounts

```bash
-v ${HOME}:/home/kubrick             # Config and conversation history
-v ${PWD}:/workspace                 # Your project files
-v /etc/localtime:/etc/localtime:ro  # (optional) Ensure the correct time
-v /etc/timezone:/etc/timezone:ro    # (optional) Ensure the correct timezone
```

**Important:** Always run from your project directory. Only files in the current directory will be accessible.

### Passing Arguments

Any arguments after the image name are passed to kubrick:

```bash
docker run ... rcland12/kubrick-cli [kubrick arguments]
```

**Examples:**

```bash
# Custom Triton URL
docker run --rm -it --network host --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
  rcland12/kubrick-cli --triton-url server:8000

# Load conversation
docker run --rm -it --network host --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
  rcland12/kubrick-cli --load 20240118_143022

# Multiple arguments
docker run --rm -it --network host --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
  rcland12/kubrick-cli --triton-url server:8000 --model-name custom-model
```

## Configuration

### Using Environment Variables

Override defaults with environment variables:

```bash
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e TRITON_URL=my-server:8000 \
  -e TRITON_MODEL_NAME=custom-model \
  rcland12/kubrick-cli
```

### Config File

Your config is stored in `~/.kubrick/config.json` (persists across runs):

```bash
# First run - configure
docker run ... rcland12/kubrick-cli
You: /config triton_url my-server:8000
You: exit

# Future runs use saved config automatically
docker run ... rcland12/kubrick-cli
```

## File Access

### What's Accessible

**Your project files:**

```bash
cd /my/project
docker run ... -v $(pwd):/workspace ...
# All files in /my/project are accessible
```

**Configuration:**

```bash
-v ~/.kubrick:/home/kubrick/.kubrick
# Config and conversations persist
```

### What's NOT Accessible

**Parent directories:**

```bash
cd /my/project
docker run ...
# Cannot access /my/ or /my/other-project
```

**Files outside the mount:**
If you didn't mount it, kubrick can't see it.

### Multiple Projects

Run from each project directory:

```bash
# Project 1
cd ~/projects/app1
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# Project 2
cd ~/projects/app2
docker run --rm -it \
  --network host \
  --user $(id -u):$(id -g) \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli
```

Configuration and history are shared via `~/.kubrick`. Files in each project are owned by you thanks to `--user` flag.

## Using Docker Compose

Docker Compose provides a convenient way to run Kubrick without typing long docker commands. The kubrick-cli repository includes a `docker-compose.yaml` file that you can reference from any project directory.

### Configuration File

The `docker-compose.yaml` file in the kubrick-cli repository:

```yaml
services:
  kubrick:
    container_name: kubrick-cli
    image: rcland12/kubrick-cli:latest
    build: .
    network_mode: host
    stdin_open: true
    tty: true
    user: "${UID}:${GID}"  # CRITICAL: Uses your UID/GID for correct permissions
    environment:
      HOME: /home/kubrick
    volumes:
      - ${HOME}:/home/kubrick
      - ${PWD}:/workspace
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    working_dir: /workspace
    command: []
```

**Key Point:** The `user: "${UID}:${GID}"` line ensures files are created with your ownership.

### Setup: Export UID and GID

**REQUIRED FIRST STEP:** Add these exports to your `~/.bashrc` or `~/.zshrc`:

```bash
export UID=$(id -u)
export GID=$(id -g)
```

Then reload your shell:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

This allows Docker Compose to use your UID/GID from the `docker-compose.yaml` file.

### Usage from Any Project Directory

**This is the recommended approach.** You don't need to copy the docker-compose.yaml file to each project. Instead, reference it using the `-f` flag:

```bash
# Navigate to YOUR project (the one you want to work on)
cd ~/dev/your-project

# Run kubrick using the compose file from kubrick-cli repo
docker compose -f /path/to/kubrick-cli/docker-compose.yaml run --rm kubrick
```

**Example workflow:**

```bash
# Work on project 1
cd ~/dev/my-web-app
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick

# Work on project 2
cd ~/dev/my-api-server
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick

# Work on project 3
cd ~/projects/data-pipeline
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick
```

**How it works:**

- `${PWD}` (your current directory) is mounted to `/workspace` in the container
- You can work on any project by just changing directories
- No need to copy docker-compose.yaml to each project

**With arguments:**

```bash
cd ~/dev/your-project
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick --triton-url my-server:8000
```

### Usage from kubrick-cli Directory

If you're in the kubrick-cli repository directory, you can run without the `-f` flag:

```bash
# If you're already in the kubrick-cli directory
cd /path/to/kubrick-cli
docker compose run --rm kubrick
```

**Note:** This will mount the kubrick-cli directory itself to `/workspace`, so you'd be working on the kubrick-cli code, not your actual projects. This is only useful for developing kubrick itself.

### Creating a Shell Alias

For convenience, create an alias that references the compose file. Add to `~/.bashrc` or `~/.zshrc`:

```bash
# Export UID/GID (REQUIRED for Docker Compose)
export UID=$(id -u)
export GID=$(id -g)

# Create alias (replace with your actual path to kubrick-cli)
alias kubrick='docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick'
```

Reload your shell:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

**Usage:**

```bash
cd ~/dev/any-project
kubrick
kubrick --triton-url my-server:8000
kubrick --load 20240118_143022
```

### Key Points

- **Always navigate to your project directory first** before running the command
- **Must export UID and GID** in your shell for correct file permissions
- The `-f` flag tells docker compose where to find the yaml file
- The `${PWD}` variable in docker-compose.yaml automatically uses your current directory
- The `${UID}:${GID}` in docker-compose.yaml ensures files are owned by you
- Configuration and conversation history are shared across all projects via `~/.kubrick`

## Troubleshooting

### Cannot Connect to Triton

**Error:** `Cannot connect to Triton server at localhost:8000`

**Solutions:**

1. Verify Triton is running:

   ```bash
   curl http://localhost:8000/v2/health/live
   ```

2. Make sure you're using `--network host`:

   ```bash
   docker run --network host ...
   ```

3. Use custom URL if Triton is not on localhost:
   ```bash
   docker run ... rcland12/kubrick-cli --triton-url my-server:8000
   ```

### Files Not Found

**Error:** CLI can't find your files

**Solutions:**

1. Run from your project directory:

   ```bash
   cd /path/to/project
   docker run ...
   ```

2. Check the working directory mount:

   ```bash
   -v $(pwd):/workspace
   ```

3. Verify files exist:
   ```bash
   ls $(pwd)
   ```

### Permission Errors

**Error:** Cannot write files, or files are owned by root

**Root Cause:** Container is not running with your UID/GID.

**Solutions:**

1. **For manual Docker commands:** Ensure you include `--user $(id -u):$(id -g)`

   ```bash
   # Wrong (creates root-owned files)
   docker run --rm -it --network host \
     -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
     rcland12/kubrick-cli

   # Correct (creates files owned by you)
   docker run --rm -it --network host --user $(id -u):$(id -g) \
     -v ${HOME}:/home/kubrick -v ${PWD}:/workspace \
     rcland12/kubrick-cli
   ```

2. **For Docker Compose:** Ensure UID/GID are exported in your shell

   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export UID=$(id -u)
   export GID=$(id -g)

   # Reload shell
   source ~/.bashrc
   ```

3. **Clean up root-owned files** (if they were already created):

   ```bash
   # List root-owned files in current directory
   find . -user root

   # Fix ownership (use with caution)
   sudo chown -R $(id -u):$(id -g) .
   ```

4. **Use `kubrick-docker` wrapper** (recommended): Handles UID/GID automatically

   ```bash
   curl -fsSL https://raw.githubusercontent.com/rcland12/kubrick-cli/master/scripts/install-kubrick-docker.sh | sh
   kubrick-docker  # No UID/GID configuration needed
   ```

## Shell Alias (Manual Docker)

For convenience with manual Docker commands, create a shell alias. Add to `~/.bashrc` or `~/.zshrc`:

```bash
alias kubrick='docker run --rm -it --network host --user $(id -u):$(id -g) -v ${HOME}:/home/kubrick -v ${PWD}:/workspace -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro rcland12/kubrick-cli'
```

Reload your shell:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

**Usage:**

```bash
cd /path/to/project
kubrick
kubrick --triton-url my-server:8000
kubrick --load 20240118_143022
```

**Note:** The `$(id -u):$(id -g)` in the alias automatically uses your UID/GID each time.

## Requirements

- Docker 20.10+
- Triton server accessible at `localhost:8000` (or custom URL)
- Project directory with files you want to work on
