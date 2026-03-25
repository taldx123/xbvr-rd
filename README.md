# XBVR Stack

Docker-based XBVR deployment with MariaDB, XBVR application, and Real-Debrid mounting via the `rclone` Docker volume plugin.

## Project Structure

```
.
├── docker/
│   ├── docker-compose.yml
│   └── mariadb/my.cnf
├── linux/
│   ├── .env
│   └── xbvr-manager.sh
├── windows/
│   ├── .env
│   ├── XBVR-Manager.bat
│   └── xbvr-manager.ps1
└── data/
    ├── mariadb/
    ├── xbvr/
    └── rclone/
        ├── cache/
        └── config/
```

The same `docker/docker-compose.yml` is shared by both operating systems. Each OS has its own launcher and `.env` file.

## Requirements

### All Platforms

- Docker with `docker compose` plugin
- Real-Debrid API key
- Existing media paths for `TS_PATH` and `JAV_PATH`

### Linux

- `bash`
- `fuse` or `fuse3` (for rclone plugin)

### Windows

- Docker Desktop
- PowerShell 5.1+

## Environment Variables

Each platform has its own `.env` file (`linux/.env` or `windows/.env`). Copy the template below and adjust values for your setup.

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

# --- Media library paths -----------------------------------
# Linux example:
TS_PATH='/media/xxx/Local Disk1/TS'
JAV_PATH='/media/xxx/Local Disk1/JAV'

# Windows example:
# TS_PATH='D:\TS'
# JAV_PATH='D:\JAV'
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
| `TS_PATH` | Path to TS media library | OS-specific |
| `JAV_PATH` | Path to JAV media library | OS-specific |

## Setup

### 1. Configure Environment

Edit the `.env` file for your platform:

- **Linux:** `linux/.env`
- **Windows:** `windows/.env`

At minimum, set:
- `RD_API_KEY` with your Real-Debrid API key
- `MARIADB_PASSWORD` to a secure password
- `TS_PATH` and `JAV_PATH` to your media directories

### 2. Run the Launcher

**Linux:**
```bash
chmod +x linux/xbvr-manager.sh
./linux/xbvr-manager.sh
```

**Windows:**
```
windows\XBVR-Manager.bat
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
| 6 | Partial cleanup (containers, volumes, rclone plugin) |
| 7 | Full cleanup (keeps rclone config on Linux) |
| 8 | View live logs |

## Access

XBVR is available at `http://localhost:9999` (default port).

## Manual Docker Commands

Run from the `docker/` directory:

**Linux:**
```bash
docker compose --env-file ../linux/.env up -d
docker compose --env-file ../linux/.env logs -f
docker compose --env-file ../linux/.env down -v
```

**Windows:**
```powershell
docker compose --env-file ../windows/.env up -d
docker compose --env-file ../windows/.env logs -f
docker compose --env-file ../windows/.env down -v
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
${TS_PATH}  -> /videos/TS
${JAV_PATH} -> /videos/JAV
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

- The repo-root `.env` is legacy and not used by current launchers
- Always pass the correct env file when using `docker compose` manually
- Media paths are OS-specific and defined in each platform's `.env` file
