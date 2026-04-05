#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
DOCKER_DIR="${PROJECT_ROOT}/docker"
COMPOSE_FILE="${DOCKER_DIR}/docker-compose.yml"
MARIADB_DATA_DIR="${PROJECT_ROOT}/data/mariadb"
XBVR_DATA_DIR="${PROJECT_ROOT}/data/xbvr"
RCLONE_DIR="${PROJECT_ROOT}/data/rclone"
RCLONE_CONFIG_DIR="${RCLONE_DIR}/config"
RCLONE_CACHE_DIR="${RCLONE_DIR}/cache"

DIRS=(
  "${MARIADB_DATA_DIR}"
  "${XBVR_DATA_DIR}"
  "${RCLONE_CONFIG_DIR}"
  "${RCLONE_CACHE_DIR}"
)

if [[ -t 1 ]]; then
  COLOR_CYAN=$'\033[36m'
  COLOR_YELLOW=$'\033[33m'
  COLOR_GREEN=$'\033[32m'
  COLOR_RED=$'\033[31m'
  COLOR_DARKGRAY=$'\033[90m'
  COLOR_DARKCYAN=$'\033[36m'
  COLOR_RESET=$'\033[0m'
else
  COLOR_CYAN=''
  COLOR_YELLOW=''
  COLOR_GREEN=''
  COLOR_RED=''
  COLOR_DARKGRAY=''
  COLOR_DARKCYAN=''
  COLOR_RESET=''
fi

write_line() {
  local color="$1"
  shift
  printf '%s%s%s\n' "${color}" "$*" "${COLOR_RESET}"
}

write_header() {
  clear 2>/dev/null || true
  write_line "${COLOR_CYAN}" "================================================="
  write_line "${COLOR_CYAN}" "              XBVR Stack Manager                 "
  write_line "${COLOR_CYAN}" "================================================="
  write_line "${COLOR_DARKGRAY}" " Project root: ${PROJECT_ROOT}"
  printf '\n'
}

read_env_value() {
  local key="$1"
  [[ -f "${ENV_FILE}" ]] || return 0

  local line
  line="$(grep -m1 -E "^[[:space:]]*${key}[[:space:]]*=" "${ENV_FILE}" || true)"
  [[ -n "${line}" ]] || return 0

  line="${line#*=}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s\n' "${line}"
}

confirm_docker_running() {
  if ! docker info >/dev/null 2>&1; then
    write_line "${COLOR_RED}" "ERROR: Docker is not running. Please start it first."
    return 1
  fi
}

pause_for_user() {
  printf '\n'
  write_line "${COLOR_DARKGRAY}" "Press Enter to return to the menu..."
  read -r _
}

ensure_directories() {
  local dir
  for dir in "$@"; do
    if [[ ! -d "${dir}" ]]; then
      mkdir -p "${dir}"
      write_line "${COLOR_GREEN}" "  Created: ${dir}"
    else
      write_line "${COLOR_DARKGRAY}" "  Already exists: ${dir}"
    fi
  done
}

ensure_rclone_plugin_dirs() {
  write_line "${COLOR_YELLOW}" "Ensuring rclone plugin directories exist..."
  ensure_directories "${RCLONE_CONFIG_DIR}" "${RCLONE_CACHE_DIR}"
  printf '\n'
}

reset_rclone_cache_dir() {
  write_line "${COLOR_YELLOW}" "Resetting ${RCLONE_CACHE_DIR} ..."
  mkdir -p "${RCLONE_CACHE_DIR}"

  if find "${RCLONE_CACHE_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null; then
    write_line "${COLOR_GREEN}" "  Cache directory emptied."
    return 0
  fi

  if command -v sudo >/dev/null 2>&1; then
    write_line "${COLOR_DARKGRAY}" "  Some cache entries need elevated permissions. You may be prompted for sudo."
    if sudo find "${RCLONE_CACHE_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; then
      write_line "${COLOR_GREEN}" "  Cache directory emptied."
      return 0
    fi
  fi

  write_line "${COLOR_RED}" "ERROR: Failed to clear ${RCLONE_CACHE_DIR}."
  write_line "${COLOR_DARKGRAY}" "  The rclone plugin created entries owned by another user."
  return 1
}

