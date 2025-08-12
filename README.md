# USB Device Auto-Config for Linux

Automatically generate udev rules for USB devices on Linux, enabling WebHID access for gaming peripherals. Fix connection issues with Pulsar, Finalmouse, Wooting, Razer, Logitech, and other gaming device configuration software.

**Solves the "Failed to open the device" error when using web-based device configuration tools.**

## Quick Start (One Command!)

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

After installation, just run:

```bash
sudo udev-autoconfig
```

The tool will:
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

If you prefer to install manually:

```bash
# Clone the repository
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig

# Run directly
sudo python3 udev-autoconfig.py

# Or install system-wide
sudo cp udev-autoconfig.py /usr/local/bin/udev-autoconfig
sudo chmod +x /usr/local/bin/udev-autoconfig
```

## How It Works

1. Uses `udevadm` to scan your system for USB devices
2. Checks `/etc/udev/rules.d/` for existing rules
3. Creates new rule files organized by vendor (e.g., `50-logitech.rules`, `50-razer.rules`)
4. Sets proper permissions (MODE="0666") for device access
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

- Python 3.6+
- Linux with udev
- sudo access (for creating rules)

## Keywords / SEO

Gaming mouse Linux, WebHID Linux, udev rules gaming, Pulsar mouse Linux, Finalmouse Linux, Wooting keyboard Linux, Failed to open device Linux, NotAllowedError WebHID, Chrome WebHID permissions, gaming peripherals Linux, RGB mouse Linux, gaming keyboard configuration Linux, USB device permissions Linux

## License

MIT