# USB Device Auto-Config for Linux

Automatically generate udev rules for USB devices on Linux, enabling WebHID access for gaming peripherals. Fix connection issues with Pulsar, Finalmouse, Wooting, Razer, Logitech, and other gaming device configuration software.

**Solves the "Failed to open the device" error when using web-based device configuration tools.**

**Now with a native Linux GUI application!**

## Installation

### Arch Linux / CachyOS

Use the pacman package path on Arch-based systems. This keeps `/usr/bin`,
the desktop entry, the polkit policy, dependencies, upgrades, and uninstall
owned by the package manager.

#### First-time install: latest code from GitHub

This builds the newest commit from GitHub and installs it as
`udev-autoconfig-git`:

```bash
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig
makepkg -si -p PKGBUILD.git
```

Update later to the latest GitHub code:

```bash
cd udev-autoconfig
git pull
makepkg -si -p PKGBUILD.git
```

Uninstall:

```bash
sudo pacman -Rns udev-autoconfig-git
```

#### AUR install/update flow

If/when the AUR packages are published, users can install with an AUR helper:

```bash
# Stable release package
paru -S udev-autoconfig

# Latest GitHub package
paru -S udev-autoconfig-git
```

Update stable package:

```bash
paru -Syu
```

Update VCS / latest-GitHub package:

```bash
paru -Syu --devel
```

The same package names work with `yay`:

```bash
yay -S udev-autoconfig-git
yay -Syu --devel
```

#### Local development install

Use this when you are editing this checkout and want to package exactly the
files in the current directory instead of re-cloning GitHub:

```bash
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig
makepkg -si -p PKGBUILD.local
```

Update a local development install:

```bash
cd udev-autoconfig
git pull
makepkg -si -p PKGBUILD.local
```

Uninstall the local package:

```bash
sudo pacman -Rns udev-autoconfig
```

### Other Distributions

Clone the repository and run the installer from inside the checkout:

```bash
git clone https://github.com/RitzDaCat/udev-autoconfig.git
cd udev-autoconfig
sudo ./install.sh
```

Manual update for script installs:

```bash
cd udev-autoconfig
git pull
sudo ./install.sh
```

Manual uninstall for script installs:

```bash
cd udev-autoconfig
sudo ./install.sh --uninstall
```

## What It Does

- **Scans** all your USB devices automatically
- **Detects** which ones need udev rules
- **Generates** proper rules for each device
- **Organizes** rules by vendor (one file per vendor)
- **Applies** rules immediately - no manual reload needed!

## Why You Need This

Many gaming peripherals use WebHID for configuration through browser-based tools. Without proper udev rules, you'll encounter:

- "Failed to open the device" errors
- "NotAllowedError" in Chrome/Chromium
- Device not detected in configuration software

**Supported Devices:**

- Gaming Mice: Pulsar, Finalmouse, Razer, Logitech G, SteelSeries, Glorious, Zowie
- Gaming Keyboards: Wooting, Razer, Corsair, HyperX, Ducky
- Controllers: Xbox, PlayStation, 8BitDo
- Gaming Headsets and other USB peripherals

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
# Show installed version
udev-autoconfig --version

# List all USB devices (no changes made)
udev-autoconfig --list

# Automatically create rules for ALL devices without prompting
sudo udev-autoconfig --auto

# Preview what would be created without making changes
udev-autoconfig --dry-run
```

## Firmware Update Mode Support

Some devices (like Wooting keyboards) change their USB product ID when entering firmware update/DFU mode. Use these options to create rules that also cover update modes:

```bash
# Create rules for a device AND its update mode product ID
sudo udev-autoconfig --devices 03eb:ff01 --update-ids 2402

# Multiple update mode IDs
sudo udev-autoconfig --devices 03eb:ff01 03eb:ff02 --update-ids 2402 2403

# Create rules matching ALL products from a vendor (e.g., "Generic Wootings")
sudo udev-autoconfig --vendor-only 31e3
```

## Device Type Configuration

Configure rules based on device type for proper GROUP and MODE assignment:

```bash
# Configure as keyboard (GROUP=input)
sudo udev-autoconfig --devices 046d:c085 --type keyboard

# Configure as serial/Arduino device (GROUP=dialout, adds ttyUSB/ttyACM rules)
sudo udev-autoconfig --devices 239a:800b --type serial --serial

# Configure with raw USB access for libusb-based tools (MODE=0666)
sudo udev-autoconfig --devices 046d:c085 --raw-usb

