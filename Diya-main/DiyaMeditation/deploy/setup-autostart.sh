#!/usr/bin/env bash
#
# setup-autostart.sh — make the kiosk launch at login, and optionally log the
# kiosk user in automatically so the machine boots straight into the app.
#
# Run as the kiosk user (NOT root). The autologin step uses sudo.
#
# Usage:
#   ./setup-autostart.sh              # autostart entry only
#   ./setup-autostart.sh --autologin  # also enable GDM automatic login
#
# Alternative: the .deb ships a systemd user service that does the same job and
# adds Restart=always, so the app relaunches if it crashes:
#   systemctl --user enable --now diya-meditation
# Use one or the other — enabling both launches the app twice.
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
AUTOSTART_DIR="${HOME}/.config/autostart"
WRAPPER="${BIN_DIR}/diya-meditation-start.sh"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing launch wrapper to ${WRAPPER}"
mkdir -p "${BIN_DIR}"
install -m 755 "${HERE}/diya-meditation-start.sh" "${WRAPPER}"

echo "==> Writing autostart entry to ${AUTOSTART_DIR}"
mkdir -p "${AUTOSTART_DIR}"
cat > "${AUTOSTART_DIR}/diya-meditation.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Diya Meditation
Exec=${WRAPPER}
X-GNOME-Autostart-enabled=true
Terminal=false
EOF

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "${AUTOSTART_DIR}/diya-meditation.desktop"
  echo "    entry is spec-compliant"
fi

if [ ! -x /opt/diya-meditation/DiyaMeditation ]; then
  echo "    WARNING: /opt/diya-meditation/DiyaMeditation not found."
  echo "             Install the package first, or autostart will do nothing:"
  echo "               sudo dpkg -i package/diya-meditation_1.5.0_amd64.deb"
fi

if [ "${1:-}" = "--autologin" ]; then
  CONF=/etc/gdm3/custom.conf
  echo "==> Enabling GDM automatic login for ${USER}"
  if [ ! -f "${CONF}" ]; then
    echo "    ERROR: ${CONF} not found — is GDM the display manager?" >&2
    exit 1
  fi
  # Edit in place rather than rewriting the file: a plain 'tee > custom.conf'
  # discards the [security] and [debug] sections GDM also reads.
  sudo cp -n "${CONF}" "${CONF}.bak"
  sudo sed -i \
    -e "s/^#\s*AutomaticLoginEnable\s*=.*/AutomaticLoginEnable=true/" \
    -e "s/^#\s*AutomaticLogin\s*=.*/AutomaticLogin=${USER}/" \
    "${CONF}"
  echo "    backup at ${CONF}.bak"
  grep -E '^Automatic' "${CONF}" | sed 's/^/    /'
fi

echo
echo "Done. Reboot to test. If the app does not appear, check /tmp/diya.log"
