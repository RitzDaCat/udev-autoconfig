#!/usr/bin/env python3

import os
import sys
import subprocess
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re

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
                with open(rule_file, 'r') as f:
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
            except:
                pass
        
        # Convert sets back to lists
        for vid in existing:
            existing[vid] = list(existing[vid])
        
        return existing
    
    def generate_rule(self, device: UdevDevice, include_snap: bool = True) -> str:
        rules = []
        
        # Use MODE:= for assignment and include GROUP and TAG
        mode = "0660"
        group = "input"
        
        comment = f" # {device.vendor_name} {device.product_name}" if device.product_name else ""
        
        # Main hidraw rule (most important for WebHID)
        rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}", TAG+="uaccess"'
        rules.append(rule + comment)
        
        # USB subsystem rule
        rule = f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", MODE:="{mode}", GROUP="{group}", TAG+="uaccess"'
        rules.append(rule + comment)
        
        # Add snap Chromium support if requested (for Ubuntu/snap users)
        if include_snap:
            rules.append("")
            rules.append(f"# Support for snap Chromium (Ubuntu){comment}")
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="snap_chromium_chromedriver"'
            rules.append(rule)
            rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="snap_chromium_chromium"'
            rules.append(rule)
        
        # Add flatpak Chrome/Chromium support
        rules.append("")
        rules.append(f"# Support for Flatpak browsers{comment}")
        rule = f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{device.vendor_id}", ATTRS{{idProduct}}=="{device.product_id}", TAG+="uaccess", TAG+="seat"'
        rules.append(rule)
        
        return '\n'.join(rules)
    
    def save_rules(self, devices: List[UdevDevice], dry_run: bool = False) -> Dict[str, List[str]]:
        rules_by_vendor = {}
        
        for device in devices:
            vendor_name = (device.vendor_name or device.vendor_id).lower()
            vendor_name = re.sub(r'[^a-z0-9]+', '-', vendor_name)
            
            if vendor_name not in rules_by_vendor:
                rules_by_vendor[vendor_name] = []
            
            rule = self.generate_rule(device)
            rules_by_vendor[vendor_name].append(rule)
        
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
            if device.vendor_id not in existing or device.product_id not in existing.get(device.vendor_id, []):
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
  %(prog)s                    # Interactive mode
  %(prog)s --list             # List all USB devices
  %(prog)s --dry-run          # Show what would be created
  %(prog)s --auto             # Create rules for all new devices
        """
    )
    
    parser.add_argument('--list', action='store_true', 
                       help='List all USB devices and exit')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what rules would be created without writing files')
    parser.add_argument('--auto', action='store_true',
                       help='Automatically create rules for all devices without existing rules')
    parser.add_argument('--subsystem', type=str,
                       help='Filter devices by subsystem (e.g., usb, hidraw, input)')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0 and not args.list and not args.dry_run:
        print("Error: This script must be run with sudo to create udev rules.")
        print("You can use --dry-run to see what would be created without sudo.")
        sys.exit(1)
    
    generator = UdevRuleGenerator()
    
    if args.list:
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
    elif args.auto:
        devices = generator.get_usb_devices()
        existing = generator.get_existing_rules()
        new_devices = [d for d in devices if d.vendor_id not in existing or 
                       d.product_id not in existing.get(d.vendor_id, [])]
        
        if new_devices:
            print(f"Creating rules for {len(new_devices)} device(s)...")
            generator.save_rules(new_devices, dry_run=args.dry_run)
            if not args.dry_run:
                print("\nRun 'sudo udevadm control --reload-rules && sudo udevadm trigger' to apply.")
        else:
            print("No new devices found that need rules.")
    else:
        ui = InteractiveUI(generator)
        ui.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()