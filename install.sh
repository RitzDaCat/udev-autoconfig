#!/bin/bash

set -e

echo "==================================="
echo "  USB Device Auto-Config Installer"
echo "==================================="
echo

# Install to /usr/local/bin for system-wide access
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="udev-autoconfig"
GUI_SCRIPT_NAME="udev-autoconfig-gui"
DESKTOP_DIR="/usr/share/applications"
POLKIT_DIR="/usr/share/polkit-1/actions"
POLKIT_POLICY="com.github.udev-autoconfig.policy"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: sudo ./install.sh [--uninstall]"
    echo
    echo "Installs udev-autoconfig to /usr/local/bin for non-Arch distributions."
    echo "Arch/CachyOS users should prefer: makepkg -si -p PKGBUILD.git"
    exit 0
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling udev-autoconfig manual install..."
    rm -f "$INSTALL_DIR/$SCRIPT_NAME"
    rm -f "$INSTALL_DIR/$GUI_SCRIPT_NAME"
    rm -f "$DESKTOP_DIR/udev-autoconfig.desktop"
    rm -f "$POLKIT_DIR/$POLKIT_POLICY"
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$DESKTOP_DIR"
    fi
    echo "✓ Manual install removed"
    echo "Generated udev rules in /etc/udev/rules.d were left untouched."
    exit 0
fi

echo "Installing udev-autoconfig..."

# Copy the CLI script
cp udev-autoconfig.py "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "✓ Installed CLI tool to $INSTALL_DIR/$SCRIPT_NAME"

# Check if GUI dependencies are available and ask to install GUI
echo
read -p "Would you like to install the GUI version? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Check for PyGObject
    if python3 -c "import gi" 2>/dev/null; then
        echo "✓ PyGObject detected"
    else
        echo "Installing PyGObject dependencies..."
        if command -v apt-get &> /dev/null; then
            apt-get update
            apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
        elif command -v dnf &> /dev/null; then
            dnf install -y python3-gobject gtk4 libadwaita
        elif command -v pacman &> /dev/null; then
            pacman -S --noconfirm python-gobject gtk4 libadwaita polkit
        else
            echo "⚠ Could not install PyGObject automatically. Please install manually:"
            echo "  - Debian/Ubuntu: sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1"
            echo "  - Fedora: sudo dnf install python3-gobject gtk4 libadwaita"
            echo "  - Arch: sudo pacman -S python-gobject gtk4 libadwaita polkit"
        fi
    fi
    
    # Copy GUI script
    cp udev-autoconfig-gui.py "$INSTALL_DIR/$GUI_SCRIPT_NAME"
    chmod +x "$INSTALL_DIR/$GUI_SCRIPT_NAME"
    echo "✓ Installed GUI to $INSTALL_DIR/$GUI_SCRIPT_NAME"
    
    # Install desktop entry
    cp udev-autoconfig.desktop "$DESKTOP_DIR/"
    echo "✓ Installed desktop entry"

    # Install polkit policy used by the GUI for privilege escalation
    mkdir -p "$POLKIT_DIR"
    cp "$POLKIT_POLICY" "$POLKIT_DIR/"
    echo "✓ Installed polkit policy"
    
    # Update desktop database
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$DESKTOP_DIR"
    fi
fi

echo
echo "Installation complete!"
echo
echo "Usage:"
echo "  sudo udev-autoconfig        # Interactive CLI mode"
echo "  sudo udev-autoconfig --auto # Auto-detect and create all rules"
echo "  udev-autoconfig --list      # List devices (no sudo needed)"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  udev-autoconfig-gui         # Launch GUI (will prompt for admin when needed)"
fi
echo
echo "Running initial setup now..."
echo

# Run the tool for first-time setup
$INSTALL_DIR/$SCRIPT_NAME
