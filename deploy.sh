#!/usr/bin/env bash
# Deploy the project to the MatrixPortal's CIRCUITPY drive (D:\ on Windows).
#
#   src/hardware/code.py        ->  D:\code.py
#   src/hardware/settings.toml  ->  D:\settings.toml  (if present; holds WiFi + HA token)
#   src/*                       ->  D:\src\   (minus __pycache__, simulator/, run.py, hardware/)
#   FILE (--state FILE)         ->  D:\state.json  (imported by the board at its next start)
#
# Usage:  ./deploy.sh [--clean] [--no-code] [--no-settings] [--state FILE]
#   --clean        also delete files in D:\src\ that no longer exist in src/
#   --no-code      skip copying code.py (only update D:\src\)
#   --no-settings  skip copying settings.toml (keep the board's own copy)
#   --state FILE   copy FILE (e.g. from tools/pull_state.py or the simulator's
#                  state.json) to CIRCUITPY/state.json
#
# Override the drive letter / mount point with DRIVE=E ./deploy.sh
# or MOUNT=/some/path ./deploy.sh.

set -euo pipefail

DRIVE="${DRIVE:-D}"
MOUNT="${MOUNT:-/mnt/$(echo "$DRIVE" | tr '[:upper:]' '[:lower:]')}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

USAGE="Usage: $0 [--clean] [--no-code] [--no-settings] [--state FILE]"
CLEAN=()
COPY_CODE=1
COPY_SETTINGS=1
STATE=""
while (( $# )); do
    case "$1" in
        --clean)   CLEAN=(--delete) ;;
        --no-code) COPY_CODE=0 ;;
        --no-settings) COPY_SETTINGS=0 ;;
        --state)
            [[ $# -ge 2 ]] || { echo "--state needs a FILE" >&2; echo "$USAGE" >&2; exit 2; }
            STATE="$2"; shift ;;
        *) echo "Unknown option: $1" >&2; echo "$USAGE" >&2; exit 2 ;;
    esac
    shift
done
if [[ -n "$STATE" && ! -f "$STATE" ]]; then
    echo "error: --state file $STATE not found" >&2
    exit 2
fi

# WSL doesn't automount removable drives, so mount the board if needed.
if [[ ! -d "$MOUNT" ]] || [[ -z "$(ls -A "$MOUNT" 2>/dev/null)" ]]; then
    echo "Mounting ${DRIVE}: at $MOUNT (needs sudo)..."
    sudo mkdir -p "$MOUNT"
    sudo mount -t drvfs "${DRIVE}:" "$MOUNT" -o uid="$(id -u)",gid="$(id -g)"
fi

if [[ ! -f "$MOUNT/boot_out.txt" ]]; then
    echo "warning: $MOUNT/boot_out.txt not found -- is this really the CIRCUITPY drive?" >&2
    read -r -p "Continue anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# FAT timestamps have 2s resolution, hence --modify-window.
RSYNC=(rsync -rt --modify-window=2 --itemize-changes)

# src/ goes first so the auto-reload triggered by code.py sees the new modules.
echo "Copying src/..."
mkdir -p "$MOUNT/src"
"${RSYNC[@]}" "${CLEAN[@]}" \
    --exclude='__pycache__/' \
    --exclude='/simulator/' \
    --exclude='/run.py' \
    --exclude='/hardware/' \
    "$ROOT/src/" "$MOUNT/src/"

# Before code.py, so the reload it triggers already sees the new settings.
SETTINGS="$ROOT/src/hardware/settings.toml"
if (( ! COPY_SETTINGS )); then
    echo "Skipping settings.toml (--no-settings)."
elif [[ -f "$SETTINGS" ]]; then
    echo "Copying settings.toml..."
    "${RSYNC[@]}" "$SETTINGS" "$MOUNT/settings.toml"
else
    echo "warning: $SETTINGS not found -- copy src/hardware/settings.toml.example there and fill it in." >&2
    echo "         Leaving the board's settings.toml as is." >&2
fi

# Also before code.py, so the reload imports it. The board only imports a
# file it hasn't imported before (it remembers the checksum).
if [[ -n "$STATE" ]]; then
    echo "Copying $STATE to state.json..."
    "${RSYNC[@]}" "$STATE" "$MOUNT/state.json"
fi

if (( COPY_CODE )); then
    echo "Copying code.py..."
    "${RSYNC[@]}" "$ROOT/src/hardware/code.py" "$MOUNT/code.py"
else
    echo "Skipping code.py (--no-code)."
fi

# Make sure everything is flushed to the board before it auto-reloads / is unplugged.
sync
echo "Done."
