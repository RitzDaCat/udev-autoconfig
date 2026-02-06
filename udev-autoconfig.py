#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
import re


# Device type to primary group mapping
TYPE_TO_GROUP = {
    "keyboard": "input",
    "mouse": "input",
    "controller": "input",
    "serial": "dialout",
    "storage": "disk",
    "audio": "audio",
    "network": "netdev",
    "generic": "input",
}

# Device presets with descriptions for GUI selection
# Each preset configures DeviceProfile with appropriate settings
DEVICE_PRESETS = {
    "controller": {
        "name": "🎮 Game Controller",
        "description": "Xbox, PlayStation, 8BitDo controllers - Full input support + no sleep",
        "settings": {"device_type": "controller", "webhid_access": True, "raw_usb_access": False},
    },
    "mouse": {
        "name": "🖱️ Gaming Mouse (WebHID)",
        "description": "Mice with web-based DPI/LOD config (VAXEE, Razer, etc.)",
        "settings": {"device_type": "mouse", "webhid_access": True, "raw_usb_access": True},
    },
    "keyboard": {
        "name": "⌨️ Custom Keyboard",
        "description": "Wooting, QMK, VIA keyboards with firmware/config access",
        "settings": {"device_type": "keyboard", "webhid_access": True, "raw_usb_access": True},
    },
    "serial": {
        "name": "🔌 Serial Device",
        "description": "Arduino, microcontrollers, debug adapters (ttyUSB/ttyACM)",
        "settings": {"device_type": "serial", "serial_access": True, "webhid_access": False},
    },
    "storage": {
        "name": "💾 Storage Device",
        "description": "USB drives, card readers, external disks",
        "settings": {"device_type": "storage", "webhid_access": False, "raw_usb_access": False},
    },
    "audio": {
        "name": "🎧 Audio Interface",
        "description": "DACs, mixers, audio interfaces (GoXLR, Focusrite, etc.)",
        "settings": {"device_type": "audio", "webhid_access": True, "raw_usb_access": False},
    },
    "network": {
        "name": "🌐 Network Adapter",
        "description": "USB WiFi, Ethernet, mobile broadband adapters",
        "settings": {"device_type": "network", "network_access": True, "webhid_access": False},
    },
    "generic": {
        "name": "📦 Generic Device",
        "description": "Default settings - basic WebHID access",
        "settings": {"device_type": "generic", "webhid_access": True, "raw_usb_access": False},
    },
}


@dataclass
class DeviceProfile:
    """Configuration profile for a USB device's udev rule generation."""
    # Device type (affects GROUP assignment)
    device_type: str = "generic"
    
    # Access toggles
    webhid_access: bool = True       # Browser WebHID (TAG+=uaccess)
    raw_usb_access: bool = False     # libusb userspace (MODE=0666)
    serial_access: bool = False      # /dev/ttyUSB*, ttyACM* (GROUP=dialout)
    network_access: bool = False     # USB network adapters (GROUP=netdev)
    
    # Browser support toggles
    snap_chromium: bool = True
    flatpak_browsers: bool = True
    
    def get_group(self) -> str:
        """Get the primary group based on device type and access toggles."""
        if self.serial_access:
            return "dialout"
        if self.network_access:
            return "netdev"
        return TYPE_TO_GROUP.get(self.device_type, "input")
    
    def get_mode(self) -> str:
        """Get file mode based on access requirements."""
        return "0666" if self.raw_usb_access else "0660"

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'
    
    @staticmethod
    def disable():
        Colors.HEADER = ''
        Colors.BLUE = ''
        Colors.CYAN = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.RED = ''
        Colors.BOLD = ''
        Colors.DIM = ''
        Colors.UNDERLINE = ''
        Colors.RESET = ''

# Disable colors if not in a terminal
if not sys.stdout.isatty():
    Colors.disable()

# Known device database for automatic update mode detection
# Structure: vendor_id -> {
#   "name": "Vendor Name",
#   "update_modes": { product_id: [update_mode_pids] },
#   "vendor_only": True/False (if True, also generate vendor-wide rules)
# }
KNOWN_DEVICES = {
    "03eb": {
        "name": "Wooting (Legacy)",
        "update_modes": {
            "ff01": ["2402"],  # Wooting One Legacy -> update mode
            "ff02": ["2403"],  # Wooting Two Legacy -> update mode
        },
        "vendor_only": False,
    },
    "31e3": {
        "name": "Wooting",
        "update_modes": {},
        "vendor_only": True,  # Generic Wootings - match all products
    },
}


class UdevDevice:
    def __init__(self, device_path: str):
        self.path = device_path
        self.properties = {}
        self._load_properties()
    
    def _load_properties(self):
        try:
            result = subprocess.run(
                ['udevadm', 'info', '--query=property', '--path=' + self.path],
                capture_output=True,
                text=True,
                check=True
            )
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    self.properties[key] = value
        except subprocess.CalledProcessError:
            pass
    
    @property
    def vendor_id(self) -> Optional[str]:
        return self.properties.get('ID_VENDOR_ID')
    
    @property
    def product_id(self) -> Optional[str]:
        return self.properties.get('ID_MODEL_ID')
    
    @property
    def vendor_name(self) -> Optional[str]:
        return self.properties.get('ID_VENDOR') or self.properties.get('ID_VENDOR_FROM_DATABASE')
    
    @property
    def product_name(self) -> Optional[str]:
        return self.properties.get('ID_MODEL') or self.properties.get('ID_MODEL_FROM_DATABASE')
    
    @property
    def subsystem(self) -> Optional[str]:
        return self.properties.get('SUBSYSTEM')
    
    @property
    def devtype(self) -> Optional[str]:
        return self.properties.get('DEVTYPE')
    
    @property
    def driver(self) -> Optional[str]:
        return self.properties.get('DRIVER')
    
    @property
    def devname(self) -> Optional[str]:
        return self.properties.get('DEVNAME')
    
    def __str__(self) -> str:
        info = []
        if self.vendor_name and self.product_name:
            info.append(f"{Colors.BOLD}{self.vendor_name} {self.product_name}{Colors.RESET}")
        if self.vendor_id and self.product_id:
            info.append(f"{Colors.DIM}[{self.vendor_id}:{self.product_id}]{Colors.RESET}")
        if self.subsystem:
            info.append(f"{Colors.CYAN}({self.subsystem}){Colors.RESET}")
        if self.devname:
            info.append(f"{Colors.DIM}→ {self.devname}{Colors.RESET}")
        return " ".join(info) if info else self.path