initialize_directories() {
  write_line "${COLOR_YELLOW}" "Creating required directories under ${PROJECT_ROOT} ..."
  ensure_directories "${DIRS[@]}"
  printf '\n'
  write_line "${COLOR_GREEN}" "OK: Directories ready."
  pause_for_user
}

find_rclone_plugin() {
  docker plugin ls --format '{{.Name}}' 2>/dev/null | grep -i 'rclone' || true
}

install_rclone_plugin() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "Checking if rclone plugin is already installed..."
  local existing
  existing="$(find_rclone_plugin)"
  if [[ -n "${existing}" ]]; then
    write_line "${COLOR_DARKGRAY}" "  Plugin already installed: ${existing}"
    pause_for_user
    return
  fi

  ensure_rclone_plugin_dirs

  write_line "${COLOR_YELLOW}" "Installing itstoggle/docker-volume-rclone_rd plugin..."
  write_line "${COLOR_DARKGRAY}" "  Config dir: ${RCLONE_CONFIG_DIR}"
  write_line "${COLOR_DARKGRAY}" "  Cache dir:  ${RCLONE_CACHE_DIR}"
  printf '\n'

  if docker plugin install itstoggle/docker-volume-rclone_rd:amd64 \
    args=-v \
    --alias rclone \
    --grant-all-permissions \
    config="${RCLONE_CONFIG_DIR}" \
    cache="${RCLONE_CACHE_DIR}"; then
    printf '\n'
    write_line "${COLOR_GREEN}" "OK: Plugin installed successfully."
  else
    write_line "${COLOR_RED}" "ERROR: Plugin installation failed."
    write_line "${COLOR_DARKGRAY}" "  If it still fails, confirm FUSE/FUSE3 is installed on the host."
  fi
  pause_for_user
}

verify_rclone_plugin() {
  local silent_if_exists="${1:-false}"
  local plugin
  plugin="$(find_rclone_plugin)"
  if [[ -z "${plugin}" ]]; then
    write_line "${COLOR_RED}" "ERROR: rclone plugin not found. Please install it first (option 2)."
    return 1
  fi

  if [[ "${silent_if_exists}" != "true" ]]; then
    write_line "${COLOR_GREEN}" "  rclone plugin is installed."
  fi
}

wait_for_xbvr_healthy() {
  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    write_line "${COLOR_RED}" "ERROR: docker-compose.yml not found at ${COMPOSE_FILE}"
    return 1
  fi

  write_line "${COLOR_DARKGRAY}" "  Waiting for XBVR to report healthy..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" up -d --wait --wait-timeout 180 xbvr
  )
}

start_stack() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    write_line "${COLOR_RED}" "ERROR: docker-compose.yml not found at ${COMPOSE_FILE}"
    pause_for_user
    return
  fi

  if ! verify_rclone_plugin true; then
    write_line "${COLOR_YELLOW}" "  Please install the rclone plugin first (option 2)."
    pause_for_user
    return
  fi

  printf '\n'
  write_line "${COLOR_YELLOW}" "Starting XBVR stack (MariaDB + XBVR)..."
  write_line "${COLOR_DARKGRAY}" "  Real-Debrid volume will be created by docker compose..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" up -d --wait --wait-timeout 180
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    write_line "${COLOR_GREEN}" "OK: Stack started."
    local port
    port="$(read_env_value "XBVR_PORT")"
    if [[ -z "${port}" ]]; then
      port="9999"
    fi
    local url="http://localhost:${port}"
    write_line "${COLOR_CYAN}" "  XBVR web UI --> ${url}"

    open_browser
  else
    write_line "${COLOR_RED}" "ERROR: Failed to start stack or XBVR did not become healthy."
  fi
  pause_for_user
}

stop_stack() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "Stopping XBVR stack..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" down -v
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    write_line "${COLOR_GREEN}" "OK: Stack stopped and volumes removed."
  else
    write_line "${COLOR_RED}" "ERROR: Failed to stop stack."
  fi
  pause_for_user
}

stop_stack_and_clear_cache() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "Stopping XBVR stack and clearing rclone cache..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" down -v
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    write_line "${COLOR_GREEN}" "OK: Stack stopped and volumes removed."
    if ! reset_rclone_cache_dir; then
      write_line "${COLOR_RED}" "WARNING: Stack stopped, but cache cleanup did not complete."
    fi
  else
    write_line "${COLOR_RED}" "ERROR: Failed to stop stack."
  fi
  pause_for_user
}

