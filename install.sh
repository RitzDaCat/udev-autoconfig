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

echo "Installing udev-autoconfig..."

# Copy the script
cp udev-autoconfig.py "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "✓ Installed to $INSTALL_DIR/$SCRIPT_NAME"
echo

echo "Installation complete!"
echo
echo "Usage:"
echo "  sudo udev-autoconfig        # Interactive mode - easiest for most users"
echo "  sudo udev-autoconfig --auto # Auto-detect and create all rules"
echo "  udev-autoconfig --list      # List devices (no sudo needed)"
echo
echo "Running initial setup now..."
echo

# Run the tool for first-time setup
$INSTALL_DIR/$SCRIPT_NAME