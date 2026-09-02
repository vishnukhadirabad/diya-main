#!/usr/bin/env bash
#
# setup-kiosk.sh — install Diya Meditation as an auto-starting, locked-down kiosk
# on a GNOME-based Ubuntu desktop. Run as the kiosk user (NOT root) for the
# gsettings part; the install step uses sudo.
#
# Usage:
#   ./setup-kiosk.sh
#
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")/.." && pwd)/publish"
INSTALL_DIR="/opt/diya-meditation"

echo "==> Installing app to ${INSTALL_DIR}"
if [ ! -d "${APP_SRC}" ]; then
  echo "ERROR: ${APP_SRC} not found. Publish first:"
  echo "  dotnet publish -c Release -r linux-x64 --self-contained true \\"
  echo "    -p:PublishSingleFile=true -o ./publish"
  exit 1
fi
sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r "${APP_SRC}/." "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}/DiyaMeditation"

echo "==> Installing Python deps for the face-identify client"
# The bundled am-mock-client (vendor/am-mock-client) does local face detection +
# embedding via OpenCV; install its pinned deps for this kiosk user. python3 is a
# package dependency of the .deb, but pip packages are not — install them here.
REQ="${INSTALL_DIR}/vendor/am-mock-client/requirements.txt"
if [ -f "${REQ}" ]; then
  python3 -m pip install --user -r "${REQ}"
else
  echo "  WARNING: ${REQ} not found — is the am-mock-client submodule bundled?"
fi

echo "==> Preparing the report directory (/opt/meditation-app/data)"
# The external meditation-app writes the report PDF here, and Diya reads it back.
# Both run as this kiosk user, so hand the folder to this user (it lives under
# root-owned /opt). Override the location with DIYA_REPORT_DIR if needed.
REPORT_DIR="/opt/meditation-app/data"
sudo mkdir -p "${REPORT_DIR}"
sudo chown -R "$(whoami):$(whoami)" "/opt/meditation-app"

echo "==> Installing systemd user service (auto-start + auto-restart)"
mkdir -p "${HOME}/.config/systemd/user"
cp "$(dirname "$0")/diya-meditation.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable diya-meditation.service
# Allow the user service to run without an active login session (kiosk boots straight in)
sudo loginctl enable-linger "$(whoami)"

echo "==> Disabling GNOME shortcuts that could let a user escape the kiosk"
# Close window, app/window switching, and the activities overview.
gsettings set org.gnome.desktop.wm.keybindings close "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-applications "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-windows "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-applications-backward "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-windows-backward "[]"
gsettings set org.gnome.desktop.wm.keybindings panel-main-menu "[]"
gsettings set org.gnome.desktop.wm.keybindings panel-run-dialog "[]"
gsettings set org.gnome.mutter overlay-key ""
gsettings set org.gnome.shell.keybindings toggle-overview "[]"
gsettings set org.gnome.shell.keybindings toggle-application-view "[]"
gsettings set org.gnome.settings-daemon.plugins.media-keys terminal "[]"

echo
echo "Done. Notes:"
echo "  * Reboot (or 'systemctl --user start diya-meditation') to launch the kiosk."
echo "  * Secret exit shortcut: Ctrl + Shift + Alt + Q"
echo "  * To block TTY switching (Ctrl+Alt+F1-F7), add to /etc/X11/xorg.conf.d:"
echo '      Section "ServerFlags"'
echo '        Option "DontVTSwitch" "true"'
echo '      EndSection'
echo "  * Enable GNOME automatic login (Settings > Users) so it boots straight in."