show_logs() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "Showing live logs (Ctrl+C to stop)..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" logs -f
  ) || true
  pause_for_user
}

restart_stack() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    write_line "${COLOR_RED}" "ERROR: docker-compose.yml not found at ${COMPOSE_FILE}"
    pause_for_user
    return
  fi

  write_line "${COLOR_YELLOW}" "Restarting the full XBVR stack..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" restart
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    if wait_for_xbvr_healthy; then
      printf '\n'
      write_line "${COLOR_GREEN}" "OK: Stack restarted."
      open_browser
    else
      printf '\n'
      write_line "${COLOR_RED}" "ERROR: XBVR did not become healthy after restart."
    fi
  else
    write_line "${COLOR_RED}" "ERROR: Failed to restart the stack."
  fi
  pause_for_user
}

restart_xbvr_service() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    write_line "${COLOR_RED}" "ERROR: docker-compose.yml not found at ${COMPOSE_FILE}"
    pause_for_user
    return
  fi

  write_line "${COLOR_YELLOW}" "Restarting XBVR service only..."
  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" restart xbvr
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    if wait_for_xbvr_healthy; then
      printf '\n'
      write_line "${COLOR_GREEN}" "OK: XBVR restarted."
      open_browser
    else
      printf '\n'
      write_line "${COLOR_RED}" "ERROR: XBVR did not become healthy after restart."
    fi
  else
    write_line "${COLOR_RED}" "ERROR: Failed to restart XBVR."
  fi
  pause_for_user
}

open_browser() {
  local port
  port="$(read_env_value "XBVR_PORT")"
  if [[ -z "${port}" ]]; then
    port="9999"
  fi
  local url="http://localhost:${port}"

  if command -v google-chrome >/dev/null 2>&1; then
    google-chrome --incognito "${url}" &
  elif command -v chromium >/dev/null 2>&1; then
    chromium --incognito "${url}" &
  elif command -v chromium-browser >/dev/null 2>&1; then
    chromium-browser --incognito "${url}" &
  fi
}

open_xbvr_chrome_incognito() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  if wait_for_xbvr_healthy; then
    printf '\n'
    open_browser
  else
    printf '\n'
    write_line "${COLOR_RED}" "ERROR: XBVR did not become healthy in time."
  fi
  pause_for_user
}

restart_menu() {
  while true; do
    write_header
    write_line "${COLOR_DARKCYAN}" "  RESTART"
    printf '%s\n' "  [1] Restart full stack"
    printf '%s\n' "  [2] Restart XBVR only"
    printf '%s\n' "  [B] Back"
    printf '\n'

    read -r -p "Choose an option: " restart_choice

    case "${restart_choice^^}" in
      1)
        restart_stack
        return
        ;;
      2)
        restart_xbvr_service
        return
        ;;
      B)
        return
        ;;
      *)
        write_line "${COLOR_RED}" "Invalid option. Please try again."
        sleep 1
        ;;
    esac
  done
}

invoke_partial_cleanup() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "================================================"
  write_line "${COLOR_YELLOW}" "   PARTIAL CLEANUP - Rclone plugin only         "
  write_line "${COLOR_YELLOW}" "================================================"
  printf '\n'
  printf '%s\n' "This will:"
  printf '%s\n' "  - Stop and remove all stack containers and volumes"
  printf '%s\n' "  - Uninstall the rclone Docker plugin"
  printf '%s\n' "  - Delete ${RCLONE_CACHE_DIR} contents"
  printf '\n'
  write_line "${COLOR_GREEN}" "This will NOT touch:"
  write_line "${COLOR_GREEN}" "  - ${MARIADB_DATA_DIR}  (your database)"
  write_line "${COLOR_GREEN}" "  - ${XBVR_DATA_DIR}  (your XBVR config)"
  write_line "${COLOR_GREEN}" "  - ${RCLONE_CONFIG_DIR}  (your rclone config)"
  printf '\n'
  read -r -p "Type YES to proceed: " confirm
  if [[ "${confirm}" != "YES" ]]; then
    write_line "${COLOR_DARKGRAY}" "Cancelled."
    pause_for_user
    return
  fi

  (
    cd "${DOCKER_DIR}" || exit 1
    printf '\n'
    write_line "${COLOR_YELLOW}" "Stopping containers and removing volumes..."
    docker compose --env-file "${ENV_FILE}" down -v >/dev/null 2>&1

    write_line "${COLOR_YELLOW}" "Disabling and removing rclone plugin..."
    docker plugin disable rclone >/dev/null 2>&1
    docker plugin rm rclone >/dev/null 2>&1
  )

  local cache_reset_failed="false"
  if ! reset_rclone_cache_dir; then
    cache_reset_failed="true"
  fi

  printf '\n'
  if [[ "${cache_reset_failed}" == "true" ]]; then
    write_line "${COLOR_RED}" "WARNING: Partial cleanup completed, but cache cleanup did not complete."
  else
    write_line "${COLOR_GREEN}" "OK: Partial cleanup complete."
  fi
  write_line "${COLOR_GREEN}" "  Your database, XBVR config and rclone config are untouched."
  write_line "${COLOR_CYAN}" "  To reconnect Real-Debrid, run options 2 then 3 again."
  pause_for_user
}

