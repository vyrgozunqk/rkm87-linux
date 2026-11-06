#!/usr/bin/env bash
#
# Royal Kludge RK M87 Linux Suite - Turnkey Installer & Uninstaller
#

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${RK_INSTALL_DIR:-$HOME/.RKLinux}"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"

# Usage help
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install, -i        Install the suite into $INSTALL_DIR (default action)"
    echo "  --uninstall, -u      Completely remove the suite, launcher, udev rules, and configuration"
    echo "  --yes, -y            Automatically answer yes to all confirmation prompts"
    echo "  --help, -h           Display this help message"
    echo ""
}

# Uninstall function
do_uninstall() {
    AUTO_CONFIRM="$1"
    echo -e "${BLUE}=====================================================${NC}"
    echo -e "${YELLOW}    Royal Kludge RK M87 Linux Suite - Uninstaller    ${NC}"
    echo -e "${BLUE}=====================================================${NC}"
    echo ""

    # 1. Clean up any obsolete background systemd service
    echo -e "${BLUE}[1/6] Checking for background systemd services...${NC}"
    systemctl --user stop rkm87.service 2>/dev/null || true
    systemctl --user disable rkm87.service 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/rkm87.service"
    systemctl --user daemon-reload 2>/dev/null || true
    echo -e "      ${GREEN}✓ Systemd service cleanup complete.${NC}"

    # 2. Remove desktop launcher and icons
    echo -e "${BLUE}[2/6] Removing desktop application launcher and icons...${NC}"
    rm -f "$DESKTOP_DIR/rkm87.desktop"
    rm -f "$ICON_DIR/rkm87.png"
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi
    echo -e "      ${GREEN}✓ Desktop launcher and icons removed.${NC}"

    # 3. Remove command binaries from ~/.local/bin
    echo -e "${BLUE}[3/6] Removing executable commands from $BIN_DIR...${NC}"
    rm -f "$BIN_DIR/rkm87" "$BIN_DIR/rkm87-cli" "$BIN_DIR/rkm87-gui"
    echo -e "      ${GREEN}✓ rkm87 command binaries removed.${NC}"

    # 4. Remove autostart entry and configs
    echo -e "${BLUE}[4/6] Removing desktop autostart configuration...${NC}"
    rm -f "$HOME/.config/autostart/rkm87.desktop"
    rm -rf "$HOME/.config/rkm87" 2>/dev/null || true
    echo -e "      ${GREEN}✓ Autostart and user configs removed.${NC}"

    # 5. Remove udev rules
    echo -e "${BLUE}[5/6] Removing udev hardware rules...${NC}"
    if [ -f "$UDEV_RULE_FILE" ]; then
        if [ "$EUID" -eq 0 ]; then
            rm -f "$UDEV_RULE_FILE"
            udevadm control --reload-rules && udevadm trigger 2>/dev/null || true
            echo -e "      ${GREEN}✓ udev rules removed and reloaded.${NC}"
        elif sudo -n true 2>/dev/null; then
            sudo rm -f "$UDEV_RULE_FILE"
            sudo udevadm control --reload-rules && sudo udevadm trigger 2>/dev/null || true
            echo -e "      ${GREEN}✓ udev rules removed and reloaded.${NC}"
        else
            if sudo rm -f "$UDEV_RULE_FILE" 2>/dev/null; then
                sudo udevadm control --reload-rules && sudo udevadm trigger 2>/dev/null || true
                echo -e "      ${GREEN}✓ udev rules removed and reloaded.${NC}"
            else
                echo -e "      ${YELLOW}Notice: Remove $UDEV_RULE_FILE manually: sudo rm $UDEV_RULE_FILE${NC}"
            fi
        fi
    else
        echo -e "      ${GREEN}✓ No udev rules found in $UDEV_RULE_FILE.${NC}"
    fi

    # 6. Remove installation directory (~/.RKLinux)
    echo -e "${BLUE}[6/6] Removing installation directory ($INSTALL_DIR)...${NC}"
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo -e "      ${GREEN}✓ Removed $INSTALL_DIR.${NC}"
    else
        echo -e "      ${GREEN}✓ $INSTALL_DIR was not present.${NC}"
    fi

    # Optional: Clean repo virtualenv if running from dev directory
    if [ -d "$PROJECT_DIR/.venv" ] && [ "$PROJECT_DIR" != "$INSTALL_DIR" ]; then
        if [ "$AUTO_CONFIRM" = "true" ]; then
            rm -rf "$PROJECT_DIR/.venv"
            echo -e "      ${GREEN}✓ Local repository virtual environment removed.${NC}"
        else
            read -rp "      Remove development virtual environment in repository ($PROJECT_DIR/.venv)? [y/N]: " REMOVE_DEV_VENV
            if [[ "$REMOVE_DEV_VENV" =~ ^[Yy]$ ]]; then
                rm -rf "$PROJECT_DIR/.venv"
                echo -e "      ${GREEN}✓ Development virtual environment removed.${NC}"
            fi
        fi
    fi

    echo ""
    echo -e "${GREEN}=====================================================${NC}"
    echo -e "${GREEN}    Uninstallation Completed Successfully!           ${NC}"
    echo -e "${GREEN}=====================================================${NC}"
    exit 0
}