class UdevRuleGenerator:
    def __init__(self):
        self.rules_dir = Path("/etc/udev/rules.d")
        self.devices = []
        
    def scan_devices(self, subsystem: Optional[str] = None) -> List[UdevDevice]:
        cmd = ['udevadm', 'info', '--export-db']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        devices = []
        current_device_path = None
        
        for line in result.stdout.split('\n'):
            if line.startswith('P: '):
                current_device_path = line[3:]
                if subsystem is None or f'/devices/' in current_device_path:
                    device = UdevDevice(current_device_path)
                    if subsystem is None or device.subsystem == subsystem:
                        if device.vendor_id and device.product_id:
                            devices.append(device)
        
        return devices
    
    def get_usb_devices(self) -> List[UdevDevice]:
        all_devices = [d for d in self.scan_devices() if d.subsystem in ['usb', 'hidraw', 'input']]
        
        # Deduplicate by vendor:product ID, preferring hidraw > usb > input
        seen = {}
        subsystem_priority = {'hidraw': 3, 'usb': 2, 'input': 1}
        
        for device in all_devices:
            key = f"{device.vendor_id}:{device.product_id}"
            if key not in seen:
                seen[key] = device
            else:
                # Keep the device with higher priority subsystem
                current_priority = subsystem_priority.get(seen[key].subsystem, 0)
                new_priority = subsystem_priority.get(device.subsystem, 0)
                if new_priority > current_priority:
                    seen[key] = device
        
        return list(seen.values())
    
    def get_existing_rules(self) -> Dict[str, List[str]]:
        existing = {}
        if not self.rules_dir.exists():
            return existing
        
        for rule_file in self.rules_dir.glob("*.rules"):
            try:
                with open(rule_file, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    # Look for complete vendor:product pairs in the same rule line
                    for line in content.split('\n'):
                        if 'idVendor' in line and 'idProduct' in line:
                            # Match both ATTRS{idVendor}=="xxxx" and idVendor=="xxxx" formats
                            vendor_match = re.search(r'(?:ATTRS\{)?idVendor[}=]+="?([0-9a-fA-F]+)"?', line)
                            product_match = re.search(r'(?:ATTRS\{)?idProduct[}=]+="?([0-9a-fA-F]+)"?', line)
                            
                            if vendor_match and product_match:
                                vid = vendor_match.group(1).lower()
                                pid = product_match.group(1).lower()
                                if vid not in existing:
                                    existing[vid] = set()
                                existing[vid].add(pid)
            except (IOError, OSError) as e:
                print(f"Warning: Could not parse {rule_file}: {e}", file=sys.stderr)
        
        # Convert sets back to lists
        for vid in existing:
            existing[vid] = list(existing[vid])
        
        return existing
    
    def generate_rule(self, device: UdevDevice, profile: DeviceProfile = None, include_snap: bool = True, extra_product_ids: List[str] = None) -> str:
        rules = []
        
        # Use profile settings or defaults
        if profile is None:
            profile = DeviceProfile()
        
        mode = profile.get_mode()
        group = profile.get_group()
        include_snap = profile.snap_chromium if profile else include_snap
        include_flatpak = profile.flatpak_browsers if profile else True
        include_webhid = profile.webhid_access if profile else True
        
        vid = device.vendor_id.lower() if device.vendor_id else ""
        pid = device.product_id.lower() if device.product_id else ""
        
        # Auto-lookup update modes from KNOWN_DEVICES database
        all_extra_pids = list(extra_product_ids) if extra_product_ids else []
        if vid in KNOWN_DEVICES:
            device_info = KNOWN_DEVICES[vid]
            if pid in device_info.get("update_modes", {}):
                for update_pid in device_info["update_modes"][pid]:
                    if update_pid not in all_extra_pids:
                        all_extra_pids.append(update_pid)
        
        comment = f" # {device.vendor_name} {device.product_name}" if device.product_name else ""
        type_comment = f" [{profile.device_type}]" if profile.device_type != "generic" else ""
        comment = comment + type_comment
        
        # Main hidraw rule (most important for WebHID)
        uaccess_tag = ', TAG+="uaccess"' if include_webhid else ''
        rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
        rules.append(rule + comment)
        
        # USB subsystem rule
        rule = f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
        rules.append(rule + comment)
        
        # Input subsystem rule (for controller buttons, thumbsticks, evdev)
        # This is essential for gamepads to work in Steam/games
        rule = f'SUBSYSTEM=="input", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
        rules.append(rule + comment)
        
        # Power supply rule (for controllers with charging capability)
        rule = f'KERNEL=="hidraw*", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}"'
        rules.append(rule + comment)
        
        # Bluetooth subsystem (for wireless controllers and Bluetooth adapters)
        rule = f'SUBSYSTEM=="bluetooth", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
        rules.append(rule + comment)
        
        # USB power management - disable autosuspend to prevent wireless controllers from sleeping
        rules.append("")
        rules.append(f"# Disable USB autosuspend (prevents controller disconnect during idle){comment}")
        rule = f'ACTION=="add", SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", ATTR{{power/autosuspend}}="-1"'
        rules.append(rule)
        
        # Add serial port rules if serial access is enabled
        if profile.serial_access:
            rules.append("")
            rules.append(f"# Serial port access (ttyUSB/ttyACM){comment}")
            rule = f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="dialout"'
            rules.append(rule)
        
        # Add snap Chromium support if requested (for Ubuntu/snap users)
        if include_snap and include_webhid:
            rules.append("")
            rules.append(f"# Support for snap Chromium (Ubuntu){comment}")
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="snap_chromium_chromedriver"'
            rules.append(rule)
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="snap_chromium_chromium"'
            rules.append(rule)
        
        # Add flatpak Chrome/Chromium support
        if include_flatpak and include_webhid:
            rules.append("")
            rules.append(f"# Support for Flatpak browsers{comment}")
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="uaccess", TAG+="seat"'
            rules.append(rule)
        
        # Add rules for extra product IDs (firmware update/DFU modes)
        if all_extra_pids:
            for extra_pid in all_extra_pids:
                rules.append("")
                rules.append(f"# Update/DFU mode ({device.vendor_id}:{extra_pid})")
                rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{extra_pid}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
                rules.append(rule)
                rule = f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{extra_pid}", MODE:="{mode}", GROUP="{group}"{uaccess_tag}'
                rules.append(rule)
                
                if include_snap and include_webhid:
                    rules.append(f"# Update mode snap Chromium support")
                    rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{extra_pid}", TAG+="snap_chromium_chromedriver"'
                    rules.append(rule)
                    rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{extra_pid}", TAG+="snap_chromium_chromium"'
                    rules.append(rule)
        
        return '\n'.join(rules)
    
    def generate_vendor_rule(self, vendor_id: str, vendor_name: str = None, include_snap: bool = True) -> str:
        """Generate rules that match all products from a vendor (no product ID filter)."""
        rules = []
        
        mode = "0660"
        group = "input"
        
        display_name = vendor_name or vendor_id
        comment = f" # {display_name} (all devices)"
        
        # Generic vendor rules (no product ID)
        rules.append(f"# Generic {display_name} devices")
        rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{vendor_id}", MODE:="{mode}", GROUP="{group}", TAG+="uaccess"'
        rules.append(rule + comment)
        
        rule = f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{vendor_id}", MODE:="{mode}", GROUP="{group}", TAG+="uaccess"'
        rules.append(rule + comment)
        
        if include_snap:
            rules.append("")
            rules.append(f"# Snap Chromium support for {display_name}")
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{vendor_id}", TAG+="snap_chromium_chromedriver"'
            rules.append(rule)
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{vendor_id}", TAG+="snap_chromium_chromium"'
            rules.append(rule)
        
        return '\n'.join(rules)

    
    def save_rules(self, devices: List[UdevDevice], dry_run: bool = False, extra_product_ids: List[str] = None) -> Dict[str, List[str]]:
        rules_by_vendor = {}
        vendors_seen = set()  # Track vendor IDs for vendor-only rules
        
        for device in devices:
            vendor_name = (device.vendor_name or device.vendor_id).lower()
            vendor_name = re.sub(r'[^a-z0-9]+', '-', vendor_name)
            
            if vendor_name not in rules_by_vendor:
                rules_by_vendor[vendor_name] = []
            
            rule = self.generate_rule(device, extra_product_ids=extra_product_ids)
            rules_by_vendor[vendor_name].append(rule)
            
            # Track vendor IDs for vendor-only rules
            if device.vendor_id:
                vendors_seen.add(device.vendor_id.lower())
        
        # Add vendor-only rules for known vendors that require them
        for vid in vendors_seen:
            if vid in KNOWN_DEVICES and KNOWN_DEVICES[vid].get("vendor_only", False):
                vendor_info = KNOWN_DEVICES[vid]
                vendor_name = vendor_info.get("name", vid).lower()
                vendor_name = re.sub(r'[^a-z0-9]+', '-', vendor_name)
                
                if vendor_name not in rules_by_vendor:
                    rules_by_vendor[vendor_name] = []
                
                vendor_rule = self.generate_vendor_rule(vid, vendor_info.get("name"))
                rules_by_vendor[vendor_name].append(vendor_rule)
        
        saved_files = {}
        
        for vendor_name, rules in rules_by_vendor.items():
            filename = f"50-{vendor_name}.rules"
            filepath = self.rules_dir / filename
            
            if dry_run:
                print(f"\n{Colors.YELLOW}--- Would create/update: {filepath} ---{Colors.RESET}")
                print('\n'.join(rules))
            else:
                if filepath.exists():
                    # Read existing file to check for duplicates
                    with open(filepath, 'r') as f:
                        existing_content = f.read()
                    
                    # Extract vendor:product pairs from new rules
                    new_rules_to_add = []
                    for rule_block in rules:
                        # Check if this device's rules already exist
                        device_already_configured = False
                        for line in rule_block.split('\n'):
                            if 'idVendor' in line and 'idProduct' in line:
                                # Match both ATTRS{idVendor}=="xxxx" and idVendor=="xxxx" formats
                                vendor_match = re.search(r'(?:ATTRS\{)?idVendor[}=]+="?([0-9a-fA-F]+)"?', line)
                                product_match = re.search(r'(?:ATTRS\{)?idProduct[}=]+="?([0-9a-fA-F]+)"?', line)
                                if vendor_match and product_match:
                                    vid = vendor_match.group(1)
                                    pid = product_match.group(1)
                                    # Check if this exact vendor:product combo already exists (check for both formats)
                                    if (f'idVendor}}=="{vid}"' in existing_content or f'idVendor}}=="{vid.lower()}"' in existing_content.lower()) and \
                                       (f'idProduct}}=="{pid}"' in existing_content or f'idProduct}}=="{pid.lower()}"' in existing_content.lower()):
                                        device_already_configured = True
                                        print(f"{Colors.YELLOW}⚠ Device {vid}:{pid} already has rules in {filepath}, skipping...{Colors.RESET}")
                                        break
                        
                        if not device_already_configured:
                            new_rules_to_add.append(rule_block)
                    
                    if new_rules_to_add:
                        print(f"{Colors.GREEN}✓{Colors.RESET} Adding new rules to: {Colors.BOLD}{filepath}{Colors.RESET}")
                        with open(filepath, 'a') as f:
                            f.write(f"\n# Additional rules added by udev-autoconfig\n")
                            f.write('\n'.join(new_rules_to_add) + '\n')
                    else:
                        print(f"{Colors.YELLOW}ℹ All selected devices already configured in {filepath}{Colors.RESET}")
                else:
                    content = f"# udev rules for {vendor_name} devices\n"
                    content += f"# Generated by udev-autoconfig\n\n"
                    content += '\n'.join(rules) + '\n'
                    
                    with open(filepath, 'w') as f:
                        f.write(content)
                    print(f"{Colors.GREEN}✓{Colors.RESET} Created: {Colors.BOLD}{filepath}{Colors.RESET}")
                
                saved_files[vendor_name] = [str(filepath)]
        
        return saved_files
    
    def remove_rules(self, device_ids: List[str], dry_run: bool = False) -> Dict[str, int]:
        """
        Remove rules for specific devices by vendor:product ID.
        Returns dict of {filepath: lines_removed}
        """
        # Parse device IDs into (vid, pid) tuples
        targets = set()
        for dev_id in device_ids:
            if ':' in dev_id:
                vid, pid = dev_id.lower().split(':', 1)
                targets.add((vid, pid))
        
        if not targets:
            return {}
        
        removed_from = {}
        
        for rule_file in self.rules_dir.glob("*.rules"):
            try:
                with open(rule_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                new_lines = []
                removed_count = 0
                skip_next_empty = False
                
                for line in lines:
                    should_remove = False
                    
                    # Check if this line contains a rule for any target device
                    if 'idVendor' in line and 'idProduct' in line:
                        vendor_match = re.search(r'idVendor[}=]+="?([0-9a-fA-F]+)"?', line)
                        product_match = re.search(r'idProduct[}=]+="?([0-9a-fA-F]+)"?', line)
                        
                        if vendor_match and product_match:
                            vid = vendor_match.group(1).lower()
                            pid = product_match.group(1).lower()
                            if (vid, pid) in targets:
                                should_remove = True
                                removed_count += 1
                    
                    # Also remove comment lines that reference the device (snap/flatpak support comments)
                    if not should_remove and line.strip().startswith('#'):
                        # Check if next non-empty line would be removed
                        # For now, just keep comments unless they're orphaned
                        pass
                    
                    if should_remove:
                        if dry_run:
                            print(f"{Colors.YELLOW}Would remove:{Colors.RESET} {line.rstrip()}")
                        skip_next_empty = True
                    else:
                        # Skip empty lines that follow removed rules
                        if skip_next_empty and line.strip() == '':
                            skip_next_empty = False
                            continue
                        skip_next_empty = False
                        new_lines.append(line)
                
                if removed_count > 0:
                    removed_from[str(rule_file)] = removed_count
                    
                    if not dry_run:
                        # Check if file would be empty (only comments/whitespace)
                        has_rules = any(l.strip() and not l.strip().startswith('#') for l in new_lines)
                        
                        if has_rules:
                            with open(rule_file, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                            print(f"{Colors.GREEN}✓{Colors.RESET} Removed {removed_count} rule(s) from {Colors.BOLD}{rule_file}{Colors.RESET}")
                        else:
                            # File is now empty, delete it
                            rule_file.unlink()
                            print(f"{Colors.GREEN}✓{Colors.RESET} Deleted empty rules file: {Colors.BOLD}{rule_file}{Colors.RESET}")
                    else:
                        print(f"{Colors.YELLOW}Would remove {removed_count} rule(s) from {rule_file}{Colors.RESET}")
                        
            except (IOError, OSError) as e:
                print(f"{Colors.RED}Error processing {rule_file}: {e}{Colors.RESET}", file=sys.stderr)
        
        return removed_from


@dataclass
class RuleEntry:
    """Represents a single parsed udev rule."""
    filepath: Path
    line_number: int
    vendor_id: str
    product_id: Optional[str]  # None for vendor-only rules
    mode: Optional[str]
    group: Optional[str]
    raw_line: str


class RulesAuditor:
    """Audits /etc/udev/rules.d/ for duplicates, conflicts, and issues."""
    
    def __init__(self, rules_dir: Path = None):
        self.rules_dir = rules_dir or Path("/etc/udev/rules.d")
        self.entries: List[RuleEntry] = []
        self.connected_devices: set = set()  # (vid, pid) tuples
        
    def scan_connected_devices(self) -> set:
        """Get set of currently connected device VID:PID pairs."""
        try:
            result = subprocess.run(
                ['udevadm', 'info', '--export-db'],
                capture_output=True, text=True, check=True
            )
            devices = set()
            current_vid = None
            current_pid = None
            
            for line in result.stdout.split('\n'):
                if line.startswith('E: ID_VENDOR_ID='):
                    current_vid = line.split('=', 1)[1].lower()
                elif line.startswith('E: ID_MODEL_ID='):
                    current_pid = line.split('=', 1)[1].lower()
                elif line.startswith('P: ') and current_vid and current_pid:
                    devices.add((current_vid, current_pid))
                    current_vid = current_pid = None
                    
            self.connected_devices = devices
            return devices
        except subprocess.CalledProcessError:
            return set()
    
    def parse_rules(self) -> List[RuleEntry]:
        """Parse all rule files and extract device rules."""
        self.entries = []
        
        if not self.rules_dir.exists():
            return self.entries
        
        for rule_file in sorted(self.rules_dir.glob("*.rules")):
            try:
                with open(rule_file, 'r', encoding='utf-8', errors='replace') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        # Extract vendor ID
                        vendor_match = re.search(
                            r'(?:ATTRS?\{)?idVendor[}=]+="?([0-9a-fA-F]+)"?', line
                        )
                        if not vendor_match:
                            continue
                        
                        vid = vendor_match.group(1).lower()
                        
                        # Extract product ID (may not exist for vendor-only rules)
                        product_match = re.search(
                            r'(?:ATTRS?\{)?idProduct[}=]+="?([0-9a-fA-F]+)"?', line
                        )
                        pid = product_match.group(1).lower() if product_match else None
                        
                        # Extract MODE
                        mode_match = re.search(r'MODE:?="?([0-9]+)"?', line)
                        mode = mode_match.group(1) if mode_match else None
                        
                        # Extract GROUP
                        group_match = re.search(r'GROUP="?([a-zA-Z0-9_-]+)"?', line)
                        group = group_match.group(1) if group_match else None
                        
                        self.entries.append(RuleEntry(
                            filepath=rule_file,
                            line_number=line_num,
                            vendor_id=vid,
                            product_id=pid,
                            mode=mode,
                            group=group,
                            raw_line=line
                        ))
            except (IOError, OSError):
                continue
        
        return self.entries
    
    def find_duplicates(self) -> Dict[str, List[RuleEntry]]:
        """Find duplicate VID:PID rules across files."""
        by_device: Dict[str, List[RuleEntry]] = {}
        
        for entry in self.entries:
            if entry.product_id:
                key = f"{entry.vendor_id}:{entry.product_id}"
                if key not in by_device:
                    by_device[key] = []
                by_device[key].append(entry)
        
        # Return only those with duplicates (more than one file)
        duplicates = {}
        for key, entries in by_device.items():
            unique_files = set(str(e.filepath) for e in entries)
            if len(unique_files) > 1:
                duplicates[key] = entries
        
        return duplicates
    
    def find_conflicts(self) -> Dict[str, List[RuleEntry]]:
        """Find VID:PID rules with conflicting MODE or GROUP."""
        by_device: Dict[str, List[RuleEntry]] = {}
        
        for entry in self.entries:
            if entry.product_id and (entry.mode or entry.group):
                key = f"{entry.vendor_id}:{entry.product_id}"
                if key not in by_device:
                    by_device[key] = []
                by_device[key].append(entry)
        
        conflicts = {}
        for key, entries in by_device.items():
            modes = set(e.mode for e in entries if e.mode)
            groups = set(e.group for e in entries if e.group)
            if len(modes) > 1 or len(groups) > 1:
                conflicts[key] = entries
        
        return conflicts
    
    def find_stale(self) -> List[RuleEntry]:
        """Find rules for devices not currently connected."""
        if not self.connected_devices:
            self.scan_connected_devices()
        
        stale = []
        for entry in self.entries:
            if entry.product_id:
                device_key = (entry.vendor_id, entry.product_id)
                if device_key not in self.connected_devices:
                    stale.append(entry)
        
        return stale
    
    def find_overlaps(self) -> Dict[str, tuple]:
        """Find vendor-only rules that overlap with specific product rules."""
        vendor_only = {}  # vid -> RuleEntry
        product_specific: Dict[str, List[RuleEntry]] = {}  # vid -> [entries with pid]
        
        for entry in self.entries:
            if entry.product_id is None:
                vendor_only[entry.vendor_id] = entry
            else:
                if entry.vendor_id not in product_specific:
                    product_specific[entry.vendor_id] = []
                product_specific[entry.vendor_id].append(entry)
        
        overlaps = {}
        for vid, vendor_entry in vendor_only.items():
            if vid in product_specific:
                overlaps[vid] = (vendor_entry, product_specific[vid])
        
        return overlaps
    
    def audit(self, show_stale: bool = True, filter_query: str = None) -> None:
        """Run full audit and print report."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}═══════════════════════════════════════{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}        Rules Audit Report             {Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}═══════════════════════════════════════{Colors.RESET}\n")
        
        if filter_query:
            print(f"{Colors.CYAN}Filter: {Colors.BOLD}{filter_query}{Colors.RESET}\n")
        
        self.parse_rules()
        if show_stale:
            self.scan_connected_devices()
        
        # Filter entries if query provided
        if filter_query:
            query = filter_query.lower()
            filtered_entries = []
            for entry in self.entries:
                device_id = f"{entry.vendor_id}:{entry.product_id}" if entry.product_id else entry.vendor_id
                # Match by VID:PID or search in raw rule line
                if query in device_id or query in entry.raw_line.lower():
                    filtered_entries.append(entry)
            self.entries = filtered_entries
            
            if not self.entries:
                print(f"{Colors.YELLOW}No rules found matching '{filter_query}'{Colors.RESET}")
                return
        
        issues_found = False
        
        # Duplicates
        duplicates = self.find_duplicates()
        if duplicates:
            issues_found = True
            for device_id, entries in duplicates.items():
                print(f"{Colors.YELLOW}⚠ DUPLICATE:{Colors.RESET} {Colors.BOLD}{device_id}{Colors.RESET}")
                for entry in entries:
                    print(f"  → {Colors.DIM}{entry.filepath}:{entry.line_number}{Colors.RESET}")
                print()
        
        # Conflicts
        conflicts = self.find_conflicts()
        if conflicts:
            issues_found = True
            for device_id, entries in conflicts.items():
                print(f"{Colors.RED}✗ CONFLICT:{Colors.RESET} {Colors.BOLD}{device_id}{Colors.RESET}")
                for entry in entries:
                    mode_str = f'MODE="{entry.mode}"' if entry.mode else ""
                    group_str = f'GROUP="{entry.group}"' if entry.group else ""
                    print(f"  → {Colors.DIM}{entry.filepath.name}:{Colors.RESET} {mode_str} {group_str}")
                print()
        
        # Stale rules
        if show_stale:
            stale = self.find_stale()
            # Deduplicate by device ID for cleaner output
            stale_devices = {}
            for entry in stale:
                key = f"{entry.vendor_id}:{entry.product_id}"
                if key not in stale_devices:
                    stale_devices[key] = entry
            
            if stale_devices:
                issues_found = True
                print(f"{Colors.DIM}ℹ STALE (disconnected devices):{Colors.RESET}")
                for device_id, entry in list(stale_devices.items())[:10]:  # Limit to 10
                    print(f"  → {device_id} in {entry.filepath.name}")
                if len(stale_devices) > 10:
                    print(f"  ... and {len(stale_devices) - 10} more")
                print()
        
        # Overlaps
        overlaps = self.find_overlaps()
        if overlaps:
            issues_found = True
            for vid, (vendor_entry, product_entries) in overlaps.items():
                print(f"{Colors.BLUE}ℹ OVERLAP:{Colors.RESET} Vendor rule {Colors.BOLD}{vid}{Colors.RESET} covers {len(product_entries)} specific product rules")
                print(f"  → Vendor rule: {vendor_entry.filepath.name}:{vendor_entry.line_number}")
                print()
        
        # If filtered and no issues, show matching rules
        if filter_query and not issues_found:
            print(f"{Colors.GREEN}✓ No issues found for '{filter_query}'{Colors.RESET}")
            print(f"\n{Colors.BOLD}Matching rules:{Colors.RESET}")
            for entry in self.entries[:20]:
                device_id = f"{entry.vendor_id}:{entry.product_id}" if entry.product_id else entry.vendor_id
                print(f"  → {device_id} in {entry.filepath.name}:{entry.line_number}")
            if len(self.entries) > 20:
                print(f"  ... and {len(self.entries) - 20} more")
        elif not issues_found:
            print(f"{Colors.GREEN}✓ No issues found!{Colors.RESET}")
        
        # Summary
        print(f"\n{Colors.DIM}Scanned {len(list(self.rules_dir.glob('*.rules')))} rule files, {len(self.entries)} rules {'matched' if filter_query else 'total'}.{Colors.RESET}")


class InteractiveUI:
    def __init__(self, generator: UdevRuleGenerator):
        self.generator = generator
        
    def display_devices(self, devices: List[UdevDevice], existing_rules: Dict[str, List[str]] = None) -> None:
        print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════╗{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║     Detected USB Devices             ║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════╝{Colors.RESET}\n")
        
        for i, device in enumerate(devices, 1):
            num_color = Colors.GREEN if i <= 9 else Colors.YELLOW
            status = ""
            
            if existing_rules and device.vendor_id and device.product_id:
                vid = device.vendor_id.lower()
                pid = device.product_id.lower()
                if vid in existing_rules and pid in existing_rules[vid]:
                    status = f" {Colors.GREEN}[✓ configured]{Colors.RESET}"
                else:
                    status = f" {Colors.YELLOW}[needs rule]{Colors.RESET}"
            
            print(f"  {num_color}{i:2}.{Colors.RESET} {device}{status}")
    
    def get_user_selection(self, devices: List[UdevDevice]) -> List[UdevDevice]:
        print(f"\n{Colors.BOLD}Select devices to configure:{Colors.RESET}")
        print(f"{Colors.DIM}Enter numbers (e.g., 1,3,5) or 'all' for all devices{Colors.RESET}")
        
        selection = input(f"\n{Colors.GREEN}➜{Colors.RESET} ").strip()
        
        if selection.lower() == 'all':
            return devices
        
        selected = []
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            for idx in indices:
                if 0 <= idx < len(devices):
                    selected.append(devices[idx])
                else:
                    print(f"{Colors.YELLOW}⚠ Device {idx + 1} out of range{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}✗ Invalid selection format{Colors.RESET}")
            return []
        
        return selected
    
    def confirm_rules(self, devices: List[UdevDevice]) -> bool:
        print(f"\n{Colors.BOLD}{Colors.BLUE}═══ Rules to be created ═══{Colors.RESET}\n")
        for device in devices:
            print(f"{Colors.GREEN}▸{Colors.RESET} {device}")
            rule = self.generator.generate_rule(device)
            for line in rule.split('\n'):
                print(f"  {Colors.DIM}{line}{Colors.RESET}")
        
        print(f"\n{Colors.BOLD}Proceed with creating these rules?{Colors.RESET} {Colors.DIM}(y/n){Colors.RESET}")
        response = input(f"{Colors.GREEN}➜{Colors.RESET} ").strip().lower()
        return response == 'y'
    
    def run(self, dry_run: bool = False) -> None:
        print(f"\n{Colors.CYAN}🔍 Scanning for USB devices...{Colors.RESET}")
        devices = self.generator.get_usb_devices()
        
        if not devices:
            print(f"{Colors.YELLOW}No USB devices found that need rules.{Colors.RESET}")
            return
        
        existing = self.generator.get_existing_rules()
        
        new_devices = []
        for device in devices:
            vid = device.vendor_id.lower() if device.vendor_id else None
            pid = device.product_id.lower() if device.product_id else None
            if vid not in existing or pid not in existing.get(vid, []):
                new_devices.append(device)
        
        if not new_devices:
            print(f"{Colors.GREEN}✓ All detected devices already have rules configured.{Colors.RESET}")
            print(f"\n{Colors.DIM}Showing all devices anyway:{Colors.RESET}")
            self.display_devices(devices, existing)
            selected = self.get_user_selection(devices)
        else:
            print(f"{Colors.YELLOW}⚠ Found {Colors.BOLD}{len(new_devices)}{Colors.RESET}{Colors.YELLOW} device(s) without rules:{Colors.RESET}")
            self.display_devices(devices, existing)
            selected = self.get_user_selection(devices)
        
        if not selected:
            print(f"{Colors.YELLOW}No devices selected.{Colors.RESET}")
            return
        
        if self.confirm_rules(selected):
            if dry_run:
                print(f"\n{Colors.YELLOW}{'='*30}{Colors.RESET}")
                print(f"{Colors.YELLOW}{Colors.BOLD}    DRY RUN MODE{Colors.RESET}")
                print(f"{Colors.YELLOW}{'='*30}{Colors.RESET}")
            
            saved = self.generator.save_rules(selected, dry_run=dry_run)
            
            if not dry_run and saved:
                print(f"\n{Colors.GREEN}{'='*40}{Colors.RESET}")
                print(f"{Colors.GREEN}{Colors.BOLD}  ✓ Rules created successfully!{Colors.RESET}")
                print(f"{Colors.GREEN}{'='*40}{Colors.RESET}")
                print(f"\n{Colors.CYAN}⚙ Applying rules...{Colors.RESET}")
                try:
                    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                    subprocess.run(['udevadm', 'trigger'], check=True)
                    print(f"{Colors.GREEN}{Colors.BOLD}✓ Rules applied!{Colors.RESET} Your devices should now work.")
                except subprocess.CalledProcessError:
                    print(f"\n{Colors.YELLOW}Couldn't auto-reload rules. Please run:{Colors.RESET}")
                    print(f"  {Colors.DIM}sudo udevadm control --reload-rules{Colors.RESET}")
                    print(f"  {Colors.DIM}sudo udevadm trigger{Colors.RESET}")
                    print(f"\n{Colors.DIM}Or disconnect and reconnect the devices.{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}Operation cancelled.{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate udev rules for USB devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Interactive mode
  %(prog)s --list                       # List all USB devices
  %(prog)s --dry-run                    # Show what would be created
  %(prog)s --auto                       # Create rules for all new devices
  %(prog)s --devices 03eb:ff01 --update-ids 2402  # Include firmware update mode
  %(prog)s --vendor-only 31e3           # Rules for all devices from vendor
        """
    )
    
    parser.add_argument('--list', action='store_true', 
                       help='List all USB devices and exit')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what rules would be created without writing files')
    parser.add_argument('--auto', action='store_true',
                       help='Automatically create rules for all devices without existing rules')
    parser.add_argument('--devices', type=str, nargs='+', metavar='VID:PID',
                       help='Create rules for specific devices by vendor:product ID (e.g., 046d:c085)')
    parser.add_argument('--update-ids', type=str, nargs='+', metavar='PID',
                       help='Additional product IDs for firmware update modes (e.g., 2402 2403). Used with --devices.')
    parser.add_argument('--vendor-only', type=str, nargs='+', metavar='VID',
                       help='Create rules matching ALL products from vendor IDs (e.g., 31e3). Useful for device families.')
    parser.add_argument('--remove', type=str, nargs='+', metavar='VID:PID',
                       help='Remove rules for specific devices by vendor:product ID')
    parser.add_argument('--subsystem', type=str,
                       help='Filter devices by subsystem (e.g., usb, hidraw, input)')
    
    # Device type and access options
    parser.add_argument('--type', type=str, choices=list(TYPE_TO_GROUP.keys()),
                       default='generic', metavar='TYPE',
                       help='Device type: keyboard, mouse, controller, serial, storage, audio, network, generic')
    parser.add_argument('--raw-usb', action='store_true',
                       help='Enable raw USB/libusb access (MODE=0666)')
    parser.add_argument('--serial', action='store_true',
                       help='Enable serial port access (GROUP=dialout)')
    parser.add_argument('--network', action='store_true',
                       help='Enable network adapter access (GROUP=netdev)')
    parser.add_argument('--no-webhid', action='store_true',
                       help='Disable WebHID browser tags (TAG+=uaccess)')
    parser.add_argument('--no-snap', action='store_true',
                       help='Disable snap Chromium support')
    parser.add_argument('--no-flatpak', action='store_true',
                       help='Disable flatpak browser support')
    
    # Audit options
    parser.add_argument('--audit', action='store_true',
                       help='Scan /etc/udev/rules.d/ for duplicates, conflicts, and issues')
    parser.add_argument('--no-stale', action='store_true',
                       help='Skip stale rule detection during audit (faster)')
    parser.add_argument('--filter', type=str, metavar='QUERY',
                       help='Filter audit results by device name or VID:PID (e.g., "xbox" or "045e:028e")')
    parser.add_argument('--show', type=str, metavar='VID:PID',
                       help='Show all rules for a specific device by VID:PID (e.g., 045e:028e for Xbox controller)')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0 and not args.list and not args.dry_run and not args.audit and not args.show:
        print("Error: This script must be run with sudo to create udev rules.")
        print("You can use --dry-run to see what would be created without sudo.")
        sys.exit(1)
    
    # Build device profile from CLI args
    profile = DeviceProfile(
        device_type=args.type,
        webhid_access=not args.no_webhid,
        raw_usb_access=args.raw_usb,
        serial_access=args.serial,
        network_access=args.network,
        snap_chromium=not args.no_snap,
        flatpak_browsers=not args.no_flatpak
    )
    
    generator = UdevRuleGenerator()
    
    if args.remove:
        # Remove rules for specific devices
        print(f"Removing rules for {len(args.remove)} device(s)...")
        removed = generator.remove_rules(args.remove, dry_run=args.dry_run)
        if removed and not args.dry_run:
            try:
                subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                subprocess.run(['udevadm', 'trigger'], check=True)
                print(f"{Colors.GREEN}{Colors.BOLD}✓ Rules reloaded!{Colors.RESET}")
            except subprocess.CalledProcessError:
                print("\nRun 'sudo udevadm control --reload-rules && sudo udevadm trigger' to apply.")
        elif not removed:
            print(f"{Colors.YELLOW}No matching rules found to remove.{Colors.RESET}")
    elif args.audit:
        # Run rules audit
        auditor = RulesAuditor()
        auditor.audit(show_stale=not args.no_stale, filter_query=args.filter)
    elif args.show:
        # Show rules for a specific device
        auditor = RulesAuditor()
        auditor.parse_rules()
        query = args.show.lower()
        matching = [e for e in auditor.entries 
                   if query in (f"{e.vendor_id}:{e.product_id}" if e.product_id else e.vendor_id)]
        
        if matching:
            print(f"\n{Colors.BOLD}{Colors.CYAN}Rules for {args.show}:{Colors.RESET}\n")
            for entry in matching:
                print(f"  {Colors.GREEN}►{Colors.RESET} {Colors.BOLD}{entry.filepath.name}{Colors.RESET}:{entry.line_number}")
                mode_str = f'MODE="{entry.mode}"' if entry.mode else ""
                group_str = f'GROUP="{entry.group}"' if entry.group else ""
                print(f"    {mode_str} {group_str}")
                print(f"    {Colors.DIM}{entry.raw_line[:100]}{'...' if len(entry.raw_line) > 100 else ''}{Colors.RESET}")
                print()
        else:
            print(f"{Colors.YELLOW}No rules found for {args.show}{Colors.RESET}")
            print(f"{Colors.DIM}Use 'udev-autoconfig --list' to see connected devices{Colors.RESET}")
    elif args.list:
        devices = generator.get_usb_devices() if not args.subsystem else generator.scan_devices(args.subsystem)
        if devices:
            print("\n=== USB Devices ===\n")
            for device in devices:
                print(f"  {device}")
                print(f"    Vendor ID:  {device.vendor_id}")
                print(f"    Product ID: {device.product_id}")
                print(f"    Subsystem:  {device.subsystem}")
                if device.driver:
                    print(f"    Driver:     {device.driver}")
                print()
        else:
            print("No USB devices found.")
    elif args.vendor_only:
        # Create vendor-only rules (match all products from a vendor)
        print(f"Creating vendor-only rules for {len(args.vendor_only)} vendor(s)...")
        for vid in args.vendor_only:
            vid = vid.lower()
            print(f"\n{Colors.CYAN}Vendor: {vid}{Colors.RESET}")
            rule = generator.generate_vendor_rule(vid)
            
            if args.dry_run:
                print(f"{Colors.YELLOW}--- Would create rules for vendor {vid} ---{Colors.RESET}")
                print(rule)
            else:
                vendor_name = f"vendor-{vid}"
                filename = f"50-{vendor_name}.rules"
                filepath = generator.rules_dir / filename
                
                content = f"# udev rules for vendor {vid} (all devices)\n"
                content += f"# Generated by udev-autoconfig\n\n"
                content += rule + '\n'
                
                with open(filepath, 'w') as f:
                    f.write(content)
                print(f"{Colors.GREEN}✓{Colors.RESET} Created: {Colors.BOLD}{filepath}{Colors.RESET}")
        
        if not args.dry_run:
            try:
                subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                subprocess.run(['udevadm', 'trigger'], check=True)
                print(f"{Colors.GREEN}{Colors.BOLD}✓ Rules applied!{Colors.RESET}")
            except subprocess.CalledProcessError:
                print("\nRun 'sudo udevadm control --reload-rules && sudo udevadm trigger' to apply.")
    elif args.devices:
        # Create rules for specific devices by vendor:product ID
        devices = generator.get_usb_devices()
        requested_ids = set()
        for dev_id in args.devices:
            if ':' in dev_id:
                vid, pid = dev_id.lower().split(':', 1)
                requested_ids.add((vid, pid))
            else:
                print(f"{Colors.YELLOW}⚠ Invalid device ID format '{dev_id}', expected VID:PID{Colors.RESET}")
        
        selected_devices = [d for d in devices if d.vendor_id and d.product_id and
                          (d.vendor_id.lower(), d.product_id.lower()) in requested_ids]
        
        # Get extra product IDs for update modes
        extra_pids = args.update_ids if args.update_ids else None
        if extra_pids:
            print(f"{Colors.CYAN}Including update mode product IDs: {', '.join(extra_pids)}{Colors.RESET}")
        
        if selected_devices:
            print(f"Creating rules for {len(selected_devices)} device(s)...")
            saved = generator.save_rules(selected_devices, dry_run=args.dry_run, extra_product_ids=extra_pids)
            if not args.dry_run and saved:
                try:
                    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                    subprocess.run(['udevadm', 'trigger'], check=True)
                    print(f"{Colors.GREEN}{Colors.BOLD}✓ Rules applied!{Colors.RESET}")
                except subprocess.CalledProcessError:
                    print("\nRun 'sudo udevadm control --reload-rules && sudo udevadm trigger' to apply.")
        else:
            print(f"{Colors.YELLOW}No matching devices found for the specified IDs.{Colors.RESET}")
    elif args.auto:
        devices = generator.get_usb_devices()
        existing = generator.get_existing_rules()
        new_devices = [d for d in devices if 
                       (d.vendor_id.lower() if d.vendor_id else None) not in existing or 
                       (d.product_id.lower() if d.product_id else None) not in existing.get(d.vendor_id.lower() if d.vendor_id else '', [])]
        
        if new_devices:
            print(f"Creating rules for {len(new_devices)} device(s)...")
            saved = generator.save_rules(new_devices, dry_run=args.dry_run)
            if not args.dry_run and saved:
                try:
                    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                    subprocess.run(['udevadm', 'trigger'], check=True)
                    print(f"{Colors.GREEN}{Colors.BOLD}✓ Rules applied!{Colors.RESET}")
                except subprocess.CalledProcessError:
                    print("\nRun 'sudo udevadm control --reload-rules && sudo udevadm trigger' to apply.")
        else:
            print("No new devices found that need rules.")
    else:
        ui = InteractiveUI(generator)
        ui.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()