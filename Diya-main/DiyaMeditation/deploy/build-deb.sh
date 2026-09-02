#!/usr/bin/env bash
#
# build-deb.sh — build a Debian/Ubuntu .deb package for Diya Meditation (amd64).
#
# Run on Ubuntu 24 (uses dpkg-deb), or on any system with `ar` + `tar` (fallback).
# The package bundles its own .NET runtime (self-contained), so the target
# machine does NOT need .NET installed.
#
# Usage:
#   ./deploy/build-deb.sh [version] [arch]
#     version : package version           (default: 1.5.0)
#     arch    : amd64 (x86 PCs) | arm64   (default: amd64)
#
# Examples:
#   ./deploy/build-deb.sh                 # 1.5.0, amd64 (x86 museum PC)
#   ./deploy/build-deb.sh 1.5.0 arm64     # arm64 (Apple Silicon VM / Raspberry Pi)
#
set -euo pipefail

VERSION="${1:-1.5.0}"
ARCH="${2:-amd64}"
PKG="diya-meditation"

case "${ARCH}" in
  amd64) RID="linux-x64" ;;
  arm64) RID="linux-arm64" ;;
  *) echo "ERROR: unsupported arch '${ARCH}' (use amd64 or arm64)"; exit 1 ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # the project directory
BUILD="${ROOT}/build"
STAGE="${BUILD}/${PKG}_${VERSION}_${ARCH}"
PUBLISH="${BUILD}/publish"

# The face-identify client is a git submodule (DiyaMeditation/vendor/am-mock-client).
# Submodules aren't checked out by default, and the csproj bundles client.py + its
# models/config from there — so make sure it's populated before publishing.
echo "==> Ensuring the am-mock-client submodule is checked out"
git -C "${ROOT}/.." submodule update --init --recursive DiyaMeditation/vendor/am-mock-client

echo "==> Publishing self-contained ${RID} build"
rm -rf "${BUILD}"
dotnet publish "${ROOT}/DiyaMeditation.csproj" -c Release -r "${RID}" \
  --self-contained true -p:PublishSingleFile=true -o "${PUBLISH}"

echo "==> Assembling package tree"
mkdir -p "${STAGE}/DEBIAN" \
         "${STAGE}/opt/${PKG}" \
         "${STAGE}/usr/share/applications" \
         "${STAGE}/usr/lib/systemd/user"

cp -r "${PUBLISH}/." "${STAGE}/opt/${PKG}/"
chmod +x "${STAGE}/opt/${PKG}/DiyaMeditation"

# Visible application launcher (shows up in the GNOME app grid)
cat > "${STAGE}/usr/share/applications/${PKG}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Diya Meditation
Comment=Meditation kiosk
Exec=/opt/${PKG}/DiyaMeditation
Terminal=false
Categories=Utility;
EOF

# systemd user service for kiosk auto-start (enable manually; see deploy/setup-kiosk.sh)
cp "${ROOT}/deploy/diya-meditation.service" "${STAGE}/usr/lib/systemd/user/${PKG}.service"

SIZE="$(du -sk "${STAGE}/opt" | cut -f1)"

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: ${PKG}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: libx11-6, libice6, libsm6, libfontconfig1, python3
Installed-Size: ${SIZE}
Maintainer: Ayush <ayush@example.com>
Description: Diya Meditation kiosk
 A fullscreen meditation kiosk application built with Avalonia and .NET 8.
 Bundles its own runtime (self-contained); no separate .NET install required.
EOF

cat > "${STAGE}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
chmod +x /opt/diya-meditation/DiyaMeditation
ln -sf /opt/diya-meditation/DiyaMeditation /usr/bin/diya-meditation
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database || true
EOF

cat > "${STAGE}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
rm -f /usr/bin/diya-meditation
EOF

chmod 0755 "${STAGE}/DEBIAN/postinst" "${STAGE}/DEBIAN/prerm"

OUT="${BUILD}/${PKG}_${VERSION}_${ARCH}.deb"

echo "==> Building .deb"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --root-owner-group --build "${STAGE}" "${OUT}"
else
  echo "    dpkg-deb not found — using ar/tar fallback"
  ( cd "${STAGE}/DEBIAN" && tar --owner=root --group=root -czf "${BUILD}/control.tar.gz" ./* )
  ( cd "${STAGE}" && tar --owner=root --group=root -czf "${BUILD}/data.tar.gz" --exclude=./DEBIAN ./* )
  printf '2.0\n' > "${BUILD}/debian-binary"
  ( cd "${BUILD}" && ar rc "${OUT}" debian-binary control.tar.gz data.tar.gz )
  rm -f "${BUILD}/control.tar.gz" "${BUILD}/data.tar.gz" "${BUILD}/debian-binary"
fi

echo
echo "Built: ${OUT}"
echo "Install on Ubuntu 24:  sudo apt install ${OUT}"
echo "Run:                   diya-meditation   (or launch it from the app menu)"
