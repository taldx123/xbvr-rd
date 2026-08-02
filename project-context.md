---
project_name: 'xbvr'
user_name: 'Maicon'
date: '2026-08-02'
sections_completed:
  ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 18
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Docker & Docker Compose**: Standard host requirements.
- **MariaDB**: `mariadb:lts`
- **XBVR**: `xbvr:latest`
- **Python**: `python3` (specifically used for host helper scripts like `download_cuepoints.py`)
- **Bash Scripting**: `#!/usr/bin/env bash` using strict error handling.
- **Rclone Plugin**: `itstoggle/docker-volume-rclone_rd:amd64` (critical dependency for Real-Debrid mounts)

## Critical Implementation Rules

### Language-Specific Rules

**Bash/Shell Scripting:**
- **Strict Error Handling:** Scripts must start with `set -euo pipefail` (or at least `set -u`) to catch uninitialized variables and pipeline errors.
- **Portability:** Always use `#!/usr/bin/env bash` rather than hardcoding `/bin/bash`.
- **Variable Quoting:** All variables must be strictly quoted (`"$VAR"`) to prevent word splitting.

**YAML (Docker Compose):**
- **Read-Only Mounts:** Always include the `:ro` suffix for configuration file bind mounts (e.g., `my.cnf`) to protect host files.
- **Variable Escaping:** In `healthcheck` commands, any `$` variable must be escaped with `$$` (e.g., `$$MARIADB_USER`).
- **Env Variable Interpolation:** Always use `${VAR_NAME}` syntax for explicitly mapping environment variables into configuration blocks.

### Framework-Specific Rules (Orchestration)

- **Rclone Plugin Requirement:** The `itstoggle/docker-volume-rclone_rd:amd64` Docker plugin must be installed on the host with full permissions before the stack can be deployed, as the `realdebrid` volume driver relies on it.
- **Interactive Management:** All stack management (start, stop, cleanup, cache reset) should go through the `xbvr-manager` script to ensure data directories are properly permissioned and caches are cleared.
- **Explicit Env File:** `docker compose` commands must always explicitly pass `--env-file .env` when run from the `docker/` directory, rather than relying on default behaviors.

### Testing Rules (Integration & Validation)

- **Docker Healthchecks:** Formal test frameworks are not used in this configuration repository. All validation is handled via Docker Compose `healthcheck` definitions.
- **Service Dependency Validation:** Services must use `depends_on` with `condition: service_healthy` to ensure dependent databases (MariaDB) are fully initialized before dependent applications (XBVR) are started.
- **Application-Level Checks:** Healthchecks should test application responsiveness (e.g., calling an API endpoint) rather than simply checking if a port is open.

### Code Quality & Style Rules

**YAML (Docker Compose):**
- **Indentation:** Use 2-space indentation strictly.
- **Section Headers:** Use dashed header comments (e.g., `# --- Section ---`) to group related services, volumes, or variables.

**Code Organization:**
- **Strict Separation:** Orchestration configurations go in `docker/`. All persistent states and caches go in `data/` (e.g., `data/mariadb`, `data/xbvr`), and backups go in `backup/`. Both of these directories must remain gitignored.

**Documentation:**
- **Script Help:** Any executable shell script must have usage/help text.
- **Comment Intent:** Comments must explain *why* a particular setting or script block exists, rather than *what* it does.

### Development Workflow Rules

**Pre-Deployment Validation:**
- **Configuration Checks:** Always validate `docker-compose.yml` syntax and `.env` variable existence before deploying a stack to avoid runtime crashes.

**Deployment Patterns:**
- **Manager Script Execution:** Deployment workflows (initialization, stopping, caching resets) should use the `docker/xbvr-manager` interactive script. 
- **Context Awareness:** Manual `docker compose` commands must always be run explicitly from the `docker/` directory (e.g., `cd docker && docker compose --env-file .env up -d`).

**Cleanups:**
- **Rclone Cache Resets:** When destroying the stack, ensure the Rclone plugin cache is properly cleared (handled in the manager script) to avoid orphaned FUSE mounts.

### Critical Don't-Miss Rules

**Anti-Patterns:**
- **No Application Code:** This repository is strictly for configuration. Do not attempt to write or edit application code here.
- **No Root .env Loading:** Do not use or rely on a root-level `.env` file. It is legacy. All environment configuration must route through `docker/.env`.

**Edge Cases:**
- **Database Migration Credentials:** When migrating `data/mariadb` from another machine, the users are not recreated. The `MARIADB_USER` and `MARIADB_PASSWORD` in `.env` must exactly match the existing migrated database users, or the service will remain unhealthy.
- **Binary Permissions:** If migrating the `data/xbvr` folder, execution bits for bundled binaries might be lost. If `ffmpeg` or `ffprobe` fail with permission denied, explicitly `chmod 755` those binaries in `data/xbvr/bin/`.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**

- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time

Last Updated: 2026-08-02