# Parse command line options
AUTO_CONFIRM=false
ACTION="install"

for arg in "$@"; do
    case "$arg" in
        --uninstall|-u|uninstall)
            ACTION="uninstall"
            ;;
        --yes|-y)
            AUTO_CONFIRM=true
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        --install|-i|install)
            ACTION="install"
            ;;
    esac
done

if [ "$ACTION" = "uninstall" ]; then
    do_uninstall "$AUTO_CONFIRM"
fi

echo -e "${BLUE}=====================================================${NC}"
echo -e "${GREEN}    Royal Kludge RK M87 Native Linux Driver Suite    ${NC}"
echo -e "${BLUE}=====================================================${NC}"
echo ""

# 1. Check Python environment
echo -e "${BLUE}[1/5] Checking Python environment...${NC}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3.10 or newer.${NC}"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "      Found Python $PY_VER"

# 2. Setup udev permissions
echo -e "${BLUE}[2/5] Setting up udev rules for non-root hardware access...${NC}"
UDEV_RULE_FILE="/etc/udev/rules.d/99-rk-m87.rules"
if [ -f "$UDEV_RULE_FILE" ] && grep -q '258a' "$UDEV_RULE_FILE" 2>/dev/null; then
    echo -e "      ${GREEN}✓ udev rules already active in $UDEV_RULE_FILE.${NC}"
elif [ -f "$PROJECT_DIR/99-rk-m87.rules" ]; then
    if [ "$EUID" -eq 0 ]; then
        cp "$PROJECT_DIR/99-rk-m87.rules" "$UDEV_RULE_FILE"
        udevadm control --reload-rules && udevadm trigger 2>/dev/null || true
        echo -e "      ${GREEN}✓ udev rules installed and reloaded.${NC}"
    elif sudo -n true 2>/dev/null; then
        sudo cp "$PROJECT_DIR/99-rk-m87.rules" "$UDEV_RULE_FILE"
        sudo udevadm control --reload-rules && sudo udevadm trigger 2>/dev/null || true
        echo -e "      ${GREEN}✓ udev rules installed and reloaded.${NC}"
    else
        echo -e "      ${YELLOW}Notice: sudo required to copy udev rules.${NC}"
        if sudo cp "$PROJECT_DIR/99-rk-m87.rules" "$UDEV_RULE_FILE" 2>/dev/null; then
            sudo udevadm control --reload-rules && sudo udevadm trigger 2>/dev/null || true
            echo -e "      ${GREEN}✓ udev rules installed and reloaded.${NC}"
        else
            echo -e "      ${YELLOW}Skipped udev install. Run manually if needed: sudo cp $PROJECT_DIR/99-rk-m87.rules $UDEV_RULE_FILE${NC}"
        fi
    fi
else
    echo -e "      ${YELLOW}Warning: 99-rk-m87.rules not found in $PROJECT_DIR.${NC}"
fi

# 3. Install Application to $INSTALL_DIR (~/.RKLinux)
echo -e "${BLUE}[3/5] Installing application suite into $INSTALL_DIR...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/bin"

