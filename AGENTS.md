# AGENTS.md - XBVR Stack Development Guidelines

This is a Docker-based deployment configuration repository for XBVR. The application code lives in a separate repository and is pulled as a pre-built Docker image.

## Project Structure

```
.
├── docker/           # Docker Compose configuration
│   ├── docker-compose.yml
│   └── mariadb/my.cnf
├── linux/            # Linux launcher and env file
├── windows/          # Windows launcher and env files
├── data/             # Persistent data (gitignored)
│   ├── mariadb/
│   ├── xbvr/
│   └── rclone/
└── example.env       # Reference template
```

## Development Commands

### Validation (Run before deploying)

```bash
# Validate docker-compose.yml syntax
docker compose -f docker/docker-compose.yml config --quiet

# Validate environment file (check required variables exist)
# Linux
grep -E '^[A-Z_]+=' docker/../linux/.env | cut -d= -f1
# Windows
type windows\.env | findstr /R "^[A-Z_]*="

# Lint Dockerfiles (install hadolint first)
hadolint docker/docker-compose.yml
```

### Docker Compose Operations

```bash
# Always pass the correct env file from docker/ directory:

# Linux
docker compose --env-file ../linux/.env up -d
docker compose --env-file ../linux/.env logs -f
docker compose --env-file ../linux/.env down -v

# Windows
docker compose --env-file ../windows/.env up -d
docker compose --env-file ../windows/.env logs -f
docker compose --env-file ../windows/.env down -v
```

### Linux Launcher

```bash
chmod +x linux/xbvr-manager.sh
./linux/xbvr-manager.sh
```

### Windows Launcher

```cmd
windows\XBVR-Manager.bat
```

### Menu Options (both launchers)

| Option | Action |
|--------|--------|
| 0 | Full setup (create dirs, install rclone, start) |
| 1 | Create required directories |
| 2 | Install rclone_RD Docker plugin |
| 3 | Start stack |
| 4 | Stop stack and remove volumes |
| 6 | Partial cleanup (containers, volumes, rclone plugin) |
| 7 | Full cleanup (keeps rclone config on Linux) |
| 8 | View live logs |

## Code Style Guidelines

### YAML (docker-compose.yml)

- Use 2-space indentation
- Comments start with `#` and describe section purpose
- Section separators use `---` style headers with dashes
- Environment variables: `${VAR_NAME}` with descriptive names
- Always include `:ro` suffix for read-only mounts
- Healthchecks required for database dependencies
- Escape `$` in healthcheck commands with `$$`

```yaml
# Good example
services:
  myservice:
    image: example:latest
    ports:
      - "${HOST_PORT}:8080"    # Map host to container
    volumes:
      - ./config:/app/config:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Shell Scripts

- Start with `#!/usr/bin/env bash` or `#!/usr/bin/env zsh`
- Use `set -euo pipefail` for error handling
- Use `[[ ]]` for conditionals (not `[ ]`)
- Quote variables: `"$VAR"` not `$VAR`
- Use `readonly` for constants
- Use `local` for function variables

```bash
#!/usr/bin/env bash
set -euo pipefail

readonly CONFIG_DIR="/path/to/config"

main() {
    local input="$1"
    [[ -d "$input" ]] || die "Directory not found: $input"
    process_files "$input"
}

die() {
    echo "$*" >&2
    exit 1
}
```

### Environment Files

- Uppercase variable names
- Group related variables with comment headers
- Document non-obvious values
- Use single quotes for paths with spaces

```env
# Database
MARIADB_USER=xbvr
MARIADB_PASSWORD=changeme
MARIADB_DATABASE=xbvr

# Paths (quote paths with spaces)
TS_PATH='/media/xxx/Local Disk1/TS'
JAV_PATH='/media/xxx/Local Disk1/JAV'
```

### Error Handling

- Shell scripts: Use `set -euo pipefail`, check exit codes
- Docker: Healthchecks for dependent services
- Always validate required environment variables exist before starting

### Documentation

- All shell scripts should have usage/help text
- README should explain OS-specific differences
- Comments should explain *why*, not *what*

## Common Issues & Solutions

### MariaDB unhealthy after migrating data

Credentials in the env file must match the existing database users. Copying `data/mariadb` from another machine won't recreate users.

### ffmpeg/ffprobe permission denied

Restore execute bits after migrating `data/xbvr`:
```bash
chmod 755 data/xbvr/bin/ffprobe data/xbvr/bin/ffmpeg
```

### rclone plugin install fails

Ensure `fuse` or `fuse3` is installed on the Linux host.

## Notes

- The repo-root `.env` is legacy; always use OS-specific env files
- This repository is configuration-only; application code is in the XBVR repository
- Real-Debrid mount requires the `rclone` Docker plugin installed on the host