# Disable browser support if not needed
sudo udev-autoconfig --devices 046d:c085 --no-webhid --no-snap --no-flatpak
```

**Available device types:** `keyboard`, `mouse`, `controller`, `serial`, `storage`, `audio`, `network`, `generic`

**Access toggles:**
| Flag | Effect |
|------|--------|
| `--raw-usb` | Set MODE=0666 for libusb access |
| `--serial` | Add ttyUSB/ttyACM rules, GROUP=dialout |
| `--network` | Set GROUP=netdev for USB network adapters |
| `--no-webhid` | Disable uaccess tag |
| `--no-snap` | Disable snap Chromium support |
| `--no-flatpak` | Disable flatpak browser support |

## Rules Audit

Scan your existing udev rules for issues:

```bash
# Full audit (checks duplicates, conflicts, stale rules, overlaps)
udev-autoconfig --audit

# Skip stale rule detection (faster)
udev-autoconfig --audit --no-stale

# Filter audit to specific device (e.g., Xbox controller)
udev-autoconfig --audit --filter xbox
udev-autoconfig --audit --filter 045e:028e

# Show all rules for a specific device
udev-autoconfig --show 045e:028e    # Xbox controller
udev-autoconfig --show 239a:800b    # Adafruit device
```

**Detects:**

- **Duplicates**: Same VID:PID in multiple files
- **Conflicts**: Different MODE/GROUP for the same device
- **Stale**: Rules for disconnected devices
- **Overlaps**: Vendor-wide rules covering specific product rules

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
sudo install -Dm644 com.github.udev-autoconfig.policy /usr/share/polkit-1/actions/com.github.udev-autoconfig.policy
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
Rules applied! Your devices should now work.
```

## Troubleshooting

### Controller Not Working (Steam/Games)

If your controller suddenly stops working in Steam or games:

```bash
# Step 1: Check if the system sees the controller
udev-autoconfig --list | grep -i controller
# If not shown, the controller isn't detected - check USB connection

# Step 2: Find your controller's VID:PID (common ones below)
#   Xbox:       045e:028e, 045e:02ea (Series X)
#   PS4/PS5:    054c:05c4, 054c:0ce6
#   8BitDo:     2dc8:*

# Step 3: Check existing rules for your controller
udev-autoconfig --show 045e:028e

# Step 4: Check for conflicting rules
udev-autoconfig --audit --filter 045e

# Step 5: If conflicts found, remove and recreate
sudo udev-autoconfig --remove 045e:028e
sudo udev-autoconfig --devices 045e:028e --type controller

# Step 6: Replug the controller and test
```

### General Troubleshooting

1. **Device not in `--list`**: Check USB cable/connection, try different port
2. **Rules exist but device doesn't work**: Check for conflicts with `--audit`
3. **"Permission denied" errors**: Ensure user is in the `input` group: `sudo usermod -aG input $USER`
4. **Changes don't take effect**: Replug device or run `sudo udevadm trigger`

## Requirements

### Core Requirements

- Python 3.6+
- Linux with systemd/udev
- sudo access (for creating rules)

### GUI Requirements (optional)

- GTK 4.0+
- libadwaita 1.0+
- PyGObject
- polkit / pkexec for GUI privilege prompts

### Installing Dependencies

**Arch Linux:**

```bash
# Installed automatically by the PKGBUILD package dependencies.
sudo pacman -S python systemd python-gobject gtk4 libadwaita polkit
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
# Stable/local package
sudo pacman -Rns udev-autoconfig

# Latest-GitHub package
sudo pacman -Rns udev-autoconfig-git
```

**Manual uninstall (other distros):**

```bash
# Preferred if you still have the cloned repository
cd udev-autoconfig
sudo ./install.sh --uninstall

# Or remove the files directly
sudo rm /usr/local/bin/udev-autoconfig
sudo rm /usr/local/bin/udev-autoconfig-gui
sudo rm /usr/share/applications/udev-autoconfig.desktop
sudo rm /usr/share/polkit-1/actions/com.github.udev-autoconfig.policy
# Optionally remove generated rules:
sudo rm /etc/udev/rules.d/50-*.rules
```

## Keywords / SEO

Gaming mouse Linux, WebHID Linux, udev rules gaming, Pulsar mouse Linux, Finalmouse Linux, Wooting keyboard Linux, Failed to open device Linux, NotAllowedError WebHID, Chrome WebHID permissions, gaming peripherals Linux, RGB mouse Linux, gaming keyboard configuration Linux, USB device permissions Linux

## License

MIT
