#!/bin/bash
# Run ONCE on an offline machine AFTER installing the .deb to install
# bundled ffmpeg, mpv, feh, and RealSense packages.
# Usage:  sudo /opt/meditation-app/install_offline.sh

[[ "$EUID" -eq 0 ]] || { echo "Run with sudo"; exit 1; }
BASE="/opt/meditation-app"
DEB_DIR="$BASE/deps/debs"

if ! ls "$DEB_DIR"/*.deb &>/dev/null 2>&1; then
    echo "No bundled .deb files found – dependencies may already be installed."
    exit 0
fi

echo "Installing bundled packages offline (dpkg)…"
dpkg -i --force-depends "$DEB_DIR"/*.deb 2>&1 | grep -E "(installed|error|warning)" || true

udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

echo "Done.  Run: meditation-app"
