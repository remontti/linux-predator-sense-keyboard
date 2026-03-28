#!/usr/bin/env bash

set -euo pipefail

INSTALL_DIR="/opt/Linux Predator Sense Keyboard"
BIN_WRAPPER="/usr/local/bin/linux-predator-sense-keyboard"
CLI_WRAPPER="/usr/local/bin/linux-predator-sense-keyboard-rgb"
DESKTOP_FILE="/usr/share/applications/linux-predator-sense-keyboard.desktop"
ICON_FILE="/usr/share/icons/hicolor/scalable/apps/linux-predator-sense-keyboard.svg"
UDEV_RULE="/etc/udev/rules.d/99-linux-predator-sense-keyboard.rules"
PURGE_CONFIG="${1:-}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this uninstaller with sudo."
    exit 1
fi

echo "Removing installed files..."
rm -rf "${INSTALL_DIR}"
rm -f "${BIN_WRAPPER}"
rm -f "${CLI_WRAPPER}"
rm -f "${DESKTOP_FILE}"
rm -f "${ICON_FILE}"
rm -f "${UDEV_RULE}"

udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true

if [[ "${PURGE_CONFIG}" == "--purge-config" ]] && [[ -n "${SUDO_USER:-}" ]]; then
    USER_HOME="$(getent passwd "${SUDO_USER}" | cut -d: -f6)"
    if [[ -n "${USER_HOME}" ]]; then
        rm -rf "${USER_HOME}/.config/linux-predator-sense-keyboard"
        echo "Removed user config from ${USER_HOME}/.config/linux-predator-sense-keyboard"
    fi
fi

echo "Uninstall complete."
