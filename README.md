# XBVR Stack

Docker-based XBVR deployment with MariaDB, XBVR application, and Real-Debrid mounting via the `rclone` Docker volume plugin.

## Project Structure

```
.
├── docker/
│   ├── .env
│   ├── docker-compose.yml
│   ├── mariadb/my.cnf
│   └── xbvr-manager.sh
└── data/
    ├── mariadb/
    ├── xbvr/
    └── rclone/
        ├── cache/
        └── config/
```

This repository now keeps the launcher and environment file in `docker/`.

## Requirements

- Docker with `docker compose` plugin
- Real-Debrid API key
- Configured Google Drive remote via `rclone config` saved in `data/rclone/config/rclone.conf`

### Linux

- `bash`
- `fuse` or `fuse3` (for rclone plugin)

## Environment Variables

Use `docker/.env` and adjust the values for your setup.

```env
# =============================================================
#  XBVR Stack - Environment Variables
# =============================================================

# --- Real-Debrid -------------------------------------------
RD_API_KEY=your_api_key_here

# --- MariaDB -----------------------------------------------
MARIADB_USER=xbvr
MARIADB_PASSWORD=changeme
MARIADB_DATABASE=xbvr

# --- XBVR --------------------------------------------------
XBVR_PORT=9999
DB_CONNECTION_POOL_SIZE=300
CONCURRENT_SCRAPERS=6
MARIADB_PORT=3306

# Timezone - change to your zone, e.g. America/Sao_Paulo
TZ=America/Sao_Paulo

# Storage Configuration
# The stack uses the rclone Docker plugin to mount Google Drive directly.
# Google Drive is configured via rclone config (placed in data/rclone/config).

```

### Variable Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `RD_API_KEY` | Real-Debrid API key (required for rclone mount) | |
| `MARIADB_USER` | Database user for XBVR | `xbvr` |
| `MARIADB_PASSWORD` | Database password | `changeme` |
| `MARIADB_DATABASE` | Database name | `xbvr` |
| `XBVR_PORT` | Host port for XBVR web UI | `9999` |
| `DB_CONNECTION_POOL_SIZE` | MariaDB connection pool size | `300` |
| `CONCURRENT_SCRAPERS` | Number of concurrent scrapers | `6` |
| `MARIADB_PORT` | Host port for MariaDB | `3306` |
| `TZ` | Timezone | `America/Sao_Paulo` |


## Setup

### 1. Configure Environment

Edit `docker/.env`.

At minimum, set:
- `RD_API_KEY` with your Real-Debrid API key
- `MARIADB_PASSWORD` to a secure password
- A valid `rclone.conf` in `data/rclone/config/` for Google Drive

### 2. Run the Launcher

```bash
chmod +x docker/xbvr-manager.sh
./docker/xbvr-manager.sh
```

Select option `0` for full setup (creates directories, installs rclone plugin, starts stack).

## Menu Options

| Option | Action |
|--------|--------|
| 0 | Full setup (create dirs, install rclone, start) |
| 1 | Create required directories |
| 2 | Install rclone_RD Docker plugin |
| 3 | Start stack |
| 4 | Stop stack and remove volumes |
| 5 | Stop stack, remove volumes, and clear rclone cache |
| 6 | Partial cleanup (containers, volumes, rclone plugin) |
| 7 | Full cleanup (removes app data, keeps rclone config) |
| 8 | View live logs |
| 9 | Open the restart submenu for full stack or XBVR-only restart |
| `B` | Open the backup submenu to backup MariaDB and/or XBVR data |
| `A` | Run the Real-Debrid keepalive scan on `.mp4` files that have not completed successfully in the last 5 days |
| `C` | Check files table for missing physical files in the XBVR container |
| `D` | Download and merge cuepoints from timestamp.trade based on database matching |
| `A -T` | Run the same keepalive scan with per-file trace output |
| `A -P 10` | Run the keepalive scan with custom parallelism |
| `A -P 10 -T` | Run the keepalive scan with both custom parallelism and trace output |
| `A -ALL` | Bypass the 5-day filter and run the keepalive scan for all `.mp4` files |
| `S` | Download and merge cuepoints from SexLikeReal based on database matching |
| `O` | Open XBVR in a Brave/Chromium incognito window |
| `Q` | Quit the helper |

The keepalive scan stores successful runs in `/root/.config/xbvr/realdebrid-keepalive-state.tsv`, which is persisted through the XBVR config volume. By default, files with a successful `ffprobe` in the last 5 days are skipped. The progress and final summary show total files, skipped files, eligible files, completed files, successes, errors, and timeouts. Without `-T`, it keeps the output quiet aside from progress, errors, and the final summary. `-P` changes the parallel worker count, the default remains `10`, and `-ALL` bypasses the 5-day skip filter.

The SexLikeReal cuepoints tool (`S`) stores successfully resolved studio IDs in `/root/.config/xbvr/slr-studio-cache.tsv` to avoid duplicate API calls. Cache entries are valid for 5 days. Both the keepalive scan and the SLR cuepoints tool use multi-threaded batch fetching with a default maximum of 10 concurrent parallel workers.

## Access

XBVR is available at `http://localhost:9999` (default port).

## Manual Docker Commands

Run from the `docker/` directory:

```bash
docker compose --env-file .env up -d
docker compose --env-file .env logs -f
docker compose --env-file .env down -v
```

## Persistent Data

| Directory | Purpose |
|-----------|---------|
| `data/mariadb/` | MariaDB database files |
| `data/xbvr/` | XBVR config and metadata |
| `data/rclone/config/` | Linux rclone plugin config |
| `data/rclone/cache/` | Linux rclone plugin cache |

The Real-Debrid mount is a Docker-managed volume, not a bind mount.

## Media Mounts

```
gdrive volume -> /videos/gdrive
realdebrid volume -> /videos/realdebrid
```

## Troubleshooting

### MariaDB unhealthy after migrating data

Credentials in the env file must match the existing database users. Copying `data/mariadb` from another machine won't recreate users.

### ffmpeg/ffprobe permission denied

After migrating `data/xbvr` from another system, binaries may lose execute bits:

```bash
chmod 755 data/xbvr/bin/ffprobe data/xbvr/bin/ffmpeg
```

### rclone plugin install fails

Ensure `fuse` or `fuse3` is installed on the Linux host.

## Cleanup Behavior

| Option | What it removes | What it keeps |
|--------|-----------------|---------------|
| 4 (Stop) | Containers, Docker volumes | Bind-mounted data directories |
| 6 (Partial) | Containers, volumes, rclone plugin | Database data, XBVR config, rclone config/cache |
| 7 (Full) | Everything | Linux rclone config only |

## Notes

- The repo-root `.env` is legacy and not used by the current launcher
- Always pass `docker/.env` when using `docker compose` manually
- Media paths are Linux host paths defined in `docker/.env`
