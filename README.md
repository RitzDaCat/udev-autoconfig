# USB Device Auto-Config for Linux

Automatically generate udev rules for USB devices on Linux, enabling WebHID access for gaming peripherals. Fix connection issues with Pulsar, Finalmouse, Wooting, Razer, Logitech, and other gaming device configuration software.

**Solves the "Failed to open the device" error when using web-based device configuration tools.**

**Now with a native Linux GUI application!** 🎉

## Installation

### Arch Linux (Recommended)

Install from local PKGBUILD:

```bash
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig
makepkg -si --noconfirm -p PKGBUILD.local
```

For GUI support, also install the optional dependencies:

```bash
sudo pacman -S python-gobject gtk4 libadwaita
```

To uninstall:

```bash
sudo pacman -Rns udev-autoconfig
```

### Other Distributions

Quick install via script:

```bash
curl -sSL https://raw.githubusercontent.com/RitzDaCat/udev-autoconfig/main/install.sh | sudo bash
```

Or if you've cloned the repo:

```bash
sudo ./install.sh
```

## What It Does

- **Scans** all your USB devices automatically
- **Detects** which ones need udev rules
- **Generates** proper rules for each device
- **Organizes** rules by vendor (one file per vendor)
- **Applies** rules immediately - no manual reload needed!

## Why You Need This

Many gaming peripherals use WebHID for configuration through browser-based tools. Without proper udev rules, you'll encounter:
- ❌ "Failed to open the device" errors
- ❌ "NotAllowedError" in Chrome/Chromium
- ❌ Device not detected in configuration software

**Supported Devices:**
- 🖱️ Gaming Mice: Pulsar, Finalmouse, Razer, Logitech G, SteelSeries, Glorious, Zowie
- ⌨️ Gaming Keyboards: Wooting, Razer, Corsair, HyperX, Ducky
- 🎮 Controllers: Xbox, PlayStation, 8BitDo
- 🎧 Gaming Headsets and other USB peripherals

This tool automatically creates the necessary udev rules with proper permissions for WebHID access.

## Basic Usage

### GUI Mode (Recommended)

After installation, launch the GUI from your application menu or run:

```bash
udev-autoconfig-gui
```

The GUI will:
- Display all USB devices with status indicators
- Allow easy selection with checkboxes
- Show which devices already have rules configured
- Provide a preview of rules before applying
- Automatically prompt for admin privileges when needed

### Command Line Mode

For command-line usage:

```bash
sudo udev-autoconfig
```

The CLI tool will:
1. Show you all USB devices
2. Highlight which ones don't have rules yet
3. Let you select which ones to configure
4. Create and apply the rules automatically

## Other Commands

```bash
# List all USB devices (no changes made)
udev-autoconfig --list

# Automatically create rules for ALL devices without prompting
sudo udev-autoconfig --auto

# Preview what would be created without making changes
udev-autoconfig --dry-run
```

## Manual Installation

If you prefer to install manually without a package manager:

```bash
# Clone the repository
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig

# Run directly (for testing)
sudo python3 udev-autoconfig.py

# Or install system-wide
sudo install -Dm755 udev-autoconfig.py /usr/local/bin/udev-autoconfig
sudo install -Dm755 udev-autoconfig-gui.py /usr/local/bin/udev-autoconfig-gui
sudo install -Dm644 udev-autoconfig.desktop /usr/share/applications/udev-autoconfig.desktop
```

## How It Works

1. Uses `udevadm` to scan your system for USB devices
2. Checks `/etc/udev/rules.d/` for existing rules
3. Creates new rule files organized by vendor (e.g., `50-logitech.rules`, `50-razer.rules`)
4. Sets proper permissions (MODE="0660", GROUP="input") for device access
5. Automatically reloads udev rules

## Example Output

```
Scanning for USB devices...
Found 3 device(s) without rules:

  1. Logitech G Pro Mouse [046d:c085] (hidraw) -> /dev/hidraw2
  2. Razer BlackWidow [1532:0228] (usb)
  3. Xbox Controller [045e:028e] (input) -> /dev/input/event15

Enter device numbers to create rules for (comma-separated, or 'all'):
> all

=== Rules created successfully ===

Applying rules...
✓ Rules applied! Your devices should now work.
```

## Troubleshooting

If your device configuration software still doesn't work:

1. Check that the device appears in `udev-autoconfig --list`
2. Verify the rules were created in `/etc/udev/rules.d/`
3. Try unplugging and reconnecting the device
4. Check your software's documentation for additional requirements

## Requirements

### Core Requirements
- Python 3.6+
- Linux with systemd/udev
- sudo access (for creating rules)

### GUI Requirements (optional)
- GTK 4.0+
- libadwaita 1.0+
- PyGObject

### Installing Dependencies

**Arch Linux:**
```bash
# Core (usually pre-installed)
sudo pacman -S python systemd

# GUI (optional)
sudo pacman -S python-gobject gtk4 libadwaita
```

**Debian/Ubuntu:**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora:**
```bash
sudo dnf install python3-gobject gtk4 libadwaita
```

## Uninstallation

**Arch Linux:**
```bash
sudo pacman -Rns udev-autoconfig
```

**Manual uninstall (other distros):**
```bash
sudo rm /usr/local/bin/udev-autoconfig
sudo rm /usr/local/bin/udev-autoconfig-gui
sudo rm /usr/share/applications/udev-autoconfig.desktop
# Optionally remove generated rules:
sudo rm /etc/udev/rules.d/50-*.rules
```

## Keywords / SEO

Gaming mouse Linux, WebHID Linux, udev rules gaming, Pulsar mouse Linux, Finalmouse Linux, Wooting keyboard Linux, Failed to open device Linux, NotAllowedError WebHID, Chrome WebHID permissions, gaming peripherals Linux, RGB mouse Linux, gaming keyboard configuration Linux, USB device permissions Linux

## License

MIT