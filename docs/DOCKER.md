# Running Kubrick CLI with Docker

Guide to running Kubrick CLI in a Docker container.

## Container Registries

Kubrick CLI Docker images are available from two registries:

- **Docker Hub**: `rcland12/kubrick-cli`
- **GitHub Container Registry**: `ghcr.io/rcland12/kubrick-cli`

Both registries have identical images. Choose whichever you prefer!

## Quick Start

### With standard Docker:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick (from Docker Hub)
docker run --rm -it \
  --network host \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# Or from GitHub Container Registry
docker run --rm -it \
  --network host \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  ghcr.io/rcland12/kubrick-cli
```

### With Docker Compose:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick (replace with your kubrick-cli path)
docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick
```

**Note:** The docker-compose.yaml file is in the kubrick-cli repository. Use the `-f` flag to reference it from any project directory. See [Using Docker Compose](#using-docker-compose) for details.

## Basic Usage

### Run in Current Directory

```bash
cd /path/to/your/project
docker run --rm -it \
  --network host \
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
--rm              # Remove container after exit
-it               # Interactive terminal
--network host    # Access localhost (for Triton)
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
docker run ... rcland12/kubrick-cli --triton-url server:8000

# Load conversation
docker run ... rcland12/kubrick-cli --load 20240118_143022

# Multiple arguments
docker run ... rcland12/kubrick-cli --triton-url server:8000 --model-name custom-model
```

## Configuration

### Using Environment Variables

Override defaults with environment variables:

```bash
docker run --rm -it \
  --network host \
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
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli

# Project 2
cd ~/projects/app2
docker run --rm -it \
  --network host \
  -v ${HOME}:/home/kubrick \
  -v ${PWD}:/workspace \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  rcland12/kubrick-cli
```

Configuration and history are shared via `~/.kubrick`.

## Using Docker Compose

Docker Compose provides a convenient way to run Kubrick without typing long docker commands. The kubrick-cli repository includes a `docker-compose.yaml` file that you can reference from any project directory.

### Configuration File

The `docker-compose.yaml` file in the kubrick-cli repository:

```yaml
services:
  kubrick:
    container_name: kubrick-cli
    image: rcland12/kubrick-cli:latest
    build:
      context: .
      args:
        UID: ${UID:-1000}
        GID: ${GID:-1000}
    network_mode: host
    stdin_open: true
    tty: true
    volumes:
      - ${HOME}:/home/kubrick
      - ${PWD}:/workspace
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    command: []
```

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

For convenience, create an alias that references the compose file:

**Bash/Zsh (~/.bashrc or ~/.zshrc):**

```bash
# Replace with your actual path to kubrick-cli
alias kubrick='docker compose -f ~/dev/kubrick-cli/docker-compose.yaml run --rm kubrick'
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
- The `-f` flag tells docker compose where to find the yaml file
- The `${PWD}` variable in docker-compose.yaml automatically uses your current directory
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

**Error:** Cannot write files

**Solutions:**

1. Check file permissions on host:

   ```bash
   ls -la /path/to/project
   ```

2. Ensure directory is writable:
   ```bash
   chmod u+w /path/to/project
   ```

## Shell Alias

For convenience, create a shell alias:

**Bash/Zsh (~/.bashrc or ~/.zshrc):**

```bash
alias kubrick='docker run --rm -it --network host -v ${HOME}:/home/kubrick -v ${PWD}:/workspace -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro rcland12/kubrick-cli'
```

**Usage:**

```bash
cd /path/to/project
kubrick
kubrick --triton-url my-server:8000
kubrick --load 20240118_143022
```

## Requirements

- Docker 20.10+
- Triton server accessible at `localhost:8000` (or custom URL)
- Project directory with files you want to work on
