#!/usr/bin/env bash
#
# Starts a virtual display, a VNC server, and a noVNC web bridge, then launches
# the app. View it in your browser at http://localhost:8080/vnc.html
#
set -e

# Virtual X display
Xvfb :99 -screen 0 1360x768x24 >/dev/null 2>&1 &
sleep 1

# VNC server exposing that display
x11vnc -display :99 -forever -nopw -shared -quiet >/dev/null 2>&1 &

# noVNC web client (browser) on port 8080 -> VNC on 5900
websockify --web=/usr/share/novnc 8080 localhost:5900 >/dev/null 2>&1 &

echo "==================================================================="
echo "  Diya Meditation preview is starting."
echo "  Open:  http://localhost:8080/vnc.html   (click Connect)"
echo "  Exit the app inside the view with: Ctrl+Shift+Alt+Q"
echo "==================================================================="

# Run the app on the virtual display (foreground = keeps container alive)
exec dotnet /app/DiyaMeditation.dll
