# AGENTS.md - XBVR Stack Development Guidelines

This is a Docker-based deployment configuration repository for XBVR. The application code lives in a separate repository and is pulled as a pre-built Docker image.

## Project Structure

```
.
├── docker/           # Docker Compose configuration, env file, and scripts
│   ├── .env
│   ├── arp-webdav/
│   ├── docker-compose.yml
│   ├── download_arp_cuepoints.py
│   ├── download_cuepoints.py
│   ├── download_slr_cuepoints.py
│   ├── manage_compilations.py
│   ├── mariadb/my.cnf
│   └── xbvr-manager
├── data/             # Persistent data (gitignored)
│   ├── jackett/
│   ├── mariadb/
│   ├── xbvr/
│   └── rclone/
└── backup/           # Database and application backups (gitignored)
```

## Development Commands

### Validation (Run before deploying)

```bash
# Validate docker-compose.yml syntax
docker compose -f docker/docker-compose.yml config --quiet

# Validate environment file (check required variables exist)
grep -E '^[A-Z_]+=' docker/.env | cut -d= -f1

# Lint Dockerfiles (install hadolint first)
hadolint docker/arp-webdav/Dockerfile
```

### Docker Compose Operations

```bash
# Always pass the correct env file from docker/ directory:
docker compose --env-file .env up -d
docker compose --env-file .env logs -f
docker compose --env-file .env down -v
```

```bash
chmod +x docker/xbvr-manager
./docker/xbvr-manager
```

### Menu Options

| Option | Action |
|--------|--------|
| 0 | Full setup (runs steps 1 through 3 automatically) |
| 1 | Create required directories |
| 2 | Install rclone_rd Docker plugin |
| 3 | Start stack (volumes managed by docker compose) |
| 4 | Stop stack and remove volumes |
| 5 | Stop stack, remove volumes, and clear rclone cache |
| A | Access files with ffprobe (Keepalive Menu, runs in a temp disabled-cache container) |
| M | Check files table for missing physical files (runs in parallel batches) |
| C | Cuepoints Menu (timestamp.trade, SexLikeReal, ARP) |
| V | VPN Menu (ProtonVPN status, rotate IP, change country, enable/disable) |
| 8 | View live logs |
| 9 | Restart menu (full stack or XBVR only) |
| O | Open XBVR in Brave incognito |
| B | Backup Menu (Database / Full) |
| T | Compilations Menu (Identify & Tag compilation scenes) |
| 6 | Partial cleanup (remove plugin + clear cache) |
| 7 | Full cleanup (remove everything including app data) |
| Q | Quit |

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

# Storage Configuration
# The stack uses the rclone_rd Docker plugin to mount Google Drive directly.
# Google Drive is configured via rclone and mounted automatically.
```

### Error Handling

- Shell scripts: Use `set -euo pipefail`, check exit codes
- Docker: Healthchecks for dependent services
- Always validate required environment variables exist before starting

### Documentation

- All shell scripts should have usage/help text
- README should explain Linux-specific setup expectations
- Comments should explain *why*, not *what*

## Common Issues & Solutions

### MariaDB unhealthy after migrating data

Credentials in the env file must match the existing database users. Copying `data/mariadb` from another machine won't recreate users.

### ffmpeg/ffprobe permission denied

Restore execute bits after migrating `data/xbvr`:
```bash
chmod 755 data/xbvr/bin/ffprobe data/xbvr/bin/ffmpeg
```

### rclone_rd plugin install fails

Ensure `fuse` or `fuse3` is installed on the Linux host.

### XBVR crashes on startup when HTTP_PROXY is set

XBVR connects internally to its own WAMP router via `ws://0.0.0.0:9998`. Ensure `0.0.0.0`, `127.0.0.1`, `localhost`, `::1`, and `::` are included in `NO_PROXY` on the `xbvr` service so internal WebSocket connections bypass the `gluetun` HTTP proxy.

## Notes

- The repo-root `.env` is legacy; always use `docker/.env`
- This repository is configuration-only; application code is in the XBVR repository
- Real-Debrid, Google Drive, and Arp mounts require the `rclone_rd` Docker plugin installed on the host
- Outbound XBVR scraper traffic is routed through `gluetun` (`xbvr-vpn`) via `HTTP_PROXY`/`HTTPS_PROXY` (`XBVR_PROXY_URL`), while local video streaming and `rclone_rd` mounts bypass the VPN
- Tracker search in XBVR uses `jackett` (`xbvr-jackett` on port `9117`) via `JACKETT_URL` and `JACKETT_API_KEY` (with `jackett` included in `xbvr`'s `NO_PROXY`)
