#!/usr/bin/env bash
# Regravity Universal Unix Shell Installer
# Local execution:  ./install.sh
# Remote execution: curl -fsSL https://raw.githubusercontent.com/warhammered/regravity/main/install.sh | bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
PYTHON_CMD=""

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[!] Python 3 is required to install Regravity."
    echo "    Please install Python 3 using your system package manager."
    exit 1
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/install.py" ]; then
    exec "$PYTHON_CMD" "$SCRIPT_DIR/install.py" "$@"
fi

# Remote 1-Liner Installation Flow
echo ""
echo "  ==============================================================="
echo "    Regravity - Native Multi-Account Manager for Antigravity     "
echo "    Remote 1-Liner Installer                                      "
echo "  ==============================================================="
echo ""

TEMP_DIR=$(mktemp -d /tmp/regravity-install-XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "[i] Fetching latest Regravity release from GitHub..."
TAR_URL="https://github.com/warhammered/regravity/archive/refs/heads/main.tar.gz"
curl -fsSL "$TAR_URL" -o "$TEMP_DIR/regravity.tar.gz"

echo "[i] Extracting package..."
tar -xzf "$TEMP_DIR/regravity.tar.gz" -C "$TEMP_DIR"

EXTRACTED_DIR="$TEMP_DIR/regravity-main"
if [ ! -f "$EXTRACTED_DIR/install.py" ]; then
    EXTRACTED_DIR=$(find "$TEMP_DIR" -name "install.py" -exec dirname {} \; | head -n 1)
fi

echo "[i] Launching installer..."
exec "$PYTHON_CMD" "$EXTRACTED_DIR/install.py" "$@"
