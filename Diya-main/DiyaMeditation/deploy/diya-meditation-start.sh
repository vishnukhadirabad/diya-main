#!/bin/sh
#
# diya-meditation-start.sh — launch wrapper used by the XDG autostart entry.
#
# Installed to ~/.local/bin by setup-autostart.sh. It exists because the
# Desktop Entry spec forbids the ';', '>', '&' and quote characters in Exec=,
# so the delay, environment and log redirect cannot live in the .desktop file.

# Let the Wayland/GNOME session finish coming up. Launching too early makes
# the app fail silently with no window and no error.
sleep "${DIYA_START_DELAY:-4}"

# Online registration API the kiosk fetches scanned passes from.
export DIYA_API_BASE="${DIYA_API_BASE:-https://diya-registration.onrender.com}"

exec /opt/diya-meditation/DiyaMeditation >"${DIYA_LOG:-/tmp/diya.log}" 2>&1
