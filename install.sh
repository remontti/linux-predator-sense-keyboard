#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/Linux Predator Sense Keyboard"
BIN_WRAPPER="/usr/local/bin/linux-predator-sense-keyboard"
CLI_WRAPPER="/usr/local/bin/linux-predator-sense-keyboard-rgb"
DESKTOP_FILE="/usr/share/applications/linux-predator-sense-keyboard.desktop"
ICON_FILE="/usr/share/icons/hicolor/scalable/apps/linux-predator-sense-keyboard.svg"
UDEV_RULE="/etc/udev/rules.d/99-linux-predator-sense-keyboard.rules"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo."
    exit 1
fi

echo "Installing Debian packages..."
apt-get update
apt-get install -y python3 python3-pyside6.qtwidgets python3-pyside6.qtsvg pkexec

echo "Copying application to ${INSTALL_DIR}..."
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cp -a "${PROJECT_DIR}/app" "${INSTALL_DIR}/"
cp -a "${PROJECT_DIR}/assets" "${INSTALL_DIR}/"
cp -a "${PROJECT_DIR}/scripts" "${INSTALL_DIR}/"
cp -a "${PROJECT_DIR}/README.md" "${INSTALL_DIR}/README.md"

install -Dm755 /dev/stdin "${BIN_WRAPPER}" <<'EOF'
#!/usr/bin/env bash
exec python3 "/opt/Linux Predator Sense Keyboard/scripts/predator-sense-app.py" "$@"
EOF

install -Dm755 /dev/stdin "${CLI_WRAPPER}" <<'EOF'
#!/usr/bin/env bash
exec python3 "/opt/Linux Predator Sense Keyboard/scripts/predator-rgb-hid.py" "$@"
EOF

install -Dm644 "${PROJECT_DIR}/packaging/linux-predator-sense-keyboard.desktop" "${DESKTOP_FILE}"
install -Dm644 "${PROJECT_DIR}/assets/linux-predator-sense-keyboard.svg" "${ICON_FILE}"
install -Dm644 "${PROJECT_DIR}/packaging/99-linux-predator-sense-keyboard.rules" "${UDEV_RULE}"

echo "Reloading desktop and udev metadata..."
udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true

echo
echo "Install complete."
echo "App directory: ${INSTALL_DIR}"
echo "Launcher: ${BIN_WRAPPER}"
echo "CLI: ${CLI_WRAPPER}"
echo
echo "The app is expected to run as a normal user after the udev rule is applied."
echo "If access still fails, log out and log back in once, then test again."
echo "pkexec remains available only as a fallback if direct HID access is still blocked."
