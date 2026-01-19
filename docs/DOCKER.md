# Running Kubrick CLI with Docker

Guide to running Kubrick CLI in a Docker container.

## Quick Start

### With standard Docker:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli
```

### With Docker Compose:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run kubrick
docker compose run --rm kubrick
```

## Basic Usage

### Run in Current Directory

```bash
cd /path/to/your/project
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli
```

### With Custom Triton Server

```bash
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli \
  --triton-url my-server:8000
```

### Load Previous Conversation

```bash
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
  rcland12/kubrick-cli \
  --load 20240118_143022
```

### With Custom Model Name

```bash
docker run --rm -it \
  --network host \
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
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
-v ~/.kubrick:/kubrick      # Config and conversation history
-v $(pwd):/workspace        # Your project files
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
  -v ~/.kubrick:/kubrick \
  -v $(pwd):/workspace \
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

## Docker Mode Detection

When running in Docker, you'll see:

```
ℹ️  Running in Docker mode
→ Files are accessible only within /workspace (mounted from your current directory)
→ Config is saved to ~/.kubrick (mounted volume)
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
-v ~/.kubrick:/kubrick
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
docker run --rm -it --network host -v ~/.kubrick:/kubrick -v $(pwd):/workspace rcland12/kubrick-cli

# Project 2
cd ~/projects/app2
docker run --rm -it --network host -v ~/.kubrick:/kubrick -v $(pwd):/workspace rcland12/kubrick-cli
```

Configuration and history are shared via `~/.kubrick`.

## Using Docker Compose

If you prefer docker-compose, reference the file `docker-compose.yaml`:

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
      - ~/.kubrick:/kubrick
      - .:/workspace
    working_dir: /workspace
    command: []
```

**Run:**

```bash
cd /path/to/your/project
docker compose run --rm kubrick
```

**With arguments:**

```bash
docker compose run --rm kubrick --triton-url my-server:8000
```

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

### Config Not Saving

**Error:** Configuration resets between runs

**Solutions:**

1. Include config mount:

   ```bash
   -v ~/.kubrick:/kubrick
   ```

2. Verify directory exists:
   ```bash
   mkdir -p ~/.kubrick
   ```

## Shell Alias

For convenience, create a shell alias:

**Bash/Zsh (~/.bashrc or ~/.zshrc):**

```bash
alias kubrick='docker run --rm -it --network host -v ~/.kubrick:/kubrick -v $(pwd):/workspace rcland12/kubrick-cli'
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