invoke_cleanup() {
  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_RED}" "================================================="
  write_line "${COLOR_RED}" "   WARNING: FULL CLEANUP - THIS IS DESTRUCTIVE   "
  write_line "${COLOR_RED}" "================================================="
  printf '\n'
  write_line "${COLOR_RED}" "This will:"
  write_line "${COLOR_RED}" "  - Stop and remove all stack containers and volumes"
  write_line "${COLOR_RED}" "  - Uninstall the rclone Docker plugin"
  write_line "${COLOR_RED}" "  - Delete ${MARIADB_DATA_DIR}  (all database files)"
  write_line "${COLOR_RED}" "  - Delete ${XBVR_DATA_DIR}  (all XBVR config and metadata)"
  write_line "${COLOR_RED}" "  - Delete ${RCLONE_CACHE_DIR}  (plugin cache/state)"
  printf '\n'
  printf '%s\n' "  This cannot be undone. ${RCLONE_CONFIG_DIR} will be kept."
  printf '\n'
  read -r -p "Type YES to proceed: " confirm
  if [[ "${confirm}" != "YES" ]]; then
    write_line "${COLOR_DARKGRAY}" "Cancelled."
    pause_for_user
    return
  fi

  (
    cd "${DOCKER_DIR}" || exit 1
    printf '\n'
    write_line "${COLOR_YELLOW}" "Stopping containers and removing volumes..."
    docker compose --env-file "${ENV_FILE}" down -v >/dev/null 2>&1

    write_line "${COLOR_YELLOW}" "Disabling and removing rclone plugin..."
    docker plugin disable rclone >/dev/null 2>&1
    docker plugin rm rclone >/dev/null 2>&1
  )

  write_line "${COLOR_YELLOW}" "Deleting ${MARIADB_DATA_DIR} ..."
  if [[ -d "${MARIADB_DATA_DIR}" ]]; then
    rm -rf "${MARIADB_DATA_DIR}"
    write_line "${COLOR_GREEN}" "  Deleted."
  else
    write_line "${COLOR_DARKGRAY}" "  Already gone."
  fi

  write_line "${COLOR_YELLOW}" "Deleting ${XBVR_DATA_DIR} ..."
  if [[ -d "${XBVR_DATA_DIR}" ]]; then
    rm -rf "${XBVR_DATA_DIR}"
    write_line "${COLOR_GREEN}" "  Deleted."
  else
    write_line "${COLOR_DARKGRAY}" "  Already gone."
  fi

  local port
  port="$(read_env_value "XBVR_PORT")"
  if [[ -z "${port}" ]]; then
    port="9999"
  fi
  local url="http://localhost:${port}"

  local cache_reset_failed="false"
  if ! reset_rclone_cache_dir; then
    cache_reset_failed="true"
  fi

  printf '\n'
  if [[ "${cache_reset_failed}" == "true" ]]; then
    write_line "${COLOR_RED}" "WARNING: Stack stopped, but cache cleanup did not complete."
  else
    write_line "${COLOR_GREEN}" "OK: Stack stopped and volumes removed."
  fi

  local should_open="${1:-false}"

  if [[ "${should_open}" == "true" ]]; then
    if command -v google-chrome >/dev/null 2>&1; then
      google-chrome --incognito "${url}" &
    elif command -v chromium >/dev/null 2>&1; then
      chromium --incognito "${url}" &
    elif command -v chromium-browser >/dev/null 2>&1; then
      chromium-browser --incognito "${url}" &
    fi
  fi

  pause_for_user
}