# Copy package modules and assets
cp -r "$PROJECT_DIR/rkm87" "$INSTALL_DIR/"
cp -r "$PROJECT_DIR/gui" "$INSTALL_DIR/"
cp -r "$PROJECT_DIR/data" "$INSTALL_DIR/"
cp "$PROJECT_DIR/main.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/app.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/cli.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/bin/rkm87" "$INSTALL_DIR/bin/"
chmod +x "$INSTALL_DIR/bin/rkm87"
cp "$PROJECT_DIR/requirements.txt" "$INSTALL_DIR/"
if [ -f "$PROJECT_DIR/LICENSE" ]; then
    cp "$PROJECT_DIR/LICENSE" "$INSTALL_DIR/"
fi

# Setup dedicated Python Virtual Environment in $INSTALL_DIR/.venv
VENV_DIR="$INSTALL_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo -e "      Created virtual environment in $VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
echo -e "      Installing dependencies into $INSTALL_DIR/.venv..."
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
echo -e "      ${GREEN}✓ Application and dependencies installed into $INSTALL_DIR.${NC}"

# 4. Install Command Launcher into ~/.local/bin
echo -e "${BLUE}[4/5] Installing executable launcher to $BIN_DIR/rkm87...${NC}"
mkdir -p "$BIN_DIR"
cp "$PROJECT_DIR/bin/rkm87" "$BIN_DIR/rkm87"
chmod +x "$BIN_DIR/rkm87"
ln -sf "$BIN_DIR/rkm87" "$BIN_DIR/rkm87-cli"
ln -sf "$BIN_DIR/rkm87" "$BIN_DIR/rkm87-gui"
echo -e "      ${GREEN}✓ Executable installed: $BIN_DIR/rkm87 (with rkm87-cli, rkm87-gui symlinks)${NC}"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "      ${YELLOW}Notice: $BIN_DIR is not yet in your PATH.${NC}"
    echo -e "      Add it with: ${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

# 5. Install Desktop Application Launcher & Icon
echo -e "${BLUE}[5/5] Installing desktop application launcher and icon...${NC}"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR"

if [ -f "$PROJECT_DIR/data/icon.png" ]; then
    cp "$PROJECT_DIR/data/icon.png" "$ICON_DIR/rkm87.png"
fi

cat <<EOF > "$DESKTOP_DIR/rkm87.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Royal Kludge M87 Studio
GenericName=Keyboard Driver & RGB Studio
Comment=Native Linux control suite, RGB lighting, LCD screen animations and key remapper for RK M87
Exec=$BIN_DIR/rkm87
Icon=$INSTALL_DIR/data/icon.png
Terminal=false
Categories=Utility;Settings;HardwareSettings;
Keywords=keyboard;rgb;rk;m87;sinowealth;
StartupNotify=true
EOF

chmod +x "$DESKTOP_DIR/rkm87.desktop"
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
echo -e "      ${GREEN}✓ Desktop launcher installed to $DESKTOP_DIR/rkm87.desktop${NC}"

echo ""
echo -e "${GREEN}=====================================================${NC}"
echo -e "${GREEN}    Installation Completed Successfully!             ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo ""
echo -e "Installed Location: ${BLUE}$INSTALL_DIR${NC}"
echo ""
echo -e "How to launch:"
echo -e "  • Open from your desktop application launcher: ${BLUE}Royal Kludge M87 Studio${NC}"
echo -e "  • Or type directly in any terminal:            ${BLUE}rkm87${NC}"
echo ""
echo -e "CLI commands (all via the single 'rkm87' binary):"
echo -e "  • Sync Clock & Volume: ${BLUE}rkm87 sync${NC} (also auto-synced whenever GUI opens)"
echo -e "  • Change RGB Mode:     ${BLUE}rkm87 mode Breathing -c Cyan${NC}"
echo -e "  • Set Debounce:        ${BLUE}rkm87 debounce gaming${NC} (or office)"
echo -e "  • Set Sleep Timer:     ${BLUE}rkm87 sleep 10${NC} (or never)"
echo -e "  • Upload GIF to LCD:   ${BLUE}rkm87 upload my_animation.gif${NC}"
echo -e "  • View Status:         ${BLUE}rkm87 status${NC}"
echo ""
echo -e "To uninstall anytime:"
echo -e "  • Run: ${YELLOW}$PROJECT_DIR/install.sh --uninstall${NC}"
echo ""
