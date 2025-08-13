#!/bin/bash

set -e

echo "==================================="
echo "  USB Device Auto-Config Installer"
echo "==================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Install to /usr/local/bin for system-wide access
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="udev-autoconfig"
GUI_SCRIPT_NAME="udev-autoconfig-gui"
DESKTOP_DIR="/usr/share/applications"

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
            pacman -S --noconfirm python-gobject gtk4 libadwaita
        else
            echo "⚠ Could not install PyGObject automatically. Please install manually:"
            echo "  - Debian/Ubuntu: sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1"
            echo "  - Fedora: sudo dnf install python3-gobject gtk4 libadwaita"
            echo "  - Arch: sudo pacman -S python-gobject gtk4 libadwaita"
        fi
    fi
    
    # Copy GUI script
    cp udev-autoconfig-gui.py "$INSTALL_DIR/$GUI_SCRIPT_NAME"
    chmod +x "$INSTALL_DIR/$GUI_SCRIPT_NAME"
    echo "✓ Installed GUI to $INSTALL_DIR/$GUI_SCRIPT_NAME"
    
    # Install desktop entry
    cp udev-autoconfig.desktop "$DESKTOP_DIR/"
    echo "✓ Installed desktop entry"
    
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