#!/usr/bin/env bash
# Deploy the project to the MatrixPortal's CIRCUITPY drive (D:\ on Windows).
#
#   src/hardware/code.py        ->  D:\code.py
#   src/hardware/settings.toml  ->  D:\settings.toml  (if present; holds WiFi + HA token)
#   src/*                       ->  D:\src\   (minus __pycache__, simulator/, run.py, hardware/)
#
# Usage:  ./deploy.sh [--clean] [--no-code] [--no-settings]
#   --clean        also delete files in D:\src\ that no longer exist in src/
#   --no-code      skip copying code.py (only update D:\src\)
#   --no-settings  skip copying settings.toml (keep the board's own copy)
#
# Override the drive letter / mount point with DRIVE=E ./deploy.sh
# or MOUNT=/some/path ./deploy.sh.

set -euo pipefail

DRIVE="${DRIVE:-D}"
MOUNT="${MOUNT:-/mnt/$(echo "$DRIVE" | tr '[:upper:]' '[:lower:]')}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLEAN=()
COPY_CODE=1
COPY_SETTINGS=1
for arg in "$@"; do
    case "$arg" in
        --clean)   CLEAN=(--delete) ;;
        --no-code) COPY_CODE=0 ;;
        --no-settings) COPY_SETTINGS=0 ;;
        *) echo "Unknown option: $arg" >&2; echo "Usage: $0 [--clean] [--no-code] [--no-settings]" >&2; exit 2 ;;
    esac
done

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

if (( COPY_CODE )); then
    echo "Copying code.py..."
    "${RSYNC[@]}" "$ROOT/src/hardware/code.py" "$MOUNT/code.py"
else
    echo "Skipping code.py (--no-code)."
fi

# Make sure everything is flushed to the board before it auto-reloads / is unplugged.
sync
echo "Done."