invoke_full_setup() {
  write_line "${COLOR_CYAN}" "Starting full setup (steps 1 through 3)..."
  printf '\n'

  write_line "${COLOR_YELLOW}" "[Step 1/3] Creating directories..."
  ensure_directories "${DIRS[@]}"
  write_line "${COLOR_GREEN}" "OK: Directories ready."
  printf '\n'

  confirm_docker_running || {
    pause_for_user
    return
  }

  write_line "${COLOR_YELLOW}" "[Step 2/3] Installing rclone_RD plugin..."
  local existing
  existing="$(find_rclone_plugin)"
  if [[ -n "${existing}" ]]; then
    write_line "${COLOR_DARKGRAY}" "  Plugin already installed: ${existing}"
  else
    if docker plugin install itstoggle/docker-volume-rclone_rd:amd64 \
      args=-v \
      --alias rclone \
      --grant-all-permissions \
      config="${RCLONE_CONFIG_DIR}" \
      cache="${RCLONE_CACHE_DIR}"; then
      write_line "${COLOR_GREEN}" "OK: Plugin installed."
    else
      write_line "${COLOR_RED}" "ERROR: Plugin installation failed."
      write_line "${COLOR_DARKGRAY}" "  If it still fails, confirm FUSE/FUSE3 is installed on the host."
      pause_for_user
      return
    fi
  fi
  printf '\n'

  write_line "${COLOR_YELLOW}" "[Step 3/3] Starting stack (volumes will be created by docker compose)..."
  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    write_line "${COLOR_RED}" "ERROR: docker-compose.yml not found at ${COMPOSE_FILE}"
    pause_for_user
    return
  fi

  (
    cd "${DOCKER_DIR}" || exit 1
    docker compose --env-file "${ENV_FILE}" up -d --wait --wait-timeout 180
  )
  local status=$?
  if [[ ${status} -eq 0 ]]; then
    printf '\n'
    write_line "${COLOR_GREEN}" "OK: Stack started."
    local port
    port="$(read_env_value "XBVR_PORT")"
    if [[ -z "${port}" ]]; then
      port="9999"
    fi
    local url="http://localhost:${port}"
    write_line "${COLOR_CYAN}" "  XBVR web UI --> ${url}"

    open_browser
  else
    write_line "${COLOR_RED}" "ERROR: Failed to start stack or XBVR did not become healthy."
  fi

  pause_for_user
}

while true; do
  write_header

  write_line "${COLOR_DARKCYAN}" "  SETUP"
  printf '%s\n' "  [0] Full setup  (runs steps 1 through 3 automatically)"
  printf '%s\n' "  [1] Create required directories"
  printf '%s\n' "  [2] Install rclone_RD Docker plugin"
  printf '\n'
  write_line "${COLOR_DARKCYAN}" "  DAILY USE"
  printf '%s\n' "  [3] Start stack  (volumes managed by docker compose)"
  printf '%s\n' "  [4] Stop stack + remove volumes"
  printf '%s\n' "  [5] Stop stack + remove volumes + clear rclone cache"
  printf '%s\n' "  [8] View live logs"
  printf '%s\n' "  [9] Restart menu  (full stack or XBVR only)"
  printf '%s\n' "  [O] Open XBVR in Chrome incognito"
  printf '\n'
  write_line "${COLOR_DARKCYAN}" "  MAINTENANCE"
  printf '%s\n' "  [6] Partial cleanup (remove plugin + clear cache)"
  printf '%s\n' "  [7] Full cleanup (remove everything including app data)"
  printf '\n'
  printf '%s\n' "  [Q] Quit"
  printf '\n'

  read -r -p "Choose an option: " choice

  case "${choice^^}" in
    0) invoke_full_setup ;;
    1) initialize_directories ;;
    2) install_rclone_plugin ;;
    3) start_stack ;;
    4) stop_stack ;;
    5) stop_stack_and_clear_cache ;;
    6) invoke_partial_cleanup ;;
    7) invoke_cleanup ;;
    8) show_logs ;;
    9) restart_menu ;;
    O) open_xbvr_chrome_incognito ;;
    Q)
      write_line "${COLOR_CYAN}" "Bye!"
      exit 0
      ;;
    *)
      write_line "${COLOR_RED}" "Invalid option. Please try again."
      sleep 1
      ;;
  esac
done
